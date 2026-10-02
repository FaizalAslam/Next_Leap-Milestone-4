from src import app as app_module


def test_health_reports_persisted_index_state(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "_ACTIVE_INDEX",
        {"chunk_count": 107, "source_count": 25, "run_id": "test-run"},
    )
    monkeypatch.setattr(app_module, "_INDEX_ERROR", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    response = app_module.app.test_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "service": "sbi-mutual-fund-faq-assistant",
        "phase": 2,
        "status": "ok",
        "query_service": "not_configured",
        "vector_store": "ready",
        "indexed_chunks": 107,
        "indexed_sources": 25,
        "index_run_id": "test-run",
    }


def test_startup_path_skips_chroma_when_no_active_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "INDEX_MANIFEST", tmp_path / "missing.json")

    assert app_module._open_active_index() == (None, None)
