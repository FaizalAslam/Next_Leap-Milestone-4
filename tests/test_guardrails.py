import pytest

from src.guardrails import classify_question, contains_pii, find_pii, mask_pii, recognize_scheme


PII_CASES = [
    ("PAN ABCDE1234F", "ABCDE1234F"),
    ("Aadhaar 1234 5678 9012", "1234 5678 9012"),
    ("Account number 1234567890123456", "1234567890123456"),
    ("OTP 123456", "123456"),
    ("Email test.user@example.com", "test.user@example.com"),
    ("Phone +91 98765 43210", "+91 98765 43210"),
]

SCHEMES = [
    "SBI Large Cap Direct Plan Growth",
    "SBI Flexicap Fund Direct Growth",
    "SBI Small Cap Fund Direct Growth",
    "SBI ELSS Tax Saver Fund Direct Growth",
    "SBI Balanced Advantage Fund Direct Growth",
]


@pytest.mark.parametrize(("question", "sensitive_value"), PII_CASES)
def test_sensitive_values_are_detected_and_fully_masked(question, sensitive_value):
    assert contains_pii(question)
    assert find_pii(question)
    assert sensitive_value not in mask_pii(question)
    assert "[REDACTED]" in mask_pii(question)


def test_multiple_identifiers_are_masked_without_losing_question_text():
    question = "My PAN ABCDE1234F and email test.user@example.com"
    masked = mask_pii(question)
    assert "My PAN" in masked
    assert "and email" in masked
    assert "ABCDE1234F" not in masked
    assert "test.user@example.com" not in masked
    assert masked.count("[REDACTED]") == 2


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("Should I invest in SBI Small Cap Fund?", "advice"),
        ("Which SBI scheme had the highest returns?", "factual"),
        ("How do I file my income tax return?", "factual"),
        ("What are the annual returns of SBI Flexicap Fund?", "factual"),
        ("Which is the best SBI mutual fund?", "advice"),
        ("What were the 3-year returns of SBI Large Cap Fund?", "factual"),
        ("How does SBI Large Cap compare with peers historically?", "factual"),
        ("What will SBI Large Cap return next year?", "performance"),
        ("Who should invest in a large-cap scheme?", "advice"),
        ("What are the top holdings of SBI Large Cap Fund?", "factual"),
        ("Is SBI Flexicap a good investment for me?", "advice"),
        ("Is SBI Flexicap Fund a good fund?", "advice"),
        ("Is SBI Small Cap suitable?", "advice"),
        ("Which SBI fund should I choose for SIP?", "advice"),
        ("Please give investment advice for my savings.", "advice"),
        ("What is the fund manager's personal phone number?", "private_information"),
        ("What is my account balance?", "private_information"),
        ("Which benchmark does SBI Bluechip Fund follow?", "factual"),
    ],
)
def test_guardrail_routing_and_benchmark_identity(question, kind):
    assert classify_question(question, SCHEMES).kind == kind


def test_scheme_recognition_supports_wireframe_alias_and_rejects_multiple_schemes():
    assert recognize_scheme("What is the benchmark of SBI Bluechip Fund?", SCHEMES) == SCHEMES[0]
    assert recognize_scheme("Should I choose SBI Flexicap or SBI Small Cap?", SCHEMES) is None
