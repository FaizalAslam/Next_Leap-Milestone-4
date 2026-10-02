"""Context-bound structured answer generation using the OpenAI Responses API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.retrieve import RetrievedChunk


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class GenerationError(RuntimeError):
    """Raised for missing OpenAI configuration or an unusable model response."""


@dataclass(frozen=True)
class GeneratedAnswer:
    supported: bool
    narrative: str
    facts: list[dict[str, str]]
    evidence_quotes: list[str]


_ANSWER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["supported", "narrative", "facts", "evidence_quotes"],
    "properties": {
        "supported": {"type": "boolean"},
        "narrative": {"type": "string"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "value"],
                "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
            },
        },
        "evidence_quotes": {"type": "array", "items": {"type": "string"}},
    },
}

_INSTRUCTIONS = """You are a facts-only SBI Mutual Fund FAQ assistant.
Use only the supplied source excerpts. Do not use outside knowledge, answer investment advice,
assess suitability, make recommendations, or forecast future returns. You may report public,
source-backed historical returns, rankings, peer comparisons, NAV, AUM, and scheme-level holdings
as facts; never present past figures as predictions. Do not invent source links or dates. Keep the
narrative to at most three sentences. Preserve numbers, labels, dates, and units exactly as written
in the excerpts.
Set supported=false when the excerpts do not directly answer the question. For a supported answer,
include one or more exact, contiguous evidence_quotes copied from the excerpts for the answer's claims.
Return only the required structured output."""


def generate_answer(
    question: str,
    contexts: list[RetrievedChunk],
    *,
    client: Any | None = None,
    model: str | None = None,
) -> GeneratedAnswer:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model_name = (model or os.getenv("OPENAI_MODEL", "")).strip()
    if not api_key or not model_name:
        raise GenerationError("OpenAI generation is not configured")
    if not contexts:
        raise GenerationError("Cannot generate without retrieved evidence")

    if client is None:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, timeout=30.0, max_retries=1)
        except Exception as exc:
            raise GenerationError("OpenAI client could not be initialized") from exc

    request_input = {
        "question": question,
        "source_excerpts": [
            {"excerpt_id": f"E{index + 1}", "text": chunk.text}
            for index, chunk in enumerate(contexts)
        ],
    }
    try:
        response = client.responses.create(
            model=model_name,
            instructions=_INSTRUCTIONS,
            input=json.dumps(request_input, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "sbi_faq_answer",
                    "strict": True,
                    "schema": _ANSWER_SCHEMA,
                }
            },
            store=False,
            max_output_tokens=500,
        )
        raw_output = response.output_text
        payload = json.loads(raw_output)
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("supported"), bool)
            or not isinstance(payload.get("narrative"), str)
            or not isinstance(payload.get("facts"), list)
            or not isinstance(payload.get("evidence_quotes"), list)
        ):
            raise ValueError("Unexpected structured response shape")
        facts = payload["facts"]
        quotes = payload["evidence_quotes"]
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("label"), str)
            or not isinstance(item.get("value"), str)
            for item in facts
        ) or any(not isinstance(item, str) for item in quotes):
            raise ValueError("Invalid fact or evidence field")
        return GeneratedAnswer(
            supported=payload["supported"],
            narrative=payload["narrative"].strip(),
            facts=facts,
            evidence_quotes=quotes,
        )
    except Exception as exc:
        raise GenerationError("OpenAI generation failed or returned invalid structured output") from exc
