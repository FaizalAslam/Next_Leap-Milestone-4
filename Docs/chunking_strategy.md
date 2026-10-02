# Corpus Inspection and Chunking Strategy

## Inspection Snapshot

The saved source run `20261002T112904Z` contains all 25 enabled and approved records. It includes five Groww SBI scheme pages, category/education pages, public FAQ/help pages, three SBI Mutual Fund pages, and the approved tax reckoner PDF. This expansion rebuilds from those preserved raw snapshots; it does not add or refetch source URLs.

The scheme HTML snapshots include visible tables for return periods, category averages/ranks, top holdings, and similar funds. Groww also includes FAQPage JSON-LD with formatted AUM/NAV values and page-stated dates. Extraction re-reads the saved HTML, keeps public FAQ questions and answers, and skips account/login, KYC, redemption, and suitability-oriented FAQ procedures. Structured source facts are not derived from arbitrary JSON. The tax reckoner remains page-separated PDF text.

## Content Scope

- Index meaningful public page content from all 25 approved sources. Keep page headings, paragraph/list boundaries, FAQ question/answer labels, and complete table rows with column labels repeated on each data row.
- Scheme pages may include public AUM, NAV, historical return periods, category averages and rankings, similar-fund comparisons, scheme holdings, scheme facts, and definitions. Use the source-rendered FAQ value/date where available; do not recompute or round a conflicting display value from a raw numeric field.
- Historical returns, rankings, peer comparisons, NAV, AUM, and public scheme holdings are answerable only as sourced historical/public facts. They are never predictions or recommendations. Advice, suitability, forecasts, and a user's own folio/account/balance/portfolio remain blocked before retrieval or generation.
- General pages keep an empty scheme value in Chroma metadata. A query requiring multiple sources remains unsupported under the single-source citation contract.
- Remove navigation, ads, consent UI, site boilerplate, private identifiers, and source-specific disclaimers that are not factual guidance. Do not treat public scheme holdings as an investor's personal holdings.
- Source 22 remains the sole explicitly user-approved Groww blog exception. Do not add URLs or fetch linked spreadsheets as independent corpus sources.

Every enabled source must produce usable, permitted public content and appear in the source accounting. Missing or unusable sources fail the candidate build; they are not silently omitted.

## Chunk Boundaries

- Use `sentence-transformers/all-MiniLM-L6-v2`'s actual tokenizer and configured maximum sequence length. Pack heading-prefixed text to a target of 220 subword tokens, including heading context, and assert final encoded length before embedding.
- Keep each chunk within one source, scheme, and inspected section/page. Never overlap across those boundaries.
- Prefer paragraph, list-item, FAQ, and table-row boundaries. Table data lines repeat labels (for example, `Fund returns: +8.0%`) so a value remains meaningful when retrieved without the original header row. Never split an oversized table row or FAQ answer; fail with the source/section instead.
- Split oversized prose at sentence boundaries. For sections spanning multiple chunks, carry a 30-token overlap within that same section. Do not add overlap to short sections.
- Generate stable document IDs from source ID and URL, and stable chunk IDs from document ID, section/page, position, and normalized chunk content. Record all final chunk text and complete metadata in `chunks_inspection.txt`.

## Rebuild and Activation

Run `python -m src.ingest --build-from 20261002T112904Z` to re-extract the local preserved snapshots without network fetches. The application does not fetch or embed during normal startup. Build and validate the candidate collection, vector dimensions, metadata, source accounting, and retrieval fixtures before activating its manifest; the previous active collection remains active if candidate construction fails.
