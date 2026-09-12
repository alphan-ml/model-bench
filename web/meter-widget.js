/**
 * Cost Meter widget — bottom-right "Cost meter" pill + drawer, shared by
 * every use-case page (Model Bench, AREA). Vanilla JS, no build step, no
 * dependencies, matches SPEC-cost-meter-and-angi-reuse.md §1.3.
 *
 * Integration (for W-A3/W-A4/W-B4/W-B5 page code):
 *
 *   <script type="module">
 *     import { initMeterWidget } from '/meter-widget.js';
 *     const meter = initMeterWidget();
 *     // Pass meter.sessionId along with your own API calls (e.g. a POST
 *     // to /api/run-one) so the server tags its usage_events row with
 *     // the same session. After each call your page makes:
 *     await meter.refresh();
 *   </script>
 *
 * The session id is created once per page load and kept ONLY in memory —
 * per §1.1, "no cookies needed; if the tab reloads, a new session starts —
 * say so on the page." This file never touches localStorage, sessionStorage,
 * or cookies for the id.
 *
 * Everything that touches the DOM lives behind initMeterWidget(), so this
 * module can be imported under Node (for tests of the pure formatting/CSV
 * helpers below) without a document/window existing.
 */

const PILL_ID = 'meter-widget-pill';
const DRAWER_ID = 'meter-widget-drawer';
const BLUE = '#1a56db';
const RED = '#c81e1e';

/** A random-enough session id. crypto.randomUUID() where available (all
 * evergreen browsers), a plain fallback otherwise. Never persisted. */
export function generateSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'sess-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

/** Dollars to 4 decimal places, per §1.3's "live session total in dollars
 * (4 decimals)". Always shows the sign only for negatives (never happens
 * for a cost, but keeps the formatting rule explicit and testable). */
export function formatUsd(value, decimals = 4) {
  const n = Number(value) || 0;
  return `$${n.toFixed(decimals)}`;
}

/** Builds the pill's label text from a /api/meter/session response shape
 * ({ session_id, events, totals: { calls, cost_usd, ... } }). Pulled out
 * as a pure function so it's testable without a DOM. */
export function computePillLabel(summary) {
  const calls = summary?.totals?.calls ?? 0;
  const costUsd = summary?.totals?.cost_usd ?? 0;
  const callWord = calls === 1 ? 'call' : 'calls';
  return `Cost meter — ${formatUsd(costUsd)} · ${calls} ${callWord}`;
}

/** Turns an itemized events list into a CSV string for "Copy as CSV".
 * Column order matches the itemized table: step, model, tokens in/out,
 * cost, latency. */
export function csvFromEvents(events) {
  const header = ['step', 'model_id', 'input_tokens', 'output_tokens', 'cost_usd', 'latency_ms', 'ok'];
  const lines = [header.join(',')];
  for (const e of events ?? []) {
    const row = [
      e.step, e.model_id, e.input_tokens, e.output_tokens,
      e.cost_usd, e.latency_ms, e.ok,
    ].map((v) => {
      const s = String(v ?? '');
      // Quote any field containing a comma, quote, or newline (RFC 4180).
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    });
    lines.push(row.join(','));
  }
  return lines.join('\n');
}

/** Fetches this session's itemized summary. Kept separate from the DOM
 * code so a test can call it with a fake `fetchImpl`. */
export async function fetchSessionSummary(sessionId, fetchImpl = fetch) {
  const res = await fetchImpl(`/api/meter/session?id=${encodeURIComponent(sessionId)}`);
  if (!res.ok) {
    throw new Error(`meter/session request failed: ${res.status}`);
  }
  return res.json();
}

function injectStyleOnce() {
  if (document.getElementById('meter-widget-style')) return;
  const style = document.createElement('style');
  style.id = 'meter-widget-style';
  style.textContent = `
    #${PILL_ID} {
      position: fixed; right: 20px; bottom: 20px; z-index: 9999;
      font-family: 'Lexend', sans-serif; font-weight: 300; font-size: 14px;
      background: #ffffff; color: #111111;
      border: 1px solid #111111; border-radius: 999px;
      padding: 10px 18px; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    #${PILL_ID} strong { font-weight: 600; color: ${BLUE}; }
    #${DRAWER_ID} {
      position: fixed; right: 20px; bottom: 72px; z-index: 9999;
      font-family: 'Lexend', sans-serif; font-weight: 300; font-size: 13px;
      background: #ffffff; color: #111111; border: 1px solid #111111;
      border-radius: 8px; padding: 16px; width: 420px; max-width: calc(100vw - 40px);
      max-height: 60vh; overflow-y: auto; box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    }
    #${DRAWER_ID} h3 { font-weight: 600; margin: 0 0 8px 0; }
    #${DRAWER_ID} table { width: 100%; border-collapse: collapse; font-size: 12px; }
    #${DRAWER_ID} th { text-align: left; font-weight: 600; border-bottom: 1px solid #111111; padding: 4px 6px; }
    #${DRAWER_ID} td { padding: 4px 6px; border-bottom: 1px solid #e5e5e5; }
    #${DRAWER_ID} td.cost { color: ${BLUE}; font-weight: 600; }
    #${DRAWER_ID} td.error { color: ${RED}; }
    #${DRAWER_ID} .csv-btn {
      font-family: 'Lexend', sans-serif; font-weight: 600; font-size: 12px;
      background: ${BLUE}; color: #ffffff; border: none; border-radius: 6px;
      padding: 6px 12px; cursor: pointer; margin-top: 10px;
    }
    #${DRAWER_ID} .note { font-size: 11px; margin-top: 8px; }
  `;
  document.head.appendChild(style);
}

function renderDrawer(summary) {
  let drawer = document.getElementById(DRAWER_ID);
  if (!drawer) {
    drawer = document.createElement('div');
    drawer.id = DRAWER_ID;
    document.body.appendChild(drawer);
  }
  const events = summary.events ?? [];
  // Itemized rows use 6 decimals (matching usage_events.cost_usd's own
  // NUMERIC(10,6)), not the pill's 4 — a single call can genuinely cost
  // $0.00004, and rounding that to 4 decimals would print "$0.0000" for
  // a real, nonzero cost. The spec's "4 decimals" (§1.3) is specifically
  // about the pill's live SESSION TOTAL, which is usually larger.
  const rows = events.map((e) => `
    <tr>
      <td>${e.step}</td>
      <td>${e.model_id}</td>
      <td>${e.input_tokens}</td>
      <td>${e.output_tokens}</td>
      <td class="cost">${formatUsd(e.cost_usd, 6)}</td>
      <td>${e.latency_ms} ms</td>
      ${e.ok === false ? `<td class="error">${e.error ?? 'error'}</td>` : '<td></td>'}
    </tr>`).join('');
  drawer.innerHTML = `
    <h3>This session's cost</h3>
    <table>
      <thead><tr><th>Step</th><th>Model</th><th>In</th><th>Out</th><th>Cost</th><th>Latency</th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="7">No calls yet this session.</td></tr>'}</tbody>
    </table>
    <button class="csv-btn" type="button">Copy as CSV</button>
    <p class="note">Session id resets if you reload this tab — no cookies are used.</p>
  `;
  drawer.querySelector('.csv-btn').addEventListener('click', async () => {
    const csv = csvFromEvents(events);
    try {
      await navigator.clipboard.writeText(csv);
    } catch {
      // Clipboard permission denied or unavailable — fall back silently;
      // the drawer's table already shows the same data on screen.
    }
  });
}

/**
 * Mounts the pill (and, on click, the drawer) into the current page.
 * @param {{ fetchImpl?: typeof fetch, autoRefreshMs?: number, sessionId?: string }} [options]
 *   `sessionId` overrides the generated id — not for page integration
 *   (real pages always want a fresh one), but so dev/preview tooling
 *   (web/dev-widget-preview.html) can point the widget at a known
 *   fixture session and exercise the REAL rendering code for visual
 *   verification, instead of hand-duplicating it.
 * @returns {{ sessionId: string, refresh: () => Promise<void>, destroy: () => void }}
 */
export function initMeterWidget(options = {}) {
  const fetchImpl = options.fetchImpl ?? fetch;
  const sessionId = options.sessionId ?? generateSessionId();
  injectStyleOnce();

  const pill = document.createElement('button');
  pill.id = PILL_ID;
  pill.type = 'button';
  pill.innerHTML = `<strong>Cost meter</strong> — $0.0000 · 0 calls`;
  document.body.appendChild(pill);

  let drawerOpen = false;
  let lastSummary = { session_id: sessionId, events: [], totals: { calls: 0, cost_usd: 0 } };

  async function refresh() {
    try {
      lastSummary = await fetchSessionSummary(sessionId, fetchImpl);
      pill.innerHTML = `<strong>Cost meter</strong> — ${computePillLabel(lastSummary).replace('Cost meter — ', '')}`;
      if (drawerOpen) renderDrawer(lastSummary);
    } catch {
      // A metering failure must never block the visitor's use of the
      // page (BUILD INSTRUCTION rule 6: visitors are never blocked for
      // cost) — leave the pill showing its last-known total.
    }
  }

  pill.addEventListener('click', () => {
    drawerOpen = !drawerOpen;
    const existing = document.getElementById(DRAWER_ID);
    if (!drawerOpen) {
      if (existing) existing.remove();
      return;
    }
    renderDrawer(lastSummary);
  });

  let intervalId = null;
  if (options.autoRefreshMs) {
    intervalId = setInterval(refresh, options.autoRefreshMs);
  }

  function destroy() {
    if (intervalId) clearInterval(intervalId);
    pill.remove();
    document.getElementById(DRAWER_ID)?.remove();
  }

  return { sessionId, refresh, destroy };
}
