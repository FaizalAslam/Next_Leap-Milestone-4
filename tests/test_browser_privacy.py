from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("PAN ABCDE1234F", "ABCDE1234F"),
    ("Aadhaar 1234 5678 9012", "1234 5678 9012"),
    ("Account number 1234567890123456", "1234567890123456"),
    ("OTP 123456", "123456"),
    ("Email test.user@example.com", "test.user@example.com"),
    ("Phone +91 98765 43210", "+91 98765 43210"),
]


def _page_with_app(browser):
    page = browser.new_page()
    page.set_content('<main id="assistant-app"></main>')
    page.add_script_tag(path=str(ROOT / "src" / "static" / "privacy_guard.js"))
    page.add_script_tag(path=str(ROOT / "src" / "static" / "app.js"))
    return page


def test_pii_questions_render_locally_and_never_post():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _page_with_app(browser)
        api_requests = []
        page.on("request", lambda request: api_requests.append(request.url) if "/api/ask" in request.url else None)

        for question, sensitive_value in CASES:
            page.locator("#query-input").fill(question)
            page.locator("#query-input").press("Enter")

            assert page.locator('[data-state="privacy"]').count() == 1
            visible_text = page.locator("#assistant-app").inner_text()
            assert sensitive_value not in visible_text
            assert "[REDACTED]" in page.locator(".user-bubble").inner_text()
            assert "Question not sent" in visible_text
            assert page.locator("#query-input").input_value() == ""
            assert page.locator(".resource-placeholder").count() == 2

            page.locator("[data-reset-chat]").click()
            assert page.locator('[data-state="welcome"]').count() == 1

        assert api_requests == []
        browser.close()
