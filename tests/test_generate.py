import json

import pytest

from src.generate import GenerationError, generate_answer
from src.retrieve import RetrievedChunk


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return type("Response", (), {"output_text": json.dumps(self.output)})()


class FakeClient:
    def __init__(self, output):
        self.responses = FakeResponses(output)


def _context():
    return [
        RetrievedChunk(
            "SBI Flexicap Fund Direct Growth\nExpense ratio (Direct): 0.82%",
            {"source_id": "source_02", "source_url": "https://groww.in/fund"},
            0.2,
        )
    ]


def test_responses_api_uses_selected_model_structured_output_and_disables_storage(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")
    client = FakeClient(
        {
            "supported": True,
            "narrative": "The direct plan expense ratio is 0.82%.",
            "facts": [{"label": "Expense ratio (Direct)", "value": "0.82%"}],
            "evidence_quotes": ["Expense ratio (Direct): 0.82%"],
        }
    )
    answer = generate_answer("What is the expense ratio?", _context(), client=client)
    assert answer.supported
    assert client.responses.kwargs["model"] == "configured-model"
    assert client.responses.kwargs["store"] is False
    assert client.responses.kwargs["text"]["format"]["type"] == "json_schema"
    request_input = json.loads(client.responses.kwargs["input"])
    assert request_input["question"] == "What is the expense ratio?"
    assert "source_url" not in client.responses.kwargs["input"]


def test_generation_requires_local_credentials_and_model(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(GenerationError):
        generate_answer("A question", _context(), client=object())


def test_malformed_structured_output_fails_closed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")
    with pytest.raises(GenerationError):
        generate_answer("A question", _context(), client=FakeClient({"unsupported": "shape"}))
