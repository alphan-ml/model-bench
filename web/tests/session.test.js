import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeSession } from '../api/meter/session.js';
import handler from '../api/meter/session.js';
import { meterRateLimiter } from '../api/meter/rate-limit.js';
import { mockReq, mockRes } from './helpers/mock-http.js';
import fixture from '../api/meter/fixtures/usage_events.fixture.json' with { type: 'json' };

const EVENTS = fixture.events;

beforeEach(() => {
  meterRateLimiter._reset();
});

describe('summarizeSession', () => {
  test('returns only the requested session\'s rows', () => {
    const summary = summarizeSession(EVENTS, 'sess-aaa111');
    assert.equal(summary.session_id, 'sess-aaa111');
    assert.equal(summary.events.length, 3);
    for (const e of summary.events) {
      assert.ok(['text-to-intent', 'live-box'].includes(e.step));
    }
  });

  test('a session with several use-case steps totals correctly (sess-bbb222: 4 events)', () => {
    const summary = summarizeSession(EVENTS, 'sess-bbb222');
    assert.equal(summary.events.length, 4);
    assert.equal(summary.totals.calls, 4);
    // 0.005400 + 0.000140 + 0.011100 + 0.000275
    assert.equal(summary.totals.cost_usd, 0.016915);
    assert.equal(summary.totals.input_tokens, 1100 + 260 + 2200 + 900);
    assert.equal(summary.totals.output_tokens, 140 + 60 + 300 + 40);
  });

  test('an unknown session id returns an empty (not missing) itemized list', () => {
    const summary = summarizeSession(EVENTS, 'sess-does-not-exist');
    assert.deepEqual(summary.events, []);
    assert.deepEqual(summary.totals, { calls: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0 });
  });

  test('includes an error row in the itemized list with its error message intact', () => {
    const summary = summarizeSession(EVENTS, 'sess-aaa111');
    const errorRow = summary.events.find((e) => e.ok === false);
    assert.ok(errorRow, 'expected the fixture\'s one error row to be present');
    assert.equal(errorRow.error, 'empty response from model');
  });
});

describe('GET /api/meter/session handler', () => {
  test('200s with the itemized summary when id is provided', () => {
    const req = mockReq('/api/meter/session?id=sess-aaa111');
    const res = mockRes();
    handler(req, res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.session_id, 'sess-aaa111');
    assert.equal(res.body.events.length, 3);
  });

  test('reads id from Vercel-style req.query when present', () => {
    const req = mockReq('/api/meter/session', { query: { id: 'sess-bbb222' } });
    const res = mockRes();
    handler(req, res);
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.session_id, 'sess-bbb222');
  });

  test('400s when id is missing', () => {
    const req = mockReq('/api/meter/session');
    const res = mockRes();
    handler(req, res);
    assert.equal(res.statusCode, 400);
    assert.match(res.body.error, /id/);
  });

  test('429s once the per-IP rate limit is exceeded, with a Retry-After header', () => {
    const res = mockRes();
    for (let i = 0; i < 60; i++) {
      handler(mockReq('/api/meter/session?id=sess-aaa111'), mockRes());
    }
    handler(mockReq('/api/meter/session?id=sess-aaa111'), res);
    assert.equal(res.statusCode, 429);
    assert.ok(res.headers['Retry-After']);
  });
});
