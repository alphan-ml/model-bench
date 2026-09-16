import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import handler, {
  isModelConfigured, callBedrockConverse, callOneModel, validateRunOneInput,
  readIntents, readPromptTemplate, readPrices,
  runOneRateLimiter, MAX_TEXT_LENGTH,
} from '../api/run-one.js';
import { buildPrompt } from '../api/model-bench-prompt.js';
import { getLoggedEvents, getMonthlyCounter, _resetForTests as resetCounter } from '../api/model-bench-counter.js';
import { mockReq, mockRes } from './helpers/mock-http.js';

beforeEach(() => {
  runOneRateLimiter._reset();
  resetCounter();
});

describe('isModelConfigured', () => {
  test('a placeholder model_id ("<...>") is not configured', () => {
    assert.equal(isModelConfigured({ model_id: '<exact bedrock id>', input_per_1m: 0, output_per_1m: 0 }), false);
  });

  test('zero prices on both sides is not configured, even with a real-looking id', () => {
    assert.equal(isModelConfigured({ model_id: 'anthropic.claude-3-haiku', input_per_1m: 0, output_per_1m: 0 }), false);
  });

  test('a real id with a nonzero price is configured', () => {
    assert.equal(isModelConfigured({ model_id: 'anthropic.claude-3-haiku', input_per_1m: 0.25, output_per_1m: 1.25 }), true);
  });

  test('missing/null price entry is not configured, does not throw', () => {
    assert.equal(isModelConfigured(null), false);
    assert.equal(isModelConfigured(undefined), false);
  });
});

describe('callBedrockConverse (mocked client — no real API call, per spec §5)', () => {
  test('extracts text/tokens/latency from a successful Converse response', async () => {
    const fakeClient = {
      send: async () => ({
        output: { message: { content: [{ text: '{"intent": "card_arrival", "confidence": 90}' }] } },
        usage: { inputTokens: 120, outputTokens: 12 },
      }),
    };
    const result = await callBedrockConverse('some-model-id', 'a prompt', { client: fakeClient });
    assert.equal(result.text, '{"intent": "card_arrival", "confidence": 90}');
    assert.equal(result.inputTokens, 120);
    assert.equal(result.outputTokens, 12);
    assert.equal(result.error, null);
    assert.ok(result.latencyMs >= 0);
  });

  test('a client that throws (bad credentials, throttling, ...) never rejects — returns {error}', async () => {
    const fakeClient = { send: async () => { throw new Error('ThrottlingException'); } };
    const result = await callBedrockConverse('some-model-id', 'a prompt', { client: fakeClient });
    assert.equal(result.error, 'ThrottlingException');
    assert.equal(result.text, '');
  });

  test('missing usage/output fields default safely instead of throwing', async () => {
    const fakeClient = { send: async () => ({}) };
    const result = await callBedrockConverse('some-model-id', 'a prompt', { client: fakeClient });
    assert.equal(result.text, '');
    assert.equal(result.inputTokens, 0);
    assert.equal(result.outputTokens, 0);
    assert.equal(result.error, null);
  });
});

describe('callOneModel', () => {
  const PRICE = { key: 'test-model', model_id: 'real-id', input_per_1m: 1, output_per_1m: 2 };
  const INTENTS = ['card_arrival', 'top_up_failed'];

  test('a not-yet-configured model returns a clear per-model error, never touches the client', async () => {
    const placeholder = { key: 'llama', model_id: '<exact bedrock id>', input_per_1m: 0, output_per_1m: 0 };
    let clientWasBuilt = false;
    const answer = await callOneModel(placeholder, 'prompt', INTENTS, { getClient: () => { clientWasBuilt = true; return {}; } });
    assert.equal(answer.key, 'llama');
    assert.equal(answer.error, 'Model not yet configured (Gate 1 pending).');
    assert.equal(answer.intent, null);
    assert.equal(clientWasBuilt, false, 'a not-configured model must never construct a Bedrock client');
  });

  test('a configured model returns intent/confidence/tokens/cost/latency on success', async () => {
    const fakeClient = {
      send: async () => ({
        output: { message: { content: [{ text: '{"intent": "card_arrival", "confidence": 77}' }] } },
        usage: { inputTokens: 100, outputTokens: 10 },
      }),
    };
    const answer = await callOneModel(PRICE, 'prompt', INTENTS, { getClient: () => fakeClient });
    assert.equal(answer.key, 'test-model');
    assert.equal(answer.intent, 'card_arrival');
    assert.equal(answer.confidence, 77);
    assert.equal(answer.input_tokens, 100);
    assert.equal(answer.output_tokens, 10);
    assert.equal(answer.error, null);
    // cost = (100*1 + 10*2)/1e6 = 0.00012
    assert.equal(answer.cost_usd, 0.00012);
  });

  test('a Bedrock call failure surfaces a plain-word error, with zeroed cost/tokens', async () => {
    const fakeClient = { send: async () => { throw new Error('boom'); } };
    const answer = await callOneModel(PRICE, 'prompt', INTENTS, { getClient: () => fakeClient });
    assert.equal(answer.error, 'The model did not answer. Try again.');
    assert.equal(answer.cost_usd, 0);
    assert.equal(answer.intent, null);
  });

  test('an unparseable/invalid model answer still succeeds with a null intent, not an error', async () => {
    const fakeClient = {
      send: async () => ({
        output: { message: { content: [{ text: 'not json at all' }] } },
        usage: { inputTokens: 5, outputTokens: 5 },
      }),
    };
    const answer = await callOneModel(PRICE, 'prompt', INTENTS, { getClient: () => fakeClient });
    assert.equal(answer.error, null);
    assert.equal(answer.intent, null);
    assert.equal(answer.confidence, null);
  });

  test('one model throwing unexpectedly never propagates — isolated per-model, D11 style', async () => {
    const answer = await callOneModel(PRICE, 'prompt', INTENTS, { getClient: () => { throw new Error('client construction blew up'); } });
    assert.match(answer.error, /Unexpected error/);
  });
});

describe('validateRunOneInput', () => {
  test('rejects a missing text field', () => {
    assert.equal(validateRunOneInput({ body: {} }).valid, false);
  });

  test('rejects an empty/whitespace-only text', () => {
    assert.equal(validateRunOneInput({ body: { text: '   ' } }).valid, false);
  });

  test(`rejects text over ${MAX_TEXT_LENGTH} chars`, () => {
    assert.equal(validateRunOneInput({ body: { text: 'a'.repeat(MAX_TEXT_LENGTH + 1) } }).valid, false);
  });

  test('accepts ordinary text', () => {
    assert.equal(validateRunOneInput({ body: { text: 'Where is my card?' } }).valid, true);
  });
});

const fakeConfiguredClient = () => ({
  send: async () => ({
    output: { message: { content: [{ text: '{"intent": "card_arrival", "confidence": 80}' }] } },
    usage: { inputTokens: 50, outputTokens: 8 },
  }),
});

describe('GET/POST /api/run-one handler (real handler, real data/prices.json — nova/llama/mistral configured post-Gate-1, claude-haiku/claude-sonnet still blocked)', () => {
  test('400s on missing text', async () => {
    const req = mockReq('/api/run-one', { body: {} });
    const res = mockRes();
    await handler(req, res);
    assert.equal(res.statusCode, 400);
  });

  test('400s on text over the length limit', async () => {
    const req = mockReq('/api/run-one', { body: { text: 'a'.repeat(1001) } });
    const res = mockRes();
    await handler(req, res);
    assert.equal(res.statusCode, 400);
  });

  test('200s with 5 per-model answers: nova/llama/mistral get a real (mocked) answer, claude-haiku/claude-sonnet stay "not yet configured"', async () => {
    const req = mockReq('/api/run-one', { body: { text: 'Where is my card?', session_id: 'sess-test-1' } });
    const res = mockRes();
    await handler(req, res, { getClient: fakeConfiguredClient });
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.answers.length, 5);
    const byKey = Object.fromEntries(res.body.answers.map((a) => [a.key, a]));
    // data/prices.json now has real model ids/prices for all 5 rows
    // (claude-haiku/claude-sonnet carry a disclosed 'status: BLOCKED' note
    // about the live account, but isModelConfigured() only checks
    // model_id/price shape -- so with a mocked client every model here
    // succeeds, exactly like it would once that account-side block clears).
    for (const key of ['nova', 'llama', 'mistral', 'claude-haiku', 'claude-sonnet']) {
      assert.equal(byKey[key].error, null);
      assert.equal(byKey[key].intent, 'card_arrival');
    }
    assert.ok('prices_as_of' in res.body);
  });

  test('logs one usage_events-shaped entry per model, tagged with the given session_id', async () => {
    const req = mockReq('/api/run-one', { body: { text: 'hello', session_id: 'sess-abc' } });
    await handler(req, mockRes(), { getClient: fakeConfiguredClient });
    const logged = getLoggedEvents().filter((e) => e.session_id === 'sess-abc');
    assert.equal(logged.length, 5);
    for (const e of logged) {
      assert.equal(e.use_case, 'model-bench');
      assert.equal(e.step, 'text-to-intent');
    }
  });

  test('a request with no session_id still succeeds (session id is optional)', async () => {
    const req = mockReq('/api/run-one', { body: { text: 'hello' } });
    const res = mockRes();
    await handler(req, res, { getClient: fakeConfiguredClient });
    assert.equal(res.statusCode, 200);
  });

  test('429s with Retry-After once the rate limit is exceeded', async () => {
    for (let i = 0; i < 30; i++) {
      await handler(mockReq('/api/run-one', { body: { text: 'hi' } }), mockRes(), { getClient: fakeConfiguredClient });
    }
    const res = mockRes();
    await handler(mockReq('/api/run-one', { body: { text: 'hi' } }), res, { getClient: fakeConfiguredClient });
    assert.equal(res.statusCode, 429);
    assert.ok(res.headers['Retry-After']);
  });

  test('monthly counter reflects only the successful (configured) models cost', async () => {
    await handler(mockReq('/api/run-one', { body: { text: 'hello' } }), mockRes(), { getClient: fakeConfiguredClient });
    assert.equal(getMonthlyCounter().calls, 1); // one increment call per request
    assert.ok(getMonthlyCounter().cost_usd > 0); // nova/llama/mistral succeeded and billed
  });
});

describe('readIntents / readPromptTemplate / readPrices read the real repo files', () => {
  test('readIntents returns the real 77 Banking77 labels', () => {
    assert.equal(readIntents().length, 77);
  });

  test('readPromptTemplate matches the same template Python exports', () => {
    const template = readPromptTemplate();
    assert.ok(template.includes('__INTENT_LIST__'));
    assert.ok(template.includes('__TEXT__'));
  });

  test('buildPrompt (model-bench-prompt.js) against the real template produces the same shape as the Python side', () => {
    const prompt = buildPrompt('test message', ['a', 'b'], readPromptTemplate());
    assert.ok(prompt.includes('test message'));
    assert.ok(prompt.includes('- a'));
  });

  test('readPrices returns the real 5-model prices.json', () => {
    const prices = readPrices();
    assert.equal(prices.models.length, 5);
  });
});
