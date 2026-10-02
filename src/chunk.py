"""Apply corpus policy and create stable, section-aware embedding chunks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from src.ingest import ContentSection, FetchResult


TARGET_TOKENS = 220
OVERLAP_TOKENS = 30
class Tokenizer(Protocol):
    model_max_length: int

    def encode(self, text: str, add_special_tokens: bool = True) -> list[int]: ...

    def decode(
        self,
        token_ids: list[int],
        skip_special_tokens: bool = True,
        clean_up_tokenization_spaces: bool = False,
    ) -> str: ...


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    metadata: dict[str, str]


class ChunkingError(RuntimeError):
    """Raised when corpus policy or model token limits cannot be satisfied."""


def _normal(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _permitted_sections(result: FetchResult) -> list[ContentSection]:
    source_id = result.source["source_id"]
    permitted = []
    for section in result.sections:
        if source_id == "source_22" and "disclaimer" in section.title.casefold():
            continue
        if source_id in {"source_13", "source_16", "source_17", "source_18", "source_19", "source_20", "source_21"}:
            if "customer support help and support" in section.text.casefold():
                cleaned = re.sub(
                    r"(?i)^\s*customer support\s+help and support\s+en\s+\u0939\u093f\s*",
                    "",
                    section.text,
                )
                section = ContentSection(title=section.title, text=cleaned, page=section.page)
        if section.title.strip() and section.text.strip():
            permitted.append(section)

    if not permitted:
        raise ChunkingError(f"{source_id} has no permitted content after source-policy filtering")
    return permitted


def _special_token_count(tokenizer: Tokenizer) -> int:
    return len(tokenizer.encode("", add_special_tokens=True))


def _count(tokenizer: Tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=True))


def _section_header(result: FetchResult, section: ContentSection) -> str:
    return f"{result.source['title']} | {section.title}"


def _text_units(text: str, tokenizer: Tokenizer, body_budget: int) -> list[str]:
    units: list[str] = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        encoded = tokenizer.encode(paragraph, add_special_tokens=False)
        if len(encoded) <= body_budget:
            units.append(paragraph)
            continue

        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        if len(sentences) > 1:
            sentence_units: list[str] = []
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                sentence_tokens = tokenizer.encode(sentence, add_special_tokens=False)
                if len(sentence_tokens) <= body_budget:
                    sentence_units.append(sentence)
                    continue
                if " | " in sentence:
                    raise ChunkingError("A table row exceeds the model token budget and cannot be split safely")
                sentence_units.extend(_hard_split(sentence, tokenizer, body_budget))
            units.extend(sentence_units)
        else:
            if " | " in paragraph:
                raise ChunkingError("A table row exceeds the model token budget and cannot be split safely")
            units.extend(_hard_split(paragraph, tokenizer, body_budget))
    return units


def _hard_split(text: str, tokenizer: Tokenizer, body_budget: int) -> list[str]:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    pieces = []
    for start in range(0, len(token_ids), body_budget):
        piece = tokenizer.decode(
            token_ids[start : start + body_budget],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        ).strip()
        if piece:
            pieces.append(piece)
    return pieces


def _pack_section(
    result: FetchResult,
    section: ContentSection,
    tokenizer: Tokenizer,
    *,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    header = _section_header(result, section)
    header_tokens = tokenizer.encode(header, add_special_tokens=False)
    special_tokens = _special_token_count(tokenizer)
    body_budget = target_tokens - len(header_tokens) - special_tokens
    if body_budget <= overlap_tokens:
        raise ChunkingError(f"Section heading leaves no safe chunk budget: {header}")

    units = _text_units(section.text, tokenizer, body_budget)
    packed: list[str] = []
    current: list[str] = []

    def render(parts: list[str]) -> str:
        return f"{header}\n" + "\n".join(parts)

    def flush() -> list[str]:
        nonlocal current
        if not current:
            return []
        rendered = render(current)
        if _count(tokenizer, rendered) > target_tokens:
            raise ChunkingError(f"Chunk exceeds the {target_tokens}-token target: {header}")
        packed.append(rendered)
        previous = tokenizer.encode("\n".join(current), add_special_tokens=False)
        carry = tokenizer.decode(
            previous[-overlap_tokens:],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        ).strip()
        current = [carry] if carry else []
        return [carry] if carry else []

    for unit in units:
        candidate = render(current + [unit])
        if _count(tokenizer, candidate) <= target_tokens:
            current.append(unit)
            continue

        flush()
        candidate = render(current + [unit])
        if current and _count(tokenizer, candidate) > target_tokens:
            current = []
            candidate = render([unit])
        if _count(tokenizer, render([unit])) > target_tokens:
            raise ChunkingError(f"A content unit exceeds the model token budget: {header}")
        current.append(unit)

    if current:
        rendered = render(current)
        if _count(tokenizer, rendered) > target_tokens:
            raise ChunkingError(f"Final chunk exceeds the {target_tokens}-token target: {header}")
        packed.append(rendered)
    return packed


def _document_id(source: dict[str, str]) -> str:
    key = f"{source['source_id']}\0{source['url']}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _chunk_id(document_id: str, section: str, position: int, text: str) -> str:
    key = f"{document_id}\0{section}\0{position}\0{_normal(text)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def build_chunks(
    results: list[FetchResult],
    tokenizer: Tokenizer,
    *,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    maximum = getattr(tokenizer, "model_max_length", 10**9)
    if target_tokens > maximum:
        raise ChunkingError(f"Chunk target {target_tokens} exceeds model max sequence length {maximum}")
    chunks: list[Chunk] = []

    for result in results:
        source = result.source
        document_id = _document_id(source)
        permitted = _permitted_sections(result)
        source_chunks = 0
        section_position = 0
        for section in permitted:
            for text in _pack_section(
                result,
                section,
                tokenizer,
                target_tokens=target_tokens,
                overlap_tokens=overlap_tokens,
            ):
                chunk_id = _chunk_id(document_id, section.title, section_position, text)
                metadata = {
                    "source_id": source["source_id"],
                    "amc": source.get("amc", ""),
                    "scheme": source.get("scheme", "") or "",
                    "category": source.get("category", ""),
                    "source": source.get("source", ""),
                    "source_url": result.final_url,
                    "source_type": source.get("source_type", ""),
                    "title": source.get("title", ""),
                    "allowed_uses": source.get("allowed_uses", ""),
                    "approval_status": source.get("approval_status", ""),
                    "section": section.title,
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "retrieved_at": result.retrieved_at,
                    "content_sha256": result.content_sha256,
                }
                if section.page is not None:
                    metadata["page"] = str(section.page)
                required = {
                    "source_id", "amc", "scheme", "category", "source", "source_url", "section",
                    "document_id", "chunk_id", "retrieved_at",
                }
                missing = required.difference(metadata)
                if missing:
                    raise ChunkingError(f"{source['source_id']} chunk lacks metadata: {sorted(missing)}")
                chunks.append(Chunk(id=chunk_id, text=text, metadata=metadata))
                source_chunks += 1
                section_position += 1
        if source_chunks == 0:
            raise ChunkingError(f"{source['source_id']} has no chunks; index build aborted")

    ids = [chunk.id for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ChunkingError("Stable chunk ID collision detected")
    return chunks
