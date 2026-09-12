/**
 * Client logic for the Model Bench page's "live box" (SPEC-model-bench.md
 * §7.1 item 6): a textarea + button that calls POST /api/run-one and shows
 * 5 answers with intent, confidence, tokens, cost in cents, and latency.
 * Pure/DOM-light functions are exported and unit-tested directly; only
 * mountLiveBox() at the bottom touches the DOM.
 */
import { escapeXml } from './charts.js';

export const MAX_TEXT_LENGTH = 1000;

/** §7.2: "Input {text} (max 1,000 chars)." Validated client-side too so a
 * visitor gets an immediate, plain-word answer instead of waiting on a
 * round trip just to learn the same thing the server would also reject. */
export function validateLiveBoxInput(text) {
  const trimmed = (text ?? '').trim();
  if (trimmed.length === 0) {
    return { valid: false, error: 'Type a message first.' };
  }
  if (text.length > MAX_TEXT_LENGTH) {
    return { valid: false, error: `Keep it under ${MAX_TEXT_LENGTH} characters (this is ${text.length}).` };
  }
  return { valid: true, error: null };
}

/** Cost per §7.1 item 6: "cost in cents." A single call is usually a small
 * fraction of a cent, so this always shows 4 decimal places of a cent
 * (e.g. "0.0042¢"), never rounding a real nonzero cost down to "0¢". */
export function formatCents(costUsd) {
  const cents = Number(costUsd) * 100;
  return `${cents.toFixed(4)}¢`;
}

export function formatLatency(ms) {
  return `${Math.round(Number(ms))} ms`;
}

/**
 * Calls POST /api/run-one. Per the Cost Meter widget's own integration
 * contract (meter-widget.js's header comment): "Pass the session id along
 * with your own API calls... so the server tags its usage_events row with
 * the same session," so session_id rides along in the request body here.
 *
 * Throws a plain-word Error on any failure — a non-OK HTTP response, a
 * network failure, or a response that isn't valid JSON — using the exact
 * wording SPEC-model-bench.md §7.1 item 6 asks for ("The model service did
 * not answer. Try again.") so the caller never has to translate a raw
 * fetch/HTTP error into page copy itself.
 *
 * @param {string} text
 * @param {string} sessionId
 * @param {typeof fetch} fetchImpl
 * @returns {Promise<{answers: object[], prices_as_of: string|null}>}
 */
export async function callRunOne(text, sessionId, fetchImpl = fetch) {
  let res;
  try {
    res = await fetchImpl('/api/run-one', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, session_id: sessionId }),
    });
  } catch {
    throw new Error('The model service did not answer. Try again.');
  }

  if (res.status === 429) {
    const retryAfter = res.headers?.get?.('Retry-After');
    throw new Error(
      retryAfter
        ? `Too many requests right now. Try again in about ${retryAfter} seconds.`
        : 'Too many requests right now. Try again shortly.'
    );
  }
  if (!res.ok) {
    throw new Error('The model service did not answer. Try again.');
  }

  try {
    return await res.json();
  } catch {
    throw new Error('The model service did not answer. Try again.');
  }
}

/** Builds one answer's table row. A per-model error (e.g. a model not yet
 * configured before Gate 1, or a real call failure) renders in the error
 * column instead of intent/confidence — the whole live box never fails
 * just because one of the 5 models did (defense in depth, same principle
 * as the runner's per-row isolation, D11 in CONTEXT.md). */
export function answerRowHtml(answer) {
  if (answer.error) {
    return `
      <tr>
        <td>${escapeXml(answer.key)}</td>
        <td colspan="4" class="error">${escapeXml(answer.error)}</td>
      </tr>`;
  }
  return `
    <tr>
      <td>${escapeXml(answer.key)}</td>
      <td>${escapeXml(answer.intent ?? '—')}</td>
      <td>${answer.confidence ?? '—'}</td>
      <td>${answer.input_tokens}/${answer.output_tokens}</td>
      <td>${formatCents(answer.cost_usd)}</td>
      <td>${formatLatency(answer.latency_ms)}</td>
    </tr>`;
}

export function answersTableHtml(answers) {
  const rows = (answers ?? []).map(answerRowHtml).join('');
  return `
    <table>
      <thead><tr><th>Model</th><th>Intent</th><th>Confidence</th><th>Tokens in/out</th><th>Cost</th><th>Latency</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6">No answers yet.</td></tr>'}</tbody>
    </table>`;
}

/**
 * Wires the textarea + button in web/index.html to callRunOne(), and
 * refreshes the Cost Meter widget after every call (per its own
 * integration contract). The only DOM-touching function in this module.
 *
 * @param {{ sessionId: string, refresh: () => Promise<void> }} meter -
 *   the object initMeterWidget() returns.
 * @param {typeof fetch} fetchImpl
 * @param {Document} doc
 */
export function mountLiveBox(meter, fetchImpl = fetch, doc = document) {
  const textarea = doc.getElementById('live-box-input');
  const button = doc.getElementById('live-box-submit');
  const resultsEl = doc.getElementById('live-box-results');
  const errorEl = doc.getElementById('live-box-error');

  button.addEventListener('click', async () => {
    const { valid, error } = validateLiveBoxInput(textarea.value);
    errorEl.hidden = true;
    if (!valid) {
      errorEl.hidden = false;
      errorEl.textContent = error;
      return;
    }

    button.disabled = true;
    resultsEl.innerHTML = '<p>Running your message through 5 models…</p>';
    try {
      const data = await callRunOne(textarea.value, meter.sessionId, fetchImpl);
      resultsEl.innerHTML = answersTableHtml(data.answers);
      await meter.refresh();
    } catch (err) {
      resultsEl.innerHTML = '';
      errorEl.hidden = false;
      errorEl.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  });
}
