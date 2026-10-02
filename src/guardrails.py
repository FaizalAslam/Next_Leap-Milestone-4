"""Input classification and sensitive-value redaction for the FAQ pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


GuardrailKind = Literal["pii", "private_information", "advice", "performance", "factual"]


@dataclass(frozen=True)
class PiiMatch:
    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class GuardrailDecision:
    kind: GuardrailKind
    scheme: str | None = None


_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)),
    ("aadhaar", re.compile(r"(?<!\d)(?P<value>\d(?:[ -]?\d){11})(?!\d)")),
    (
        "account_number",
        re.compile(
            r"\b(?:bank\s+)?(?:account|acct|a/c)\s*(?:number|no\.?|#|is|:)?\s*"
            r"(?P<value>\d(?:[ -]?\d){7,17})\b",
            re.IGNORECASE,
        ),
    ),
    ("otp", re.compile(r"\b(?:otp|one[- ]time\s+password|verification\s+code)\D{0,12}(?P<value>\d{4,8})\b", re.IGNORECASE)),
    ("email", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")),
    (
        "phone",
        re.compile(r"(?<!\w)(?:(?:\+?91|0091)[\s().-]*)?(?:[6-9](?:[\s().-]*\d){9})(?!\w)"),
    ),
)

_PRIVATE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bpersonal\b.{0,30}\b(?:phone|mobile|email|address|contact|number)\b",
        r"\b(?:phone|mobile|email|address|contact)\b.{0,35}\b(?:fund\s+manager|manager|employee|person)\b",
        r"\bfund\s+manager\b.{0,35}\b(?:personal|private|mobile|phone|email|contact)\b",
        r"\b(?:check|look\s+up|retrieve|show|access)\b.{0,25}\b(?:my|our)\b.{0,20}\b(?:folio|account|portfolio|holdings?|balance|units?)\b",
        r"\b(?:my|our)\b.{0,15}\b(?:folio|account|portfolio|holdings?|balance|units?)\b.{0,20}\b(?:status|details|value|check|access)\b",
        r"\b(?:what(?:'s|\s+is)|tell\s+me|show\s+me)\b.{0,25}\bmy\b.{0,20}\b(?:folio|account|portfolio|balance|holdings?|units?)\b",
        r"\bmy\b.{0,15}\b(?:folio|account|portfolio)\b.{0,20}\b(?:number|balance|status|holdings?|units?|details)\b",
        r"\b(?:private|confidential)\b.{0,25}\b(?:contact|phone|mobile|email|address|data|details)\b",
    )
)

_ADVICE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bshould\s+i\s+(?:invest|buy|sell|hold|choose|switch|redeem|allocate)\b",
        r"\bwould\s+you\s+recommend\b|\b(?:recommend|recommendation)\b",
        r"\badvice\b|\bsuitability\b|\b(?:suitable|appropriate)\b",
        r"\b(?:suitable|right)\s+for\s+me\b|\bfit\s+my\s+(?:needs|goals|risk)\b",
        r"\b(?:good|bad|better|right|suitable|appropriate)\b.{0,35}\b(?:choice|option|investment|fund|scheme|for\s+me|for\s+my)\b",
        r"\b(?:suit|suits|suitable)\b.{0,20}\bme\b|\b(?:okay|ok)\b.{0,25}\bfor\s+me\b",
        r"\b(?:investment|financial)\s+advice\b",
        r"\bwhich\b.{0,60}\bshould\s+i\s+(?:choose|select|invest|buy)\b",
        r"\b(?:which|what)\b.{0,40}\b(?:fund|scheme)\b.{0,25}\b(?:invest\s+in|buy|choose|select)\b",
        r"\bwho\s+should\s+invest\b|\bhow\s+should\s+i\s+invest\b",
        r"\b(?:best|better)\s+(?:fund|scheme|investment)\s+for\s+me\b",
    )
)

_PERFORMANCE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:forecast|predict|project|estimate)\b.{0,40}\b(?:future|fund|scheme|return|market|NAV|performance)\b",
        r"\b(?:future|fund|scheme|return|market|NAV|performance)\b.{0,40}\b(?:forecast|predict|project|estimate)\b",
        r"\bexpected\s+(?:future\s+)?returns?\b|\bwhat\s+will\b.{0,40}\b(?:return|NAV|performance)\b",
    )
)

_PUBLIC_METRIC_CUES = re.compile(
    r"\b(?:return|returned|performance|rank(?:ed|ing)?|rating|rated|AUM|NAV|holdings?|"
    r"expense|benchmark|compare|comparison|versus|\d+\s*[- ]?years?|\d+\s*[ym])\b",
    re.IGNORECASE,
)

_SCHEME_ALIASES = {
    "SBI Bluechip Fund": "large cap",
    "SBI Bluechip": "large cap",
    "SBI Blue Chip Fund": "large cap",
    "SBI Large Cap Fund": "large cap",
    "SBI Flexi Cap Fund": "flexicap",
}


def find_pii(question: str) -> list[PiiMatch]:
    matches: list[PiiMatch] = []
    for kind, pattern in _PII_PATTERNS:
        for match in pattern.finditer(question):
            group = "value" if "value" in match.groupdict() else None
            start, end = match.span(group) if group else match.span()
            matches.append(PiiMatch(kind=kind, start=start, end=end))

    matches.sort(key=lambda item: (item.start, -(item.end - item.start)))
    merged: list[PiiMatch] = []
    for match in matches:
        if merged and match.start < merged[-1].end:
            previous = merged[-1]
            merged[-1] = PiiMatch(
                kind=previous.kind if previous.end - previous.start >= match.end - match.start else match.kind,
                start=previous.start,
                end=max(previous.end, match.end),
            )
        else:
            merged.append(match)
    return merged


def contains_pii(question: str) -> bool:
    return bool(find_pii(question))


def mask_pii(question: str) -> str:
    matches = find_pii(question)
    masked = question
    for match in reversed(matches):
        masked = masked[: match.start] + "[REDACTED]" + masked[match.end :]
    return masked


def _normalize_scheme_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def recognize_scheme(question: str, scheme_names: list[str]) -> str | None:
    aliases: list[tuple[str, str]] = []
    for canonical in scheme_names:
        candidates = {canonical}
        for suffix in (" Direct Plan Growth", " Direct Growth", " Growth", " Plan"):
            if canonical.endswith(suffix):
                candidates.add(canonical[: -len(suffix)])
        for candidate in tuple(candidates):
            if " fund" not in candidate.casefold() and candidate.casefold().startswith("sbi "):
                candidates.add(candidate + " Fund")
        for alias, hint in _SCHEME_ALIASES.items():
            if hint in canonical.casefold():
                candidates.add(alias)
        aliases.extend((_normalize_scheme_text(candidate), canonical) for candidate in candidates)

    normalized_question = f" {_normalize_scheme_text(question)} "
    matches = {
        canonical
        for alias, canonical in sorted(aliases, key=lambda item: len(item[0]), reverse=True)
        if alias and f" {alias} " in normalized_question
    }
    return next(iter(matches)) if len(matches) == 1 else None


def classify_question(question: str, scheme_names: list[str]) -> GuardrailDecision:
    if contains_pii(question):
        return GuardrailDecision("pii")
    if any(pattern.search(question) for pattern in _PRIVATE_PATTERNS):
        return GuardrailDecision("private_information")
    scheme = recognize_scheme(question, scheme_names)
    if any(pattern.search(question) for pattern in _ADVICE_PATTERNS):
        return GuardrailDecision("advice", scheme)
    if re.search(r"\b(?:which|what(?:'s|\s+is))\b.{0,45}\b(?:best|better)\b.{0,30}\b(?:fund|scheme|investment)\b", question, re.IGNORECASE) and not _PUBLIC_METRIC_CUES.search(question):
        return GuardrailDecision("advice", scheme)
    if any(pattern.search(question) for pattern in _PERFORMANCE_PATTERNS):
        return GuardrailDecision("performance", scheme)
    return GuardrailDecision("factual", scheme)
