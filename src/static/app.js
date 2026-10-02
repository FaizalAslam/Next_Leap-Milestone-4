"use strict";

(function attachAssistantUI(global) {
  const app = document.getElementById("assistant-app");
  if (!app) return;

  const promptCards = [
    { icon: "description", question: "What is the expense ratio of SBI Flexicap Fund?" },
    { icon: "lock", question: "What is the lock-in period of SBI ELSS Tax Saver Fund?" },
    { icon: "download", question: "How do I download my capital-gains statement?" },
  ];
  const topics = [
    ["Expense Ratio", "Tell me about expense ratios of popular SBI funds"],
    ["Minimum SIP", "What is the minimum SIP amount for SBI Mutual Funds?"],
    ["Exit Load", "What is the exit load policy for SBI schemes?"],
    ["Riskometer", "How do I read a fund Riskometer?"],
    ["Benchmark", "Which benchmark index does SBI Bluechip Fund follow?"],
    ["ELSS Lock-in", "What are the ELSS lock-in rules?"],
    ["Statements", "Where can I download my annual account statements?"],
    ["Fund Category", "What fund categories are available in SBI Mutual Fund?"],
  ];
  const schemes = [
    ["SBI Large Cap Direct Plan Growth", "Large Cap"],
    ["SBI Flexicap Fund Direct Growth", "Flexi Cap"],
    ["SBI Small Cap Fund Direct Growth", "Small Cap"],
    ["SBI ELSS Tax Saver Fund Direct Growth", "ELSS"],
    ["SBI Balanced Advantage Fund Direct Growth", "Hybrid"],
  ];
  const transcript = [];
  let activeView = "assistant";
  let requestPending = false;
  let requestGeneration = 0;
  const investorPortalUrl = safeConfiguredUrl(app.dataset.investorUrl);
  const growwDashboardUrl = safeConfiguredUrl(app.dataset.growwUrl);
  const iconFallbacks = {
    description: "▤", lock: "▣", download: "↓", chevron_right: "›", info: "i",
    chat_bubble_outline: "□", arrow_forward: "→", account_balance: "▤", verified_user: "✓",
    link: "↗", open_in_new: "↗", person: "♙", smart_toy: "●", thumb_up: "+",
    thumb_down: "−", content_copy: "▣", warning: "!", person_search: "?", search_off: "?",
    shield_lock: "◇", refresh: "↻", shield_person: "◇", phone_iphone: "▯",
    sync_problem: "!", help: "?",
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  function safeConfiguredUrl(value) {
    if (typeof value !== "string" || !value || value.length > 2048 || /[\r\n\s]/.test(value)) return "";
    try {
      const url = new URL(value);
      return url.protocol === "https:" && url.hostname && !url.username && !url.password ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  function enableSymbolFallback() {
    document.documentElement.classList.add("symbols-fallback");
    document.querySelectorAll(".material-symbols-outlined[data-fallback]").forEach((element) => {
      element.textContent = element.dataset.fallback;
    });
  }

  function icon(name, extraClass = "") {
    const fallback = iconFallbacks[name] || "•";
    const content = document.documentElement.classList.contains("symbols-fallback") ? fallback : name;
    return `<span class="material-symbols-outlined ${extraClass}" data-fallback="${escapeHtml(fallback)}" aria-hidden="true">${escapeHtml(content)}</span>`;
  }

  function trustBanner(text) {
    return `<div class="trust-banner">${icon("verified_user")}<span>${escapeHtml(text)}</span></div>`;
  }

  function currentTime() {
    return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date());
  }

  function sourceMarkup(source) {
    if (!source || typeof source !== "object") return "";
    let url;
    try {
      url = new URL(source.url);
      if (url.protocol !== "https:" || !url.hostname || url.username || url.password) return "";
    } catch (_error) {
      return "";
    }
    const label = escapeHtml(source.label || "Source");
    const retrievedAt = escapeHtml(source.retrieved_at || "");
    return `<div class="source-row">
      <a class="source-link" href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">${icon("link")}<span>Source: ${label}</span>${icon("open_in_new")}</a>
      ${retrievedAt ? `<span class="source-date-row"><span class="source-date-dot" aria-hidden="true"></span><span class="source-date">Last updated from sources: ${retrievedAt}.</span></span>` : ""}
    </div>`;
  }

  function factsMarkup(facts, title = "Available scheme facts") {
    if (!Array.isArray(facts) || !facts.length) return "";
    const items = facts.map((fact) => `<div class="fact"><span class="fact-label">${escapeHtml(fact.label)}</span><span class="fact-value">${escapeHtml(fact.value)}</span></div>`).join("");
    return `<section class="facts-block" aria-label="${escapeHtml(title)}"><h3 class="facts-title">${escapeHtml(title)}</h3><div class="facts-grid">${items}</div></section>`;
  }

  function suggestionsMarkup(suggestions, heading = "Suggested questions") {
    if (!Array.isArray(suggestions) || !suggestions.length) return "";
    const chips = suggestions.filter((question) => typeof question === "string" && question.trim()).map((question) => `<button class="suggestion-chip" type="button" data-prompt="${escapeHtml(question)}">${escapeHtml(question)}</button>`).join("");
    if (!chips) return "";
    return `<section class="suggestion-section"><h3 class="section-label">${escapeHtml(heading)}</h3><div class="suggestion-chips">${chips}</div></section>`;
  }

  function userMessage(question, time = currentTime()) {
    return `<div class="user-message"><div class="user-content"><div class="user-bubble">${escapeHtml(question)}</div><time class="timestamp">${escapeHtml(time)}</time></div><div class="avatar" aria-hidden="true">${icon("person")}</div></div>`;
  }

  function assistantStart() {
    return `<div class="assistant-row"><div class="avatar" aria-hidden="true">${icon("smart_toy")}</div><div class="assistant-content">`;
  }

  function assistantEnd(question, time = currentTime(), showActions = true, response = {}) {
    const entryIndex = Number.isInteger(response.entry_index) ? response.entry_index : -1;
    const helpful = response.feedback === "helpful";
    const notHelpful = response.feedback === "not_helpful";
    const actions = showActions ? `<div class="feedback-actions" aria-label="Answer actions">
      <button class="icon-button" type="button" aria-label="Helpful" aria-pressed="${helpful}" data-feedback="helpful" data-entry-index="${entryIndex}" title="Mark this answer helpful">${icon("thumb_up")}</button>
      <button class="icon-button" type="button" aria-label="Not helpful" aria-pressed="${notHelpful}" data-feedback="not_helpful" data-entry-index="${entryIndex}" title="Mark this answer not helpful">${icon("thumb_down")}</button>
      <button class="icon-button" type="button" aria-label="Copy answer" data-copy-answer="${entryIndex}" title="Copy answer and source">${icon("content_copy")}</button>
    </div>` : "";
    return `<div class="message-meta"><time class="timestamp">${escapeHtml(time)}</time>${actions}</div></div></div>`;
  }

  function composer(note = "Factual scheme information from the available sources", disabled = false) {
    return `<div class="composer-dock"><form class="composer" id="chat-form" aria-label="Ask a question">
      ${icon("chat_bubble_outline", "composer-icon")}
      <input id="query-input" name="question" type="text" maxlength="1000" autocomplete="off" placeholder="Ask a question about SBI Mutual Fund..." aria-label="Your question about SBI Mutual Fund"${disabled ? " disabled" : ""}>
      <button class="send-button" type="submit" aria-label="Send inquiry"${disabled ? " disabled" : ""}>${icon("arrow_forward")}</button>
    </form><p class="composer-note">${escapeHtml(note)}</p></div>`;
  }

  function renderHome(target = app) {
    const cards = promptCards.map((item) => `<button class="prompt-card" type="button" data-prompt="${escapeHtml(item.question)}">
      <span class="prompt-icon">${icon(item.icon)}</span><span class="prompt-copy">${escapeHtml(item.question)}<span class="prompt-chevron">${icon("chevron_right")}</span></span>
    </button>`).join("");
    const chips = topics.map(([label, question]) => `<button class="topic-chip" type="button" data-prompt="${escapeHtml(question)}">${escapeHtml(label)}</button>`).join("");
    target.innerHTML = `<section class="home-view" data-state="welcome">
      <div class="hero">
        <p class="eyebrow">AI Assisted Knowledge Desk</p>
        <h1>SBI Mutual Fund<br>FAQ Assistant</h1>
        <p class="hero-description">Get factual answers about SBI Mutual Fund schemes.</p>
        <div class="facts-badge">${icon("info", "filled-icon")}<span>Facts-only. No investment advice.</span></div>
      </div>
      <section class="prompt-grid" aria-label="Example questions">${cards}</section>
      <section class="topics"><h2 class="section-label">Popular topics</h2><div class="chip-list">${chips}</div></section>
      ${composer("Press Enter to ask · Answers cite a supporting source when available")}
    </section>`;
  }

  function renderLoading(state, target = app) {
    const question = state.question || "";
    const context = state.scheme || state.source ? `<div class="scheme-context"><span>Scheme context:</span>${state.scheme ? `<span class="context-tag primary">${icon("account_balance")}${escapeHtml(state.scheme)}</span>` : ""}${state.source ? `<span class="context-tag">${icon("verified_user")}${escapeHtml(state.source.label || "Source")}</span>` : ""}</div>` : "";
    target.innerHTML = `<section class="conversation-view" data-state="loading"><div class="conversation" aria-label="Conversation">
      ${userMessage(question, state.time)}
      ${assistantStart()}<div class="assistant-card" role="status" aria-live="polite"><div class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></div><p class="loading-copy">Searching relevant information from available SBI Mutual Fund sources...</p><div class="skeleton"></div><div class="skeleton short"></div></div>${assistantEnd(question, state.time, false)}
      ${context}
    </div>${composer("Factual scheme information from the available sources", Boolean(state.pending))}</section>`;
  }

  function renderFactual(response, question, target = app) {
    const heading = response.scheme ? `<div class="scheme-heading"><div class="scheme-name">${icon("account_balance")}<h2 class="scheme-title">${escapeHtml(response.scheme)}</h2></div>${response.category ? `<span class="category-badge">${escapeHtml(response.category)}</span>` : ""}</div>` : "";
    const paragraph = response.narrative ? `<p class="card-body">${escapeHtml(response.narrative)}</p>` : "";
    const facts = factsMarkup(response.facts);
    const card = `<div class="assistant-card">${heading}${paragraph}${facts}${sourceMarkup(response.source)}</div>`;
    target.innerHTML = `<section class="conversation-view" data-state="factual"><div class="conversation" aria-label="Conversation">
      ${trustBanner("Facts-only assistance · Supporting source details shown with answers")}${userMessage(question, response.user_time)}${assistantStart()}${card}${assistantEnd(question, response.assistant_time, true, response)}
      ${response.suggestions?.length ? `<div class="conversation-suggestions">${suggestionsMarkup(response.suggestions, "Suggested")}</div>` : ""}
    </div>${composer("Factual scheme information from the available sources")}</section>`;
  }

  function renderRefusal(response, question, target = app) {
    const performance = response.reason === "performance";
    const title = performance ? "I can't forecast future performance." : "I can't provide investment advice.";
    const factsTitle = response.scheme ? "Factual fund overview" : "Available facts";
    const card = `<div class="assistant-card guardrail"><div class="card-heading"><span class="status-icon warning">${icon("warning")}</span><h2 class="warning-title">${title}</h2></div>
      ${response.narrative ? `<p class="card-body">${escapeHtml(response.narrative)}</p>` : ""}
      ${factsMarkup(response.facts, factsTitle)}${suggestionsMarkup(response.suggestions, "Permitted factual questions")}${sourceMarkup(response.source)}
    </div>`;
    target.innerHTML = `<section class="conversation-view" data-state="refusal"><div class="conversation" aria-label="Conversation">
      ${trustBanner("Facts-only assistance · Recommendations are outside its scope")}${userMessage(question, response.user_time)}${assistantStart()}${card}${assistantEnd(question, response.assistant_time, false)}
    </div>${composer("Facts only · Historical figures are facts, not forecasts")}</section>`;
  }

  function renderUnsupported(response, question, target = app) {
    const isPrivate = response.reason === "private_information";
    const title = isPrivate ? "That personal information isn't available here." : "I couldn't find that information in the available source data.";
    const narrative = response.narrative || (isPrivate
      ? "This assistant provides public scheme information and cannot provide personal contact or account details."
      : "You can ask about scheme details, charges, SIP, exit load, riskometer, or other information in the available sources.");
    const card = `<div class="assistant-card neutral"><div class="card-heading"><span class="status-icon">${icon(isPrivate ? "person_search" : "search_off")}</span><h2>${title}</h2></div>
      <p class="card-body">${escapeHtml(narrative)}</p>${suggestionsMarkup(response.suggestions, "Try asking about")}${sourceMarkup(response.source)}
    </div>`;
    target.innerHTML = `<section class="conversation-view" data-state="unsupported"><div class="conversation" aria-label="Conversation">
      ${userMessage(question, response.user_time)}${assistantStart()}${card}${assistantEnd(question, response.assistant_time, true, response)}
    </div>${composer("Official scheme facts from the available sources")}</section>`;
  }

  function configuredResource(url, title, iconName) {
    if (url) {
      return `<a class="resource-placeholder resource-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${icon(iconName)}<div><strong>${escapeHtml(title)}</strong><span>Open official service</span></div>${icon("open_in_new")}</a>`;
    }
    return `<div class="resource-placeholder" aria-disabled="true">${icon(iconName)}<div><strong>${escapeHtml(title)}</strong><span>Destination not configured</span></div></div>`;
  }

  function renderPrivacy(state, target = app) {
    const question = state.maskedQuestion || "[Sensitive values removed]";
    const questionMarkup = userMessage(question, state.time);
    target.innerHTML = `<section class="conversation-view privacy-screen" data-state="privacy"><div class="conversation" aria-label="Privacy-protected conversation">
      <div class="privacy-status"><strong>${icon("shield_lock")}PII detected · Question not sent</strong><button type="button" data-reset-chat>${icon("refresh")} Reset chat</button></div>
      <div class="context-tag primary privacy-mask-label">${icon("verified_user")}Sensitive values masked in this browser</div>
      ${questionMarkup}
      ${assistantStart()}<div class="assistant-card privacy-card" role="alert" aria-live="assertive">
        <div class="card-heading"><span class="status-icon danger">${icon("shield_person")}</span><div><h2>Please don't share personal or account credentials here.</h2><p class="source-date">The original question was not sent to the assistant service.</p></div></div>
        <div class="privacy-info"><p>The SBI Mutual Fund FAQ Assistant provides public scheme information. It cannot access investor folios, execute transactions, or process private credentials such as PAN, Aadhaar, OTPs, or bank account details.</p><p>For folio balances, unit allotments, or personal statements, use an authenticated service from your provider.</p></div>
        <div class="resource-row" aria-label="Self-service destinations">
          ${configuredResource(investorPortalUrl, "Official Investor Portal", "account_balance")}
          ${configuredResource(growwDashboardUrl, "Groww Investment Dashboard", "phone_iphone")}
        </div>
        ${suggestionsMarkup(["How to download a capital gains statement?", "What is the SBI ELSS lock-in period?", "How do I update my nominee?"], "Suggested factual questions")}
      </div>${assistantEnd(question, undefined, false)}
      <div class="privacy-panel"><div class="privacy-panel-top"><span class="privacy-footer-icon">${icon("shield_lock")}</span><div class="privacy-footer-copy"><h3>Privacy safeguard</h3><p>Sensitive values were masked locally. The masked version stays in this page session until reset or page close.</p></div></div></div>
    </div>${composer("Only factual answers about public scheme information are provided", Boolean(state.pending))}</section>`;
  }

  function renderError(response, question, target = app) {
    const entryIndex = Number.isInteger(response.entry_index) ? response.entry_index : -1;
    const card = `<div class="assistant-card error-card"><div class="card-heading"><span class="status-icon danger">${icon("sync_problem")}</span><h2>Something went wrong.</h2></div>
      <p class="card-body">${escapeHtml(response.narrative || "The assistant couldn't retrieve a reliable answer right now. Please try again in a moment.")}</p>
      <div class="error-note">${icon("info")}<span>This FAQ assistant has no investor account or portfolio access.</span></div>
      <div class="error-actions"><button class="action-button" type="button" data-retry-index="${entryIndex}">${icon("refresh")}Try again</button><button class="action-button secondary" type="button" data-different-question>${icon("help")}Ask a different question</button></div>
      <div class="error-shortcuts"><h3 class="section-label">Browse standard scheme facts</h3><div class="suggestion-chips">${[
        ["Scheme NAV", "What is the NAV of SBI Flexicap Fund Direct Growth?"],
        ["Expense ratio", "What is the expense ratio of SBI Flexicap Fund Direct Growth?"],
        ["Fund riskometer", "What is the Riskometer of SBI Flexicap Fund Direct Growth?"],
      ].map(([text, questionText]) => `<button class="suggestion-chip" type="button" data-prompt="${escapeHtml(questionText)}">${escapeHtml(text)}${icon("open_in_new")}</button>`).join("")}</div></div>
      ${sourceMarkup(response.source)}</div>`;
    target.innerHTML = `<section class="conversation-view" data-state="error"><div class="conversation" aria-label="Conversation">
      ${trustBanner("Facts-only assistant · Source details accompany supported answers")}${userMessage(question, response.user_time)}${assistantStart()}${card}${assistantEnd(question, response.assistant_time, false)}
    </div>${composer("Factual scheme information from the available sources")}</section>`;
  }

  function renderState(state, question = "", target = app) {
    if (!state || typeof state !== "object") return;
    const effectiveQuestion = question || state.question || "";
    if (state.state === "welcome") renderHome(target);
    else if (state.state === "loading") renderLoading(state, target);
    else if (state.state === "factual") renderFactual(state, effectiveQuestion, target);
    else if (state.state === "refusal") renderRefusal(state, effectiveQuestion, target);
    else if (state.state === "unsupported") renderUnsupported(state, effectiveQuestion, target);
    else if (state.state === "privacy") renderPrivacy(state, target);
    else if (state.state === "error") renderError(state, effectiveQuestion, target);
    else renderHome(target);
  }

  function statusRegion() {
    let region = document.getElementById("interaction-status");
    if (!region) {
      region = document.createElement("div");
      region.id = "interaction-status";
      region.className = "sr-only";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    return region;
  }

  function announce(message) {
    statusRegion().textContent = message;
  }

  function safeSource(source) {
    if (!source || typeof source !== "object" || typeof source.label !== "string" || !source.label.trim()) return false;
    if (typeof source.source_type !== "string" || !source.source_type.trim()) return false;
    if (typeof source.url !== "string" || typeof source.retrieved_at !== "string") return false;
    let url;
    try { url = new URL(source.url); } catch (_error) { return false; }
    const date = source.retrieved_at;
    if (url.protocol !== "https:" || !url.hostname || url.username || url.password || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
    const parsed = new Date(`${date}T00:00:00Z`);
    return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === date;
  }

  function runtimeError(reason = "retrieval_failure", source) {
    const narratives = {
      validation_failure: "That question could not be processed. Please edit it and try again.",
      generation_failure: "The assistant couldn't retrieve a reliable answer right now. Please try again in a moment.",
      retrieval_failure: "The assistant couldn't retrieve a reliable answer right now. Please try again in a moment.",
    };
    const error = { state: "error", reason: narratives[reason] ? reason : "retrieval_failure", narrative: narratives[reason] || narratives.retrieval_failure, suggestions: [] };
    if (safeSource(source)) error.source = source;
    return error;
  }

  function validateApiResponse(payload, httpOk) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return runtimeError();
    if (!httpOk || payload.state === "error") return runtimeError(payload.reason, payload.source);
    if (!["factual", "refusal", "unsupported"].includes(payload.state)) return runtimeError();
    const reasonsByState = {
      factual: ["supported_fact"],
      refusal: ["advice", "performance"],
      unsupported: ["not_found", "private_information", "validation_failure"],
    };
    if (!reasonsByState[payload.state].includes(payload.reason)) return runtimeError();
    if (payload.narrative !== undefined && typeof payload.narrative !== "string") return runtimeError();
    if ((payload.scheme !== undefined && typeof payload.scheme !== "string") || (payload.category !== undefined && typeof payload.category !== "string")) return runtimeError();
    if (payload.source !== undefined && !safeSource(payload.source)) return runtimeError();
    if (payload.facts !== undefined && (!Array.isArray(payload.facts) || payload.facts.some((fact) => !fact || typeof fact.label !== "string" || !fact.label.trim() || typeof fact.value !== "string" || !fact.value.trim()))) return runtimeError();
    if (payload.suggestions !== undefined && (!Array.isArray(payload.suggestions) || payload.suggestions.some((item) => typeof item !== "string"))) return runtimeError();
    if (payload.state === "factual" && (typeof payload.narrative !== "string" || !payload.narrative.trim() || !safeSource(payload.source))) return runtimeError();
    return payload;
  }

  function turnMarkup(entry, index) {
    const scratch = document.createElement("div");
    let state;
    if (entry.response === null) {
      state = { state: "loading", question: entry.question, time: entry.user_time, pending: true };
    } else if (entry.response.state === "privacy") {
      state = { ...entry.response, maskedQuestion: entry.question, time: entry.user_time };
    } else {
      state = { ...entry.response, user_time: entry.user_time, entry_index: index, feedback: entry.feedback };
    }
    renderState(state, entry.question, scratch);
    return scratch.querySelector(".conversation")?.innerHTML || "";
  }

  function renderTranscript() {
    if (!transcript.length) return renderHome();
    const latest = transcript[transcript.length - 1];
    const latestState = latest.response ? latest.response.state : "loading";
    const privacyClass = latestState === "privacy" ? " privacy-screen" : "";
    const note = latestState === "privacy"
      ? "Only factual answers about public scheme information are provided"
      : "Factual scheme information from the available sources";
    app.innerHTML = `<section class="conversation-view${privacyClass}" data-state="${escapeHtml(latestState)}"><div class="conversation" aria-label="Conversation">${transcript.map((entry, index) => `<div class="conversation-turn" data-turn-index="${index}">${turnMarkup(entry, index)}</div>`).join("")}</div>${composer(note, requestPending)}</section>`;
  }

  function configuredRoutesMarkup() {
    const routes = [
      configuredResource(investorPortalUrl, "Official Investor Portal", "account_balance"),
      configuredResource(growwDashboardUrl, "Groww Investment Dashboard", "phone_iphone"),
    ];
    if (!investorPortalUrl && !growwDashboardUrl) return `<p class="info-muted">Support destinations are not configured in this local app.</p>`;
    return `<div class="resource-row info-resources">${routes.filter((_route, index) => index === 0 ? investorPortalUrl : growwDashboardUrl).join("")}</div>`;
  }

  function renderInfoPage(view) {
    if (view === "schemes") {
      const items = schemes.map(([name, category]) => `<li class="scheme-directory-item"><div><h2>${escapeHtml(name)}</h2><p>${escapeHtml(category)} scheme</p></div><button type="button" class="info-action" data-prompt="What is the category of ${escapeHtml(name)}?">Ask about this scheme ${icon("arrow_forward")}</button></li>`).join("");
      app.innerHTML = `<section class="info-view" data-state="schemes"><p class="eyebrow">SBI Mutual Fund</p><h1 tabindex="-1">Schemes</h1><p class="info-lead">Browse factual FAQs for the five schemes covered by this assistant.</p><ul class="scheme-directory">${items}</ul></section>`;
    } else if (view === "help") {
      const quickQuestions = ["What is the AUM of SBI Large Cap Fund?", "What are the historical returns of SBI Flexicap Fund?", "What are the top holdings of SBI Large Cap Fund?"];
      app.innerHTML = `<section class="info-view" data-state="help"><p class="eyebrow">FAQ Assistant</p><h1 tabindex="-1">Help</h1><p class="info-lead">Ask about public SBI Mutual Fund scheme information available in the approved source collection.</p><section class="info-section"><h2>What you can ask</h2><p>Questions about categories, expenses, AUM, NAV, scheme holdings, historical returns, rankings, peer comparisons, risk information, benchmarks, and public FAQ guidance. Historical figures are not forecasts or recommendations.</p><div class="suggestion-chips">${quickQuestions.map((question) => `<button class="suggestion-chip" type="button" data-prompt="${escapeHtml(question)}">${escapeHtml(question)}</button>`).join("")}</div></section><section class="info-section"><h2>Personal investor services</h2><p>This FAQ assistant has no sign-in, folio, balance, personal portfolio, or transaction access.</p>${configuredRoutesMarkup()}</section></section>`;
    } else {
      app.innerHTML = `<section class="info-view" data-state="about"><p class="eyebrow">SBI Mutual Fund FAQ Assistant</p><h1 tabindex="-1">About</h1><p class="info-lead">A facts-only interface for public scheme FAQs, not investment advice.</p><section class="info-section"><h2>Answer policy</h2><p>Permitted answers use retrieved material from the approved source index. Factual responses show a supporting source and its retrieval date. When the available evidence does not support an answer, the assistant says so.</p></section><section class="info-section"><h2>Limits</h2><p>The assistant can report sourced historical returns, rankings, peer comparisons, and scheme holdings, but does not provide recommendations, suitability assessments, or future forecasts. It has no sign-in, account, personal portfolio, or transaction access.</p></section><section class="info-section"><h2>Source scope</h2><p>The knowledge collection is limited to the enabled, approved records in the documented 25-source manifest.</p></section></section>`;
    }
  }

  function updateNavigation() {
    document.querySelectorAll("[data-nav-view]").forEach((button) => {
      const current = button.dataset.navView === activeView;
      button.classList.toggle("is-current", current);
      if (current) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
  }

  function renderCurrent() {
    updateNavigation();
    if (activeView === "assistant") {
      if (transcript.length) renderTranscript();
      else renderHome();
      return;
    }
    renderInfoPage(activeView);
  }

  function navigate(view, moveFocus = true) {
    activeView = view;
    renderCurrent();
    if (!moveFocus) return;
    const focusTarget = app.querySelector(".info-view h1") || app.querySelector(".conversation") || app.querySelector(".hero h1");
    if (focusTarget) {
      if (!focusTarget.hasAttribute("tabindex")) focusTarget.setAttribute("tabindex", "-1");
      focusTarget.focus({ preventScroll: true });
    }
  }

  function populateQuestion(question) {
    if (requestPending) return;
    activeView = "assistant";
    renderCurrent();
    const input = document.getElementById("query-input");
    if (!input) return;
    input.value = question;
    input.focus();
  }

  function appendLocalPrivacy(maskedQuestion) {
    const entry = {
      question: maskedQuestion || "[Sensitive values removed]",
      user_time: currentTime(),
      response: { state: "privacy" },
      feedback: null,
    };
    transcript.push(entry);
    activeView = "assistant";
    renderCurrent();
    announce("Sensitive information was detected. The masked question was not sent.");
  }

  async function submitQuestion(value, retryIndex = -1) {
    const question = String(value || "").trim();
    if (!question || requestPending) return;
    let inspected;
    try {
      if (!global.SBIFaqPrivacy || typeof global.SBIFaqPrivacy.inspect !== "function") throw new Error("Privacy check unavailable");
      inspected = global.SBIFaqPrivacy.inspect(question);
    } catch (_error) {
      announce("The local privacy check is unavailable. The question was not sent.");
      return;
    }
    if (inspected.detected) {
      appendLocalPrivacy(inspected.masked);
      return;
    }

    activeView = "assistant";
    let entryIndex = retryIndex;
    if (entryIndex >= 0 && transcript[entryIndex]?.response?.state === "error") {
      transcript[entryIndex].question = question;
      transcript[entryIndex].user_time = currentTime();
      transcript[entryIndex].response = null;
      transcript[entryIndex].feedback = null;
    } else {
      entryIndex = transcript.length;
      transcript.push({ question, user_time: currentTime(), response: null, feedback: null });
    }
    requestPending = true;
    renderCurrent();
    announce("Searching the available SBI Mutual Fund sources.");
    const generation = ++requestGeneration;

    let response;
    try {
      const result = await global.fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      let payload;
      try { payload = await result.json(); } catch (_error) { payload = null; }
      response = validateApiResponse(payload, result.ok);
    } catch (_error) {
      response = runtimeError("retrieval_failure");
    }
    if (generation !== requestGeneration) return;

    requestPending = false;
    response.assistant_time = currentTime();
    transcript[entryIndex].response = response;
    transcript[entryIndex].markup = turnMarkup(transcript[entryIndex], entryIndex);
    renderCurrent();
    announce(response.state === "factual" ? "Answer ready, with its supporting source." : response.state === "refusal" ? "The assistant provided a safety response." : response.state === "unsupported" ? "The requested information was not available." : "The assistant encountered an error. You can retry the question.");
  }

  function resetChat() {
    requestGeneration += 1;
    requestPending = false;
    transcript.length = 0;
    activeView = "assistant";
    renderCurrent();
    const input = document.getElementById("query-input");
    if (input) input.focus();
    announce("Chat cleared.");
  }

  function copyText(response) {
    const lines = [];
    if (response.narrative) lines.push(response.narrative);
    if (Array.isArray(response.facts)) response.facts.forEach((fact) => lines.push(`${fact.label}: ${fact.value}`));
    if (safeSource(response.source)) {
      lines.push(`Source: ${response.source.label} (${response.source.url})`);
      lines.push(`Last updated from sources: ${response.source.retrieved_at}.`);
    }
    return lines.join("\n");
  }

  async function copyAnswer(index) {
    const response = transcript[index]?.response;
    if (!response || !["factual", "unsupported"].includes(response.state)) return;
    const text = copyText(response);
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const field = document.createElement("textarea");
        field.value = text;
        field.setAttribute("readonly", "");
        field.style.position = "fixed";
        field.style.opacity = "0";
        document.body.appendChild(field);
        let copied;
        try {
          field.select();
          copied = document.execCommand("copy");
        } finally {
          field.remove();
        }
        if (!copied) throw new Error("Clipboard unavailable");
      }
      announce("Answer and source copied to the clipboard.");
    } catch (_error) {
      announce("Could not copy the answer. Check clipboard permissions and try again.");
    }
  }

  function renderEntry(index) {
    const entry = transcript[index];
    if (!entry || !entry.response) return;
    entry.markup = turnMarkup(entry, index);
    renderCurrent();
  }

  app.addEventListener("click", (event) => {
    const target = event.target.closest("button");
    if (!target) return;
    if (target.matches("[data-reset-chat]")) {
      event.preventDefault();
      resetChat();
      return;
    }
    const prompt = target.getAttribute("data-prompt");
    if (prompt) {
      event.preventDefault();
      populateQuestion(prompt);
      return;
    }
    if (target.hasAttribute("data-retry-index")) {
      const retryIndex = Number(target.getAttribute("data-retry-index"));
      const failed = Number.isInteger(retryIndex) && retryIndex >= 0 ? transcript[retryIndex] : null;
      if (failed?.response?.state === "error") submitQuestion(failed.question, retryIndex);
      return;
    }
    if (target.matches("[data-different-question]")) {
      const input = document.getElementById("query-input");
      if (input) { input.value = ""; input.focus(); }
      return;
    }
    if (target.matches("[data-feedback]")) {
      const index = Number(target.dataset.entryIndex);
      const entry = transcript[index];
      if (!entry || !["factual", "unsupported"].includes(entry.response?.state)) return;
      entry.feedback = entry.feedback === target.dataset.feedback ? null : target.dataset.feedback;
      renderEntry(index);
      app.querySelector(`[data-entry-index="${index}"][data-feedback="${target.dataset.feedback}"]`)?.focus();
      announce(entry.feedback === "helpful" ? "Feedback recorded for this page session: helpful." : entry.feedback === "not_helpful" ? "Feedback recorded for this page session: not helpful." : "Feedback selection cleared.");
      return;
    }
    if (target.matches("[data-copy-answer]")) copyAnswer(Number(target.dataset.copyAnswer));
  });

  document.addEventListener("click", (event) => {
    const navButton = event.target.closest("[data-nav-view]");
    if (navButton) {
      event.preventDefault();
      navigate(navButton.dataset.navView);
      return;
    }
    if (event.target.closest("[data-disabled-action]")) event.preventDefault();
  });

  app.addEventListener("submit", (event) => {
    if (!event.target.matches("#chat-form")) return;
    event.preventDefault();
    const input = event.target.querySelector("#query-input");
    if (!input || !input.value.trim() || requestPending) return;
    const question = input.value.trim();
    input.value = "";
    submitQuestion(question);
  });

  renderCurrent();
  const logo = document.querySelector(".brand-logo");
  const logoFallback = document.querySelector(".brand-logo-fallback");
  if (logo && logoFallback) {
    const showLogoFallback = () => { logo.hidden = true; logoFallback.hidden = false; };
    logo.addEventListener("error", showLogoFallback, { once: true });
    if (logo.complete && !logo.naturalWidth) showLogoFallback();
  }
  if (document.fonts?.ready) {
    document.fonts.ready.then(async () => {
      try {
        const faces = await document.fonts.load('20px "Material Symbols Outlined"', "person");
        if (!faces.some((face) => face.status === "loaded")) enableSymbolFallback();
      } catch (_error) {
        enableSymbolFallback();
      }
    });
  } else {
    enableSymbolFallback();
  }
  global.SBIFaqUI = Object.freeze({ renderState });
})(window);
