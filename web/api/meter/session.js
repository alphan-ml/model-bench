/**
 * Cost Meter — "what did this session cost?" on request.
 *
 * Per SPEC-cost-meter-and-angi-reuse.md section 1.2:
 *   GET /api/meter/session?id=<session_id> -> itemized list of this
 *   session's events (step, model, tokens, cost, latency) + totals.
 *
 * summarizeSession is the pure, directly-testable half; `handler` is the
 * thin Vercel Node function wrapper around it (rate limit -> parse -> call
 * -> respond), following the same split as ledger.js and health.js so every
 * meter endpoint is testable without a running server.
 */

import { getAllEvents } from './store.js';
import { roundCostUsd } from './cost.js';
import { meterRateLimiter, clientIpFrom } from './rate-limit.js';

/**
 * @param {Array<object>} events - full usage_events rows (see schema.sql).
 * @param {string} sessionId
 * @returns {{session_id: string, events: Array<object>, totals: {calls: number, input_tokens: number, output_tokens: number, cost_usd: number}}}
 */
export function summarizeSession(events, sessionId) {
  const rows = events
    .filter((e) => e.session_id === sessionId)
    .map((e) => ({
      ts: e.ts,
      step: e.step,
      model_id: e.model_id,
      input_tokens: e.input_tokens,
      output_tokens: e.output_tokens,
      cost_usd: e.cost_usd,
      latency_ms: e.latency_ms,
      ok: e.ok,
      error: e.error,
    }));

  const totals = rows.reduce(
    (acc, r) => ({
      calls: acc.calls + 1,
      input_tokens: acc.input_tokens + r.input_tokens,
      output_tokens: acc.output_tokens + r.output_tokens,
      cost_usd: roundCostUsd(acc.cost_usd + r.cost_usd),
    }),
    { calls: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0 }
  );

  return { session_id: sessionId, events: rows, totals };
}

/** Parses `id` from either Vercel's auto-populated req.query (the normal
 * path in production) or, failing that, the raw req.url (so this handler
 * also runs correctly under the zero-dependency local dev server in
 * web/dev-server.js, which does not inject req.query). */
function readSessionIdParam(req) {
  if (req.query && typeof req.query.id === 'string') {
    return req.query.id;
  }
  const url = new URL(req.url, 'http://localhost');
  return url.searchParams.get('id');
}

/** @param {import('node:http').IncomingMessage} req
 *  @param {import('node:http').ServerResponse & {status: Function, json: Function}} res */
export default function handler(req, res) {
  const { allowed, retryAfterSeconds } = meterRateLimiter.check(clientIpFrom(req));
  if (!allowed) {
    res.setHeader('Retry-After', String(retryAfterSeconds));
    res.status(429).json({ error: 'Too many requests. Try again shortly.' });
    return;
  }

  const sessionId = readSessionIdParam(req);
  if (!sessionId) {
    res.status(400).json({ error: 'Missing required query parameter: id' });
    return;
  }

  res.status(200).json(summarizeSession(getAllEvents(), sessionId));
}
