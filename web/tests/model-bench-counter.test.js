import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  logUsageEvent, getLoggedEvents, incrementMonthlyCounter, getMonthlyCounter, _resetForTests,
} from '../api/model-bench-counter.js';

beforeEach(() => {
  _resetForTests();
});

describe('logUsageEvent / getLoggedEvents', () => {
  test('records an event with a ts stamped on', () => {
    logUsageEvent({ session_id: 's1', use_case: 'model-bench', step: 'text-to-intent' });
    const events = getLoggedEvents();
    assert.equal(events.length, 1);
    assert.equal(events[0].session_id, 's1');
    assert.ok(events[0].ts);
  });

  test('caps the in-memory list rather than growing unbounded', () => {
    for (let i = 0; i < 600; i++) {
      logUsageEvent({ session_id: `s${i}` });
    }
    assert.ok(getLoggedEvents().length <= 500);
  });
});

describe('incrementMonthlyCounter / getMonthlyCounter', () => {
  test('starts at zero', () => {
    assert.deepEqual(getMonthlyCounter(new Date('2026-09-12T00:00:00Z')), { calls: 0, cost_usd: 0 });
  });

  test('accumulates calls and cost within the same UTC month', () => {
    const now = new Date('2026-09-12T00:00:00Z');
    incrementMonthlyCounter(0.01, now);
    incrementMonthlyCounter(0.02, now);
    const counter = getMonthlyCounter(now);
    assert.equal(counter.calls, 2);
    assert.ok(Math.abs(counter.cost_usd - 0.03) < 1e-9);
  });

  test('resets when the UTC month rolls over', () => {
    incrementMonthlyCounter(1, new Date('2026-09-30T23:00:00Z'));
    assert.equal(getMonthlyCounter(new Date('2026-10-01T00:00:01Z')).calls, 0);
  });

  test('a non-numeric cost is treated as 0 rather than producing NaN', () => {
    const now = new Date('2026-09-12T00:00:00Z');
    incrementMonthlyCounter(undefined, now);
    assert.equal(getMonthlyCounter(now).cost_usd, 0);
  });
});
