"""Local sentence-transformer embeddings shared by ingestion and retrieval."""

from __future__ import annotations

from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EXPECTED_DIMENSION = 384


class EmbeddingError(RuntimeError):
    """Raised when model loading or embedding validation fails."""


class LocalEmbedder:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        *,
        device: str = "cpu",
        local_files_only: bool = False,
    ) -> None:
        self.model_name = model_name
        try:
            self.model = SentenceTransformer(model_name, device=device, local_files_only=local_files_only)
        except Exception as exc:
            raise EmbeddingError(f"Could not load local embedding model {model_name}: {exc}") from exc
        self.tokenizer = self.model.tokenizer
        self.max_sequence_length = int(self.model.max_seq_length)
        dimension_getter = getattr(self.model, "get_embedding_dimension", None)
        if dimension_getter is None:
            dimension_getter = self.model.get_sentence_embedding_dimension
        self.dimension = int(dimension_getter() or 0)
        if self.dimension != EXPECTED_DIMENSION:
            raise EmbeddingError(f"Expected {EXPECTED_DIMENSION}-dimensional vectors, got {self.dimension}")

    def token_count(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=True))

    def encode(self, texts: list[str], *, batch_size: int = 32) -> np.ndarray:
        if not texts:
            raise EmbeddingError("Cannot embed an empty chunk set")
        for index, text in enumerate(texts):
            count = self.token_count(text)
            if count > self.max_sequence_length:
                raise EmbeddingError(
                    f"Chunk {index} has {count} tokens; model limit is {self.max_sequence_length}"
                )
        try:
            vectors = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception as exc:
            raise EmbeddingError(f"Local embedding failed: {exc}") from exc
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape != (len(texts), EXPECTED_DIMENSION):
            raise EmbeddingError(
                f"Embedding shape must be ({len(texts)}, {EXPECTED_DIMENSION}), got {vectors.shape}"
            )
        if not np.isfinite(vectors).all():
            raise EmbeddingError("Embedding output contains non-finite values")
        return vectors
