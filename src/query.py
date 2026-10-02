"""Guardrail-first orchestration for the local facts-only FAQ service."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from src.generate import GeneratedAnswer, GenerationError, generate_answer
from src.guardrails import classify_question, contains_pii
from src.contracts import MAX_QUESTION_CHARS
from src.retrieve import QuestionTooLong, RetrievalError, RetrievedChunk, Retriever, SchemeMetadata, load_local_embedder


class InputRejected(ValueError):
    """Raised for invalid or sensitive direct API input without echoing its content."""


class QueryService:
    def __init__(
        self,
        collection: Any,
        *,
        retriever: Any | None = None,
        generator: Callable[..., GeneratedAnswer] = generate_answer,
        scheme_metadata: SchemeMetadata | None = None,
    ) -> None:
        self.collection = collection
        self.scheme_metadata = scheme_metadata or SchemeMetadata.from_collection(collection)
        self._retriever = retriever
        self._generator = generator

    def answer(self, question: str) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
            raise InputRejected("Invalid question")
        question = question.strip()
        if contains_pii(question):
            raise InputRejected("Sensitive information is not accepted")

        decision = classify_question(question, self.scheme_metadata.names)
        if decision.kind == "private_information":
            return {
                "state": "unsupported",
                "reason": "private_information",
                "narrative": "I can't access or disclose private investor or personal contact information.",
                "suggestions": [],
            }
        if decision.kind == "advice":
            result: dict[str, Any] = {
                "state": "refusal",
                "reason": "advice",
                "narrative": "I can't provide investment advice or assess whether a scheme is suitable for you.",
                "suggestions": ["What is the expense ratio?", "What is the exit load?"],
            }
            record = self.scheme_metadata.records.get(decision.scheme or "")
            if record:
                result.update({"scheme": record.scheme, "category": record.category})
            return result
        if decision.kind == "performance":
            return {
                "state": "refusal",
                "reason": "performance",
                "narrative": "I can't forecast future returns or investment performance. I can answer factual questions about historical, source-reported figures when they are available.",
                "suggestions": ["What is the scheme category?", "What is the expense ratio?"],
            }

        try:
            contexts = self._get_retriever().retrieve(question, decision.scheme)
        except QuestionTooLong:
            return {
                "state": "error",
                "reason": "validation_failure",
                "narrative": "That question is too long to process. Please shorten it and try again.",
                "suggestions": [],
            }
        except RetrievalError:
            return self._error("retrieval_failure")
        except Exception:
            return self._error("retrieval_failure")
        if not contexts:
            return self._unsupported("not_found")

        try:
            generated = self._generator(question, contexts)
        except GenerationError:
            return self._error("generation_failure")
        except Exception:
            return self._error("generation_failure")
        if not generated.supported:
            return self._unsupported("not_found")

        try:
            return self._factual_response(generated, contexts, decision.scheme)
        except (TypeError, ValueError, KeyError):
            return self._unsupported("validation_failure")

    def _get_retriever(self) -> Any:
        if self._retriever is None:
            self._retriever = Retriever(self.collection, load_local_embedder())
        return self._retriever

    @staticmethod
    def _unsupported(reason: str) -> dict[str, Any]:
        return {
            "state": "unsupported",
            "reason": reason,
            "narrative": "I couldn't find that fact in the approved sources.",
            "suggestions": [],
        }

    @staticmethod
    def _error(reason: str) -> dict[str, Any]:
        return {
            "state": "error",
            "reason": reason,
            "narrative": "The assistant couldn't retrieve a reliable answer right now. Please try again.",
            "suggestions": [],
        }

    def _factual_response(
        self,
        generated: GeneratedAnswer,
        contexts: list[RetrievedChunk],
        requested_scheme: str | None,
    ) -> dict[str, Any]:
        narrative = generated.narrative.strip()
        if not narrative or _sentence_count(narrative) > 3:
            raise ValueError("Narrative must contain one to three sentences")
        generated_text = " ".join(
            [narrative, *(part for fact in generated.facts for part in (fact["label"], fact["value"]))]
        )
        if re.search(r"https?://|\bwww\.|last\s+updated|source\s*:", generated_text, re.IGNORECASE):
            raise ValueError("Source and update metadata must come from the index")
        if any(not quote.strip() or not _contains_exact(contexts, quote) for quote in generated.evidence_quotes):
            raise ValueError("Evidence quote does not occur in the retrieved source")
        if not generated.evidence_quotes:
            raise ValueError("Supported answer has no quoted evidence")

        source_ids = {chunk.metadata["source_id"] for chunk in contexts}
        source_urls = {chunk.metadata["source_url"] for chunk in contexts}
        source_labels = {chunk.metadata["source"] for chunk in contexts}
        source_types = {chunk.metadata["source_type"] for chunk in contexts}
        dates = {chunk.metadata["retrieved_at"] for chunk in contexts}
        schemes = {chunk.metadata.get("scheme", "") for chunk in contexts if chunk.metadata.get("scheme", "")}
        categories = {chunk.metadata.get("category", "") for chunk in contexts if chunk.metadata.get("category", "")}
        if any(len(values) != 1 for values in (source_ids, source_urls, source_labels, source_types, dates)):
            raise ValueError("Answer context must have one consistent source and date")
        if len(schemes) > 1 or len(categories) > 1:
            raise ValueError("Answer context contains mixed scheme metadata")

        source_url = next(iter(source_urls))
        source_label = next(iter(source_labels))
        source_type = next(iter(source_types))
        retrieved_at = next(iter(dates))
        date.fromisoformat(retrieved_at)
        if not source_url.startswith("https://") or not source_label or not source_type:
            raise ValueError("Supporting source metadata is invalid")

        context_text = "\n".join(chunk.text for chunk in contexts)
        _validate_grounding(narrative, generated.facts, generated.evidence_quotes, context_text)
        if any(_contains_restricted_intent(text) for text in [narrative, *(fact["value"] for fact in generated.facts)]):
            raise ValueError("Generated response contains restricted intent")

        context_scheme = next(iter(schemes), "")
        if requested_scheme and context_scheme and context_scheme != requested_scheme:
            raise ValueError("Retrieved scheme does not match the question")
        scheme = requested_scheme or context_scheme or None
        if requested_scheme:
            record = self.scheme_metadata.records.get(requested_scheme)
            category = record.category if record else None
        else:
            category = next(iter(categories), "") or None
            if category and category.casefold() == "general":
                category = None

        return {
            "state": "factual",
            "reason": "supported_fact",
            "narrative": narrative,
            **({"scheme": scheme} if scheme else {}),
            **({"category": category} if category else {}),
            "facts": generated.facts,
            "source": {
                "label": source_label,
                "url": source_url,
                "source_type": source_type,
                "retrieved_at": retrieved_at,
            },
            "suggestions": [],
        }


def _contains_exact(contexts: list[RetrievedChunk], quote: str) -> bool:
    normalized_quote = re.sub(r"\s+", " ", quote).strip().casefold()
    return any(
        normalized_quote in re.sub(r"\s+", " ", chunk.text).strip().casefold()
        for chunk in contexts
    )


def _sentence_count(text: str) -> int:
    normalized = re.sub(r"(?i)\b(e\.g|i\.e|mr|mrs|ms|dr|rs)\.", r"\1", text.strip())
    return len([part for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()])


def _validate_grounding(
    narrative: str,
    facts: list[dict[str, str]],
    evidence_quotes: list[str],
    context: str,
) -> None:
    context_folded = re.sub(r"\s+", " ", context).casefold()
    quote_text = " ".join(evidence_quotes)
    numeric_values = {value.replace(",", "") for value in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", context)}
    quoted_numbers = {value.replace(",", "") for value in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", quote_text)}
    answer_text = " ".join([narrative, *(fact["value"] for fact in facts)])
    answer_numbers = {value.replace(",", "") for value in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", answer_text)}
    if not answer_numbers.issubset(numeric_values) or not answer_numbers.issubset(quoted_numbers):
        raise ValueError("Answer contains a number absent from its quoted evidence")
    metric_patterns = (
        r"\breturns?\b", r"\brank(?:ed|ing)?\b", r"\bperformance\b", r"\bholdings?\b",
        r"\bAUM\b", r"\bNAV\b", r"\ballocation\b", r"\bpeers?\b", r"\bcompar(?:e|ed|ison)\b",
    )
    for pattern in metric_patterns:
        if re.search(pattern, answer_text, re.IGNORECASE) and not re.search(pattern, quote_text, re.IGNORECASE):
            raise ValueError("Answer's public metric claim is absent from its quoted evidence")
    if contains_pii(answer_text):
        raise ValueError("Generated response contains a sensitive identifier")

    stop_words = {"about", "also", "and", "are", "from", "has", "have", "into", "its", "more", "only", "that", "the", "their", "there", "these", "this", "those", "through", "with", "when", "where", "which", "will", "your"}
    answer_words = {word for word in re.findall(r"[a-z]{3,}", narrative.casefold()) if word not in stop_words}
    context_words = set(re.findall(r"[a-z]{3,}", context_folded))
    if answer_words and len(answer_words & context_words) / len(answer_words) < 0.25:
        raise ValueError("Narrative is not lexically grounded in the source excerpts")

    for match in re.finditer(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][A-Za-z]{2,})*\b", narrative):
        entity = match.group(0)
        if entity in {"The", "This", "That", "There", "These", "According"}:
            continue
        if entity.casefold() not in context_folded:
            raise ValueError("Narrative contains a named entity absent from the source excerpts")
    for acronym in re.findall(r"\b[A-Z]{2,}\b", narrative):
        if acronym.casefold() not in context_folded:
            raise ValueError("Narrative contains an acronym absent from the source excerpts")

    for fact in facts:
        value = re.sub(r"\s+", " ", fact["value"]).strip().casefold()
        label_words = [word for word in re.findall(r"[a-z]{3,}", fact["label"].casefold()) if word not in stop_words]
        if (
            not fact["label"].strip()
            or not value
            or value not in context_folded
            or any(word not in context_words for word in label_words)
            or value not in quote_text.casefold()
        ):
            raise ValueError("Structured fact is not directly present in evidence")


def _contains_restricted_intent(text: str) -> bool:
    from src.guardrails import classify_question

    direct_recommendation = re.search(
        r"\b(?:you\s+should|you\s+ought\s+to|i\s+recommend|you\s+may\s+want\s+to|"
        r"buy\s+this\s+fund|sell\s+this\s+fund|hold\s+this\s+fund|invest\s+in\s+this\s+fund)\b",
        text,
        re.IGNORECASE,
    )
    return bool(direct_recommendation) or classify_question(text, []).kind in {
        "advice", "performance", "private_information", "pii"
    }
