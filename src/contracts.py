"""Typed API payloads shared by the Flask service and UI integration."""

from typing import Literal, NotRequired, TypedDict


MAX_QUESTION_CHARS = 1000
ApiHTTPStatus = Literal[200, 400, 413, 503]
ResponseState = Literal["factual", "refusal", "unsupported", "error"]
ResponseReason = Literal[
    "supported_fact",
    "advice",
    "performance",
    "not_found",
    "private_information",
    "retrieval_failure",
    "generation_failure",
    "validation_failure",
]


class AskRequest(TypedDict):
    question: str


class Fact(TypedDict):
    label: str
    value: str


class Source(TypedDict):
    label: str
    url: str
    source_type: str
    retrieved_at: str


class AssistantResponse(TypedDict):
    state: ResponseState
    reason: ResponseReason
    narrative: NotRequired[str]
    scheme: NotRequired[str]
    category: NotRequired[str]
    facts: NotRequired[list[Fact]]
    source: NotRequired[Source]
    suggestions: NotRequired[list[str]]


class AssistantError(TypedDict):
    state: Literal["error"]
    reason: Literal["validation_failure", "retrieval_failure", "generation_failure"]
    narrative: str
    suggestions: list[str]
