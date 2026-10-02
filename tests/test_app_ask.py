from src import app as app_module


class FakeService:
    def __init__(self, result=None):
        self.result = result or {"state": "unsupported", "reason": "not_found", "narrative": "Not found."}
        self.questions = []

    def answer(self, question):
        self.questions.append(question)
        return self.result


def test_api_returns_validation_error_without_echoing_or_logging_pii(caplog):
    client = app_module.app.test_client()
    response = client.post("/api/ask", json={"question": "My PAN is ABCDE1234F"})
    assert response.status_code == 400
    assert response.get_json()["reason"] == "validation_failure"
    assert "ABCDE1234F" not in response.get_data(as_text=True)
    assert "ABCDE1234F" not in caplog.text


def test_api_validates_request_shape_without_echoing_question():
    client = app_module.app.test_client()
    response = client.post("/api/ask", json={"question": "  "})
    assert response.status_code == 400
    assert response.get_json()["state"] == "error"
    assert client.post("/api/ask", data="not-json", content_type="application/json").status_code == 400
    oversized = client.post("/api/ask", data="x" * 9000, content_type="application/json")
    assert oversized.status_code == 413
    assert oversized.get_json()["reason"] == "validation_failure"


def test_api_dispatches_safe_question_and_returns_structured_service_result(monkeypatch):
    service = FakeService({"state": "factual", "reason": "supported_fact", "source": {"url": "https://example.test"}})
    monkeypatch.setattr(app_module, "_QUERY_SERVICE", service)
    monkeypatch.setattr(app_module, "_INDEX_ERROR", None)
    response = app_module.app.test_client().post("/api/ask", json={"question": "What is an expense ratio?"})
    assert response.status_code == 200
    assert response.get_json()["state"] == "factual"
    assert service.questions == ["What is an expense ratio?"]


def test_api_returns_503_for_service_failures(monkeypatch):
    service = FakeService({"state": "error", "reason": "generation_failure", "narrative": "Try again."})
    monkeypatch.setattr(app_module, "_QUERY_SERVICE", service)
    monkeypatch.setattr(app_module, "_INDEX_ERROR", None)
    response = app_module.app.test_client().post("/api/ask", json={"question": "What is an expense ratio?"})
    assert response.status_code == 503
    assert response.get_json()["reason"] == "generation_failure"
