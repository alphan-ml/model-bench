import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import pg from 'pg';

/**
 * Runs api/meter/schema.sql against a REAL PostgreSQL 16 database and
 * checks that the constraints actually reject bad rows, not just that
 * the DDL text looks right. A regex/text check can't catch a typo'd
 * constraint name or a CHECK expression that silently never fires;
 * only executing the SQL can.
 *
 * Requires TEST_DATABASE_URL, e.g.:
 *   postgresql://user:pass@host:5432/some_scratch_db
 * The target database must exist and be empty (or at least not already
 * have a `usage_events` table) — this suite creates that table and
 * drops it again in `after`.
 *
 * If TEST_DATABASE_URL is not set, every test in this file is SKIPPED
 * (not silently passed) with a message explaining why, so a missing
 * env var shows up as "8 skipped" in the test output, never as false
 * green. CI sets TEST_DATABASE_URL against a postgres:16 service
 * container (see .github/workflows/ci.yml), so in CI this always runs
 * for real. For local development, see README.md's "Testing the
 * cost-meter schema" section for a one-line way to start a local
 * Postgres 16 instance.
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCHEMA_SQL_PATH = path.join(__dirname, '..', 'api', 'meter', 'schema.sql');

const DATABASE_URL = process.env.TEST_DATABASE_URL;
const skip = !DATABASE_URL;
// node:test's `skip` option: false runs the test; a string skips it and
// is shown as the reason. Computed once so every test below just spreads
// `{ skip: SKIP_OPTION }`.
const SKIP_OPTION = skip
  ? 'TEST_DATABASE_URL is not set — skipping live-database schema tests. ' +
    'See README.md "Testing the cost-meter schema" to run these locally.'
  : false;

let client;

before(async () => {
  if (skip) return;
  client = new pg.Client({ connectionString: DATABASE_URL });
  await client.connect();
  // Start from a clean slate in case a previous run was interrupted
  // before its `after` cleanup ran.
  await client.query('DROP TABLE IF EXISTS usage_events;');
  const schemaSql = fs.readFileSync(SCHEMA_SQL_PATH, 'utf8');
  await client.query(schemaSql);
});

after(async () => {
  if (skip) return;
  await client.query('DROP TABLE IF EXISTS usage_events;');
  await client.end();
});

async function insertRow(overrides = {}) {
  const row = {
    session_id: 's1',
    use_case: 'model-bench',
    step: 'text-to-intent',
    model_id: 'claude-haiku',
    adapter: 'bedrock',
    input_tokens: 100,
    output_tokens: 50,
    cost_usd: 0.000125,
    latency_ms: 600,
    ok: true,
    ...overrides,
  };
  return client.query(
    `INSERT INTO usage_events
      (session_id, use_case, step, model_id, adapter, input_tokens, output_tokens, cost_usd, latency_ms, ok, error, trace_id)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
     RETURNING event_id`,
    [
      row.session_id, row.use_case, row.step, row.model_id, row.adapter,
      row.input_tokens, row.output_tokens, row.cost_usd, row.latency_ms,
      row.ok, row.error ?? null, row.trace_id ?? null,
    ]
  );
}

describe('schema.sql applies cleanly to a real PostgreSQL 16 database', () => {
  test('usage_events table exists with the spec\'s columns', { skip: SKIP_OPTION }, async () => {
    const res = await client.query(
      `SELECT column_name, data_type, is_nullable
       FROM information_schema.columns
       WHERE table_name = 'usage_events'
       ORDER BY ordinal_position`
    );
    const names = res.rows.map((r) => r.column_name);
    assert.deepEqual(names, [
      'event_id', 'ts', 'session_id', 'use_case', 'step', 'model_id',
      'adapter', 'input_tokens', 'output_tokens', 'cost_usd', 'latency_ms',
      'trace_id', 'ok', 'error',
    ]);
    const costCol = res.rows.find((r) => r.column_name === 'cost_usd');
    assert.equal(costCol.data_type, 'numeric');
  });

  test('a valid row inserts successfully', { skip: SKIP_OPTION }, async () => {
    const res = await insertRow({ session_id: 'valid-1' });
    assert.ok(res.rows[0].event_id > 0);
  });

  test('rejects an unrecognized use_case', { skip: SKIP_OPTION }, async () => {
    await assert.rejects(
      () => insertRow({ session_id: 'bad-use-case', use_case: 'not-a-real-use-case' }),
      /violates check constraint "usage_events_use_case_check"/
    );
  });

  test('rejects an unrecognized step', { skip: SKIP_OPTION }, async () => {
    await assert.rejects(
      () => insertRow({ session_id: 'bad-step', step: 'not-a-real-step' }),
      /violates check constraint "usage_events_step_check"/
    );
  });

  test('accepts every step value from BOTH spec sections (D15 union)', { skip: SKIP_OPTION }, async () => {
    // SPEC-cost-meter-and-angi-reuse.md §1.1 lists:
    //   'text-to-intent' | 'text-to-sql' | 'text-to-plan' | 'compose' | 'verify' | 'live-box'
    // §3 lists:
    //   text-to-intent, text-to-plan, text-to-sql, text-to-forecast-call, text-to-answer
    // D15 resolves the conflict as the union of both. Every one of the
    // eight distinct values across both lists must be accepted.
    const steps = [
      'text-to-intent', 'text-to-sql', 'text-to-plan', 'compose', 'verify',
      'live-box', 'text-to-forecast-call', 'text-to-answer',
    ];
    for (const step of steps) {
      const res = await insertRow({ session_id: `step-${step}`, step });
      assert.ok(res.rows[0].event_id > 0, `expected step "${step}" to be accepted`);
    }
  });

  test('rejects negative cost_usd', { skip: SKIP_OPTION }, async () => {
    await assert.rejects(
      () => insertRow({ session_id: 'bad-cost', cost_usd: -0.01 }),
      /violates check constraint "usage_events_cost_usd_check"/
    );
  });

  test('rejects negative input_tokens and output_tokens', { skip: SKIP_OPTION }, async () => {
    await assert.rejects(
      () => insertRow({ session_id: 'bad-input', input_tokens: -1 }),
      /violates check constraint "usage_events_input_tokens_check"/
    );
    await assert.rejects(
      () => insertRow({ session_id: 'bad-output', output_tokens: -1 }),
      /violates check constraint "usage_events_output_tokens_check"/
    );
  });

  test('rejects negative latency_ms', { skip: SKIP_OPTION }, async () => {
    await assert.rejects(
      () => insertRow({ session_id: 'bad-latency', latency_ms: -1 }),
      /violates check constraint "usage_events_latency_ms_check"/
    );
  });

  test('rejects a missing (null) session_id', { skip: SKIP_OPTION }, async () => {
    await assert.rejects(
      () => insertRow({ session_id: null }),
      /null value in column "session_id"/
    );
  });

  test('cost_usd rounds to 6 decimal places, matching NUMERIC(10,6)', { skip: SKIP_OPTION }, async () => {
    const res = await insertRow({ session_id: 'rounding-check', cost_usd: 0.0000001 });
    const stored = await client.query('SELECT cost_usd FROM usage_events WHERE event_id = $1', [res.rows[0].event_id]);
    assert.equal(Number(stored.rows[0].cost_usd), 0);
  });

  test('event_id auto-increments and ts defaults to now() when omitted', { skip: SKIP_OPTION }, async () => {
    const before = await insertRow({ session_id: 'autoinc-1' });
    const afterRow = await insertRow({ session_id: 'autoinc-2' });
    assert.ok(afterRow.rows[0].event_id > before.rows[0].event_id);
    const tsRes = await client.query('SELECT ts FROM usage_events WHERE event_id = $1', [afterRow.rows[0].event_id]);
    assert.ok(tsRes.rows[0].ts instanceof Date);
  });

  test('indexes required for the ledger/session queries exist', { skip: SKIP_OPTION }, async () => {
    const res = await client.query(
      `SELECT indexname FROM pg_indexes WHERE tablename = 'usage_events'`
    );
    const names = res.rows.map((r) => r.indexname);
    assert.ok(names.includes('idx_usage_events_session_id'), 'session lookups need an index on session_id');
    assert.ok(names.includes('idx_usage_events_ts'), 'window filtering needs an index on ts');
    assert.ok(names.includes('idx_usage_events_use_case_ts'), 'per-use-case windowed queries need a composite index');
  });
});
