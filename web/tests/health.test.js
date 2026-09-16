import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { computeHealth, readPricesAsOf } from '../api/meter/health.js';
import handler from '../api/meter/health.js';
import { meterRateLimiter } from '../api/meter/rate-limit.js';
import { mockReq, mockRes } from './helpers/mock-http.js';
import fixture from '../api/meter/fixtures/usage_events.fixture.json' with { type: 'json' };
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';

const EVENTS = fixture.events;
const __dirname = path.dirname(fileURLToPath(import.meta.url));

beforeEach(() => {
  meterRateLimiter._reset();
});

describe('computeHealth', () => {
  test('last_event_ts is the latest event regardless of fixture order', () => {
    const health = computeHealth(EVENTS, { now: new Date('2026-09-12T20:00:00Z') });
    assert.equal(health.last_event_ts, '2026-09-12T18:40:00.000Z');
  });

  test('rows_this_month and est_month_to_date_cost_usd only count the current UTC month', () => {
    // All 8 fixture events fall in September 2026.
    const health = computeHealth(EVENTS, { now: new Date('2026-09-12T20:00:00Z') });
    assert.equal(health.rows_this_month, 8);
    const expectedTotal = EVENTS.reduce((sum, e) => sum + e.cost_usd, 0);
    assert.ok(Math.abs(health.est_month_to_date_cost_usd - expectedTotal) < 1e-9);
  });

  test('a "now" in the next month counts zero rows for that new month', () => {
    const health = computeHealth(EVENTS, { now: new Date('2026-10-01T00:00:01Z') });
    assert.equal(health.rows_this_month, 0);
    assert.equal(health.est_month_to_date_cost_usd, 0);
  });

  test('passes prices_as_of through unchanged', () => {
    const health = computeHealth(EVENTS, { now: new Date('2026-09-12T20:00:00Z'), pricesAsOf: '2026-09-12' });
    assert.equal(health.prices_as_of, '2026-09-12');
  });

  test('an empty event list is healthy-shaped, not an error', () => {
    const health = computeHealth([], { now: new Date('2026-09-12T20:00:00Z') });
    assert.equal(health.ok, true);
    assert.equal(health.last_event_ts, null);
    assert.equal(health.rows_this_month, 0);
  });
});

describe('readPricesAsOf', () => {
  test('reads the real model-bench/data/prices.json as_of date', () => {
    const realPricesPath = path.join(__dirname, '..', '..', 'data', 'prices.json');
    const asOf = readPricesAsOf(realPricesPath);
    // Read the real committed as_of directly rather than hardcoding it, so
    // this test stays correct as data/prices.json is updated over time.
    const expected = JSON.parse(readFileSync(realPricesPath, 'utf8')).as_of;
    assert.equal(asOf, expected);
  });

  test('returns null instead of throwing when the file is missing', () => {
    assert.equal(readPricesAsOf('/nonexistent/path/prices.json'), null);
  });

  test('returns null instead of throwing when the file is not valid JSON', () => {
    const badJsonPath = path.join(__dirname, 'helpers', 'mock-http.js'); // any non-JSON file
    assert.equal(readPricesAsOf(badJsonPath), null);
  });
});

describe('GET /api/meter/health handler', () => {
  test('200s with the health shape', () => {
    const req = mockReq('/api/meter/health');
    const res = mockRes();
    handler(req, res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.ok, true);
    assert.ok('rows_this_month' in res.body);
    assert.ok('est_month_to_date_cost_usd' in res.body);
    assert.ok('prices_as_of' in res.body);
  });
});
