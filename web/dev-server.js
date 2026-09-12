#!/usr/bin/env node
/**
 * Zero-dependency local dev server — NOT used in production (Vercel does
 * its own routing there; see vercel.json once it exists). This exists
 * solely so the cost-meter widget and the cost-ledger page can be opened
 * in a real browser against the fixture data, for visual verification
 * against BUILD INSTRUCTION rule 11 (fonts, colors, chart style) — the
 * kind of thing a unit test can't confirm.
 *
 * Usage:
 *   node dev-server.js [port]   # defaults to 3000
 *
 * Serves static files from this directory, and adapts the three Vercel
 * function handlers under api/meter/ to plain Node http so they work
 * here unchanged — no vercel dev, no extra dependency.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import sessionHandler from './api/meter/session.js';
import ledgerHandler from './api/meter/ledger.js';
import healthHandler from './api/meter/health.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.argv[2]) || Number(process.env.PORT) || 3000;

const ROUTES = {
  '/api/meter/session': sessionHandler,
  '/api/meter/ledger': ledgerHandler,
  '/api/meter/health': healthHandler,
};

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
};

/** Adapts a Vercel-style handler(req, res) to Node's raw http req/res:
 * adds .status()/.json() to res, and normalizes req just enough (url,
 * headers, socket) to match what the handlers and tests already expect. */
function adaptToVercelStyle(nodeReq, nodeRes) {
  const req = {
    url: nodeReq.url,
    headers: nodeReq.headers,
    socket: nodeReq.socket,
    query: null,
  };
  const res = {
    statusCode: 200,
    headers: {},
    setHeader(name, value) {
      nodeRes.setHeader(name, value);
    },
    status(code) {
      res.statusCode = code;
      return res;
    },
    json(payload) {
      const body = JSON.stringify(payload);
      nodeRes.writeHead(res.statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
      nodeRes.end(body);
      return res;
    },
  };
  return { req, res };
}

const server = http.createServer(async (nodeReq, nodeRes) => {
  const urlPath = nodeReq.url.split('?')[0];

  const routeHandler = ROUTES[urlPath];
  if (routeHandler) {
    const { req, res } = adaptToVercelStyle(nodeReq, nodeRes);
    try {
      await routeHandler(req, res);
    } catch (err) {
      nodeRes.writeHead(500, { 'Content-Type': 'application/json' });
      nodeRes.end(JSON.stringify({ error: String(err) }));
    }
    return;
  }

  // Static file serving, rooted at this directory. "/" -> cost-ledger.html
  // since that's the one standalone page this task builds.
  const relPath = urlPath === '/' ? '/cost-ledger.html' : urlPath;
  const filePath = path.join(__dirname, relPath);
  if (!filePath.startsWith(__dirname)) {
    nodeRes.writeHead(403);
    nodeRes.end('Forbidden');
    return;
  }
  fs.readFile(filePath, (err, data) => {
    if (err) {
      nodeRes.writeHead(404, { 'Content-Type': 'text/plain' });
      nodeRes.end('Not found');
      return;
    }
    const ext = path.extname(filePath);
    nodeRes.writeHead(200, { 'Content-Type': CONTENT_TYPES[ext] ?? 'application/octet-stream' });
    nodeRes.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`dev server (fixture data) on http://localhost:${PORT}/`);
  console.log(`  cost-ledger page: http://localhost:${PORT}/cost-ledger.html`);
});
