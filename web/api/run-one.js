/**
 * Model Bench — POST /api/run-one (SPEC-model-bench.md §7.2).
 *
 * Input (JSON body): {text, session_id?}. text max 1,000 chars. session_id
 * is optional and, when present, is passed through to logUsageEvent() so a
 * visitor's Cost Meter session (meter-widget.js's meter.sessionId) picks up
 * these calls too -- meter-widget.js's own integration comment says to pass
 * it along with page API calls for exactly this reason.
 *
 * Calls the 5 models named in data/prices.json in parallel through AWS
 * Bedrock's Converse API, using the exact same prompt as the Python side
 * (data/prompt.txt + model-bench-prompt.js -- see that file's header
 * comment for the shared-template contract with modelbench.prompt.py).
 *
 * Per-IP rate limit: 30 calls per 10 minutes -- abuse control only, not a
 * spend cap (rule 6/8: visitors are never blocked for cost).
 *
 * Gate 1 is still open (CONTEXT.md "Open items"): every entry in
 * data/prices.json still carries a placeholder model_id and zero prices.
 * A model still carrying a placeholder is reported back as a per-model
 * `error` instead of attempting a real Bedrock call that could only fail
 * -- the same isolate-one-bad-row-not-the-whole-batch principle as the
 * Python runner's D11 fix. This makes the endpoint fully exercisable (and
 * its tests fully green) today, and it needs no code change once Gate 1
 * lands real ids/prices: isModelConfigured() will simply start returning
 * true and callOneModel() will start making real calls.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { createRateLimiter, clientIpFrom } from './meter/rate-limit.js';
import { computeCostUsd } from './meter/cost.js';
import { buildPrompt, parseModelResponse } from './model-bench-prompt.js';
import { logUsageEvent, incrementMonthlyCounter } from './model-bench-counter.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..', '..');
const PROMPT_PATH = path.join(REPO_ROOT, 'data', 'prompt.txt');
const LABELS_PATH = path.join(REPO_ROOT, 'data', '_labels.json');
const PRICES_PATH = path.join(REPO_ROOT, 'data', 'prices.json');

export const MAX_TEXT_LENGTH = 1000;
// Per SPEC-model-bench.md §4: "Temperature 0. Max output tokens 60." --
// identical constants to modelbench.prompt.TEMPERATURE/MAX_OUTPUT_TOKENS.
export const TEMPERATURE = 0;
export const MAX_OUTPUT_TOKENS = 60;

/** Per §7.2: "Per-IP rate limit: 30 calls per 10 minutes... in-memory +
 * Retry-After header." Same mechanism as api/meter/rate-limit.js's
 * meterRateLimiter, a separate instance with this endpoint's own
 * limit/window (createRateLimiter is a factory for exactly this reason). */
export const runOneRateLimiter = createRateLimiter({ limit: 30, windowMs: 10 * 60 * 1000 });

let _cachedPromptTemplate = null;
export function readPromptTemplate(promptPath = PROMPT_PATH) {
  if (_cachedPromptTemplate === null) {
    _cachedPromptTemplate = readFileSync(promptPath, 'utf8');
  }
  return _cachedPromptTemplate;
}

let _cachedIntents = null;
export function readIntents(labelsPath = LABELS_PATH) {
  if (_cachedIntents === null) {
    _cachedIntents = JSON.parse(readFileSync(labelsPath, 'utf8'));
  }
  return _cachedIntents;
}

/** Not cached like the two above: prices.json is small, read once per
 * request, and Gate 1 will change it from outside this process -- a
 * cached copy could otherwise keep reporting "not configured" after
 * Leon fills in real prices until the next cold start. */
export function readPrices(pricesPath = PRICES_PATH) {
  return JSON.parse(readFileSync(pricesPath, 'utf8'));
}

/** True when a model's prices.json entry is real, not the Gate-1
 * placeholder -- mirrors report.py's ZeroPricesError check (a placeholder
 * model_id contains "<", and/or both prices are still 0.0). */
export function isModelConfigured(priceEntry) {
  if (!priceEntry) return false;
  if (typeof priceEntry.model_id !== 'string' || priceEntry.model_id.includes('<')) return false;
  if (priceEntry.input_per_1m === 0 && priceEntry.output_per_1m === 0) return false;
  return true;
}

let _client = null;
/** Lazily constructs (and caches) the Bedrock client. Not called at all
 * for a not-yet-configured model, so this endpoint never requires
 * AWS_REGION/credentials to exist before Gate 1. */
export function getBedrockClient() {
  if (_client === null) {
    _client = new BedrockRuntimeClient({ region: process.env.AWS_REGION });
  }
  return _client;
}

/** Test-only: forces the next getBedrockClient() call to construct fresh
 * (so tests can swap AWS_REGION or inject nothing between runs). */
export function _resetClientForTests() {
  _client = null;
}

/**
 * Calls one model via Bedrock's Converse API. Never throws: any SDK error
 * (missing credentials, throttling, an invalid model id, a network
 * failure) is caught and returned as `{error}` instead, the same
 * catch-inside-the-adapter defense D11 added to the Python provider layer
 * after a real bug there once took down an entire run.
 *
 * @param {string} modelId
 * @param {string} prompt
 * @param {{client: {send: Function}}} deps - injected so tests never call
 *   a real API (spec §5's rule, applied here too: "Tests mock the
 *   network; no test calls a real API").
 */
export async function callBedrockConverse(modelId, prompt, { client }) {
  const start = Date.now();
  try {
    const command = new ConverseCommand({
      modelId,
      messages: [{ role: 'user', content: [{ text: prompt }] }],
      inferenceConfig: { temperature: TEMPERATURE, maxTokens: MAX_OUTPUT_TOKENS },
    });
    const response = await client.send(command);
    return {
      text: response.output?.message?.content?.[0]?.text ?? '',
      inputTokens: response.usage?.inputTokens ?? 0,
      outputTokens: response.usage?.outputTokens ?? 0,
      latencyMs: Date.now() - start,
      error: null,
    };
  } catch (err) {
    return {
      text: '', inputTokens: 0, outputTokens: 0,
      latencyMs: Date.now() - start,
      error: String(err?.message ?? err),
    };
  }
}

/**
 * Runs one model end to end: configuration check -> Bedrock call -> parse
 * -> cost. Always resolves (never rejects) with an answer-shaped object,
 * so Promise.all() over all 5 models can never reject because one model
 * had a bad day -- the whole point of per-row isolation (D11's principle,
 * applied to this endpoint).
 * @returns {Promise<{key, intent, confidence, input_tokens, output_tokens, cost_usd, latency_ms, error}>}
 */
export async function callOneModel(priceEntry, prompt, intents, { getClient = getBedrockClient } = {}) {
  const key = priceEntry?.key ?? 'unknown';
  try {
    if (!isModelConfigured(priceEntry)) {
      return {
        key, intent: null, confidence: null, input_tokens: 0, output_tokens: 0,
        cost_usd: 0, latency_ms: 0, error: 'Model not yet configured (Gate 1 pending).',
      };
    }

    const client = getClient();
    const result = await callBedrockConverse(priceEntry.model_id, prompt, { client });
    if (result.error) {
      return {
        key, intent: null, confidence: null, input_tokens: 0, output_tokens: 0,
        cost_usd: 0, latency_ms: result.latencyMs,
        error: 'The model did not answer. Try again.',
      };
    }

    const parsed = parseModelResponse(result.text, intents);
    const costUsd = computeCostUsd(result.inputTokens, result.outputTokens, priceEntry);
    return {
      key, intent: parsed.intent, confidence: parsed.confidence,
      input_tokens: result.inputTokens, output_tokens: result.outputTokens,
      cost_usd: costUsd, latency_ms: result.latencyMs, error: null,
    };
  } catch (err) {
    // Defense in depth: whatever went wrong (a bug in this function, a
    // malformed price entry), one model's failure must never take down
    // the other 4 or the whole request.
    return {
      key, intent: null, confidence: null, input_tokens: 0, output_tokens: 0,
      cost_usd: 0, latency_ms: 0, error: `Unexpected error: ${String(err?.message ?? err)}`,
    };
  }
}

/** @param {{body?: {text?: string, session_id?: string}}} req */
export function validateRunOneInput(req) {
  const text = req.body?.text;
  if (typeof text !== 'string' || text.trim().length === 0) {
    return { valid: false, error: 'text is required.' };
  }
  if (text.length > MAX_TEXT_LENGTH) {
    return { valid: false, error: `text must be at most ${MAX_TEXT_LENGTH} characters.` };
  }
  return { valid: true, error: null };
}

/** @param {import('node:http').IncomingMessage} req
 *  @param {import('node:http').ServerResponse & {status: Function, json: Function}} res */
export default async function handler(req, res) {
  const { allowed, retryAfterSeconds } = runOneRateLimiter.check(clientIpFrom(req));
  if (!allowed) {
    res.setHeader('Retry-After', String(retryAfterSeconds));
    res.status(429).json({ error: 'Too many requests. Try again shortly.' });
    return;
  }

  const { valid, error } = validateRunOneInput(req);
  if (!valid) {
    res.status(400).json({ error });
    return;
  }

  const text = req.body.text;
  const sessionId = req.body.session_id ?? null;

  const intents = readIntents();
  const prompt = buildPrompt(text, intents, readPromptTemplate());
  const prices = readPrices();

  const answers = await Promise.all(
    prices.models.map((priceEntry) => callOneModel(priceEntry, prompt, intents))
  );

  // Best-effort metering only, from here down: a bug in either call must
  // never fail the response the visitor is waiting on (rule 6).
  try {
    for (const answer of answers) {
      logUsageEvent({
        session_id: sessionId,
        use_case: 'model-bench',
        step: 'text-to-intent',
        model_id: answer.key,
        adapter: 'bedrock',
        input_tokens: answer.input_tokens,
        output_tokens: answer.output_tokens,
        cost_usd: answer.cost_usd,
        latency_ms: answer.latency_ms,
        ok: !answer.error,
        error: answer.error,
      });
    }
    const successfulCostUsd = answers.filter((a) => !a.error).reduce((sum, a) => sum + a.cost_usd, 0);
    incrementMonthlyCounter(successfulCostUsd);
  } catch {
    // Never fail the response over a metering bug.
  }

  res.status(200).json({ answers, prices_as_of: prices.as_of });
}
