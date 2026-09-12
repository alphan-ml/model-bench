/**
 * Model Bench — usage/monthly-counter write seam.
 *
 * Neither a real usage_events WRITE path (SPEC-cost-meter-and-angi-reuse.md
 * §1.1: "written by the provider layer") nor the model_bench_calls monthly
 * counter table (SPEC-model-bench.md §7.2) exists yet -- both need Neon,
 * which W-M2 wires. This module is the one seam W-M2 has to cut, the exact
 * same pattern api/meter/store.js already established for the READ side
 * (see that file's own header comment).
 *
 * Until W-M2:
 *   - logUsageEvent() records into an in-memory, capped list -- enough for
 *     tests and local dev to see it happened, but nothing persists across
 *     a process restart or a Vercel cold start, and it is never read by
 *     the public /api/meter/* endpoints (those still only read the
 *     committed fixture -- this is a separate, run-one.js-only record).
 *   - incrementMonthlyCounter()/getMonthlyCounter() are an in-memory,
 *     per-UTC-month counter for the same reason.
 *
 * Neither function ever throws. run-one.js calls both best-effort, in a
 * try/catch, and must never fail a visitor's request over a metering bug
 * (BUILD INSTRUCTION rule 6: visitors are never blocked for cost).
 */

const MAX_IN_MEMORY_EVENTS = 500;

let _events = [];
let _monthKey = null;
let _monthlyCallCount = 0;
let _monthlyCostUsd = 0;

function currentMonthKey(now) {
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}`;
}

/** @param {object} event - a usage_events-shaped row (see schema.sql). */
export function logUsageEvent(event) {
  _events.push({ ...event, ts: new Date().toISOString() });
  if (_events.length > MAX_IN_MEMORY_EVENTS) {
    _events.shift();
  }
}

/** Test/dev-only: everything logged so far, oldest first. */
export function getLoggedEvents() {
  return _events;
}

/**
 * @param {number} costUsd - cost of the call(s) to add to this month's total.
 * @param {Date} [now]
 */
export function incrementMonthlyCounter(costUsd, now = new Date()) {
  const monthKey = currentMonthKey(now);
  if (_monthKey !== monthKey) {
    _monthKey = monthKey;
    _monthlyCallCount = 0;
    _monthlyCostUsd = 0;
  }
  _monthlyCallCount += 1;
  _monthlyCostUsd += Number(costUsd) || 0;
}

/** @param {Date} [now] @returns {{calls: number, cost_usd: number}} */
export function getMonthlyCounter(now = new Date()) {
  const monthKey = currentMonthKey(now);
  if (_monthKey !== monthKey) {
    return { calls: 0, cost_usd: 0 };
  }
  return { calls: _monthlyCallCount, cost_usd: _monthlyCostUsd };
}

/** Test-only: resets all in-memory state. */
export function _resetForTests() {
  _events = [];
  _monthKey = null;
  _monthlyCallCount = 0;
  _monthlyCostUsd = 0;
}
