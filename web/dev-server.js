#!/usr/bin/env node
/**
 * Zero-dependency local dev server — NOT used in production (Vercel does
 * its own routing there; see vercel.json once it exists). This exists
 * solely so the cost-meter widget, the cost-ledger page, and (as of W-A3)
 * the Model Bench page and its live box can be opened in a real browser
 * against fixture/sample data, for visual verification against BUILD
 * INSTRUCTION rule 11 (fonts, colors, chart style) — the kind of thing a
 * unit test can't confirm.
 *
 * Usage:
 *   node dev-server.js [port]   # defaults to 3000
 *   # web/index.html must already exist -- build it first, e.g.:
 *   #   python3 ../scripts_build_web_page.py --results ../results.sample.json
 *
 * Serves static files from this directory, and adapts the Vercel function
 * handlers under api/ and api/meter/ to plain Node http so they work here
 * unchanged — no vercel dev, no extra dependency.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import sessionHandler from './api/meter/session.js';
import ledgerHandler from './api/meter/ledger.js';
import meterHealthHandler from './api/meter/health.js';
import runOneHandler from './api/run-one.js';
import modelBenchHealthHandler from './api/health.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.argv[2]) || Number(process.env.PORT) || 3000;

const ROUTES = {
  '/api/meter/session': sessionHandler,
  '/api/meter/ledger': ledgerHandler,
  '/api/meter/health': meterHealthHandler,
  '/api/run-one': runOneHandler,
  '/api/health': modelBenchHealthHandler,
};

/** Reads and JSON-parses a request body — plain Node http does not do this
 * automatically the way Vercel's Node runtime does (which populates
 * req.body before a function handler ever runs). Only POST /api/run-one
 * needs this today; GET requests never have a body to read. */
function readJsonBody(nodeReq) {
  return new Promise((resolve, reject) => {
    if (nodeReq.method !== 'POST') {
      resolve(undefined);
      return;
    }
    let raw = '';
    nodeReq.on('data', (chunk) => { raw += chunk; });
    nodeReq.on('end', () => {
      if (raw.length === 0) {
        resolve(undefined);
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (err) {
        reject(err);
      }
    });
    nodeReq.on('error', reject);
  });
}

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
};

/** Adapts a Vercel-style handler(req, res) to Node's raw http req/res:
 * adds .status()/.json() to res, and normalizes req just enough (url,
 * headers, socket, a parsed body) to match what the handlers and tests
 * already expect. */
function adaptToVercelStyle(nodeReq, nodeRes, body) {
  const req = {
    url: nodeReq.url,
    method: nodeReq.method,
    headers: nodeReq.headers,
    socket: nodeReq.socket,
    query: null,
    body,
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
    let body;
    try {
      body = await readJsonBody(nodeReq);
    } catch {
      nodeRes.writeHead(400, { 'Content-Type': 'application/json' });
      nodeRes.end(JSON.stringify({ error: 'Invalid JSON body.' }));
      return;
    }
    const { req, res } = adaptToVercelStyle(nodeReq, nodeRes, body);
    try {
      await routeHandler(req, res);
    } catch (err) {
      nodeRes.writeHead(500, { 'Content-Type': 'application/json' });
      nodeRes.end(JSON.stringify({ error: String(err) }));
    }
    return;
  }

  // Static file serving, rooted at this directory. "/" -> index.html, the
  // Model Bench page (build it first with scripts_build_web_page.py — see
  // this file's header comment); the cost-ledger page stays reachable at
  // its own path.
  const relPath = urlPath === '/' ? '/index.html' : urlPath;
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
  console.log(`dev server (fixture/sample data) on http://localhost:${PORT}/`);
  console.log(`  model-bench page: http://localhost:${PORT}/index.html`);
  console.log(`  cost-ledger page: http://localhost:${PORT}/cost-ledger.html`);
});
