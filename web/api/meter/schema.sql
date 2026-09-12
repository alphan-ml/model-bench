-- Cost Meter — usage_events table.
--
-- Per SPEC-cost-meter-and-angi-reuse.md section 1.1. Not yet wired to a real
-- Neon database (that is W-M2, per the addendum's task list in section 6);
-- this file is the schema itself, kept correct and reviewable now so W-M2 is
-- "run this file against Neon and point the provider layers at it," not
-- "design the table."
--
-- D15 (see CONTEXT.md): the addendum's own two sections disagree on the
-- `step` enum. Section 1.1 lists:
--   'text-to-intent' | 'text-to-sql' | 'text-to-plan' | 'compose' | 'verify' | 'live-box'
-- Section 3 ("text-to-whatever") instead lists these text-to-X labels:
--   text-to-intent, text-to-plan, text-to-sql, text-to-forecast-call, text-to-answer
-- 'text-to-forecast-call' and 'text-to-answer' are missing from 1.1's set;
-- 'compose', 'verify', and 'live-box' are missing from section 3's set. Per
-- the BUILD INSTRUCTION's stop rule ("any spec requirement conflicts with
-- another; quote both lines"), this is flagged to Leon in this task's chat
-- report rather than silently picked one way — but rejecting a legitimate
-- future AREA event because of an unresolved enum question would be a worse
-- default than accepting one extra label, so the CHECK constraint below is
-- the UNION of both lists until Leon confirms which is right (or that both
-- are, which is the working assumption for now).
CREATE TABLE IF NOT EXISTS usage_events (
    event_id      BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id    TEXT NOT NULL,
    use_case      TEXT NOT NULL CHECK (use_case IN ('model-bench', 'area', 'ops-bot')),
    step          TEXT NOT NULL CHECK (step IN (
                      'text-to-intent',
                      'text-to-sql',
                      'text-to-plan',
                      'text-to-forecast-call',
                      'text-to-answer',
                      'compose',
                      'verify',
                      'live-box'
                  )),
    model_id      TEXT NOT NULL,
    adapter       TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    cost_usd      NUMERIC(10, 6) NOT NULL CHECK (cost_usd >= 0),
    latency_ms    INTEGER NOT NULL CHECK (latency_ms >= 0),
    trace_id      TEXT,
    ok            BOOLEAN NOT NULL,
    error         TEXT
);

-- Per section 1.1: "Indexes: (session_id), (ts), (use_case, ts)."
CREATE INDEX IF NOT EXISTS idx_usage_events_session_id ON usage_events (session_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_ts ON usage_events (ts);
CREATE INDEX IF NOT EXISTS idx_usage_events_use_case_ts ON usage_events (use_case, ts);
