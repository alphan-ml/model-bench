import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  validateLiveBoxInput, formatCents, formatLatency, callRunOne,
  answerRowHtml, answersTableHtml, MAX_TEXT_LENGTH,
} from '../model-bench-live-box.js';

describe('validateLiveBoxInput', () => {
  test('rejects empty input', () => {
    assert.equal(validateLiveBoxInput('').valid, false);
    assert.equal(validateLiveBoxInput('   ').valid, false);
  });

  test('accepts ordinary input', () => {
    assert.equal(validateLiveBoxInput('Where is my card?').valid, true);
  });

  test(`rejects input over ${MAX_TEXT_LENGTH} characters, per spec §7.2`, () => {
    const tooLong = 'a'.repeat(MAX_TEXT_LENGTH + 1);
    const result = validateLiveBoxInput(tooLong);
    assert.equal(result.valid, false);
    assert.match(result.error, /1000/);
  });

  test(`accepts input at exactly ${MAX_TEXT_LENGTH} characters`, () => {
    assert.equal(validateLiveBoxInput('a'.repeat(MAX_TEXT_LENGTH)).valid, true);
  });
});

describe('formatCents', () => {
  test('formats a small dollar cost as cents with 4 decimals', () => {
    assert.equal(formatCents(0.000042), '0.0042¢');
  });
  test('a zero cost still shows as a real 0, not blank', () => {
    assert.equal(formatCents(0), '0.0000¢');
  });
});

describe('formatLatency', () => {
  test('rounds to the nearest millisecond', () => {
    assert.equal(formatLatency(432.6), '433 ms');
  });
});

describe('callRunOne', () => {
  function fakeFetch(response) {
    return async () => response;
  }

  test('POSTs text and session_id as JSON to /api/run-one', async () => {
    let capturedUrl, capturedInit;
    const fetchImpl = async (url, init) => {
      capturedUrl = url;
      capturedInit = init;
      return { ok: true, status: 200, json: async () => ({ answers: [], prices_as_of: '2026-09-12' }) };
    };
    await callRunOne('hello', 'sess-123', fetchImpl);
    assert.equal(capturedUrl, '/api/run-one');
    assert.equal(capturedInit.method, 'POST');
    assert.deepEqual(JSON.parse(capturedInit.body), { text: 'hello', session_id: 'sess-123' });
  });

  test('returns the parsed JSON on success', async () => {
    const data = { answers: [{ key: 'nova' }], prices_as_of: '2026-09-12' };
    const result = await callRunOne('hi', 's1', fakeFetch({ ok: true, status: 200, json: async () => data }));
    assert.deepEqual(result, data);
  });

  test('throws the plain-word message on a non-OK response', async () => {
    await assert.rejects(
      () => callRunOne('hi', 's1', fakeFetch({ ok: false, status: 500 })),
      /The model service did not answer\. Try again\./
    );
  });

  test('throws a specific message on 429, using Retry-After when present', async () => {
    const res = { ok: false, status: 429, headers: { get: (h) => (h === 'Retry-After' ? '42' : null) } };
    await assert.rejects(() => callRunOne('hi', 's1', fakeFetch(res)), /42 seconds/);
  });

  test('throws the plain-word message when fetch itself rejects (network failure)', async () => {
    const fetchImpl = async () => { throw new Error('network down'); };
    await assert.rejects(() => callRunOne('hi', 's1', fetchImpl), /The model service did not answer\. Try again\./);
  });

  test('throws the plain-word message when the response body is not valid JSON', async () => {
    const fetchImpl = fakeFetch({ ok: true, status: 200, json: async () => { throw new Error('bad json'); } });
    await assert.rejects(() => callRunOne('hi', 's1', fetchImpl), /The model service did not answer\. Try again\./);
  });
});

describe('answerRowHtml / answersTableHtml', () => {
  test('renders a successful answer with intent, confidence, tokens, cost, latency', () => {
    const html = answerRowHtml({
      key: 'claude-haiku', intent: 'card_arrival', confidence: 87,
      input_tokens: 120, output_tokens: 12, cost_usd: 0.000042, latency_ms: 310.4,
    });
    assert.match(html, />claude-haiku</);
    assert.match(html, />card_arrival</);
    assert.match(html, />87</);
    assert.match(html, />120\/12</);
    assert.match(html, />0\.0042¢</);
    assert.match(html, />310 ms</);
  });

  test('renders a per-model error inline instead of intent/confidence', () => {
    const html = answerRowHtml({ key: 'llama', error: 'Model not yet configured (Gate 1 pending)' });
    assert.match(html, /class="error"/);
    assert.match(html, /Model not yet configured/);
    assert.doesNotMatch(html, /undefined/);
  });

  test('answersTableHtml handles an empty answers list without throwing', () => {
    assert.doesNotThrow(() => answersTableHtml([]));
    assert.match(answersTableHtml([]), /No answers yet/);
  });

  test('answersTableHtml renders one row per answer (plus the header row)', () => {
    const html = answersTableHtml([{ key: 'a', error: 'x' }, { key: 'b', error: 'y' }]);
    assert.equal((html.match(/<tr>/g) ?? []).length, 3, '1 header row + 2 answer rows');
  });
});
