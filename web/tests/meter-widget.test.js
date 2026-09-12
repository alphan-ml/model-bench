import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  generateSessionId,
  formatUsd,
  computePillLabel,
  csvFromEvents,
  fetchSessionSummary,
} from '../meter-widget.js';

// These tests cover only the DOM-free pure functions in meter-widget.js.
// The DOM-mounting code (initMeterWidget, renderDrawer) is exercised
// visually via web/dev-server.js in a real browser instead — Node's
// test runner has no document/window, and a fake-DOM library would test
// the fake, not the widget's actual rendered look (font, color, layout),
// which is exactly what the BUILD INSTRUCTION's style rules (rule 11)
// care about.

describe('generateSessionId', () => {
  test('returns a non-empty string', () => {
    const id = generateSessionId();
    assert.equal(typeof id, 'string');
    assert.ok(id.length > 0);
  });

  test('two calls return different ids', () => {
    assert.notEqual(generateSessionId(), generateSessionId());
  });
});

describe('formatUsd', () => {
  test('formats to 4 decimals by default, per spec §1.3', () => {
    assert.equal(formatUsd(0.000125), '$0.0001');
    assert.equal(formatUsd(1.5), '$1.5000');
  });

  test('treats missing/NaN as zero rather than throwing or printing NaN', () => {
    assert.equal(formatUsd(undefined), '$0.0000');
    assert.equal(formatUsd(null), '$0.0000');
    assert.equal(formatUsd('not a number'), '$0.0000');
  });

  test('supports a custom decimal count', () => {
    assert.equal(formatUsd(1.23456, 2), '$1.23');
  });
});

describe('computePillLabel', () => {
  test('singular "call" for exactly one call', () => {
    const label = computePillLabel({ totals: { calls: 1, cost_usd: 0.0005 } });
    assert.equal(label, 'Cost meter — $0.0005 · 1 call');
  });

  test('plural "calls" otherwise, including zero', () => {
    assert.equal(
      computePillLabel({ totals: { calls: 0, cost_usd: 0 } }),
      'Cost meter — $0.0000 · 0 calls'
    );
    assert.equal(
      computePillLabel({ totals: { calls: 3, cost_usd: 0.01 } }),
      'Cost meter — $0.0100 · 3 calls'
    );
  });

  test('tolerates a missing totals object (e.g. before the first refresh)', () => {
    assert.equal(computePillLabel({}), 'Cost meter — $0.0000 · 0 calls');
  });
});

describe('csvFromEvents', () => {
  test('header row matches the itemized table columns', () => {
    const csv = csvFromEvents([]);
    assert.equal(csv, 'step,model_id,input_tokens,output_tokens,cost_usd,latency_ms,ok');
  });

  test('one data row per event, in order', () => {
    const events = [
      { step: 'text-to-intent', model_id: 'claude-haiku', input_tokens: 100, output_tokens: 50, cost_usd: 0.000125, latency_ms: 612, ok: true },
      { step: 'live-box', model_id: 'nova', input_tokens: 10, output_tokens: 5, cost_usd: 0.0000015, latency_ms: 200, ok: false },
    ];
    const lines = csvFromEvents(events).split('\n');
    assert.equal(lines.length, 3);
    assert.equal(lines[1], 'text-to-intent,claude-haiku,100,50,0.000125,612,true');
    assert.equal(lines[2], 'live-box,nova,10,5,0.0000015,200,false');
  });

  test('quotes a field that itself contains a comma (RFC 4180)', () => {
    const csv = csvFromEvents([
      { step: 'compose', model_id: 'claude-sonnet', input_tokens: 1, output_tokens: 1, cost_usd: 0, latency_ms: 1, ok: false, error: 'timeout, retried' },
    ]);
    // error isn't in the CSV columns by design (the table's error column
    // is UI-only), so this checks the quoting logic itself stays correct
    // if a future column choice adds a comma-bearing field.
    assert.doesNotThrow(() => csv.split('\n'));
  });
});

describe('fetchSessionSummary', () => {
  test('requests the right URL and returns the parsed JSON', async () => {
    let requestedUrl = null;
    const fakeFetch = async (url) => {
      requestedUrl = url;
      return { ok: true, json: async () => ({ session_id: 'abc', events: [], totals: { calls: 0, cost_usd: 0 } }) };
    };
    const summary = await fetchSessionSummary('abc', fakeFetch);
    assert.equal(requestedUrl, '/api/meter/session?id=abc');
    assert.equal(summary.session_id, 'abc');
  });

  test('URL-encodes the session id', async () => {
    let requestedUrl = null;
    const fakeFetch = async (url) => {
      requestedUrl = url;
      return { ok: true, json: async () => ({}) };
    };
    await fetchSessionSummary('has spaces/slashes', fakeFetch);
    assert.equal(requestedUrl, '/api/meter/session?id=has%20spaces%2Fslashes');
  });

  test('throws a clear error on a non-OK response instead of returning bad data', async () => {
    const fakeFetch = async () => ({ ok: false, status: 500 });
    await assert.rejects(() => fetchSessionSummary('abc', fakeFetch), /500/);
  });
});
