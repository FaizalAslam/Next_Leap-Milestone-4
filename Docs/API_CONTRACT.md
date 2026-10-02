# Assistant API Contract

This contract is established in Phase 0. The question endpoint and browser integration use the contract below.

## Request

`POST /api/ask`

```json
{
  "question": "What is the expense ratio of SBI Flexicap Fund?"
}
```

The browser runs the PII guard before sending. If a PII-bearing question is detected, the browser replaces the sensitive value with `[REDACTED]`, renders a local warning, and does not post the question. The server repeats PII detection for direct API callers and refuses the request before embedding or retrieval. Neither layer logs or echoes question text.

`question` must be a non-empty string of at most 1,000 characters and fit the local embedding model's input limit. Invalid JSON, invalid shape, overlong input, and server-detected PII return HTTP 400 (or 413 for a request exceeding the body limit) with `state: "error"` and `reason: "validation_failure"`; the response never includes the submitted question. Valid policy and content outcomes return HTTP 200. Retrieval or generation failures return HTTP 503 with `state: "error"` and the corresponding failure reason.

## Response

```json
{
  "state": "factual",
  "reason": "supported_fact",
  "narrative": "The expense ratio is ...",
  "scheme": "SBI Flexicap Fund Direct Growth",
  "category": "Flexi Cap",
  "facts": [
    {"label": "Expense Ratio (Direct)", "value": "..."}
  ],
  "source": {
    "label": "Groww",
    "url": "https://groww.in/mutual-funds/sbi-flexicap-fund-direct-growth",
    "source_type": "scheme_page",
    "retrieved_at": "2026-10-02"
  },
  "suggestions": ["What is the exit load?"]
}
```

The values above illustrate shape only; they are not a live answer or a claim that the source was fetched on that date.

`state` is one of `factual`, `refusal`, `unsupported`, or `error`. `reason` distinguishes supported facts, advice, performance, not-found, private-information, retrieval, generation, and validation outcomes. Loading is a browser state; the PII/privacy state is handled locally and is not a server response state.

For factual responses, `source` is required and singular, `retrieved_at` must be a valid date, and `narrative` must be no more than three sentences. Non-factual states may omit source metadata; they must not include unrelated sources. Error responses omit source metadata unless evidence was actually retrieved. The server never accepts source URLs or dates from generated model text.

Factual generation uses only the single-source retrieved context, the OpenAI model named by `OPENAI_MODEL`, and strict JSON Schema output through the Responses API with response storage disabled. Configure a model that supports this output mode. The server derives source metadata from ChromaDB; source labels, URLs, or dates supplied by the model are ignored/rejected. Advice, performance, private-information, and PII requests do not reach generation; advice fallback may include only scheme/category values from indexed metadata.

The API is local to the Flask application. It does not provide authentication, portfolio access, transaction actions, or persistent conversation storage. Configure `OPENAI_API_KEY` and `OPENAI_MODEL` in a local `.env`; never commit credentials.

## Browser workflow

The UI posts only a browser-approved question to this endpoint. Detected PII is masked and shown locally without a request. Conversation messages and retry questions exist only in the active page memory; Reset clears them. Prompt cards, topic chips, and suggestions populate the composer and require an explicit submit. Feedback is a page-local selection and is not sent to the server. The source/date shown in the UI come only from the API response metadata.

The optional `SBI_INVESTOR_PORTAL_URL` and `GROWW_DASHBOARD_URL` settings configure the two self-service destinations shown in privacy/help content. Leave them blank until the destinations are approved. The app rejects non-HTTPS or malformed values and otherwise keeps the wireframe's non-clickable placeholder.
