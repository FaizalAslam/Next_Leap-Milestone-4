from pathlib import Path
import re
import struct

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
# Visual-only fixture values; these never enter the application or live API.
FACTUAL = {
    "state": "factual",
    "reason": "supported_fact",
    "narrative": "The total expense ratio is 1.72% for the regular plan, as shown in this visual-only fixture.",
    "scheme": "SBI Flexicap Fund Direct Growth",
    "category": "Equity / Flexi Cap",
    "facts": [
        {"label": "Expense Ratio (Regular)", "value": "1.72%"},
        {"label": "Expense Ratio (Direct)", "value": "0.86%"},
    ],
    "source": {
        "label": "Fixture Source",
        "url": "https://example.test/fund",
        "source_type": "scheme_page",
        "retrieved_at": "2026-01-02",
    },
    "suggestions": ["Exit load of SBI Flexicap", "Minimum SIP amount"],
    "user_time": "10:24 AM",
    "assistant_time": "10:24 AM",
}
STATES = [
    ("welcome", {"state": "welcome"}, "welcome"),
    (
        "loading",
        {
            "state": "loading",
            "question": "What is the expense ratio of SBI Flexicap Fund?",
            "scheme": "SBI Flexicap Fund Direct Growth",
            "source": {"label": "Fixture Source"},
            "time": "10:24 AM",
        },
        "loading",
    ),
    ("factual", FACTUAL, "factual"),
    (
        "refusal",
        {
            "state": "refusal",
            "reason": "advice",
            "narrative": "I can provide factual scheme information, but I cannot recommend whether you should invest.",
            "scheme": "SBI Small Cap Fund Direct Growth",
            "category": "Small Cap",
            "facts": [
                {"label": "Scheme category", "value": "Small Cap"},
                {"label": "Expense ratio", "value": "1.61% (Regular)"},
                {"label": "Riskometer", "value": "Very High"},
                {"label": "Minimum SIP", "value": "Rs. 500"},
            ],
            "suggestions": ["What is the expense ratio?", "What is the exit load?"],
            "user_time": "10:26 AM",
            "assistant_time": "10:26 AM",
        },
        "refusal",
    ),
    (
        "not_found",
        {
            "state": "unsupported",
            "reason": "not_found",
            "narrative": "We could not find that information in the available public scheme sources. Try another supported scheme fact.",
            "suggestions": ["SBI Bluechip Fund NAV?", "Exit load policy?", "Fund manager tenure?"],
            "user_time": "10:28 AM",
            "assistant_time": "10:28 AM",
        },
        "unsupported",
    ),
    (
        "private_information",
        {"state": "unsupported", "reason": "private_information", "narrative": "Fixture privacy response."},
        "unsupported",
    ),
    (
        "privacy",
        {
            "state": "privacy",
            "maskedQuestion": "Can you check my folio status? My PAN is [REDACTED] and Aadhaar is [REDACTED].",
            "time": "10:30 AM",
        },
        "privacy",
    ),
    (
        "error",
        {
            "state": "error",
            "reason": "retrieval_failure",
            "narrative": "The assistant could not retrieve reliable information right now. Please try the question again in a moment.",
            "user_time": "10:32 AM",
            "assistant_time": "10:32 AM",
        },
        "error",
    ),
]

VISUAL_QUESTIONS = {
    "factual": "What is the expense ratio of SBI Flexicap Fund?",
    "refusal": "Should I invest in SBI Small Cap Fund?",
    "not_found": "What are the latest NAV details for SBI Mutual Fund schemes?",
    "private_information": "Can you check my folio status?",
    "error": "What is the expense ratio and exit load for SBI Flexicap Fund Direct Growth?",
}


def _app_page(browser, width=1408, height=905, device_scale_factor=1):
    page = browser.new_page(
        viewport={"width": width, "height": height},
        device_scale_factor=device_scale_factor,
    )
    html = (ROOT / "src" / "templates" / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'<link[^>]+href="https://[^"]+"[^>]*>', "", html)
    html = re.sub(r'<script[^>]+src="/static/[^"]+"[^>]*></script>', "", html)
    html = re.sub(r' src="https://[^"]+"', "", html)
    page.set_content(html)
    page.add_style_tag(path=str(ROOT / "src" / "static" / "app.css"))
    page.add_script_tag(path=str(ROOT / "src" / "static" / "privacy_guard.js"))
    page.add_script_tag(path=str(ROOT / "src" / "static" / "app.js"))
    page.evaluate("() => document.fonts.ready.then(() => true)")
    return page


@pytest.mark.parametrize(("name", "fixture", "expected_state"), STATES)
def test_response_and_local_states_render(name, fixture, expected_state):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _app_page(browser)
        page.evaluate("fixture => window.SBIFaqUI.renderState(fixture, 'Fixture user question?')", fixture)

        assert page.locator(f'[data-state="{expected_state}"]').count() == 1, name
        assert page.locator("#query-input").count() == 1, name
        if name in {"factual", "refusal"}:
            assert page.locator(".assistant-card").count() == 1
        browser.close()


def test_source_metadata_is_escaped_and_missing_private_source_stays_absent():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _app_page(browser)
        unsafe = {
            **FACTUAL,
            "narrative": '<img src=x onerror="window.__xss=true">',
            "source": {**FACTUAL["source"], "label": '<script>bad()</script>'},
        }
        page.evaluate("fixture => window.SBIFaqUI.renderState(fixture)", unsafe)
        assert page.locator("img[src='x']").count() == 0
        assert not page.evaluate("window.__xss === true")
        assert page.locator(".source-link").inner_text().find("<script>") >= 0

        page.evaluate(
            "window.SBIFaqUI.renderState({state:'unsupported', reason:'private_information', narrative:'Private details are unavailable.'})"
        )
        assert page.locator(".source-row").count() == 0
        browser.close()


@pytest.mark.parametrize(("name", "fixture", "expected_state"), STATES)
def test_mobile_states_do_not_overflow_viewport(name, fixture, expected_state):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _app_page(browser, width=390, height=844)
        page.evaluate("fixture => window.SBIFaqUI.renderState(fixture, 'A long fixture question with an extended scheme name?')", fixture)
        overflow = page.evaluate("""() => ({
            width: document.documentElement.scrollWidth,
            viewport: window.innerWidth,
            offenders: [...document.querySelectorAll('body *')]
              .map(el => ({tag: el.tagName, className: String(el.className), left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right, scrollWidth: el.scrollWidth}))
              .filter(item => item.right > window.innerWidth + 1 || item.left < -1)
              .slice(0, 8)
        })""")
        assert overflow["width"] <= overflow["viewport"], (name, overflow)
        assert page.locator("#query-input").is_visible(), name
        browser.close()


def test_home_has_all_prompt_controls_and_no_runtime_sample_facts():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _app_page(browser)
        assert page.locator(".prompt-card").count() == 3
        assert page.locator(".topic-chip").count() == 8
        assert page.locator(".fact-value").count() == 0
        page.locator(".prompt-card").first.click()
        assert page.locator("#query-input").input_value() == "What is the expense ratio of SBI Flexicap Fund?"
        page.locator(".topic-chip").nth(1).focus()
        page.locator(".topic-chip").nth(1).press("Enter")
        assert page.locator("#query-input").input_value() == "What is the minimum SIP amount for SBI Mutual Funds?"
        browser.close()


def test_desktop_states_capture_at_wireframe_canvas_sizes(tmp_path):
    reference_canvases = {
        "welcome": (2112, 1357),
        "loading": (2112, 1633),
        "factual": (2112, 1181),
        "refusal": (2112, 1633),
        "not_found": (2112, 1263),
        "privacy": (1600, 1365),
        "error": (2112, 1320),
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for name, fixture, _expected_state in STATES:
            if name == "private_information":
                continue
            reference_width, reference_height = reference_canvases[name]
            scale = 1 if name == "privacy" else 1.5
            width = round(reference_width / scale)
            height = round(reference_height / scale)
            page = _app_page(browser, width=width, height=height, device_scale_factor=scale)
            question = VISUAL_QUESTIONS.get(name, "What is the expense ratio of SBI Flexicap Fund?")
            page.evaluate("([fixture, question]) => window.SBIFaqUI.renderState(fixture, question)", [fixture, question])
            if name == "welcome":
                assert page.locator(".prompt-card").count() == 3
            elif name == "loading":
                assert page.locator(".scheme-context .context-tag").count() == 2
            elif name == "factual":
                assert page.locator(".fact-value").count() == 2
                assert page.locator(".source-link").count() == 1
                assert page.locator(".source-date-row").count() == 1
                assert page.locator(".suggestion-chip").count() == 2
                source_box = page.locator(".source-link").bounding_box()
                date_box = page.locator(".source-date-row").bounding_box()
                assert date_box["y"] >= source_box["y"] + source_box["height"]
            elif name == "refusal":
                assert page.locator(".trust-banner").count() == 1
                assert page.locator(".fact-value").count() == 4
                assert page.locator(".suggestion-chip").count() == 2
            elif name == "not_found":
                assert page.locator(".suggestion-chip").count() == 3
                assert page.locator(".source-row").count() == 0
            elif name == "privacy":
                assert page.locator(".resource-placeholder").count() == 2
            elif name == "error":
                assert page.locator(".trust-banner").count() == 1
                assert page.locator(".error-actions .action-button").count() == 2
                assert page.locator(".error-shortcuts .suggestion-chip").count() == 3
            screenshot_path = tmp_path / f"{name}.png"
            page.screenshot(path=str(screenshot_path))
            screenshot_width, screenshot_height = struct.unpack(">II", screenshot_path.read_bytes()[16:24])
            assert screenshot_width == reference_width, name
            assert abs(screenshot_height - reference_height) <= 1, name
            page.close()
        browser.close()
