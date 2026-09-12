import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  computeInsights,
  formatPercent,
  insightBullets,
  dayRowsToBars,
  keyRowsToBars,
  stepRowsToCostPerAnswerBars,
  loadLedgerData,
} from '../cost-ledger.js';

// render() itself (the only DOM-touching export of cost-ledger.js) is
// verified visually in a real browser via web/dev-server.js, not here —
// Node's test runner has no document, and the page's whole point is how
// it actually renders (fonts, chart layout, colors per BUILD INSTRUCTION
// rule 11), which a fake DOM can't confirm either.

const HEALTH = { est_month_to_date_cost_usd: 0.0186, prices_as_of: '2026-09-12' };
const BY_USE_CASE = { rows: [
  { key: 'model-bench', calls: 4, cost_usd: 0.00185 },
  { key: 'area', calls: 4, cost_usd: 0.016915 },
] };
const BY_STEP = { rows: [
  { key: 'text-to-intent', calls: 3, cost_usd: 0.00181 },
  { key: 'compose', calls: 1, cost_usd: 0.0054 },
  { key: 'verify', calls: 1, cost_usd: 0.00014 },
] };

describe('computeInsights', () => {
  test('pulls month-to-date cost and prices_as_of straight from health', () => {
    const insights = computeInsights({ health: HEALTH, byUseCase: BY_USE_CASE, byStep: BY_STEP });
    assert.equal(insights.monthToDateCostUsd, 0.0186);
    assert.equal(insights.pricesAsOf, '2026-09-12');
  });

  test('finds the cheapest and dearest step by cost PER ANSWER (cost_usd / calls), not raw total', () => {
    const insights = computeInsights({ health: HEALTH, byUseCase: BY_USE_CASE, byStep: BY_STEP });
    // per-answer: text-to-intent 0.00181/3=0.0006033, compose 0.0054/1=0.0054, verify 0.00014/1=0.00014
    assert.equal(insights.cheapestStep.key, 'verify');
    assert.equal(insights.dearestStep.key, 'compose');
  });

  test('computes each use case\'s share of total cost, summing to 1', () => {
    const insights = computeInsights({ health: HEALTH, byUseCase: BY_USE_CASE, byStep: BY_STEP });
    const totalShare = insights.shareByUseCase.reduce((sum, s) => sum + s.share, 0);
    assert.ok(Math.abs(totalShare - 1) < 1e-9);
  });

  test('handles an empty ledger (no rows yet) without throwing', () => {
    const insights = computeInsights({
      health: { est_month_to_date_cost_usd: 0, prices_as_of: null },
      byUseCase: { rows: [] },
      byStep: { rows: [] },
    });
    assert.equal(insights.cheapestStep, null);
    assert.equal(insights.dearestStep, null);
    assert.deepEqual(insights.shareByUseCase, []);
  });
});

describe('formatPercent', () => {
  test('rounds a fraction to a whole-number percentage', () => {
    assert.equal(formatPercent(0.6183), '62%');
    assert.equal(formatPercent(0), '0%');
    assert.equal(formatPercent(1), '100%');
  });
});

describe('insightBullets', () => {
  test('produces one bullet per fact, in the spec\'s order', () => {
    const insights = computeInsights({ health: HEALTH, byUseCase: BY_USE_CASE, byStep: BY_STEP });
    const bullets = insightBullets(insights);
    assert.equal(bullets.length, 4);
    assert.match(bullets[0], /Month-to-date cost: \$0\.0186/);
    assert.match(bullets[1], /Cheapest step per answer: verify/);
    assert.match(bullets[2], /Dearest step per answer: compose/);
    assert.match(bullets[3], /Share of cost by use case:/);
  });
});

describe('dayRowsToBars', () => {
  test('sorts chronologically and formats each day distinctly ("Mon D" — D16, see charts.js)', () => {
    const bars = dayRowsToBars({ rows: [
      { key: '2026-09-12', cost_usd: 0.0001 },
      { key: '2026-09-10', cost_usd: 0.002 },
      { key: '2026-09-11', cost_usd: 0.017 },
    ] });
    // All three days share a month, so this is exactly the case where
    // "Mon YY" (the spec's literal text) would collapse to three
    // identical "Sep 26" labels — the reason for D16's "Mon D" choice.
    assert.deepEqual(bars.map((b) => b.label), ['Sep 10', 'Sep 11', 'Sep 12']);
    assert.deepEqual(bars.map((b) => b.value), [0.002, 0.017, 0.0001]);
  });
});

describe('keyRowsToBars', () => {
  test('maps key/cost_usd straight to label/value', () => {
    assert.deepEqual(keyRowsToBars(BY_USE_CASE.rows), [
      { label: 'model-bench', value: 0.00185 },
      { label: 'area', value: 0.016915 },
    ]);
  });
});

describe('stepRowsToCostPerAnswerBars', () => {
  test('divides cost_usd by calls per row', () => {
    const bars = stepRowsToCostPerAnswerBars(BY_STEP.rows);
    const compose = bars.find((b) => b.label === 'compose');
    assert.ok(Math.abs(compose.value - 0.0054) < 1e-9);
  });

  test('excludes a step with zero calls (would divide by zero)', () => {
    const bars = stepRowsToCostPerAnswerBars([{ key: 'ghost-step', calls: 0, cost_usd: 0 }]);
    assert.deepEqual(bars, []);
  });
});

describe('loadLedgerData', () => {
  test('fetches health plus all four ledger groupings, over a 30d window', async () => {
    const requested = [];
    const fakeFetch = async (url) => {
      requested.push(url);
      return { ok: true, json: async () => ({ rows: [] }) };
    };
    await loadLedgerData(fakeFetch);
    assert.deepEqual(requested.sort(), [
      '/api/meter/health',
      '/api/meter/ledger?window=30d&group=day',
      '/api/meter/ledger?window=30d&group=model',
      '/api/meter/ledger?window=30d&group=step',
      '/api/meter/ledger?window=30d&group=use_case',
    ].sort());
  });

  test('propagates a failed request as a rejected promise, not silent bad data', async () => {
    const fakeFetch = async () => ({ ok: false, status: 500 });
    await assert.rejects(() => loadLedgerData(fakeFetch));
  });
});
