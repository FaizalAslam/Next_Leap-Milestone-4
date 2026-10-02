import json

import numpy as np
import pytest

from src.chunk import Chunk
from src import vector_store


def _chunk(source_id="source_01", index=1):
    chunk_id = f"chunk-{source_id}-{index}"
    metadata = {
        "source_id": source_id,
        "amc": "SBI Mutual Fund",
        "scheme": "",
        "category": "General",
        "source": "Groww",
        "source_url": "https://example.com/faq",
        "section": "FAQ",
        "document_id": f"doc-{source_id}",
        "chunk_id": chunk_id,
        "retrieved_at": "2026-10-02",
    }
    return Chunk(id=chunk_id, text="Approved factual content", metadata=metadata)


def _redirect_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_store, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(vector_store, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(vector_store, "INDEX_MANIFEST", tmp_path / "processed" / "index_manifest.json")
    monkeypatch.setattr(vector_store, "CHUNK_INSPECTION", tmp_path / "Docs" / "chunks_inspection.txt")


def test_activates_persistent_cosine_collection_and_reopens_it(tmp_path, monkeypatch):
    _redirect_paths(tmp_path, monkeypatch)
    chunks = [_chunk("source_01"), _chunk("source_02")]
    vectors = np.ones((2, 384), dtype=np.float32)

    manifest = vector_store.activate_index(
        chunks,
        vectors,
        run_id="test-run",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        expected_source_ids={"source_01", "source_02"},
    )
    collection, loaded_manifest = vector_store.load_active_index()

    assert manifest == loaded_manifest
    assert collection.count() == 2
    assert collection.metadata["hnsw:space"] == "cosine"
    assert manifest["dimensions"] == 384
    assert manifest["source_count"] == 2
    inspection = vector_store.CHUNK_INSPECTION.read_text(encoding="utf-8")
    assert "chunk-source_01-1" in inspection
    assert "Metadata:" in inspection


def test_failed_staging_preserves_active_index_and_inspection(tmp_path, monkeypatch):
    _redirect_paths(tmp_path, monkeypatch)
    vector_store.activate_index(
        [_chunk()],
        np.ones((1, 384), dtype=np.float32),
        run_id="first",
        embedding_model="local-model",
        expected_source_ids={"source_01"},
    )
    old_manifest = vector_store.INDEX_MANIFEST.read_bytes()
    old_inspection = vector_store.CHUNK_INSPECTION.read_bytes()
    monkeypatch.setattr(vector_store, "_inspection_text", lambda *_args: (_ for _ in ()).throw(RuntimeError("disk failure")))

    with pytest.raises(RuntimeError, match="disk failure"):
        vector_store.activate_index(
            [_chunk("source_02")],
            np.ones((1, 384), dtype=np.float32),
            run_id="second",
            embedding_model="local-model",
            expected_source_ids={"source_02"},
        )

    assert vector_store.INDEX_MANIFEST.read_bytes() == old_manifest
    assert vector_store.CHUNK_INSPECTION.read_bytes() == old_inspection
    client = vector_store._client()
    names = [collection if isinstance(collection, str) else collection.name for collection in client.list_collections()]
    assert names == [json.loads(old_manifest)["collection_name"]]


def test_bad_vector_shape_does_not_modify_existing_active_index(tmp_path, monkeypatch):
    _redirect_paths(tmp_path, monkeypatch)
    vector_store.activate_index(
        [_chunk()],
        np.ones((1, 384), dtype=np.float32),
        run_id="first",
        embedding_model="local-model",
        expected_source_ids={"source_01"},
    )
    old_manifest = vector_store.INDEX_MANIFEST.read_bytes()

    with pytest.raises(vector_store.VectorStoreError, match="dimension 384"):
        vector_store.activate_index(
            [_chunk("source_02")],
            np.ones((1, 12), dtype=np.float32),
            run_id="invalid",
            embedding_model="local-model",
            expected_source_ids={"source_02"},
        )

    assert vector_store.INDEX_MANIFEST.read_bytes() == old_manifest

