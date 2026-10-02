"""Scheme-aware retrieval over the active persistent ChromaDB collection."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.embed import LocalEmbedder


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_TOP_K = 5
DEFAULT_MAX_COSINE_DISTANCE = 0.45
SCHEME_MATCH_BOOST = 0.08
RECENCY_TIE_DISTANCE = 0.05


class RetrievalError(RuntimeError):
    """Raised when embedding or querying the active index fails."""


class QuestionTooLong(ValueError):
    """Raised when a question exceeds the local embedding model's input limit."""


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    metadata: dict[str, str]
    distance: float


@dataclass(frozen=True)
class SchemeRecord:
    scheme: str
    category: str
    source_id: str


class SchemeMetadata:
    """A startup snapshot of allow-listed scheme/category index metadata."""

    def __init__(self, records: dict[str, SchemeRecord]) -> None:
        self.records = records

    @classmethod
    def from_collection(cls, collection: Any) -> "SchemeMetadata":
        records: dict[str, SchemeRecord] = {}
        stored = collection.get(include=["metadatas"])
        for metadata in stored.get("metadatas") or []:
            scheme = (metadata or {}).get("scheme", "")
            if not scheme:
                continue
            record = SchemeRecord(
                scheme=scheme,
                category=(metadata or {}).get("category", ""),
                source_id=(metadata or {}).get("source_id", ""),
            )
            existing = records.get(scheme)
            if existing and existing.category != record.category:
                raise RetrievalError("Active index has inconsistent scheme metadata")
            records[scheme] = record
        if not records:
            raise RetrievalError("Active index has no scheme metadata")
        return cls(records)

    @property
    def names(self) -> list[str]:
        return sorted(self.records)


class Retriever:
    def __init__(
        self,
        collection: Any,
        embedder: Any,
        *,
        top_k: int | None = None,
        max_cosine_distance: float | None = None,
    ) -> None:
        self.collection = collection
        self.embedder = embedder
        self.top_k = top_k if top_k is not None else int(os.getenv("TOP_K", DEFAULT_TOP_K))
        self.max_cosine_distance = (
            max_cosine_distance
            if max_cosine_distance is not None
            else float(os.getenv("RETRIEVAL_MAX_DISTANCE", DEFAULT_MAX_COSINE_DISTANCE))
        )
        if self.top_k < 1 or not 0.0 <= self.max_cosine_distance <= 2.0:
            raise ValueError("Invalid retrieval configuration")

    def retrieve(self, question: str, scheme: str | None = None) -> list[RetrievedChunk]:
        try:
            token_count = getattr(self.embedder, "token_count", None)
            max_length = getattr(self.embedder, "max_sequence_length", None)
            retrieval_question = question
            if re.search(r"\b(?:fund\s+)?size\b|\bcorpus\b", question, re.IGNORECASE):
                retrieval_question = f"{question} AUM assets under management"
            if token_count and max_length and token_count(retrieval_question) > max_length:
                raise QuestionTooLong("Question exceeds the embedding model token limit")
            encoded = self.embedder.encode([retrieval_question])[0]
            vector = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
            candidates: list[RetrievedChunk] = []
            if scheme:
                candidates.extend(self._query(vector, {"scheme": scheme}))
                candidates.extend(self._query(vector, {"scheme": ""}))
            else:
                candidates.extend(self._query(vector, {"scheme": ""}))
        except Exception as exc:
            if isinstance(exc, QuestionTooLong):
                raise
            if isinstance(exc, RetrievalError):
                raise
            raise RetrievalError("Embedding or vector retrieval failed") from exc

        candidates = [item for item in candidates if item.distance <= self.max_cosine_distance]
        if not candidates:
            return []

        def adjusted_distance(item: RetrievedChunk) -> float:
            if scheme and item.metadata.get("scheme") == scheme:
                return item.distance - SCHEME_MATCH_BOOST
            return item.distance

        # Keep one supporting source per answer so the response can expose one truthful citation.
        by_source: dict[str, list[RetrievedChunk]] = {}
        for item in candidates:
            source_id = item.metadata.get("source_id", "")
            if not source_id:
                raise RetrievalError("Retrieved chunk is missing source identity")
            by_source.setdefault(source_id, []).append(item)
        source_scores = {
            source_id: min(adjusted_distance(item) for item in items)
            for source_id, items in by_source.items()
        }
        best_score = min(source_scores.values())
        near_best = [
            source_id for source_id, score in source_scores.items()
            if score <= best_score + RECENCY_TIE_DISTANCE
        ]
        try:
            selected_source = max(
                near_best,
                key=lambda source_id: (
                    max(date.fromisoformat(item.metadata["retrieved_at"]) for item in by_source[source_id]),
                    -source_scores[source_id],
                ),
            )
        except (KeyError, ValueError) as exc:
            raise RetrievalError("Retrieved chunks have invalid source dates") from exc
        selected = sorted(by_source[selected_source], key=adjusted_distance)
        return selected[: self.top_k]

    def _query(self, vector: list[float], where: dict[str, str]) -> list[RetrievedChunk]:
        result = self.collection.query(
            query_embeddings=[vector],
            n_results=self.top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        if not (len(documents) == len(metadatas) == len(distances)):
            raise RetrievalError("Vector store returned incomplete retrieval data")
        chunks: list[RetrievedChunk] = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            if not document or not isinstance(metadata, dict):
                continue
            chunks.append(RetrievedChunk(document, metadata, float(distance)))
        return chunks


def load_local_embedder() -> LocalEmbedder:
    """Load only the already-cached Phase 1 model; question handling never downloads it."""
    try:
        return LocalEmbedder(local_files_only=True)
    except Exception as exc:
        raise RetrievalError("The local question embedding model is unavailable") from exc
