from src.retrieve import QuestionTooLong, Retriever


def _metadata(source_id, scheme="", section="Overview"):
    return {
        "source_id": source_id,
        "scheme": scheme,
        "category": "Large Cap" if scheme else "General",
        "source": "Groww",
        "source_type": "scheme_page" if scheme else "education",
        "source_url": f"https://example.test/{source_id}",
        "section": section,
        "document_id": f"doc-{source_id}",
        "chunk_id": f"chunk-{source_id}-{section}",
        "retrieved_at": "2026-10-02",
    }


class FakeEmbedder:
    def encode(self, questions):
        assert len(questions) == 1
        return [[0.1, 0.2, 0.3]]


class FakeCollection:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = []

    def query(self, *, query_embeddings, n_results, where, include):
        self.calls.append({"n_results": n_results, "where": where, "include": include})
        selected = [item for item in self.candidates if item["metadata"].get("scheme", "") == where["scheme"]]
        selected = selected[:n_results]
        return {
            "documents": [[item["text"] for item in selected]],
            "metadatas": [[item["metadata"] for item in selected]],
            "distances": [[item["distance"] for item in selected]],
        }


def _candidate(source_id, distance, scheme="", section="Overview"):
    return {
        "text": f"Evidence from {source_id} {section}",
        "metadata": _metadata(source_id, scheme, section),
        "distance": distance,
    }


def test_named_scheme_queries_exact_and_general_then_prefers_exact_without_other_funds():
    scheme = "SBI Small Cap Fund Direct Growth"
    collection = FakeCollection(
        [
            _candidate("small-cap", 0.24, scheme, "Scheme facts"),
            _candidate("small-cap", 0.29, scheme, "Expense ratio"),
            _candidate("other-fund", 0.12, "SBI Large Cap Direct Plan Growth"),
            _candidate("general", 0.23, "", "Minimum SIP definition"),
        ]
    )
    chunks = Retriever(collection, FakeEmbedder(), top_k=2, max_cosine_distance=0.45).retrieve(
        "What is the minimum SIP for SBI Small Cap Fund?", scheme
    )
    assert len(collection.calls) == 2
    assert collection.calls[0]["n_results"] == collection.calls[1]["n_results"] == 2
    assert {call["where"]["scheme"] for call in collection.calls} == {scheme, ""}
    assert len(chunks) == 2
    assert {chunk.metadata["source_id"] for chunk in chunks} == {"small-cap"}


def test_general_question_only_searches_general_chunks_and_respects_distance_cutoff():
    collection = FakeCollection(
        [
            _candidate("general", 0.4),
            _candidate("far-general", 0.8),
            _candidate("scheme", 0.1, "SBI Flexicap Fund Direct Growth"),
        ]
    )
    chunks = Retriever(collection, FakeEmbedder(), top_k=5, max_cosine_distance=0.45).retrieve(
        "How do I download a statement?"
    )
    assert [call["where"] for call in collection.calls] == [{"scheme": ""}]
    assert len(chunks) == 1
    assert chunks[0].metadata["source_id"] == "general"
    assert chunks[0].metadata["retrieved_at"] == "2026-10-02"


def test_no_candidate_within_cutoff_is_unsupported_material():
    collection = FakeCollection([_candidate("unrelated", 0.46)])
    chunks = Retriever(collection, FakeEmbedder(), top_k=5, max_cosine_distance=0.45).retrieve("A factual question")
    assert chunks == []


def test_recency_breaks_close_source_relevance_ties():
    older = _candidate("older", 0.2)
    older["metadata"]["retrieved_at"] = "2026-09-01"
    newer = _candidate("newer", 0.23)
    newer["metadata"]["retrieved_at"] = "2026-10-02"
    collection = FakeCollection([older, newer])
    chunks = Retriever(collection, FakeEmbedder(), top_k=5, max_cosine_distance=0.45).retrieve("A factual question")
    assert {chunk.metadata["source_id"] for chunk in chunks} == {"newer"}


def test_default_top_k_is_five():
    collection = FakeCollection([_candidate("general", 0.2)])
    Retriever(collection, FakeEmbedder()).retrieve("A factual question")
    assert collection.calls[0]["n_results"] == 5


def test_fund_size_question_expands_to_aum_terms_for_retrieval():
    class RecordingEmbedder(FakeEmbedder):
        def __init__(self):
            self.questions = []

        def encode(self, questions):
            self.questions.extend(questions)
            return super().encode(questions)

    scheme = "SBI Large Cap Direct Plan Growth"
    collection = FakeCollection([_candidate("aum", 0.2, scheme, "FAQ AUM")])
    embedder = RecordingEmbedder()
    chunks = Retriever(collection, embedder).retrieve("What is the size of SBI Large Cap Fund?", scheme)

    assert embedder.questions == ["What is the size of SBI Large Cap Fund? AUM assets under management"]
    assert chunks[0].metadata["source_id"] == "aum"


def test_question_over_model_token_limit_is_input_validation_not_retrieval_failure():
    class LongEmbedder:
        max_sequence_length = 256

        def token_count(self, _question):
            return 257

        def encode(self, _questions):
            raise AssertionError("must reject before embedding")

    import pytest

    with pytest.raises(QuestionTooLong):
        Retriever(FakeCollection([]), LongEmbedder()).retrieve("a long question")
