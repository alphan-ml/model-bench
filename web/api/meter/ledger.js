/**
 * Cost Meter — "cost of every chat", aggregated.
 *
 * Per SPEC-cost-meter-and-angi-reuse.md section 1.2:
 *   GET /api/meter/ledger?window=30d&group=day|use_case|model|step ->
 *   aggregated cost, calls, tokens, p50 latency.
 *
 * The p50-latency percentile uses the same linear-interpolation method as
 * modelbench.metrics.latency_p50_p95 (model-bench/src/modelbench/metrics.py)
 * so a number computed here and a number computed there never disagree on
 * method, only on which rows they cover — and, matching that Python
 * function, latency is computed over ok (non-error) rows only, since a
 * failed call's latency does not describe how fast an answer arrived.
 */

import { getAllEvents } from './store.js';
import { roundCostUsd } from './cost.js';
import { meterRateLimiter, clientIpFrom } from './rate-limit.js';

const WINDOW_RE = /^(\d+)d$/;

/** @param {string} windowStr - e.g. "30d". @returns {number} milliseconds */
export function parseWindowMs(windowStr) {
  const match = WINDOW_RE.exec(windowStr);
  if (!match) {
    throw new RangeError(`Unsupported window format: ${JSON.stringify(windowStr)} (expected e.g. "30d")`);
  }
  return Number(match[1]) * 24 * 60 * 60 * 1000;
}

/** Linear-interpolation percentile over an already-sorted array, pct in [0, 100]. */
export function percentile(sortedValues, pct) {
  if (sortedValues.length === 0) return 0;
  if (sortedValues.length === 1) return sortedValues[0];
  const rank = (pct / 100) * (sortedValues.length - 1);
  const lower = Math.floor(rank);
  const upper = Math.min(lower + 1, sortedValues.length - 1);
  const frac = rank - lower;
  return sortedValues[lower] + (sortedValues[upper] - sortedValues[lower]) * frac;
}

const GROUP_KEY_FNS = {
  // ts is stored as an ISO-8601 UTC timestamp, so slicing the first 10
  // characters is a UTC calendar day — no timezone library needed.
  day: (e) => e.ts.slice(0, 10),
  use_case: (e) => e.use_case,
  model: (e) => e.model_id,
  step: (e) => e.step,
};

export const SUPPORTED_GROUPS = Object.keys(GROUP_KEY_FNS);

/**
 * @param {Array<object>} events - full usage_events rows.
 * @param {{window?: string, group?: string, now?: Date}} opts
 * @returns {{window: string, group: string, generated_at: string, rows: Array<object>}}
 */
export function aggregateLedger(events, { window = '30d', group = 'day', now = new Date() } = {}) {
  if (!(group in GROUP_KEY_FNS)) {
    throw new RangeError(`Unsupported group: ${JSON.stringify(group)} (expected one of ${SUPPORTED_GROUPS.join(', ')})`);
  }
  const cutoffMs = now.getTime() - parseWindowMs(window);
  const inWindow = events.filter((e) => new Date(e.ts).getTime() >= cutoffMs);

  const keyFn = GROUP_KEY_FNS[group];
  const buckets = new Map();
  for (const event of inWindow) {
    const key = keyFn(event);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(event);
  }

  const rows = [...buckets.entries()].map(([key, bucketEvents]) => {
    const cost_usd = roundCostUsd(bucketEvents.reduce((sum, e) => sum + e.cost_usd, 0));
    const input_tokens = bucketEvents.reduce((sum, e) => sum + e.input_tokens, 0);
    const output_tokens = bucketEvents.reduce((sum, e) => sum + e.output_tokens, 0);
    const okLatencies = bucketEvents
      .filter((e) => e.ok)
      .map((e) => e.latency_ms)
      .sort((a, b) => a - b);

    return {
      key,
      calls: bucketEvents.length,
      cost_usd,
      input_tokens,
      output_tokens,
      p50_latency_ms: Math.round(percentile(okLatencies, 50)),
    };
  });

  rows.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));

  return { window, group, generated_at: now.toISOString(), rows };
}

function readLedgerParams(req) {
  const source =
    req.query && typeof req.query === 'object' && Object.keys(req.query).length > 0
      ? req.query
      : Object.fromEntries(new URL(req.url, 'http://localhost').searchParams);
  return { window: source.window || '30d', group: source.group || 'day' };
}

/** @param {import('node:http').IncomingMessage} req
 *  @param {import('node:http').ServerResponse & {status: Function, json: Function}} res */
export default function handler(req, res) {
  const { allowed, retryAfterSeconds } = meterRateLimiter.check(clientIpFrom(req));
  if (!allowed) {
    res.setHeader('Retry-After', String(retryAfterSeconds));
    res.status(429).json({ error: 'Too many requests. Try again shortly.' });
    return;
  }

  const { window, group } = readLedgerParams(req);
  try {
    res.status(200).json(aggregateLedger(getAllEvents(), { window, group }));
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
}
