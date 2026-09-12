/**
 * Cost Meter — health/summary endpoint.
 *
 * Per SPEC-cost-meter-and-angi-reuse.md section 1.2:
 *   GET /api/meter/health -> last event ts, rows this month,
 *   est. month-to-date cost, prices_as_of.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { getAllEvents } from './store.js';
import { roundCostUsd } from './cost.js';
import { meterRateLimiter, clientIpFrom } from './rate-limit.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// data/prices.json is model-bench's one file of pricing truth (see
// SPEC-model-bench.md section 3.3). Read directly rather than waiting on a
// "vendor into web/ at build" copy step (addendum section 1.1) that no task
// has built yet — same file, same as_of, no reason for health.js to depend
// on a build step that does not exist until later.
const PRICES_JSON_PATH = path.join(__dirname, '..', '..', '..', 'data', 'prices.json');

/** Reads data/prices.json's as_of date. Never throws: a missing or
 * unreadable prices.json makes prices_as_of null rather than failing the
 * whole health check — this endpoint's job is to report meter health, not
 * to re-validate the pricing file (report.py already does that, loudly, per
 * D-decisions in CONTEXT.md). */
export function readPricesAsOf(pricesJsonPath = PRICES_JSON_PATH) {
  try {
    const parsed = JSON.parse(readFileSync(pricesJsonPath, 'utf8'));
    return parsed.as_of ?? null;
  } catch {
    return null;
  }
}

/**
 * @param {Array<object>} events - full usage_events rows.
 * @param {{now?: Date, pricesAsOf?: string | null}} opts
 */
export function computeHealth(events, { now = new Date(), pricesAsOf = null } = {}) {
  const sortedByTs = [...events].sort((a, b) => new Date(a.ts) - new Date(b.ts));
  const lastEvent = sortedByTs[sortedByTs.length - 1] ?? null;

  const monthStartMs = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1);
  const thisMonth = events.filter((e) => new Date(e.ts).getTime() >= monthStartMs);

  return {
    ok: true,
    last_event_ts: lastEvent ? lastEvent.ts : null,
    rows_this_month: thisMonth.length,
    est_month_to_date_cost_usd: roundCostUsd(thisMonth.reduce((sum, e) => sum + e.cost_usd, 0)),
    prices_as_of: pricesAsOf,
  };
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

  res.status(200).json(computeHealth(getAllEvents(), { pricesAsOf: readPricesAsOf() }));
}
