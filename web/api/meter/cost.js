/**
 * Cost Meter — cost calculation.
 *
 * Per SPEC-cost-meter-and-angi-reuse.md section 1.1: "cost_usd is computed at
 * write time from prices.json (same file both builds read; one copy of
 * truth, vendored into web/ at build with its as_of)." This file holds the
 * one formula every write path (the Python runner, the Vercel run-one.js
 * function, and — later — the AREA provider layer) must use, so the ledger
 * and the per-model report can never silently disagree on how a dollar is
 * computed.
 *
 * The formula is the same one already used per-1,000-messages in
 * modelbench.metrics.cost_per_1k (model-bench/src/modelbench/metrics.py),
 * just evaluated for a single call's actual token counts rather than a
 * batch mean, and expressed in dollars (not dollars per 1k):
 *
 *   cost_usd = (input_tokens * input_per_1m + output_tokens * output_per_1m) / 1e6
 */

/** Number of decimal places usage_events.cost_usd is stored at (NUMERIC(10,6)
 * in schema.sql). Every cost this module returns is rounded to this many
 * places so a value computed here always matches what a real Postgres
 * NUMERIC(10,6) column would store — no silent extra floating-point digits
 * leaking into the ledger's arithmetic. */
export const COST_USD_DECIMALS = 6;

/**
 * @param {number} inputTokens - non-negative integer.
 * @param {number} outputTokens - non-negative integer. 0 is valid (a model
 *   that returned nothing still consumed input tokens and still costs
 *   something).
 * @param {{input_per_1m: number, output_per_1m: number}} price - one entry
 *   from prices.json's "models" list (or the fixture equivalent).
 * @returns {number} cost in US dollars, rounded to COST_USD_DECIMALS places.
 */
export function computeCostUsd(inputTokens, outputTokens, price) {
  if (!Number.isFinite(inputTokens) || inputTokens < 0) {
    throw new TypeError(`inputTokens must be a non-negative finite number, got ${inputTokens}`);
  }
  if (!Number.isFinite(outputTokens) || outputTokens < 0) {
    throw new TypeError(`outputTokens must be a non-negative finite number, got ${outputTokens}`);
  }
  if (!price || !Number.isFinite(price.input_per_1m) || !Number.isFinite(price.output_per_1m)) {
    throw new TypeError(
      `price must be {input_per_1m, output_per_1m} of finite numbers, got ${JSON.stringify(price)}`
    );
  }

  const raw = (inputTokens * price.input_per_1m + outputTokens * price.output_per_1m) / 1e6;
  return roundCostUsd(raw);
}

/** Rounds to COST_USD_DECIMALS places using round-half-up, matching how a
 * Postgres NUMERIC(10,6) column rounds on insert. Plain `Math.round` after a
 * power-of-ten scale is enough here — every value this module ever computes
 * is a small positive number, so binary floating-point edge cases (like
 * negative-zero or scale overflow) do not apply. */
export function roundCostUsd(value) {
  const scale = 10 ** COST_USD_DECIMALS;
  return Math.round((value + Number.EPSILON) * scale) / scale;
}
