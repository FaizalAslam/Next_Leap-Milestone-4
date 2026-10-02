"""Persistent ChromaDB operations with staged index activation."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.chunk import Chunk


ROOT = Path(__file__).resolve().parents[1]
CHROMA_DIR = ROOT / "chroma_db"
PROCESSED_DIR = ROOT / "data" / "processed"
INDEX_MANIFEST = PROCESSED_DIR / "index_manifest.json"
CHUNK_INSPECTION = ROOT / "Docs" / "chunks_inspection.txt"
REQUIRED_METADATA = {
    "source_id", "amc", "scheme", "category", "source", "source_url", "section",
    "document_id", "chunk_id", "retrieved_at",
}


class VectorStoreError(RuntimeError):
    """Raised when a persistent collection fails integrity checks."""


def _client():
    import chromadb

    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _inspection_text(chunks: list[Chunk], run_id: str, model_name: str) -> str:
    lines = [
        "# Chunks Inspection",
        "",
        f"Run: {run_id}",
        f"Embedding model: {model_name}",
        f"Chunk count: {len(chunks)}",
        "",
    ]
    for chunk in chunks:
        lines.extend(
            [
                f"## {chunk.metadata['source_id']} / {chunk.id}",
                "",
                "Metadata:",
                "```json",
                json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True, indent=2),
                "```",
                "",
                "Text:",
                "```text",
                chunk.text,
                "```",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


def _validate_chunk_inputs(chunks: list[Chunk], embeddings: Any) -> list[list[float]]:
    import numpy as np

    vectors = np.asarray(embeddings, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape != (len(chunks), 384):
        raise VectorStoreError(f"Expected {len(chunks)} vectors of dimension 384, got {vectors.shape}")
    if not np.isfinite(vectors).all():
        raise VectorStoreError("Embedding batch contains non-finite values")
    if not chunks:
        raise VectorStoreError("Cannot activate an empty vector collection")
    ids = [chunk.id for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise VectorStoreError("Chunk IDs must be unique")
    for chunk in chunks:
        missing = REQUIRED_METADATA.difference(chunk.metadata)
        if missing:
            raise VectorStoreError(f"Chunk {chunk.id} lacks metadata: {sorted(missing)}")
        if chunk.metadata["chunk_id"] != chunk.id or not chunk.text.strip():
            raise VectorStoreError(f"Chunk {chunk.id} has inconsistent identity or empty text")
    return vectors.tolist()


def activate_index(
    chunks: list[Chunk],
    embeddings: Any,
    *,
    run_id: str,
    embedding_model: str,
    expected_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    vectors = _validate_chunk_inputs(chunks, embeddings)
    source_ids = sorted({chunk.metadata["source_id"] for chunk in chunks})
    if expected_source_ids is not None and set(source_ids) != expected_source_ids:
        missing = sorted(expected_source_ids - set(source_ids))
        extra = sorted(set(source_ids) - expected_source_ids)
        raise VectorStoreError(f"Source coverage mismatch; missing={missing}, extra={extra}")

    safe_run_id = re.sub(r"[^a-zA-Z0-9_-]", "", run_id).lower()
    collection_name = f"sbi_faq_{safe_run_id}_{uuid.uuid4().hex[:8]}"
    client = _client()
    collection = None
    old_inspection = CHUNK_INSPECTION.read_bytes() if CHUNK_INSPECTION.exists() else None
    old_manifest = INDEX_MANIFEST.read_bytes() if INDEX_MANIFEST.exists() else None
    inspection_swapped = False

    try:
        collection = client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "embedding_model": embedding_model, "run_id": run_id},
        )
        batch_size = 128
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            batch = chunks[start:end]
            collection.add(
                ids=[chunk.id for chunk in batch],
                embeddings=vectors[start:end],
                documents=[chunk.text for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )

        if collection.count() != len(chunks):
            raise VectorStoreError(f"Collection count mismatch: expected {len(chunks)}, got {collection.count()}")
        stored = collection.get(include=["embeddings", "metadatas"])
        stored_embeddings = stored.get("embeddings")
        stored_metadata = stored.get("metadatas") or []
        if len(stored_embeddings) != len(chunks) or any(len(vector) != 384 for vector in stored_embeddings):
            raise VectorStoreError("Persisted collection contains missing or incorrectly sized vectors")
        if len(stored_metadata) != len(chunks) or any(
            REQUIRED_METADATA.difference(metadata or {}) for metadata in stored_metadata
        ):
            raise VectorStoreError("Persisted collection contains incomplete chunk metadata")

        manifest = {
            "collection_name": collection_name,
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "embedding_model": embedding_model,
            "dimensions": 384,
            "distance_metric": "cosine",
            "chunk_count": len(chunks),
            "source_count": len(source_ids),
            "source_ids": source_ids,
        }
        _atomic_write(CHUNK_INSPECTION, _inspection_text(chunks, run_id, embedding_model))
        inspection_swapped = True
        _atomic_write(INDEX_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        return manifest
    except Exception:
        if inspection_swapped:
            if old_inspection is None:
                CHUNK_INSPECTION.unlink(missing_ok=True)
            else:
                _atomic_write(CHUNK_INSPECTION, old_inspection.decode("utf-8"))
        if old_manifest is None:
            INDEX_MANIFEST.unlink(missing_ok=True)
        else:
            _atomic_write(INDEX_MANIFEST, old_manifest.decode("utf-8"))
        if collection is not None:
            try:
                client.delete_collection(collection_name)
            except Exception:
                pass
        raise


def load_active_index() -> tuple[Any, dict[str, Any]]:
    if not INDEX_MANIFEST.is_file():
        raise FileNotFoundError(f"No active vector index at {INDEX_MANIFEST}")
    try:
        manifest = json.loads(INDEX_MANIFEST.read_text(encoding="utf-8"))
        collection = _client().get_collection(name=manifest["collection_name"])
    except Exception as exc:
        raise VectorStoreError(f"Could not open the active ChromaDB collection: {exc}") from exc
    if collection.count() != manifest.get("chunk_count"):
        raise VectorStoreError("Active ChromaDB collection count does not match its manifest")
    return collection, manifest

