from pathlib import Path
import re

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FACTUAL = {
    "state": "factual",
    "reason": "supported_fact",
    "narrative": "The expense ratio is listed in the available scheme information.",
    "scheme": "SBI Flexicap Fund Direct Growth",
    "category": "Flexi Cap",
    "facts": [{"label": "Expense ratio", "value": "0.75%"}],
    "source": {
        "label": "Approved source",
        "url": "https://example.test/fund",
        "source_type": "scheme_page",
        "retrieved_at": "2026-10-02",
    },
    "suggestions": ["What is the exit load?"],
}


def _page(browser, width=1408, height=905, destinations=None):
    page = browser.new_page(viewport={"width": width, "height": height})
    html = (ROOT / "src" / "templates" / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'<link[^>]+href="https://[^"]+"[^>]*>', "", html)
    html = re.sub(r'<script[^>]+src="/static/[^\"]+"[^>]*></script>', "", html)
    html = re.sub(r' src="https://[^"]+"', "", html)
    if destinations:
        html = html.replace('data-investor-url="{{ investor_portal_url }}"', f'data-investor-url="{destinations[0]}"')
        html = html.replace('data-groww-url="{{ groww_dashboard_url }}"', f'data-groww-url="{destinations[1]}"')
    page.set_content(html)
    page.add_style_tag(path=str(ROOT / "src" / "static" / "app.css"))
    page.add_script_tag(path=str(ROOT / "src" / "static" / "privacy_guard.js"))
    page.add_script_tag(path=str(ROOT / "src" / "static" / "app.js"))
    return page


def _install_mock_fetch(page, responses):
    page.evaluate(
        """responses => {
          window.__requests = [];
          window.__responses = responses;
          window.fetch = async (url, options) => {
            window.__requests.push({url, options, body: JSON.parse(options.body)});
            const next = window.__responses.shift();
            if (next && next.throw) throw new Error('mock network failure');
            return {ok: next.ok !== false, json: async () => next.body};
          };
        }""",
        responses,
    )


def test_brand_and_symbol_fallbacks_work_without_external_assets():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _page(browser)
        page.wait_for_function("document.documentElement.classList.contains('symbols-fallback')")
        assert page.locator(".brand-logo-fallback").is_visible()
        assert page.locator(".brand-logo").is_hidden()
        assert page.locator(".material-symbols-outlined").first.inner_text() == "♙"
        browser.close()


def test_safe_submit_renders_loading_then_factual_and_populates_suggestion():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _page(browser)
        page.evaluate(
            """() => {
              window.__requests = [];
              let resolveRequest;
              window.__releaseRequest = (body) => resolveRequest({ok: true, json: async () => body});
              window.fetch = (url, options) => {
                window.__requests.push({url, options, body: JSON.parse(options.body)});
                return new Promise(resolve => { resolveRequest = resolve; });
              };
            }"""
        )

        page.locator("#query-input").fill("What is the expense ratio of SBI Flexicap Fund?")
        page.locator("#query-input").press("Enter")
        assert page.locator('[data-state="loading"]').count() == 1
        assert page.locator(".user-bubble").inner_text() == "What is the expense ratio of SBI Flexicap Fund?"
        assert page.locator("#query-input").is_disabled()
        assert page.evaluate("window.__requests[0].body") == {"question": "What is the expense ratio of SBI Flexicap Fund?"}

        page.evaluate("body => window.__releaseRequest(body)", FACTUAL)
        page.locator('[data-state="factual"]').wait_for()
        assert page.locator(".source-link").get_attribute("href") == "https://example.test/fund"
        page.locator(".suggestion-chip").click()
        assert page.locator("#query-input").input_value() == "What is the exit load?"
        assert len(page.evaluate("window.__requests")) == 1
        page.evaluate("""() => {
          window.fetch = async (url, options) => {
            window.__requests.push({url, options, body: JSON.parse(options.body)});
            return {ok: true, json: async () => ({state:'unsupported', reason:'not_found', narrative:'No supporting fact was found.'})};
          };
        }""")
        page.locator(".send-button").click()
        page.locator('[data-state="unsupported"]').wait_for()
        assert page.locator(".conversation-turn").count() == 2
        assert [text.strip() for text in page.locator(".user-bubble").all_inner_texts()] == [
            "What is the expense ratio of SBI Flexicap Fund?", "What is the exit load?"
        ]
        assert len(page.evaluate("window.__requests")) == 2
        browser.close()


def test_response_states_and_malformed_or_failed_requests():
    cases = [
        (FACTUAL, True, "factual"),
        ({"state": "refusal", "reason": "advice", "narrative": "Advice is not available."}, True, "refusal"),
        ({"state": "refusal", "reason": "performance", "narrative": "Performance analysis is not available."}, True, "refusal"),
        ({"state": "unsupported", "reason": "not_found", "narrative": "Not found."}, True, "unsupported"),
        ({"state": "unsupported", "reason": "private_information", "narrative": "Personal information is not available."}, True, "unsupported"),
        ({"state": "factual", "reason": "supported_fact", "narrative": "Missing required source metadata."}, True, "error"),
        ({"state": "refusal", "reason": "not_found", "narrative": "Mismatched state and reason."}, True, "error"),
        ({"state": "error", "reason": "generation_failure", "narrative": "Failure."}, False, "error"),
        (None, True, "error"),
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for body, ok, state in cases:
            page = _page(browser)
            _install_mock_fetch(page, [{"body": body, "ok": ok}])
            page.locator("#query-input").fill("Tell me a factual scheme detail")
            page.locator(".send-button").click()
            page.locator(f'[data-state="{state}"]').wait_for()
            assert page.locator("#query-input").count() == 1
            page.close()

        page = _page(browser)
        _install_mock_fetch(page, [{"throw": True}])
        page.locator("#query-input").fill("What is a scheme category?")
        page.locator(".send-button").click()
        page.locator('[data-state="error"]').wait_for()
        assert "What is a scheme category?" not in page.locator(".card-body").inner_text()
        browser.close()


def test_retry_reuses_safe_question_and_different_question_focuses_composer():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _page(browser)
        _install_mock_fetch(page, [
            {"ok": False, "body": {"state": "error", "reason": "retrieval_failure"}},
            {"ok": True, "body": {"state": "unsupported", "reason": "not_found", "narrative": "No supported fact was found."}},
        ])
        question = "What is the scheme category?"
        page.locator("#query-input").fill(question)
        page.locator(".send-button").click()
        page.locator('[data-state="error"]').wait_for()
        page.get_by_role("button", name="Try again").click()
        page.locator('[data-state="unsupported"]').wait_for()
        requests = page.evaluate("window.__requests.map(request => request.body)")
        assert requests == [{"question": question}, {"question": question}]
        assert page.locator(".user-bubble").count() == 1

        page.evaluate("window.__responses.push({ok:false, body:{state:'error', reason:'retrieval_failure'}})")
        page.locator("#query-input").fill("Another safe question")
        page.locator(".send-button").click()
        page.locator('[data-state="error"]').wait_for()
        page.get_by_role("button", name="Ask a different question").click()
        assert page.locator("#query-input").input_value() == ""
        assert page.locator("#query-input").evaluate("element => document.activeElement === element")
        browser.close()


def test_navigation_keeps_transcript_and_schemes_fill_composer():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _page(browser, width=390, height=844)
        _install_mock_fetch(page, [{"ok": True, "body": FACTUAL}])
        question = "What is the expense ratio of SBI Flexicap Fund?"
        page.locator("#query-input").fill(question)
        page.locator(".send-button").click()
        page.locator('[data-state="factual"]').wait_for()

        page.get_by_role("button", name="Schemes").click()
        assert page.locator(".scheme-directory-item").count() == 5
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.get_by_role("button", name="Ask about this scheme").first.click()
        assert page.locator("#query-input").input_value().startswith("What is the category of SBI Large Cap")
        assert page.locator(".user-bubble").inner_text() == question

        page.get_by_role("button", name="Help", exact=True).click()
        assert page.locator('[data-state="help"]').count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.get_by_role("button", name="About", exact=True).click()
        assert page.locator('[data-state="about"]').count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.get_by_role("button", name="Assistant", exact=True).click()
        assert page.locator('[data-state="factual"]').count() == 1
        assert page.locator(".user-bubble").inner_text() == question
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()


def test_feedback_and_copy_are_page_local_and_configured_links_require_https():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = _page(browser, destinations=("https://investor.example.test/login", "http://unapproved.example.test/"))
        _install_mock_fetch(page, [{"ok": True, "body": FACTUAL}])
        page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {
          configurable: true, value: {writeText: async text => {window.__copiedText = text;}}
        })""")
        page.locator("#query-input").fill("What is the expense ratio?")
        page.locator(".send-button").click()
        page.locator('[data-state="factual"]').wait_for()
        helpful_button = page.get_by_role("button", name="Helpful", exact=True)
        helpful_button.focus()
        helpful_button.press("Enter")
        assert page.get_by_role("button", name="Helpful", exact=True).get_attribute("aria-pressed") == "true"
        assert page.locator("[data-feedback='helpful']").evaluate("element => document.activeElement === element")
        page.get_by_role("button", name="Copy answer").click()
        page.wait_for_function("window.__copiedText && window.__copiedText.includes('Last updated from sources: 2026-10-02.')")
        assert "Source: Approved source (https://example.test/fund)" in page.evaluate("window.__copiedText")
        assert len(page.evaluate("window.__requests")) == 1
        assert page.evaluate("""() => {
          try { return localStorage.length + sessionStorage.length; }
          catch (_error) { return null; }
        }""") in (0, None)

        page.evaluate("window.SBIFaqUI.renderState({state:'privacy', maskedQuestion:'PAN [REDACTED]'})")
        links = page.locator(".resource-link")
        assert links.count() == 1
        assert links.first.get_attribute("href") == "https://investor.example.test/login"
        assert links.first.get_attribute("rel") == "noopener noreferrer"
        assert page.locator(".resource-placeholder[aria-disabled='true']").count() == 1
        browser.close()
