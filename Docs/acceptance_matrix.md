# Phase 5 Acceptance Matrix

Status: Section 6 checklist audit passed; Phase 5 live factual QA and final release approval remain pending local OpenAI configuration.

## Evidence

| Area | Acceptance evidence | Status |
| --- | --- | --- |
| Automated tests | `python -m pytest -q` | PASS: 102 tests |
| Persistent index | Reopened `sbi_faq_20261002t112904z_a1e7b2dc`; collection count is 107, manifest source count is 25, and collection/manifest/app health agree on run `20261002T112904Z` | PASS |
| Embedding consistency | Active manifest and Chroma metadata both identify `sentence-transformers/all-MiniLM-L6-v2`; manifest dimension is 384 and collection distance metric is cosine. Ingestion and query code use the same model identifier. | PASS: persisted metadata and code review |
| UI states and responsive layout | Side-by-side review of all seven states at their supplied canvas dimensions; Playwright asserts each layout-bearing region and checks mobile overflow at 390 x 844 | PASS: layout hierarchy reviewed; text/source differences are limited to safety and evidence requirements; no pixel-diff threshold is defined |
| Browser workflows | Mocked API coverage for safe submit, loading, response states, multiple turns, navigation, reset, retry, copy, feedback, and populated prompts | PASS |
| Browser PII | PAN, Aadhaar, account number, OTP, email, and phone fixtures render masked locally and make no `/api/ask` request | PASS |
| Server guardrails | PII, personal-information, advice, and performance paths are covered before retrieval/generation; benchmark identity remains factual | PASS: unit/service tests |
| Provenance and grounding | Factual responses require one metadata-derived source, a valid retrieval date, and grounded content; unsupported/error states do not attach unrelated sources | PASS: unit/service and renderer tests |
| Logs and browser persistence | Static review found no app use of `localStorage` or `sessionStorage`; conversation state is page-memory-only and Reset clears it. Existing log review was limited to checking for serialized question/request fields and common identifier patterns. | PASS: code/test review; not a general privacy guarantee |
| Model request | Generation constructs input from the safe question and selected excerpts and sets Responses API `store=False` | PASS: code review; no live provider request was available to inspect |
| Live factual answers | 5-10 questions across all five schemes, with answer/source/date verification | BLOCKED: `.env`, `OPENAI_API_KEY`, and `OPENAI_MODEL` are not configured in this workspace |
| Release claims | No daily-refresh, SEBI-source, or blanket privacy claim is enabled by this implementation | PASS: README and UI copy review |

## Section 6 Checklist

Result: 9/9 checklist items pass based on this matrix, the automated tests, and the local index review. This verifies the current implementation and does not close Phase 5's live factual-answer gate.

## Live QA Set

Run the prompts in `Docs/sample_qa.md` through the configured app. For each factual response, verify that the response is supported by the returned evidence, identifies the intended scheme where applicable, has exactly one source link, and shows the exact retrieval date from response metadata. Record unsupported results as gaps; do not replace them with outside facts or wireframe examples.

## Release Gate

Do not mark Phase 5 complete until live factual verification is recorded, the candidate factual set has at least five supported examples covering all five schemes and the required question categories, source/date checks pass, and no P0 acceptance item fails. Any failed live answer or unavailable evidence remains a release blocker.
