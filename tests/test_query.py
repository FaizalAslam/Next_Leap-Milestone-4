from dataclasses import dataclass

import pytest

from src.query import InputRejected, QueryService
from src.retrieve import QuestionTooLong, SchemeMetadata


SCHEME = "SBI Flexicap Fund Direct Growth"


class MetadataCollection:
    def get(self, *, include):
        assert include == ["metadatas"]
        return {
            "metadatas": [
                {"scheme": SCHEME, "category": "Flexi Cap", "source_id": "source_02"},
                {"scheme": "SBI Small Cap Fund Direct Growth", "category": "Small Cap", "source_id": "source_03"},
            ]
        }


class RetrieverSpy:
    def __init__(self, chunks=None):
        self.chunks = chunks or []
        self.calls = []

    def retrieve(self, question, scheme):
        self.calls.append((question, scheme))
        return self.chunks


@dataclass
class FakeAnswer:
    supported: bool = True
    narrative: str = "The direct plan expense ratio is 0.82%."
    facts: list = None
    evidence_quotes: list = None

    def __post_init__(self):
        if self.facts is None:
            self.facts = [{"label": "Expense ratio (Direct)", "value": "0.82%"}]
        if self.evidence_quotes is None:
            self.evidence_quotes = ["Expense ratio (Direct): 0.82%"]


def _chunk(*, scheme=SCHEME, section="Expense ratio", source_id="source_02", source="Groww", source_url="https://groww.in/fund"):
    from src.retrieve import RetrievedChunk

    return RetrievedChunk(
        text=f"{SCHEME} {section}\nExpense ratio (Direct): 0.82%",
        metadata={
            "source_id": source_id,
            "scheme": scheme,
            "category": "Flexi Cap" if scheme else "General",
            "source": source,
            "source_type": "scheme_page" if scheme else "education",
            "source_url": source_url,
            "section": section,
            "document_id": "doc-02",
            "chunk_id": "chunk-02",
            "retrieved_at": "2026-10-02",
        },
        distance=0.2,
    )


def _service(retriever=None, generator=None):
    return QueryService(
        MetadataCollection(),
        retriever=retriever,
        generator=generator or (lambda _question, _contexts: FakeAnswer()),
    )


@pytest.mark.parametrize(
    "question",
    [
        "PAN ABCDE1234F",
        "Aadhaar 1234 5678 9012",
        "Account number 1234567890123456",
        "OTP 123456",
        "Email test.user@example.com",
        "Phone +91 98765 43210",
    ],
)
def test_direct_service_rejects_pii_before_retrieval_or_generation(question):
    retriever = RetrieverSpy([_chunk()])
    generated = []
    service = _service(retriever, lambda *args: generated.append(args))
    with pytest.raises(InputRejected):
        service.answer(question)
    assert retriever.calls == []
    assert generated == []


@pytest.mark.parametrize(
    ("question", "state", "reason"),
    [
        ("Should I invest in SBI Flexicap Fund?", "refusal", "advice"),
        ("What will SBI Flexicap Fund return next year?", "refusal", "performance"),
        ("What is the personal phone of the fund manager?", "unsupported", "private_information"),
    ],
)
def test_restricted_questions_bypass_retrieval_and_generation(question, state, reason):
    retriever = RetrieverSpy([_chunk()])
    generated = []
    result = _service(retriever, lambda *args: generated.append(args)).answer(question)
    assert result["state"] == state
    assert result["reason"] == reason
    assert retriever.calls == []
    assert generated == []
    if reason == "advice":
        assert result["scheme"] == SCHEME
        assert result["category"] == "Flexi Cap"


def test_benchmark_identity_question_uses_factual_retrieval():
    retriever = RetrieverSpy([_chunk(section="Benchmark")])
    calls = []
    result = _service(retriever, lambda question, contexts: calls.append((question, contexts)) or FakeAnswer()).answer(
        "Which benchmark does SBI Flexicap Fund follow?"
    )
    assert result["state"] == "factual"
    assert retriever.calls[0][1] == SCHEME
    assert len(calls) == 1


def test_historical_return_question_uses_factual_retrieval():
    retriever = RetrieverSpy([_chunk(section="Historical returns")])
    generated = []
    result = _service(
        retriever,
        lambda question, contexts: generated.append((question, contexts)) or FakeAnswer(),
    ).answer("What were the historical returns of SBI Flexicap Fund?")

    assert result["state"] == "factual"
    assert retriever.calls == [("What were the historical returns of SBI Flexicap Fund?", SCHEME)]
    assert len(generated) == 1


def test_factual_response_uses_one_metadata_source_and_index_date():
    context = _chunk()
    result = _service(RetrieverSpy([context])).answer("What is the expense ratio of SBI Flexicap Fund?")
    assert result["state"] == "factual"
    assert result["source"] == {
        "label": "Groww",
        "url": "https://groww.in/fund",
        "source_type": "scheme_page",
        "retrieved_at": "2026-10-02",
    }
    assert result["facts"] == [{"label": "Expense ratio (Direct)", "value": "0.82%"}]


def test_named_scheme_with_general_source_uses_scheme_category_metadata():
    context = _chunk(scheme="", source_id="source_22", source_url="https://groww.in/blog")
    result = _service(RetrieverSpy([context])).answer(
        "How do I download the capital gains statement for SBI Flexicap Fund?"
    )
    assert result["state"] == "factual"
    assert result["scheme"] == SCHEME
    assert result["category"] == "Flexi Cap"
    assert result["source"]["url"] == "https://groww.in/blog"


@pytest.mark.parametrize(
    "answer",
    [
        FakeAnswer(narrative="One. Two. Three. Four."),
        FakeAnswer(narrative="The ratio is 0.91%."),
        FakeAnswer(evidence_quotes=["quote not in source"]),
        FakeAnswer(narrative="You should invest in this fund."),
        FakeAnswer(narrative="This is the highest-return SBI scheme."),
        FakeAnswer(narrative="The fund manager is John Smith.", facts=[]),
        FakeAnswer(facts=[{"label": "Link", "value": "https://example.test/source"}]),
    ],
)
def test_invalid_or_ungrounded_model_output_downgrades_to_unsupported(answer):
    result = _service(RetrieverSpy([_chunk()]), lambda *_args: answer).answer(
        "What is the expense ratio of SBI Flexicap Fund?"
    )
    assert result["state"] == "unsupported"
    assert result["reason"] == "validation_failure"
    assert "source" not in result


def test_missing_retrieval_evidence_is_not_sent_to_generator():
    generated = []
    result = _service(RetrieverSpy(), lambda *args: generated.append(args)).answer("What is an unknown fact?")
    assert result["state"] == "unsupported"
    assert result["reason"] == "not_found"
    assert generated == []


def test_invalid_date_or_mixed_source_metadata_downgrades_without_citation():
    from dataclasses import replace

    valid = _chunk()
    invalid_date = replace(valid, metadata={**valid.metadata, "retrieved_at": "not-a-date"})
    result = _service(RetrieverSpy([invalid_date])).answer("What is the expense ratio of SBI Flexicap Fund?")
    assert result["state"] == "unsupported"
    assert result["reason"] == "validation_failure"
    second_source = replace(valid, metadata={**valid.metadata, "source_id": "source_11", "source_url": "https://groww.in/expense"})
    result = _service(RetrieverSpy([valid, second_source])).answer("What is the expense ratio of SBI Flexicap Fund?")
    assert result["state"] == "unsupported"
    assert "source" not in result


def test_retrieval_and_generation_failures_are_distinct_error_states():
    class BrokenRetriever:
        def retrieve(self, *_args):
            raise RuntimeError("backend details must stay private")

    result = _service(BrokenRetriever()).answer("What is the expense ratio of SBI Flexicap Fund?")
    assert result["state"] == "error"
    assert result["reason"] == "retrieval_failure"

    def broken_generator(*_args):
        from src.generate import GenerationError

        raise GenerationError("private SDK details")

    result = _service(RetrieverSpy([_chunk()]), broken_generator).answer(
        "What is the expense ratio of SBI Flexicap Fund?"
    )
    assert result["state"] == "error"
    assert result["reason"] == "generation_failure"
    assert "private SDK details" not in result["narrative"]


def test_overlong_model_input_maps_to_validation_failure():
    class LongRetriever:
        def retrieve(self, *_args):
            raise QuestionTooLong("token count is not user-facing")

    result = _service(LongRetriever()).answer("What is the expense ratio of SBI Flexicap Fund?")
    assert result["state"] == "error"
    assert result["reason"] == "validation_failure"
