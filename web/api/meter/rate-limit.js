/**
 * Cost Meter — per-IP rate limiting.
 *
 * Per SPEC-cost-meter-and-angi-reuse.md section 1.2: "All read-only, public,
 * rate-limited per IP (60 per 10 minutes)." This is abuse control on a
 * public, unauthenticated read API — matching the spirit of
 * SPEC-model-bench.md section 7.2's rate limiter for api/run-one.js (same
 * in-memory approach, different limit/window), not a spend cap: rule 8 in
 * the BUILD INSTRUCTION is explicit that visitors are never blocked for
 * cost, only for abuse.
 *
 * In-memory by design, per spec. A known, accepted limitation: a Vercel
 * serverless function's memory does not persist across cold starts or
 * separate instances, so this limiter is best-effort, not a hard guarantee,
 * until/unless a shared store (e.g. Neon, once W-M2 wires it) backs it
 * instead. That tradeoff is the spec's, not this file's.
 */

/**
 * @param {{limit: number, windowMs: number}} opts
 * @returns {{check: (ip: string, nowMs?: number) => {allowed: boolean, retryAfterSeconds: number}, _reset: () => void}}
 */
export function createRateLimiter({ limit, windowMs }) {
  if (!Number.isInteger(limit) || limit <= 0) {
    throw new TypeError(`limit must be a positive integer, got ${limit}`);
  }
  if (!Number.isInteger(windowMs) || windowMs <= 0) {
    throw new TypeError(`windowMs must be a positive integer, got ${windowMs}`);
  }

  /** @type {Map<string, number[]>} ip -> sorted list of hit timestamps (ms) still inside the window */
  const hits = new Map();

  return {
    /**
     * Records one request from `ip` at `nowMs` (defaults to the real clock)
     * and reports whether it is allowed under the limit.
     */
    check(ip, nowMs = Date.now()) {
      const existing = hits.get(ip) || [];
      const inWindow = existing.filter((t) => nowMs - t < windowMs);

      if (inWindow.length >= limit) {
        const oldest = inWindow[0];
        const retryAfterMs = windowMs - (nowMs - oldest);
        hits.set(ip, inWindow); // drop expired entries even on a blocked check
        return { allowed: false, retryAfterSeconds: Math.max(1, Math.ceil(retryAfterMs / 1000)) };
      }

      inWindow.push(nowMs);
      hits.set(ip, inWindow);
      return { allowed: true, retryAfterSeconds: 0 };
    },

    /** Test-only: clears all recorded hits. */
    _reset() {
      hits.clear();
    },
  };
}

/** The shared limiter every meter API handler (session.js, ledger.js,
 * health.js) checks against: 60 requests per IP per 10 minutes. */
export const meterRateLimiter = createRateLimiter({ limit: 60, windowMs: 10 * 60 * 1000 });

/**
 * Best-effort client IP extraction for a Vercel Node function request. Falls
 * back to a constant so a request that genuinely carries no identifying
 * header still gets rate-limited as "one caller" rather than crashing the
 * handler.
 * @param {import('node:http').IncomingMessage} req
 */
export function clientIpFrom(req) {
  const forwarded = req.headers?.['x-forwarded-for'];
  if (typeof forwarded === 'string' && forwarded.length > 0) {
    return forwarded.split(',')[0].trim();
  }
  return req.socket?.remoteAddress || 'unknown';
}
