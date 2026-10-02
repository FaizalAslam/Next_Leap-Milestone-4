"use strict";

(function attachPrivacyGuard(global) {
  const patterns = [
    /\b[A-Z]{5}\d{4}[A-Z]\b/gi,
    /(?<!\d)(?<value>\d(?:[ -]?\d){11})(?!\d)/g,
    /\b(?:bank\s+)?(?:account|acct|a\/c)\s*(?:number|no\.?|#|is|:)?\s*(?<value>\d(?:[ -]?\d){7,17})\b/gi,
    /\b(?:otp|one[- ]time\s+password|verification\s+code)\D{0,12}(?<value>\d{4,8})\b/gi,
    /(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])/g,
    /(?<!\w)(?:(?:\+?91|0091)[\s().-]*)?(?:[6-9](?:[\s().-]*\d){9})(?!\w)/g,
  ];

  function inspect(question) {
    const spans = [];
    for (const pattern of patterns) {
      pattern.lastIndex = 0;
      for (const match of question.matchAll(pattern)) {
        const value = match.groups && match.groups.value;
        const start = match.index + (value ? match[0].indexOf(value) : 0);
        spans.push({ start, end: start + (value || match[0]).length });
      }
    }
    spans.sort((left, right) => left.start - right.start || right.end - left.end);
    const merged = [];
    for (const span of spans) {
      const previous = merged[merged.length - 1];
      if (previous && span.start < previous.end) {
        previous.end = Math.max(previous.end, span.end);
      } else {
        merged.push({ ...span });
      }
    }
    let masked = question;
    for (const span of merged.reverse()) {
      masked = masked.slice(0, span.start) + "[REDACTED]" + masked.slice(span.end);
    }
    return { detected: merged.length > 0, masked };
  }

  function blockIfSensitive(input, warning) {
    const result = inspect(input.value);
    if (!result.detected) {
      warning.hidden = true;
      warning.textContent = "";
      return false;
    }
    input.value = result.masked;
    warning.textContent = `Sensitive information was detected, masked, and not sent: ${result.masked}`;
    warning.hidden = false;
    return true;
  }

  global.SBIFaqPrivacy = Object.freeze({ inspect, blockIfSensitive });
})(window);
