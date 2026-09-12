/**
 * Every one of these cases mirrors a case in tests/test_prompt.py (the
 * Python side) exactly, by design: this file exists to prove the JS port
 * behaves identically to the Python original it was ported from, not just
 * that it behaves *reasonably*.
 */
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { buildPrompt, parseModelResponse } from '../api/model-bench-prompt.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..', '..');
const TEMPLATE = readFileSync(path.join(REPO_ROOT, 'data', 'prompt.txt'), 'utf8');

const ALLOWED = ['card_arrival', 'top_up_failed', 'exchange_rate'];

describe('parseModelResponse', () => {
  test('valid JSON', () => {
    const parsed = parseModelResponse('{"intent": "card_arrival", "confidence": 87}', ALLOWED);
    assert.equal(parsed.intent, 'card_arrival');
    assert.equal(parsed.confidence, 87);
    assert.equal(parsed.invalid, false);
  });

  test('fenced JSON', () => {
    const parsed = parseModelResponse('```json\n{"intent": "top_up_failed", "confidence": 55}\n```', ALLOWED);
    assert.equal(parsed.intent, 'top_up_failed');
    assert.equal(parsed.confidence, 55);
    assert.equal(parsed.invalid, false);
  });

  test('fenced JSON, no language tag', () => {
    const parsed = parseModelResponse('```\n{"intent": "exchange_rate", "confidence": 10}\n```', ALLOWED);
    assert.equal(parsed.intent, 'exchange_rate');
    assert.equal(parsed.invalid, false);
  });

  test('JSON with trailing text', () => {
    const parsed = parseModelResponse('{"intent": "card_arrival", "confidence": 90} thanks, hope that helps!', ALLOWED);
    assert.equal(parsed.intent, 'card_arrival');
    assert.equal(parsed.confidence, 90);
    assert.equal(parsed.invalid, false);
  });

  test('JSON with leading text', () => {
    const parsed = parseModelResponse('Sure, here is my answer: {"intent": "card_arrival", "confidence": 90}', ALLOWED);
    assert.equal(parsed.intent, 'card_arrival');
    assert.equal(parsed.invalid, false);
  });

  test('label not in the allowed set', () => {
    const parsed = parseModelResponse('{"intent": "not_a_real_label", "confidence": 80}', ALLOWED);
    assert.equal(parsed.intent, null);
    assert.equal(parsed.invalid, true);
    assert.equal(parsed.confidence, 80, 'confidence is still parsed out even though the label is invalid');
  });

  test('empty string', () => {
    const parsed = parseModelResponse('', ALLOWED);
    assert.equal(parsed.intent, null);
    assert.equal(parsed.confidence, null);
    assert.equal(parsed.invalid, true);
    assert.equal(parsed.raw, '');
  });

  test('null input does not throw', () => {
    assert.doesNotThrow(() => parseModelResponse(null, ALLOWED));
    assert.equal(parseModelResponse(null, ALLOWED).invalid, true);
  });

  test('garbage non-JSON does not throw', () => {
    const parsed = parseModelResponse('the model refused to answer today', ALLOWED);
    assert.equal(parsed.intent, null);
    assert.equal(parsed.invalid, true);
  });

  test('confidence out of range high is clamped to 100', () => {
    const parsed = parseModelResponse('{"intent": "card_arrival", "confidence": 250}', ALLOWED);
    assert.equal(parsed.intent, 'card_arrival');
    assert.equal(parsed.confidence, 100);
    assert.equal(parsed.invalid, false);
  });

  test('confidence out of range negative is clamped to 0', () => {
    const parsed = parseModelResponse('{"intent": "card_arrival", "confidence": -30}', ALLOWED);
    assert.equal(parsed.confidence, 0);
  });

  test('confidence missing is null but not invalid', () => {
    const parsed = parseModelResponse('{"intent": "card_arrival"}', ALLOWED);
    assert.equal(parsed.intent, 'card_arrival');
    assert.equal(parsed.confidence, null);
    assert.equal(parsed.invalid, false);
  });

  test('confidence wrong type is null', () => {
    const parsed = parseModelResponse('{"intent": "card_arrival", "confidence": "very sure"}', ALLOWED);
    assert.equal(parsed.confidence, null);
    assert.equal(parsed.invalid, false);
  });

  test('confidence as a boolean is null, not 0/1 (JS/Python parity)', () => {
    const parsed = parseModelResponse('{"intent": "card_arrival", "confidence": true}', ALLOWED);
    assert.equal(parsed.confidence, null);
  });

  test('malformed JSON does not throw', () => {
    const parsed = parseModelResponse('{"intent": "card_arrival", "confidence": 80', ALLOWED); // missing closing brace
    assert.equal(parsed.invalid, true);
  });
});

describe('buildPrompt', () => {
  test('contains all intents and the message text', () => {
    const prompt = buildPrompt('Where is my card?', ALLOWED, TEMPLATE);
    for (const intent of ALLOWED) {
      assert.ok(prompt.includes(intent));
    }
    assert.ok(prompt.includes('Where is my card?'));
    assert.ok(prompt.includes('JSON'));
  });

  test('reading data/prompt.txt and substituting matches the byte-shared template contract', () => {
    // This is the exact operation run-one.js performs against the exact
    // file Python's scripts_export_prompt.py writes -- if this ever
    // produces different text than modelbench.prompt.build_prompt() would
    // for the same inputs, the two languages would silently send
    // different prompts to the model.
    const prompt = buildPrompt('Where is my card?', ALLOWED, TEMPLATE);
    assert.ok(prompt.startsWith("You are sorting a customer's banking message"));
    assert.ok(prompt.includes('Categories:\n- card_arrival\n- top_up_failed\n- exchange_rate'));
    assert.ok(prompt.endsWith('Customer message:\nWhere is my card?\n'));
  });
});
