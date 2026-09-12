/**
 * Model Bench — GET /api/health (SPEC-model-bench.md §7.3).
 *
 * Returns {ok, results_as_of, prices_as_of, calls_this_month,
 * est_cost_this_month_usd}. Distinct from api/meter/health.js (the shared
 * Cost Meter's own health endpoint, which reports usage_events-wide
 * numbers across every use case) -- this one is Model Bench-specific,
 * per the repo layout in SPEC-model-bench.md §2 (`web/api/health.js`,
 * a sibling of `web/api/run-one.js`, not under api/meter/).
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { readPricesAsOf } from './meter/health.js';
import { roundCostUsd } from './meter/cost.js';
import { getMonthlyCounter } from './model-bench-counter.js';
import { meterRateLimiter, clientIpFrom } from './meter/rate-limit.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..', '..');
const RESULTS_PATH = path.join(REPO_ROOT, 'results.json');
const PRICES_PATH = path.join(REPO_ROOT, 'data', 'prices.json');

/** Reads results.json's generated_at date, or null if it doesn't exist
 * yet -- no real run exists before Gate 1 (see CONTEXT.md "Open items"),
 * so "no results.json" must read as a normal, healthy "not run yet"
 * state, not an error. Mirrors readPricesAsOf's own null-safe try/catch
 * pattern in api/meter/health.js, for the same reason: this endpoint's
 * job is to report health, not to re-validate results.json (report.py's
 * check_results_schema already does that, loudly, at build time). */
export function readResultsAsOf(resultsPath = RESULTS_PATH) {
  try {
    const parsed = JSON.parse(readFileSync(resultsPath, 'utf8'));
    return parsed.generated_at ?? null;
  } catch {
    return null;
  }
}

/** @param {{resultsPath?: string, pricesPath?: string, now?: Date}} [opts] */
export function computeModelBenchHealth({ resultsPath = RESULTS_PATH, pricesPath = PRICES_PATH, now } = {}) {
  const counter = getMonthlyCounter(now);
  return {
    ok: true,
    results_as_of: readResultsAsOf(resultsPath),
    prices_as_of: readPricesAsOf(pricesPath),
    calls_this_month: counter.calls,
    est_cost_this_month_usd: roundCostUsd(counter.cost_usd),
  };
}

/** @param {import('node:http').IncomingMessage} req
 *  @param {import('node:http').ServerResponse & {status: Function, json: Function}} res */
export default function handler(req, res) {
  // This page-specific health check reads the same in-memory counter
  // run-one.js writes to, so it shares that endpoint's rate limiter
  // rather than the Cost Meter's — both are public, read-only, abuse
  // control only (rule 6/8).
  const { allowed, retryAfterSeconds } = meterRateLimiter.check(clientIpFrom(req));
  if (!allowed) {
    res.setHeader('Retry-After', String(retryAfterSeconds));
    res.status(429).json({ error: 'Too many requests. Try again shortly.' });
    return;
  }

  res.status(200).json(computeModelBenchHealth());
}
