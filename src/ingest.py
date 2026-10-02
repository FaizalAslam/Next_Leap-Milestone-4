"""Fetch approved public sources and stage normalized content for indexing."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sys
import time
import unicodedata
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "data" / "sources.csv"
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
APPROVED_STATUSES = {"approved_listed", "user_approved_exception"}
EXCEPTION_SOURCE_ID = "source_22"
EXCEPTION_URL = "https://groww.in/blog/how-to-get-capital-gains-statement-for-mutual-fund-investments"
MIN_CONTENT_CHARACTERS = 120
MIN_CONTENT_WORDS = 18
USER_AGENT = "SBI-Mutual-Fund-FAQ-Assistant/1.0 (public-source ingestion)"
LOGGER = logging.getLogger("sbi_faq.ingest")


class SourceIngestionError(RuntimeError):
    """Raised when an approved source cannot be fetched or extracted safely."""


@dataclass(frozen=True)
class ContentSection:
    title: str
    text: str
    page: int | None = None


@dataclass(frozen=True)
class FetchResult:
    source: dict[str, str]
    sections: list[ContentSection]
    retrieved_at: str
    final_url: str
    content_type: str
    content_sha256: str
    extraction_method: str
    raw_files: list[str]

    @property
    def extracted_text(self) -> str:
        return "\n\n".join(section.text for section in self.sections).strip()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def new_run_id() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value.replace("\xa0", " "))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _text(tag: Tag) -> str:
    return _normalize_text(tag.get_text(" ", strip=True))


def _remove_boilerplate(soup: BeautifulSoup) -> None:
    for node in soup.select(
        "script, style, noscript, nav, footer, aside, form, button, svg, canvas, "
        "[aria-hidden='true'], [hidden], [role='navigation'], [role='contentinfo']"
    ):
        node.decompose()

    for node in soup.select(
        "[class*='cookie' i], [id*='cookie' i], [class*='consent' i], "
        "[id*='consent' i], [class*='modal' i], [class*='advert' i], "
        "[id*='advert' i], [class*='breadcrumb' i]"
    ):
        node.decompose()


def _content_container(soup: BeautifulSoup) -> Tag | BeautifulSoup:
    for selector in ("article", "main", "[role='main']"):
        candidates = [node for node in soup.select(selector) if isinstance(node, Tag)]
        if candidates:
            return max(candidates, key=lambda node: len(_text(node)))
    return soup.body or soup


def _html_sections(
    html: str,
    default_title: str,
    source: dict[str, str] | None = None,
) -> tuple[list[ContentSection], dict[str, int]]:
    soup = BeautifulSoup(html, "html.parser")
    _remove_boilerplate(soup)
    container = None
    if source and source.get("source") == "Groww" and source.get("source_type") == "help":
        container = soup.select_one(".qap761ScrollableContent") or soup.select_one(".qap761Wrapper")
    container = container or _content_container(soup)
    block_tags = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr", "blockquote", "dt", "dd")
    elements = container.find_all(block_tags)

    heading_stack: list[tuple[int, str]] = []
    grouped: OrderedDict[str, list[str]] = OrderedDict()
    table_rows = 0
    paragraph_count = 0
    heading_count = 0
    consumed_definition_descriptions: set[int] = set()

    for element in elements:
        if not isinstance(element, Tag):
            continue
        if any(parent.name in {"tr", "li"} for parent in element.parents if isinstance(parent, Tag)):
            if element.name in {"p", "dt", "dd"}:
                continue
        if element.name == "dd" and id(element) in consumed_definition_descriptions:
            continue

        block = ""
        if re.fullmatch(r"h[1-6]", element.name or ""):
            title = _text(element)
            if not title:
                continue
            level = int(element.name[1])
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            heading_count += 1
            continue
        if element.name == "tr":
            cells = [_text(cell) for cell in element.find_all(["th", "td"], recursive=False)]
            cells = [cell for cell in cells if cell]
            if cells:
                table = element.find_parent("table")
                header_row = table.find("tr") if isinstance(table, Tag) else None
                headers = (
                    [_text(cell) for cell in header_row.find_all(["th", "td"], recursive=False)]
                    if isinstance(header_row, Tag) and header_row is not element
                    else []
                )
                if headers and len(headers) == len(cells) and not element.find("th", recursive=False):
                    block = " | ".join(f"{label}: {value}" for label, value in zip(headers, cells))
                else:
                    block = " | ".join(cells)
                table_rows += 1
        elif element.name == "dt":
            label = _text(element)
            following = element.find_next_sibling("dd")
            value = _text(following) if isinstance(following, Tag) else ""
            if value:
                consumed_definition_descriptions.add(id(following))
                block = f"{label}: {value}" if label else value
            else:
                block = label
        elif element.name == "dd":
            block = _text(element)
        elif element.name == "li":
            block = f"- {_text(element)}"
        else:
            block = _text(element)
            if element.name in {"p", "blockquote"} and block:
                paragraph_count += 1

        if block:
            section_title = " > ".join(title for _, title in heading_stack) or default_title
            grouped.setdefault(section_title, []).append(block)

    sections = [
        ContentSection(title=title, text="\n".join(blocks))
        for title, blocks in grouped.items()
        if "\n".join(blocks).strip()
    ]
    if not sections:
        text = _normalize_text(container.get_text("\n", strip=True))
        if text:
            sections = [ContentSection(title=default_title, text=text)]

    structure = {
        "heading_count": heading_count,
        "paragraph_count": paragraph_count,
        "table_row_count": table_rows,
        "section_count": len(sections),
    }
    return sections, structure


def _public_faq_sections(html: str) -> list[ContentSection]:
    soup = BeautifulSoup(html, "html.parser")
    sections: list[ContentSection] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        kind = value.get("@type", [])
        types = {kind} if isinstance(kind, str) else set(kind) if isinstance(kind, list) else set()
        if "FAQPage" in types:
            entities = value.get("mainEntity", [])
            if not isinstance(entities, list):
                entities = [entities]
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                question = _normalize_text(str(entity.get("name", "")))
                answer = entity.get("acceptedAnswer", {})
                answer_text = answer.get("text", "") if isinstance(answer, dict) else ""
                answer_soup = BeautifulSoup(str(answer_text), "html.parser")
                text = _normalize_text(answer_soup.get_text(" ", strip=True))
                folded = f"{question} {text}".casefold()
                if not question or not text:
                    continue
                if re.search(
                    r"\b(log\s*in|log\s*on|sign\s*in|kyc|redeem|redemption|cancel.{0,20}sip|"
                    r"sell your|account balance|risk tolerance|investment objective)\b",
                    folded,
                ):
                    continue
                sections.append(
                    ContentSection(title=f"FAQ > {question}", text=f"Question: {question}\nAnswer: {text}")
                )
            return
        for key, child in value.items():
            if key in {"@graph", "mainEntity"}:
                visit(child)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (json.JSONDecodeError, TypeError):
            continue
    return sections


def _extract_html_sections(
    html: str, source: dict[str, str]
) -> tuple[list[ContentSection], dict[str, int]]:
    sections, structure = _html_sections(html, source.get("title", source["source_id"]), source)
    faq_sections = _public_faq_sections(html)
    if faq_sections:
        sections.extend(faq_sections)
        structure["faq_count"] = len(faq_sections)
    scheme_facts = _scheme_fact_section(html, source)
    if scheme_facts:
        sections.insert(0, scheme_facts)
        structure["scheme_fact_count"] = len(scheme_facts.text.splitlines()) - 1
    ter_access = _ter_access_section(html, source)
    if ter_access:
        sections.append(ter_access)
        structure["ter_link_count"] = len(ter_access.text.splitlines())
    structure["section_count"] = len(sections)
    return sections, structure


def _ter_access_section(html: str, source: dict[str, str]) -> ContentSection | None:
    if source.get("source_id") != "source_24":
        return None
    soup = BeautifulSoup(html, "html.parser")
    links: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        path = urlparse(urljoin(source["url"], anchor["href"])).path.casefold()
        if path.endswith("/current-year-ter.xlsx"):
            links["Current-year TER spreadsheet"] = urljoin(source["url"], anchor["href"])
        elif path.endswith("/historical-ter.xlsx"):
            links["Historical TER spreadsheet"] = urljoin(source["url"], anchor["href"])
    expected_host = urlparse(source["url"]).netloc
    if not links or any(urlparse(link).netloc != expected_host for link in links.values()):
        return None
    text = "\n".join(f"{label}: {url}" for label, url in links.items())
    return ContentSection(title="Approved TER access", text=text)


def _scheme_fact_section(html: str, source: dict[str, str]) -> ContentSection | None:
    if source.get("source_type") != "scheme_page":
        return None

    soup = BeautifulSoup(html, "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")
    if not isinstance(next_data, Tag):
        return None
    try:
        payload = json.loads(next_data.string or next_data.get_text())
        details = payload["props"]["pageProps"]["mfServerSideData"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(details, dict):
        return None

    def normalize_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.casefold())

    expected_scheme = source.get("scheme", "").strip()
    actual_scheme = str(details.get("scheme_name", "")).strip()
    if not expected_scheme or normalize_name(expected_scheme) != normalize_name(actual_scheme):
        return None

    allowed = source.get("allowed_uses", "").casefold()
    facts: list[str] = [f"Scheme name: {expected_scheme}"]

    def add(label: str, key: str, allowed_phrase: str, formatter: Callable[[Any], str] = str) -> None:
        value = details.get(key)
        if allowed_phrase in allowed and value not in (None, "", {}):
            facts.append(f"{label}: {formatter(value)}")

    def amount(value: Any) -> str:
        try:
            number = float(value)
            return f"INR {number:,.0f}" if number.is_integer() else f"INR {number:,.2f}"
        except (TypeError, ValueError):
            return str(value)

    def percent(value: Any) -> str:
        text = str(value).strip()
        return text if text.endswith("%") else f"{text}%"

    if "category" in allowed:
        category = str(details.get("sub_category") or details.get("category") or "").strip()
        parent = str(details.get("category") or "").strip()
        if category:
            value = f"{category} ({parent})" if parent and parent.casefold() != category.casefold() else category
            facts.append(f"Category: {value}")
    add("Minimum SIP investment", "min_sip_investment", "minimum sip", amount)
    add("Minimum investment", "min_investment_amount", "minimum investment", amount)
    add("Expense ratio", "expense_ratio", "expense information", percent)
    add("Exit load", "exit_load", "exit load")
    add("Risk level", "nfo_risk", "risk")
    benchmark = details.get("benchmark_name") or details.get("benchmark")
    if "benchmark" in allowed and benchmark:
        facts.append(f"Benchmark: {benchmark}")
    if "lock-in" in allowed or "lock in" in allowed:
        lock_in = details.get("lock_in")
        if isinstance(lock_in, dict):
            parts = [
                f"{lock_in.get('years')} year(s)" for _ in [0]
                if lock_in.get("years") not in (None, 0)
            ]
            parts.extend(
                f"{lock_in.get(key)} {unit}"
                for key, unit in (("months", "month(s)"), ("days", "day(s)"))
                if lock_in.get(key) not in (None, 0)
            )
            if parts:
                facts.append(f"Lock-in: {', '.join(parts)}")

    if len(facts) <= 1:
        return None
    return ContentSection(title="Approved scheme facts", text="\n".join(facts))


def _is_usable(sections: Iterable[ContentSection]) -> bool:
    text = "\n".join(section.text for section in sections).strip()
    words = re.findall(r"\b[\w'-]+\b", text)
    if len(text) < MIN_CONTENT_CHARACTERS or len(words) < MIN_CONTENT_WORDS:
        return False
    normalized = {word.casefold() for word in words}
    return len(normalized) >= 10


def _is_pdf(url: str, content_type: str, content: bytes) -> bool:
    return "application/pdf" in content_type.casefold() or url.casefold().split("?", 1)[0].endswith(".pdf") or content[:1024].lstrip().startswith(b"%PDF-")


def _pdf_sections(content: bytes) -> list[ContentSection]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            if reader.decrypt("") == 0:
                raise SourceIngestionError("Encrypted PDF cannot be opened without credentials")
        sections = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = _normalize_text(page.extract_text() or "")
            if page_text:
                sections.append(ContentSection(title=f"Page {page_number}", text=page_text, page=page_number))
    except SourceIngestionError:
        raise
    except Exception as exc:
        raise SourceIngestionError(f"PDF extraction failed: {exc}") from exc

    if not _is_usable(sections):
        raise SourceIngestionError("PDF yielded no usable text; OCR is not configured")
    return sections


def _save_raw(raw_dir: Path, source_id: str, run_id: str, suffix: str, content: bytes) -> str:
    destination = raw_dir / run_id / f"{source_id}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return str(destination.relative_to(ROOT)).replace("\\", "/")


def _browser_fetch(url: str) -> tuple[bytes, str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SourceIngestionError(
            "Static extraction was incomplete and Playwright is unavailable; install requirements and Chromium"
        ) from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(1000)
            if response is not None and response.status >= 400:
                raise SourceIngestionError(f"Browser fallback returned HTTP {response.status}")
            html = page.content().encode("utf-8")
            final_url = page.url
            browser.close()
            return html, final_url, "text/html"
    except SourceIngestionError:
        raise
    except Exception as exc:
        raise SourceIngestionError(f"Browser fallback failed: {exc}") from exc


def fetch_source(
    source: dict[str, str],
    run_id: str,
    *,
    session: requests.Session | None = None,
    browser_fetch: Callable[[str], tuple[bytes, str, str]] = _browser_fetch,
    raw_dir: Path = RAW_DIR,
) -> tuple[FetchResult, dict[str, int]]:
    source_id = source["source_id"]
    url = source["url"]
    owns_session = session is None
    client = session or requests.Session()
    client.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8"})
    raw_files: list[str] = []
    retrieved_at = _utc_now().date().isoformat()

    try:
        try:
            response = client.get(url, timeout=(10, 35), allow_redirects=True)
        except requests.RequestException as exc:
            raise SourceIngestionError(f"HTTP fetch failed: {exc}") from exc

        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
        if response.status_code in {401, 403, 429, 500, 502, 503, 504}:
            static_error = SourceIngestionError(f"HTTP returned {response.status_code}; trying browser fallback")
            response_body = response.content
        else:
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                raise SourceIngestionError(f"HTTP returned {response.status_code}: {exc}") from exc
            response_body = response.content
            static_error = None

        final_url = response.url
        response_hash = hashlib.sha256(response_body).hexdigest()
        if _is_pdf(final_url, content_type, response_body):
            raw_files.append(_save_raw(raw_dir, source_id, run_id, ".pdf", response_body))
            sections = _pdf_sections(response_body)
            structure = {"page_count": len(sections), "section_count": len(sections)}
            method = "pypdf"
        else:
            response.encoding = response.apparent_encoding or "utf-8"
            html = response.text
            sections, structure = _extract_html_sections(html, source)
            usable = static_error is None and _is_usable(sections)
            if usable:
                raw_files.append(_save_raw(raw_dir, source_id, run_id, ".html", response_body))
                method = "requests+beautifulsoup"
            else:
                raw_files.append(_save_raw(raw_dir, source_id, run_id, ".http.html", response_body))
                rendered_html, rendered_url, rendered_type = browser_fetch(url)
                rendered_text = rendered_html.decode("utf-8", errors="replace")
                sections, structure = _extract_html_sections(rendered_text, source)
                if not _is_usable(sections):
                    raise SourceIngestionError("Static and browser extraction contained no usable page-specific text")
                raw_files.append(_save_raw(raw_dir, source_id, run_id, ".rendered.html", rendered_html))
                final_url = rendered_url
                content_type = rendered_type
                response_hash = hashlib.sha256(rendered_html).hexdigest()
                method = "playwright+beautifulsoup"

        result = FetchResult(
            source=source,
            sections=sections,
            retrieved_at=retrieved_at,
            final_url=final_url,
            content_type=content_type,
            content_sha256=response_hash,
            extraction_method=method,
            raw_files=raw_files,
        )
        return result, structure
    finally:
        if owns_session:
            client.close()


def load_sources(path: Path = SOURCE_MANIFEST) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        required = {
            "source_id", "title", "url", "source_type", "source", "amc", "scheme",
            "category", "allowed_uses", "approval_status", "enabled", "retrieved_at",
        }
        if not required.issubset(reader.fieldnames or []):
            raise SourceIngestionError(f"Source manifest missing columns: {sorted(required - set(reader.fieldnames or []))}")
        records = list(reader)

    ids = [record["source_id"].strip() for record in records]
    if not records or len(ids) != len(set(ids)):
        raise SourceIngestionError("Source manifest is empty or contains duplicate source IDs")

    exceptions = [row for row in records if row["approval_status"].strip() == "user_approved_exception"]
    if len(exceptions) > 1 or any(
        row["source_id"].strip() != EXCEPTION_SOURCE_ID or row["url"].strip() != EXCEPTION_URL
        for row in exceptions
    ):
        raise SourceIngestionError("Only the approved source_22 Groww blog exception may be enabled")

    for record in records:
        record["source_id"] = record["source_id"].strip()
        record["url"] = record["url"].strip()
        record["enabled"] = record["enabled"].strip().casefold()
        if record["enabled"] not in {"true", "false"}:
            raise SourceIngestionError(f"Invalid enabled flag for {record['source_id']}")
        if not record["url"].startswith(("https://", "http://")):
            raise SourceIngestionError(f"Non-public URL scheme for {record['source_id']}")
        if record["source_id"] == EXCEPTION_SOURCE_ID and record["approval_status"].strip() != "user_approved_exception":
            raise SourceIngestionError("source_22 must retain its explicit user-approved exception status")

    return records


def eligible_sources(records: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return [
        record for record in records
        if record["enabled"] == "true" and record["approval_status"].strip() in APPROVED_STATUSES
    ]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_corpus(
    sources: list[dict[str, str]],
    run_id: str,
    *,
    sleep_seconds: float = 0.35,
    browser_fetch: Callable[[str], tuple[bytes, str, str]] = _browser_fetch,
) -> tuple[list[FetchResult], list[dict[str, str]]]:
    results: list[FetchResult] = []
    failures: list[dict[str, str]] = []
    with requests.Session() as session:
        for index, source in enumerate(sources):
            if index:
                time.sleep(sleep_seconds)
            try:
                result, structure = fetch_source(source, run_id, session=session, browser_fetch=browser_fetch)
                results.append(result)
                processed_file = PROCESSED_DIR / run_id / f"{source['source_id']}.json"
                _write_json(
                    processed_file,
                    {
                        "source": source,
                        "retrieved_at": result.retrieved_at,
                        "final_url": result.final_url,
                        "content_type": result.content_type,
                        "content_sha256": result.content_sha256,
                        "extraction_method": result.extraction_method,
                        "raw_files": result.raw_files,
                        "structure": structure,
                        "sections": [asdict(section) for section in result.sections],
                    },
                )
                LOGGER.info(
                    "%s: %s, %d sections, %d characters",
                    source["source_id"], result.extraction_method, len(result.sections), len(result.extracted_text),
                )
            except Exception as exc:
                failures.append({"source_id": source["source_id"], "url": source["url"], "error": str(exc)})
                LOGGER.error("%s: source ingestion failed: %s", source["source_id"], exc)

    manifest = {
        "run_id": run_id,
        "created_at": _utc_now().isoformat(),
        "eligible_count": len(sources),
        "succeeded_count": len(results),
        "failed_count": len(failures),
        "results": [
            {
                "source_id": result.source["source_id"],
                "status": "extracted",
                "retrieved_at": result.retrieved_at,
                "final_url": result.final_url,
                "content_type": result.content_type,
                "content_sha256": result.content_sha256,
                "extraction_method": result.extraction_method,
                "raw_files": result.raw_files,
            }
            for result in results
        ],
        "failures": failures,
    }
    _write_json(PROCESSED_DIR / run_id / "ingestion_manifest.json", manifest)
    return results, failures


def load_staged_run(run_id: str) -> tuple[list[FetchResult], list[dict[str, Any]]]:
    run_dir = PROCESSED_DIR / run_id
    manifest_path = run_dir / "ingestion_manifest.json"
    if not manifest_path.is_file():
        raise SourceIngestionError(f"No completed source inspection found for run {run_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("failed_count") != 0:
        raise SourceIngestionError(f"Inspection run {run_id} contains failed sources")

    source_by_id = {row["source_id"]: row for row in load_sources()}
    results = []
    structures = []
    for entry in manifest["results"]:
        source_path = run_dir / f"{entry['source_id']}.json"
        record = json.loads(source_path.read_text(encoding="utf-8"))
        source = source_by_id.get(entry["source_id"], record["source"])
        sections = [ContentSection(**section) for section in record["sections"]]
        structure = record.get("structure", {})
        html_path = next(
            (
                ROOT / raw_file
                for raw_file in reversed(record.get("raw_files", []))
                if raw_file.casefold().endswith((".html", ".http.html", ".rendered.html"))
            ),
            None,
        )
        if html_path and html_path.is_file():
            raw_html = html_path.read_text(encoding="utf-8", errors="replace")
            sections, structure = _extract_html_sections(raw_html, source)
        else:
            pdf_path = next(
                (ROOT / raw_file for raw_file in record.get("raw_files", []) if raw_file.casefold().endswith(".pdf")),
                None,
            )
            if pdf_path is None or not pdf_path.is_file():
                raise SourceIngestionError(f"Saved source {entry['source_id']} has no raw snapshot to re-extract")
            sections = _pdf_sections(pdf_path.read_bytes())
            structure = {"page_count": len(sections), "section_count": len(sections)}
        if not _is_usable(sections):
            raise SourceIngestionError(f"Saved source {entry['source_id']} has no usable normalized content")
        record["source"] = source
        record["sections"] = [asdict(section) for section in sections]
        record["structure"] = structure
        record["normalization_version"] = 3
        _write_json(source_path, record)
        results.append(
            FetchResult(
                source=source,
                sections=sections,
                retrieved_at=record["retrieved_at"],
                final_url=record["final_url"],
                content_type=record["content_type"],
                content_sha256=record["content_sha256"],
                extraction_method=record["extraction_method"],
                raw_files=record["raw_files"],
            )
        )
        structures.append({"source_id": source["source_id"], **record["structure"]})
    return results, structures


def _print_inspection(
    results: list[FetchResult],
    structures: list[dict[str, Any]],
    failures: list[dict[str, str]],
    *,
    detail: bool = False,
) -> None:
    def safe_print(value: str = "") -> None:
        print(value.encode("ascii", errors="backslashreplace").decode("ascii"))

    structure_by_id = {row["source_id"]: row for row in structures}
    for result in results:
        structure = structure_by_id.get(result.source["source_id"], {})
        safe_print(
            f"{result.source['source_id']} | {result.source['title']} | {result.extraction_method} | "
            f"{len(result.sections)} sections | {len(result.extracted_text)} chars | "
            f"{result.final_url} | {structure}"
        )
        if detail:
            for section in result.sections:
                excerpt = re.sub(r"\s+", " ", section.text)[:150]
                safe_print(f"  - {section.title}: {excerpt}")
    if failures:
        safe_print(f"\nFailed sources: {len(failures)}")
        for failure in failures:
            safe_print(f"  - {failure['source_id']}: {failure['error']}")


def _validate_candidate_retrieval(chunks: list[Any], embeddings: Any, embedder: Any) -> None:
    import chromadb

    from src.retrieve import Retriever, SchemeMetadata

    client = chromadb.EphemeralClient()
    collection = client.create_collection(
        name=f"candidate_{new_run_id().lower()}", metadata={"hnsw:space": "cosine"}
    )
    try:
        collection.add(
            ids=[chunk.id for chunk in chunks],
            embeddings=embeddings.tolist(),
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.metadata for chunk in chunks],
        )
        schemes = SchemeMetadata.from_collection(collection)
        retriever = Retriever(collection, embedder)
        for scheme in schemes.names:
            contexts = retriever.retrieve(f"What is the AUM of {scheme}?", scheme)
            if not any(
                chunk.metadata.get("scheme") == scheme
                and "AUM" in chunk.text
                and re.search(r"₹|INR", chunk.text)
                for chunk in contexts
            ):
                raise SourceIngestionError(f"Candidate retrieval did not return the page AUM for {scheme}")

        fixtures = (
            ("What is the size of SBI Large Cap Fund?", "SBI Large Cap Direct Plan Growth", "AUM"),
            ("What are the historical returns of SBI Large Cap Direct Plan Growth?", "SBI Large Cap Direct Plan Growth", "returns"),
            ("What was the five-year category ranking for SBI Large Cap Direct Plan Growth?", "SBI Large Cap Direct Plan Growth", "rank"),
            ("What are the top holdings of SBI Large Cap Direct Plan Growth?", "SBI Large Cap Direct Plan Growth", "holdings"),
            ("Which similar funds are compared with SBI Large Cap Direct Plan Growth?", "SBI Large Cap Direct Plan Growth", "similar funds"),
        )
        for question, scheme, expected in fixtures:
            contexts = retriever.retrieve(question, scheme)
            if not any(expected in chunk.text.casefold() for chunk in contexts):
                raise SourceIngestionError(f"Candidate retrieval fixture was not supported: {expected}")
    finally:
        client.delete_collection(collection.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect approved corpus sources or build the persistent index.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inspect-only", action="store_true", help="Fetch and save source structure without building an index.")
    mode.add_argument("--build-from", metavar="RUN_ID", help="Build from a successful saved inspection run without refetching.")
    parser.add_argument("--sleep", type=float, default=0.35, help="Delay between sequential requests in seconds.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        if args.build_from:
            results, structures = load_staged_run(args.build_from)
            failures: list[dict[str, str]] = []
            run_id = args.build_from
            expected_ids = {source["source_id"] for source in eligible_sources(load_sources())}
        else:
            records = load_sources()
            sources = eligible_sources(records)
            expected_ids = {source["source_id"] for source in sources}
            if len(records) != 25 or len(sources) != 25:
                raise SourceIngestionError(
                    f"Expected all 25 manifest records to be enabled and approved; found {len(records)} records and {len(sources)} eligible"
                )
            run_id = new_run_id()
            results, failures = fetch_corpus(sources, run_id, sleep_seconds=args.sleep)
            structures = []
            for result in results:
                record = json.loads((PROCESSED_DIR / run_id / f"{result.source['source_id']}.json").read_text(encoding="utf-8"))
                structures.append({"source_id": result.source["source_id"], **record["structure"]})

        _print_inspection(results, structures, failures, detail=args.inspect_only)
        if failures:
            return 1
        if args.inspect_only:
            print(f"\nInspection run saved: {run_id}")
            return 0
        actual_ids = {result.source["source_id"] for result in results}
        if actual_ids != expected_ids:
            raise SourceIngestionError(
                f"Source coverage mismatch; missing={sorted(expected_ids - actual_ids)}, "
                f"unexpected={sorted(actual_ids - expected_ids)}"
            )

        from src.chunk import build_chunks
        from src.embed import LocalEmbedder
        from src.vector_store import activate_index

        embedder = LocalEmbedder(local_files_only=True)
        chunks = build_chunks(results, embedder.tokenizer)
        texts = [chunk.text for chunk in chunks]
        embeddings = embedder.encode(texts)
        _validate_candidate_retrieval(chunks, embeddings, embedder)
        activate_index(
            chunks,
            embeddings,
            run_id=run_id,
            embedding_model=embedder.model_name,
            expected_source_ids=expected_ids,
        )
        print(f"\nIndexed {len(chunks)} chunks from {len(results)} sources (run {run_id}).")
        return 0
    except Exception as exc:
        LOGGER.exception("Ingestion stopped: %s", exc)
        print(f"Ingestion stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
