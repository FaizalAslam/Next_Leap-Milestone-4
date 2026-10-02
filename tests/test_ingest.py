import json
import sys
from types import SimpleNamespace

import pytest

from src import ingest


def _source(source_id="source_13", source_type="help", allowed_uses="help procedure"):
    return {
        "source_id": source_id,
        "title": "Exit load help",
        "url": "https://example.com/help",
        "source_type": source_type,
        "source": "Example",
        "amc": "SBI Mutual Fund",
        "scheme": "",
        "category": "General",
        "allowed_uses": allowed_uses,
        "approval_status": "approved_listed",
        "enabled": "true",
        "retrieved_at": "",
    }


def test_manifest_has_25_enabled_approved_records_and_one_exception():
    records = ingest.load_sources()
    eligible = ingest.eligible_sources(records)

    assert len(records) == len(eligible) == 25
    assert all(record["enabled"] == "true" for record in records)
    assert [record["source_id"] for record in records if record["approval_status"] == "user_approved_exception"] == [
        "source_22"
    ]
    assert records[21]["url"] == ingest.EXCEPTION_URL


def test_html_extraction_keeps_headings_and_table_rows_and_drops_chrome():
    html = """<html><body><nav>Global menu</nav><main>
      <h1>Exit load</h1><p>A long factual explanation of the exit load applies to this fund.</p>
      <h2>Scheme facts</h2><table><tr><th>Holding</th><th>Sector</th><th>Allocation</th></tr>
      <tr><td>Example Bank</td><td>Financials</td><td>8.5%</td></tr></table>
      </main><footer>Unrelated footer text</footer></body></html>"""

    sections, structure = ingest._html_sections(html, "Exit load help")
    joined = "\n".join(section.text for section in sections)

    assert "Global menu" not in joined
    assert "Unrelated footer" not in joined
    assert any(
        section.title.endswith("Scheme facts") and "Holding: Example Bank | Sector: Financials | Allocation: 8.5%" in section.text
        for section in sections
    )
    assert structure["heading_count"] == 2
    assert structure["table_row_count"] == 2


def test_scheme_next_data_extracts_only_approved_fact_fields():
    source = _source(
        "source_04",
        "scheme_page",
        "category; minimum SIP; minimum investment; expense information; exit load; risk; benchmark; lock-in",
    )
    source["scheme"] = "SBI ELSS Tax Saver Fund Direct Growth"
    payload = {
        "props": {
            "pageProps": {
                "mfServerSideData": {
                    "scheme_name": source["scheme"],
                    "category": "Equity",
                    "sub_category": "ELSS",
                    "min_sip_investment": 500,
                    "min_investment_amount": 500,
                    "expense_ratio": "1.25",
                    "exit_load": "Nil",
                    "nfo_risk": "Moderately High",
                    "benchmark_name": "Benchmark Index",
                    "lock_in": {"years": 3, "months": 0, "days": 0},
                    "return_stats": {"return1y": 42},
                    "holdings": [{"name": "Do not index"}],
                }
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'

    section = ingest._scheme_fact_section(html, source)

    assert section is not None
    assert "Minimum SIP investment: INR 500" in section.text
    assert "Lock-in: 3 year(s)" in section.text
    assert "return" not in section.text.casefold()
    assert "Do not index" not in section.text


def test_scheme_payload_must_match_manifest_scheme():
    source = _source("source_01", "scheme_page", "category; minimum SIP")
    source["scheme"] = "SBI Large Cap Direct Plan Growth"
    html = '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"mfServerSideData":{"scheme_name":"Other Scheme","min_sip_investment":500}}}}</script>'

    assert ingest._scheme_fact_section(html, source) is None


def test_faq_jsonld_extracts_formatted_public_aum_and_nav_with_page_dates():
    html = """<script type="application/ld+json">{
      "@type":"FAQPage","mainEntity":[
        {"@type":"Question","name":"What is the AUM of SBI Large Cap Fund?",
         "acceptedAnswer":{"@type":"Answer","text":"<p>AUM is ₹55,139.84 Cr as of 02 Oct 2026.</p>"}},
        {"@type":"Question","name":"What is the NAV?",
         "acceptedAnswer":{"@type":"Answer","text":"<p>NAV is ₹98.91 as of 01 Oct 2026.</p>"}},
        {"@type":"Question","name":"How do I redeem?",
         "acceptedAnswer":{"@type":"Answer","text":"<p>Sign in and redeem from your account.</p>"}}
      ]}</script>"""

    sections = ingest._public_faq_sections(html)
    text = "\n".join(section.text for section in sections)

    assert "₹55,139.84 Cr as of 02 Oct 2026" in text
    assert "₹98.91 as of 01 Oct 2026" in text
    assert "How do I redeem?" not in text


def test_staged_snapshot_reextracts_all_sections_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    monkeypatch.setattr(ingest, "PROCESSED_DIR", tmp_path / "data" / "processed")
    processed = tmp_path / "data" / "processed" / "saved-run"
    raw = tmp_path / "data" / "raw" / "saved-run"
    processed.mkdir(parents=True)
    raw.mkdir(parents=True)
    source = _source("source_01", "scheme_page")
    source["scheme"] = "SBI Large Cap Direct Plan Growth"
    html = (
        "<main><h1>Historical returns</h1><p>Published historical fund return data is provided by period for reference. "
        "This page includes source labels and values that should remain connected during extraction.</p>"
        "<table><tr><th>Period</th><th>Return</th></tr><tr><td>3 years</td><td>12%</td></tr></table></main>"
    )
    (raw / "source_01.html").write_text(html, encoding="utf-8")
    source_record = {
        "source": source,
        "retrieved_at": "2026-10-02",
        "final_url": source["url"],
        "content_type": "text/html",
        "content_sha256": "saved-hash",
        "extraction_method": "requests+beautifulsoup",
        "raw_files": ["data/raw/saved-run/source_01.html"],
        "structure": {},
        "sections": [{"title": "Old curated facts", "text": "old facts only"}],
    }
    (processed / "source_01.json").write_text(json.dumps(source_record), encoding="utf-8")
    (processed / "ingestion_manifest.json").write_text(
        json.dumps({"failed_count": 0, "results": [{"source_id": "source_01"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(ingest, "load_sources", lambda: [source])

    results, _ = ingest.load_staged_run("saved-run")

    assert "Period: 3 years | Return: 12%" in results[0].extracted_text
    assert results[0].retrieved_at == "2026-10-02"
    assert results[0].content_sha256 == "saved-hash"


def test_pdf_extraction_preserves_page_sections(monkeypatch):
    page_text = "This tax table has enough factual text and labels for reliable extraction. " * 4

    class FakePage:
        def extract_text(self):
            return page_text

    class FakeReader:
        is_encrypted = False
        pages = [FakePage(), FakePage()]

        def __init__(self, _stream, strict=True):
            pass

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))
    sections = ingest._pdf_sections(b"%PDF-fake")

    assert [section.page for section in sections] == [1, 2]
    assert sections[0].title == "Page 1"


def test_unreadable_static_html_uses_browser_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    source = _source()

    class FakeResponse:
        status_code = 200
        url = source["url"]
        headers = {"Content-Type": "text/html; charset=utf-8"}
        content = b"<main><p>Short.</p></main>"
        text = content.decode()
        apparent_encoding = "utf-8"
        encoding = None

        @staticmethod
        def raise_for_status():
            return None

    class FakeSession:
        headers = {}

        @staticmethod
        def get(*_args, **_kwargs):
            return FakeResponse()

    rendered = (
        "<main><h1>Exit load procedure</h1><p>" +
        "This detailed help article explains the approved steps to view the exit load information. " * 4 +
        "</p></main>"
    ).encode()
    result, structure = ingest.fetch_source(
        source,
        "test-run",
        session=FakeSession(),
        browser_fetch=lambda _url: (rendered, source["url"], "text/html"),
        raw_dir=tmp_path / "raw",
    )

    assert result.extraction_method == "playwright+beautifulsoup"
    assert len(result.raw_files) == 2
    assert structure["section_count"] == 1
    assert "approved steps" in result.extracted_text


def test_empty_static_and_browser_content_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    source = _source()

    class FakeResponse:
        status_code = 200
        url = source["url"]
        headers = {"Content-Type": "text/html"}
        content = b"<main><nav>Menu only</nav></main>"
        text = content.decode()
        apparent_encoding = "utf-8"
        encoding = None

        @staticmethod
        def raise_for_status():
            return None

    class FakeSession:
        headers = {}

        @staticmethod
        def get(*_args, **_kwargs):
            return FakeResponse()

    with pytest.raises(ingest.SourceIngestionError, match="no usable page-specific text"):
        ingest.fetch_source(
            source,
            "test-run",
            session=FakeSession(),
            browser_fetch=lambda _url: (FakeResponse.content, source["url"], "text/html"),
            raw_dir=tmp_path / "raw",
        )
