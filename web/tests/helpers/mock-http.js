/**
 * Minimal req/res doubles for testing a Vercel Node function handler
 * directly, without vercel dev or any HTTP server. Vercel's Node.js runtime
 * augments the plain http.ServerResponse with .status()/.json() helpers
 * automatically in production; this mock reproduces just that surface, and
 * nothing else, so tests exercise the exact same handler code that deploys.
 */

/** @param {string} url - e.g. "/api/meter/session?id=sess-aaa111"
 * @param {{headers?: object, query?: object|null, body?: object}} [opts]
 *   `body` simulates Vercel's Node runtime, which auto-parses a JSON
 *   request body into req.body before a function handler ever runs --
 *   handlers (e.g. run-one.js) read req.body directly, never req stream
 *   events, so tests never need to fake a readable stream. */
export function mockReq(url, { headers = {}, query = null, body = undefined } = {}) {
  return {
    url,
    headers,
    socket: { remoteAddress: '127.0.0.1' },
    // Only set when a test wants to simulate Vercel's auto-populated
    // req.query directly; otherwise handlers fall back to parsing req.url.
    query,
    body,
  };
}

export function mockRes() {
  const res = {
    statusCode: 200,
    headers: {},
    body: undefined,
    setHeader(name, value) {
      res.headers[name] = value;
    },
    status(code) {
      res.statusCode = code;
      return res;
    },
    json(payload) {
      res.body = payload;
      return res;
    },
  };
  return res;
}
