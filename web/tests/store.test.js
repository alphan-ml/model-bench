import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { getAllEvents, getEventsForSession, _resetCacheForTests } from '../api/meter/store.js';
import fixture from '../api/meter/fixtures/usage_events.fixture.json' with { type: 'json' };

describe('getAllEvents', () => {
  test('reads every row from the fixture file', () => {
    const events = getAllEvents();
    assert.equal(events.length, fixture.events.length);
  });

  test('caches after the first read (repeated calls return the same array reference)', () => {
    _resetCacheForTests();
    const first = getAllEvents();
    const second = getAllEvents();
    assert.strictEqual(first, second);
  });
});

describe('getEventsForSession', () => {
  test('returns only rows for that session, in fixture order', () => {
    const rows = getEventsForSession('sess-bbb222');
    assert.equal(rows.length, 4);
    assert.ok(rows.every((r) => r.session_id === 'sess-bbb222'));
  });

  test('an unknown session returns an empty array, not null/undefined', () => {
    assert.deepEqual(getEventsForSession('no-such-session'), []);
  });
});
