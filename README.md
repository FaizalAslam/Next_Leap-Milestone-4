# SBI Mutual Fund FAQ Assistant

Local, facts-only FAQ assistant for the five SBI Mutual Fund schemes and the 25 public sources listed in `data/sources.csv`. Phases 1-4 provide the approved-source index, guarded query service, all seven wireframe UI states, and end-to-end browser workflows. The Section 6 implementation checklist passes its local audit; Phase 5 live factual QA and final release approval remain pending local OpenAI configuration.

## Requirements

- Python 3.12
- An OpenAI API key and an OpenAI model selection before the generation phase
- The configured OpenAI model must support the Responses API and strict JSON Schema output
- Network access for explicit source ingestion, first model download, and the Playwright Chromium install

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `.env` locally. Do not commit `.env` or `chroma_db/`.

Install the matching Chromium browser once for JavaScript-rendered source fallback:

```powershell
python -m playwright install chromium
```

## Phase 1 ingestion

Inspect and preserve the enabled, approved corpus:

```powershell
python -m src.ingest --inspect-only
```

The command prints a run ID and stores raw responses, normalized content, and the source audit manifest under `data/`. Review `Docs/chunking_strategy.md`, then build from that exact snapshot without refetching:

```powershell
python -m src.ingest --build-from <run-id>
```

For a later source refresh and full rebuild, run `python -m src.ingest`. A new Chroma collection becomes active only after all eligible sources, chunks, metadata, and 384-dimensional vectors pass validation. Previous active collections are retained.

## Service check

```powershell
python -m flask --app src.app run --debug --host 127.0.0.1
```

The app serves the seven-state Assistant UI at `http://127.0.0.1:5000/` and reports persisted-index status at `http://127.0.0.1:5000/api/health`. `POST /api/ask` is available for permitted factual questions. The browser renders detected PII locally with masked values and does not submit that question; the API independently applies the same guardrail before query embedding. Advice, performance, and private-information requests are routed before generation. Permitted factual requests use the existing local embedding model, ChromaDB collection, and configured OpenAI Responses model. Set `OPENAI_API_KEY` and `OPENAI_MODEL` in `.env`; responses use retrieved source metadata and validate evidence before returning facts. The Assistant UI submits safe questions, keeps the conversation and retry state in page memory, and clears them on Reset. Feedback is local to the current page and is not transmitted or persisted. Optional self-service links may be configured with `SBI_INVESTOR_PORTAL_URL` and `GROWW_DASHBOARD_URL`; only HTTPS destinations are rendered, and unset or invalid settings remain non-clickable placeholders.

## Phase 5 acceptance

Run the automated acceptance suite with:

```powershell
python -m pytest -q
```

The current baseline is 102 passing tests. The active persistent index is run `20261002T112904Z` with 25 sources and 107 chunks. See `Docs/acceptance_matrix.md` for coverage and outstanding gates, and `Docs/sample_qa.md` for the live-answer capture checklist. Live factual examples must be recorded from actual `/api/ask` responses after local OpenAI configuration; fixture values are not product facts.

The app does not run a scheduled corpus refresh. Refresh is explicit through `python -m src.ingest`; the UI reports source retrieval dates rather than claiming daily synchronization. Browser conversation data is held in page memory. PII checks prevent recognized sensitive patterns from being submitted, but safe questions and selected source excerpts are sent to the configured OpenAI model for factual generation. `store=False` is set for Responses API calls; this is not a blanket privacy, security, or provider-retention guarantee.

The Section 6 checklist audit is recorded in `Docs/acceptance_matrix.md` and the implementation blueprint. Its UI review preserves the supplied screen hierarchy while replacing unverified wireframe claims and unsupported citations with evidence-based copy. This local checklist result does not mean live model answers have passed Phase 5 QA.

## Product references

- `Docs/SBI_Mutual_Fund_FAQ_Assistant_Implementation_Plan.md` is the phased implementation specification.
- `Docs/SBI_Mutual_Fund_FAQ_Assistant_PRD_v1.0.docx` defines product and RAG requirements.
- `Docs/SBI_Mutual_Fund_Product_Brief_Wireframe_Aligned_v2.docx` defines the source inventory and ingestion workflow.
- `Docs/wireframes/` contains the supplied screen references and design system.

## Architecture

Preserve the PRD pipeline: explicit source ingestion, section-aware chunks, local `sentence-transformers/all-MiniLM-L6-v2` embeddings, persistent ChromaDB, scheme-aware top-K retrieval, OpenAI generation grounded only in retrieved context, output validation, and response-state rendering. Normal application startup must reuse the persisted ChromaDB collection.
