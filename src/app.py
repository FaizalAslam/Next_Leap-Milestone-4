"""Flask routes for the SBI Mutual Fund FAQ Assistant."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from src.guardrails import contains_pii
from src.contracts import MAX_QUESTION_CHARS
from src.query import InputRejected, QueryService

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8192
INDEX_MANIFEST = ROOT / "data" / "processed" / "index_manifest.json"


def _open_active_index():
    if not INDEX_MANIFEST.is_file():
        return None, None
    from src.vector_store import load_active_index

    return load_active_index()


try:
    _ACTIVE_COLLECTION, _ACTIVE_INDEX = _open_active_index()
    _INDEX_ERROR = None
except Exception as exc:
    _ACTIVE_COLLECTION, _ACTIVE_INDEX = None, None
    _INDEX_ERROR = str(exc)

try:
    _QUERY_SERVICE = QueryService(_ACTIVE_COLLECTION) if _ACTIVE_COLLECTION is not None else None
except Exception as exc:
    _QUERY_SERVICE = None
    _INDEX_ERROR = str(exc)


def _error(reason: str, narrative: str, status: int):
    return jsonify({"state": "error", "reason": reason, "narrative": narrative, "suggestions": []}), status


def _configured_https_url(value: str | None) -> str:
    if not value or len(value) > 2048 or any(character.isspace() for character in value):
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            return ""
        parsed.port
    except ValueError:
        return ""
    return value


@app.get("/")
def home():
    return render_template(
        "index.html",
        investor_portal_url=_configured_https_url(os.getenv("SBI_INVESTOR_PORTAL_URL", "")),
        groww_dashboard_url=_configured_https_url(os.getenv("GROWW_DASHBOARD_URL", "")),
    )


@app.get("/api/health")
def health():
    if _INDEX_ERROR:
        vector_state = "unavailable"
    elif _ACTIVE_INDEX:
        vector_state = "ready"
    else:
        vector_state = "not_initialized"
    configured = bool(os.getenv("OPENAI_API_KEY", "").strip() and os.getenv("OPENAI_MODEL", "").strip())
    query_state = "unavailable" if _INDEX_ERROR else "not_initialized" if not _QUERY_SERVICE else "ready" if configured else "not_configured"
    return jsonify(
        {
            "service": "sbi-mutual-fund-faq-assistant",
            "phase": 2,
            "status": "degraded" if _INDEX_ERROR else "ok",
            "query_service": query_state,
            "vector_store": vector_state,
            "indexed_chunks": _ACTIVE_INDEX.get("chunk_count") if _ACTIVE_INDEX else 0,
            "indexed_sources": _ACTIVE_INDEX.get("source_count") if _ACTIVE_INDEX else 0,
            "index_run_id": _ACTIVE_INDEX.get("run_id") if _ACTIVE_INDEX else None,
        }
    )


@app.post("/api/ask")
def ask():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("validation_failure", "Submit a JSON question to continue.", 400)
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        return _error(
            "validation_failure",
            f"Enter a question of {MAX_QUESTION_CHARS:,} characters or fewer.",
            400,
        )
    if contains_pii(question):
        return _error(
            "validation_failure",
            "Sensitive information is not accepted. Remove it and ask a general FAQ question.",
            400,
        )
    if _INDEX_ERROR or _QUERY_SERVICE is None:
        return _error("retrieval_failure", "The assistant could not open its approved source index.", 503)

    try:
        result = _QUERY_SERVICE.answer(question)
    except InputRejected:
        return _error("validation_failure", "The question could not be processed.", 400)
    except Exception:
        app.logger.error("FAQ request failed at the service boundary")
        return _error("retrieval_failure", "The assistant couldn't retrieve a reliable answer right now. Please try again.", 503)

    if result.get("state") == "error":
        status = 400 if result.get("reason") == "validation_failure" else 503
        return jsonify(result), status
    return jsonify(result), 200


@app.errorhandler(413)
def request_too_large(_error_value):
    return _error("validation_failure", "The request is too large to process.", 413)
