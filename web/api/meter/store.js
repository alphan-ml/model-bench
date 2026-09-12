/**
 * Cost Meter — data access.
 *
 * W-M1 (this file, no secrets, no database): every read goes to the
 * committed fixture at fixtures/usage_events.fixture.json. W-M2 replaces the
 * body of getAllEvents() with a real query against Neon's usage_events table
 * (schema.sql) — nothing else in this folder changes, because session.js,
 * ledger.js, and health.js only ever call the functions exported here, never
 * touch the fixture file directly. That is the entire point of this file
 * existing on its own: it is the one seam W-M2 has to cut.
 *
 * Read with fs.readFileSync + JSON.parse rather than an import assertion
 * (`with { type: "json" }`) so this file behaves identically under plain
 * `node --test`, under `vercel dev`, and once deployed as a Vercel Node
 * function — import assertions are still landing unevenly across those
 * runtimes as of Node 22 / Sep 2026, and this module has no reason to bet on
 * that landing before Gate 1.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.join(__dirname, 'fixtures', 'usage_events.fixture.json');

let _cachedEvents = null;

/**
 * Every usage_events row, oldest first. Cached after the first read for the
 * lifetime of the process (a fixture file never changes at runtime; a real
 * Neon-backed W-M2 implementation of this function will not cache, since a
 * live table does change between calls).
 * @returns {Array<object>}
 */
export function getAllEvents() {
  if (_cachedEvents === null) {
    const parsed = JSON.parse(readFileSync(FIXTURE_PATH, 'utf8'));
    _cachedEvents = parsed.events;
  }
  return _cachedEvents;
}

/** Test-only: forces the next getAllEvents() call to re-read the fixture
 * file from disk. Production code never needs this. */
export function _resetCacheForTests() {
  _cachedEvents = null;
}

/**
 * @param {string} sessionId
 * @returns {Array<object>} events for that session, oldest first.
 */
export function getEventsForSession(sessionId) {
  return getAllEvents().filter((e) => e.session_id === sessionId);
}
