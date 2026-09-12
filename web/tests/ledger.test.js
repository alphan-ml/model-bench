import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { aggregateLedger, parseWindowMs, percentile } from '../api/meter/ledger.js';
import handler from '../api/meter/ledger.js';
import { meterRateLimiter } from '../api/meter/rate-limit.js';
import { mockReq, mockRes } from './helpers/mock-http.js';
import fixture from '../api/meter/fixtures/usage_events.fixture.json' with { type: 'json' };

const EVENTS = fixture.events;
// A fixed "now" just after the fixture's latest event (2026-09-12T18:40:00Z)
// so window filtering is deterministic no matter when this suite runs.
const NOW = new Date('2026-09-12T20:00:00.000Z');

beforeEach(() => {
  meterRateLimiter._reset();
});

describe('parseWindowMs', () => {
  test('parses "30d" as 30 days in milliseconds', () => {
    assert.equal(parseWindowMs('30d'), 30 * 24 * 60 * 60 * 1000);
  });

  test('rejects an unsupported format', () => {
    assert.throws(() => parseWindowMs('1w'), RangeError);
    assert.throws(() => parseWindowMs('30'), RangeError);
  });
});

describe('percentile', () => {
  test('matches the hand-computed p50 of a small odd-length set', () => {
    assert.equal(percentile([100, 200, 300], 50), 200);
  });

  test('interpolates for an even-length set', () => {
    assert.equal(percentile([100, 200], 50), 150);
  });

  test('a single value is its own every percentile', () => {
    assert.equal(percentile([42], 50), 42);
    assert.equal(percentile([42], 95), 42);
  });

  test('an empty set is 0, not NaN or a thrown error', () => {
    assert.equal(percentile([], 50), 0);
  });
});

describe('aggregateLedger grouping sums match a hand-checked fixture', () => {
  test('group=use_case, window=30d: model-bench vs area totals', () => {
    const ledger = aggregateLedger(EVENTS, { window: '30d', group: 'use_case', now: NOW });
    const modelBench = ledger.rows.find((r) => r.key === 'model-bench');
    const area = ledger.rows.find((r) => r.key === 'area');

    // model-bench: events 1, 2, 3, 8 -> 0.000125 + 0.001560 + 0.000040 + 0.000125
    assert.equal(modelBench.calls, 4);
    assert.equal(modelBench.cost_usd, 0.00185);

    // area: events 4, 5, 6, 7 -> 0.005400 + 0.000140 + 0.011100 + 0.000275
    assert.equal(area.calls, 4);
    assert.equal(area.cost_usd, 0.016915);
  });

  test('group=step, window=30d: text-to-intent totals across both its sessions', () => {
    const ledger = aggregateLedger(EVENTS, { window: '30d', group: 'step', now: NOW });
    const textToIntent = ledger.rows.find((r) => r.key === 'text-to-intent');
    // events 1, 2, 8 are text-to-intent -> 0.000125 + 0.001560 + 0.000125
    assert.equal(textToIntent.calls, 3);
    assert.equal(textToIntent.cost_usd, 0.00181);
  });

  test('group=model: sums across use cases for the same model id', () => {
    const ledger = aggregateLedger(EVENTS, { window: '30d', group: 'model', now: NOW });
    const sonnet = ledger.rows.find((r) => r.key === 'anthropic.claude-3-5-sonnet-20240620-v1:0');
    // events 2, 4, 6 -> 0.001560 + 0.005400 + 0.011100
    assert.equal(sonnet.calls, 3);
    assert.equal(sonnet.cost_usd, 0.01806);
  });

  test('group=day: buckets by UTC calendar day', () => {
    const ledger = aggregateLedger(EVENTS, { window: '30d', group: 'day', now: NOW });
    const sep10 = ledger.rows.find((r) => r.key === '2026-09-10');
    const sep11 = ledger.rows.find((r) => r.key === '2026-09-11');
    const sep12 = ledger.rows.find((r) => r.key === '2026-09-12');
    assert.equal(sep10.calls, 3); // events 1, 2, 3
    assert.equal(sep11.calls, 4); // events 4, 5, 6, 7
    assert.equal(sep12.calls, 1); // event 8
  });

  test('p50 latency excludes error (ok=false) rows, matching modelbench.metrics.latency_p50_p95', () => {
    // model-bench group's rows are events 1 (612ms, ok), 2 (980ms, ok),
    // 3 (340ms, NOT ok — excluded), 8 (5200ms, ok). p50 of [612, 980, 5200].
    const ledger = aggregateLedger(EVENTS, { window: '30d', group: 'use_case', now: NOW });
    const modelBench = ledger.rows.find((r) => r.key === 'model-bench');
    assert.equal(modelBench.p50_latency_ms, 980);
  });

  test('a narrow window excludes events outside it', () => {
    // NOW is 2026-09-12T20:00:00Z; a 1-day window reaches back to
    // 2026-09-11T20:00:00Z, which only event 8 (2026-09-12T18:40:00Z) is inside.
    const ledger = aggregateLedger(EVENTS, { window: '1d', group: 'use_case', now: NOW });
    assert.equal(ledger.rows.length, 1);
    assert.equal(ledger.rows[0].key, 'model-bench');
    assert.equal(ledger.rows[0].calls, 1);
  });

  test('rejects an unsupported group', () => {
    assert.throws(() => aggregateLedger(EVENTS, { group: 'nonsense', now: NOW }), RangeError);
  });
});

describe('GET /api/meter/ledger handler', () => {
  test('200s with default window/group when none given', () => {
    const req = mockReq('/api/meter/ledger');
    const res = mockRes();
    handler(req, res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.window, '30d');
    assert.equal(res.body.group, 'day');
  });

  test('reads window and group from the query string', () => {
    const req = mockReq('/api/meter/ledger?window=1d&group=step');
    const res = mockRes();
    handler(req, res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.window, '1d');
    assert.equal(res.body.group, 'step');
  });

  test('400s on an invalid group rather than 500ing', () => {
    const req = mockReq('/api/meter/ledger?group=nonsense');
    const res = mockRes();
    handler(req, res);
    assert.equal(res.statusCode, 400);
    assert.ok(res.body.error);
  });
});
