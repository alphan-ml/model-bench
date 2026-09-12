import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { computeCostUsd, roundCostUsd, COST_USD_DECIMALS } from '../api/meter/cost.js';
import pricesFixture from '../api/meter/fixtures/prices.fixture.json' with { type: 'json' };

const { models: PRICES } = pricesFixture;

describe('computeCostUsd', () => {
  test('hand-checked case: claude-haiku, normal input/output', () => {
    // (420 * 0.25 + 16 * 1.25) / 1e6 = (105 + 20) / 1e6 = 0.000125
    assert.equal(computeCostUsd(420, 16, PRICES['claude-haiku']), 0.000125);
  });

  test('hand-checked case: claude-sonnet, normal input/output', () => {
    // (2200 * 3.00 + 300 * 15.00) / 1e6 = (6600 + 4500) / 1e6 = 0.0111
    assert.equal(computeCostUsd(2200, 300, PRICES['claude-sonnet']), 0.0111);
  });

  test('zero-output row still costs for its input tokens', () => {
    // (400 * 0.10 + 0 * 0.30) / 1e6 = 0.00004 — a model that returned
    // nothing (see fixture event_id 3, an error row) still consumed input
    // tokens and so is not free.
    assert.equal(computeCostUsd(400, 0, PRICES['nova']), 0.00004);
  });

  test('a row with retries costs exactly the same as one without, given the same token counts', () => {
    // CallResult.retries (and usage_events.retries in the fixture) is
    // metadata about how many attempts a single logical call took — the
    // provider layer already resolved retries into the one row's actual
    // token counts before this function ever sees it, so retries must never
    // enter the cost formula itself.
    const withRetries = computeCostUsd(400, 20, PRICES['claude-haiku']);
    const withoutRetries = computeCostUsd(400, 20, PRICES['claude-haiku']);
    assert.equal(withRetries, withoutRetries);
    assert.equal(withRetries, 0.000125);
  });

  test('rejects a negative token count instead of silently returning a negative cost', () => {
    assert.throws(() => computeCostUsd(-1, 0, PRICES['claude-haiku']), TypeError);
    assert.throws(() => computeCostUsd(0, -1, PRICES['claude-haiku']), TypeError);
  });

  test('rejects a malformed price object', () => {
    assert.throws(() => computeCostUsd(100, 100, {}), TypeError);
    assert.throws(() => computeCostUsd(100, 100, null), TypeError);
  });
});

describe('roundCostUsd', () => {
  test(`rounds to ${COST_USD_DECIMALS} decimal places, matching NUMERIC(10,6)`, () => {
    assert.equal(roundCostUsd(0.00012345678), 0.000123);
    assert.equal(roundCostUsd(0.0001234999999), 0.000123);
  });

  test('does not perturb a value already at exactly 6 decimal places', () => {
    assert.equal(roundCostUsd(0.0111), 0.0111);
    assert.equal(roundCostUsd(0.005400), 0.0054);
  });
});
