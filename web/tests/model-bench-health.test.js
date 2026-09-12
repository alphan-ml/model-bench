import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import handler, { readResultsAsOf, computeModelBenchHealth } from '../api/health.js';
import { incrementMonthlyCounter, _resetForTests as resetCounter } from '../api/model-bench-counter.js';
import { meterRateLimiter } from '../api/meter/rate-limit.js';
import { mockReq, mockRes } from './helpers/mock-http.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

beforeEach(() => {
  resetCounter();
  meterRateLimiter._reset();
});

describe('readResultsAsOf', () => {
  test('returns null instead of throwing when results.json does not exist yet (pre-Gate-1 state)', () => {
    assert.equal(readResultsAsOf('/nonexistent/results.json'), null);
  });

  test('returns null instead of throwing on invalid JSON', () => {
    const badJsonPath = path.join(__dirname, 'helpers', 'mock-http.js');
    assert.equal(readResultsAsOf(badJsonPath), null);
  });

  test('reads generated_at from a real results-shaped file', () => {
    const sampleResultsPath = path.join(__dirname, '..', '..', 'results.sample.json');
    const asOf = readResultsAsOf(sampleResultsPath);
    assert.equal(asOf, '2026-09-12T00:00:00+00:00');
  });
});

describe('computeModelBenchHealth', () => {
  test('is healthy-shaped even with no results.json and no calls yet', () => {
    const health = computeModelBenchHealth({ resultsPath: '/nonexistent/results.json', now: new Date('2026-09-12T00:00:00Z') });
    assert.equal(health.ok, true);
    assert.equal(health.results_as_of, null);
    assert.equal(health.calls_this_month, 0);
    assert.equal(health.est_cost_this_month_usd, 0);
  });

  test('reflects the monthly counter', () => {
    const now = new Date('2026-09-12T00:00:00Z');
    incrementMonthlyCounter(0.0001234, now);
    incrementMonthlyCounter(0.0002, now);
    const health = computeModelBenchHealth({ resultsPath: '/nonexistent/results.json', now });
    assert.equal(health.calls_this_month, 2);
    assert.equal(health.est_cost_this_month_usd, 0.000323); // rounded to 6 decimals, matches roundCostUsd
  });

  test('reads prices_as_of from the real data/prices.json', () => {
    const health = computeModelBenchHealth({ resultsPath: '/nonexistent/results.json' });
    assert.equal(health.prices_as_of, '2026-09-12');
  });
});

describe('GET /api/health handler', () => {
  test('200s with the model-bench health shape', () => {
    const req = mockReq('/api/health');
    const res = mockRes();
    handler(req, res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.ok, true);
    assert.ok('results_as_of' in res.body);
    assert.ok('prices_as_of' in res.body);
    assert.ok('calls_this_month' in res.body);
    assert.ok('est_cost_this_month_usd' in res.body);
  });

  test('429s once its shared rate limit is exceeded', () => {
    for (let i = 0; i < 60; i++) {
      handler(mockReq('/api/health'), mockRes());
    }
    const res = mockRes();
    handler(mockReq('/api/health'), res);
    assert.equal(res.statusCode, 429);
  });
});
