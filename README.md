# Model Bench

A live comparison of hosted models on one common business task: routing a
customer's banking message to the right intent. Runs on the full public
**Banking77** test split (3,080 messages, 77 intents) and reports accuracy,
cost per 1,000 messages, latency, and calibration.

This repository is the code and data behind the `/use-cases/model-bench` page
on [giggitai.com](https://giggitai.com). See `CONTEXT.md` for the working
notes (decisions made, open items, exact commands).

## What's here (tasks W-A1 + W-A2)

- The full Banking77 test split, pulled by direct file download (not
  hand-copied) — `data/golden.jsonl`, 3,080 rows.
- A hand-built map from the 77 fine-grained intents to 10 coarse groups —
  `data/coarse_map.json` — see the table below. This grouping is a judgment
  call, not part of the original dataset; challenge it if it looks wrong.
- The shared prompt and response parser used by every model —
  `src/modelbench/prompt.py` — with tests covering valid JSON, fenced JSON,
  trailing text, an out-of-set label, an empty response, and out-of-range
  confidence values.
- A zeroed `data/prices.json` skeleton (real prices and Bedrock model ids are
  filled in at Gate 1, once Leon provides them).
- The provider layer — `src/modelbench/providers/`: a Bedrock adapter
  (Converse API), a direct-Anthropic fallback, an OpenAI-compatible-endpoint
  fallback, and a fake adapter for local smoke tests. All four share one
  retry helper (up to 5 attempts, exponential backoff with jitter, on
  throttling/5xx only). Every network boundary is mocked in tests — no test
  calls a real API.
- The runner (`runner.py`): resumable and idempotent (re-running skips ids
  already in the output file), a bounded worker pool, one JSON line written
  per row.
- Metrics (`metrics.py`): accuracy (fine/coarse), cost per 1,000 messages,
  p50/p95 latency, Brier score, reliability bins, and per-intent accuracy —
  all pure functions, all covered by a hand-computed 10-row toy dataset.
- The report step (`report.py`): builds `results.json` from `outputs/*.jsonl`
  + `data/golden.jsonl` + `data/prices.json`; refuses to run against
  zero-priced models with a clear error.
- `modelbench run --model KEY [--limit N]`, `modelbench report`, and
  `modelbench smoke` are all implemented now (`smoke` needs no network or
  secrets — it runs 20 real Banking77 rows through the fake adapter).
- CI (GitHub Actions): `ruff check` + `pytest -q` on every push and PR. No
  network calls in CI — the pulled data is committed, so tests run against
  the files, not a live pull.

Not yet built (later tasks): the model-bench use-case web page and its two
functions (W-A3), and the full 5-model × 3,080-row run against real Bedrock
(W-A4, needs Gate 1 credentials first). The cost meter's live-Neon wiring
(W-M2) is also not yet built — see below for what the cost meter is today.

## Cost Meter (task W-M1)

A shared module, used by both Model Bench and AREA, that records every
model call as one `usage_events` row and serves three small read-only API
endpoints so anyone can see what a run actually cost. It lives in
`web/api/meter/` — plain Node, zero runtime dependencies, so a Vercel cold
start has nothing to install. Python never deploys here (BUILD INSTRUCTION
rule 9).

What's built now:

- `cost.js` — the cost formula, kept identical to `modelbench.metrics.cost_per_1k`.
- `store.js` — reads fixture data (`fixtures/usage_events.fixture.json`);
  this is the one seam that changes when W-M2 wires up a real Neon database.
- `rate-limit.js` — a per-IP, in-memory rate limiter (60 requests/10 min).
  This limits abuse, not spend — visitors are never blocked for cost
  (BUILD INSTRUCTION rule 6).
- `session.js`, `ledger.js`, `health.js` — the three endpoints from
  `SPEC-cost-meter-and-angi-reuse.md` §1.2: `GET /api/meter/session?id=`,
  `GET /api/meter/ledger?window=&group=`, `GET /api/meter/health`.
- `schema.sql` — the `usage_events` table definition for the eventual
  Postgres/Neon database, including the CHECK constraints on `use_case`
  and `step`.
- `meter-widget.js` — the bottom-right "Cost meter" pill + drawer, shared
  by every use-case page (`SPEC-cost-meter-and-angi-reuse.md` §1.3): live
  session total (4 decimals) and call count on the pill; an itemized table
  (step, model, tokens in/out, cost to 6 decimals, latency) and a "Copy as
  CSV" button in the drawer. The session id lives only in memory for the
  tab — no cookies, and a page reload starts a new session, as the spec
  requires.
- `charts.js` — a small hand-built inline-SVG bar chart (title, axis
  lines, tick values, bold axis titles, no gridlines, value labels drawn
  on/above each bar) used by the ledger page below. No charting library —
  this is easier to make match BUILD INSTRUCTION rule 11 exactly than a
  general-purpose one.
- `cost-ledger.js` + `cost-ledger.html` — the standalone `/use-cases/cost-ledger`
  page: an "Overall insights" bullet card (month-to-date cost, cheapest
  and dearest step per answer, cost share by use case), four charts (cost
  per day, by use case, by model, and cost-per-answer by step), and a
  cost-by-day table. Every number is fetched live from `/api/meter/health`
  and `/api/meter/ledger` at load — nothing is hard-coded.

This task's scope is deliberately fixture-only: no secrets, no live
database connection (see `SPEC-cost-meter-and-angi-reuse.md` §6, W-M1).
W-A3/W-A4/W-B4/W-B5 wire the widget into their own pages' `<script>` tags
(see `meter-widget.js`'s header comment for the integration snippet); this
task builds and tests it against fixtures only.

### Viewing the widget and ledger page in a browser

```bash
cd web
npm install
node dev-server.js        # http://localhost:3000/cost-ledger.html
```

`dev-server.js` is a zero-dependency local-only server (never deployed —
Vercel does its own routing in production) that serves the static files
here and adapts the three `api/meter/*.js` handlers to plain Node `http`,
unchanged, so what you see is the real handler code running against the
fixture data. `dev-widget-preview.html` (also dev-only) mounts the pill +
drawer pinned to a fixture session, for checking the widget itself the
same way.

### Running the web tests

```bash
cd web
npm install
npm test
```

Most of the suite (cost math, rate limiting, the three endpoint handlers,
the fixture store) needs nothing beyond Node — it runs standalone.

### Testing the cost-meter schema

`tests/schema.test.js` runs `api/meter/schema.sql` against a **real**
PostgreSQL 16 database and checks that its constraints actually reject bad
rows (an unrecognized `use_case`, a negative `cost_usd`, and so on) — a
text/regex check on the SQL can't catch a typo'd constraint name or a
CHECK expression that silently never fires, so this test executes the DDL
for real. It needs a `TEST_DATABASE_URL` environment variable pointing at
an empty scratch database; without it, this file's tests are **skipped**
(reported as `skipped`, not `pass`) with a message saying why — CI always
sets this variable (see `.github/workflows/ci.yml`'s `web-test` job, which
runs a `postgres:16` service container), so these tests are never silently
skipped there.

To run them locally with Docker:

```bash
docker run -d --name modelbench-test-db \
  -e POSTGRES_USER=modelbench_test \
  -e POSTGRES_PASSWORD=modelbench_test_pw \
  -e POSTGRES_DB=modelbench_schema_test \
  -p 5432:5432 postgres:16

cd web
TEST_DATABASE_URL="postgresql://modelbench_test:modelbench_test_pw@localhost:5432/modelbench_schema_test" npm test
```

Or, with a local PostgreSQL 16 install: create a role and an empty
database, then point `TEST_DATABASE_URL` at it the same way.

## Model Bench page (task W-A3)

The actual use-case page at `web/index.html` (built from `web/index.template.html`
by `scripts_build_web_page.py`, not hand-edited) plus its two Vercel
functions, per `SPEC-model-bench.md` §7. This is the first page where
`meter-widget.js` (W-M1) is embedded live.

What's built now:

- `web/index.template.html` — the page shell: title/subtitle, "Overall
  insights" card, leaderboard table, 4 headline charts (accuracy, cost,
  latency, Brier), a calibration chart + per-model reliability tables, a
  "worst 10 intents" grid per model, the live "try it yourself" box, and
  the methodology list. `window.__RESULTS__` is inlined by the build
  script from a results JSON — never fetched at runtime, so the page has
  no load-bearing network call for its own numbers.
- `web/model-bench-render.js` — pure, DOM-free rendering functions
  (leaderboard sort, the 4 headline insight bullets, chart specs, the
  reliability scatter series, the worst-intents tables, methodology
  facts) plus a `render()` that mounts them. Kept DOM-free so every
  function is unit-testable without a browser.
- `web/model-bench-live-box.js` — the "try it live" box: validates input
  (max 1,000 characters), POSTs to `/api/run-one`, and renders the
  5-model answer table, including the plain-English errors the API can
  return.
- `web/api/model-bench-prompt.js` — a byte-for-byte JS port of
  `src/modelbench/prompt.py`'s prompt-building and response-parsing
  logic, sharing the same template text via `data/prompt.txt` (see D-prompt
  below) so Python and JS never drift.
- `web/api/run-one.js` — `POST /api/run-one`: validates the message,
  builds the shared prompt, calls all 5 Bedrock models in parallel
  (`@aws-sdk/client-bedrock-runtime` — see the dependency note below),
  logs a usage event and increments the monthly call counter per model
  (best-effort, never blocks the response), and returns each model's
  answer, cost, and latency. A model whose `data/prices.json` entry is
  still a Gate-1 placeholder degrades gracefully to a plain-English
  "Model not yet configured (Gate 1 pending)" answer instead of calling
  Bedrock or erroring.
- `web/api/health.js` — `GET /api/health`: results-file freshness
  (`results_as_of`), the prices sheet's `as_of` date, and this month's
  live-box call count and estimated cost — the numbers the methodology
  section's last two bullets show.
- `web/api/model-bench-counter.js` — the in-memory write-seam for usage
  events and the monthly counter (same pattern as W-M1's `store.js`);
  W-M2 replaces this with real Neon writes.
- `scripts_build_web_page.py` — embeds a results JSON into the template
  at `window.__RESULTS__`. Defaults to `results.json` and refuses to run
  if it doesn't exist yet (prints a clear message pointing at
  `--results results.sample.json` for local development) — this keeps a
  sample/fixture build from ever being mistaken for production output.
- `results.sample.json` — real Banking77 label/intent data, but
  synthetic per-model numbers (clearly marked `"sample_disclosure"` in
  the file itself), used only for local development and the screenshots
  in this task's report. Never used by the default build.

The prompt template (`data/prompt.txt`, exported by
`scripts_export_prompt.py` from `src/modelbench/prompt.py`'s
`PROMPT_TEMPLATE`) uses `__INTENT_LIST__`/`__TEXT__` string-replace
tokens rather than `.format()`-style braces, so the same literal text
substitutes identically in both Python and JavaScript with no
escaping rules to keep in sync — verified byte-identical by a test in
each language.

### Viewing the Model Bench page in a browser

```bash
cd web
npm install
python3 ../scripts_build_web_page.py --results ../results.sample.json --out index.html
node dev-server.js        # http://localhost:3000/index.html
```

Real Bedrock calls need Gate-1 credentials; until then the live box's
5 answers correctly show "Model not yet configured" for every model
(verified in a real browser, not just by reading the code).

## Run it yourself (60 seconds)

```bash
git clone <this-repo>
cd model-bench
pip install -e ".[dev]"
python3 -m pytest -q
```

That runs the full test suite (prompt parser + coarse-map/data checks)
against the committed data. No network access and no secrets are needed for
this.

To re-pull the Banking77 data from source (not required — it's already
committed):

```bash
python3 -m modelbench.cli pull-data
```

## Coarse intent groups

Every one of the 77 fine-grained Banking77 intents is mapped to exactly one
of 10 coarse groups, used for the "accuracy by intent group" breakdown on the
page. The rule of thumb used to classify each intent (documented in full in
`scripts_build_coarse_map.py`):

- **card** — physical/virtual card lifecycle: ordering, arrival, activation,
  linking, replacement, expiry, acceptance, "not working" (non-fraud)
- **transfers_payments** — sending/receiving money, transfer or payment
  status/timing, cancelling a transfer in progress (not a refund)
- **top_up** — adding funds to the account by any method, including a
  balance not updating after a deposit or incoming transfer
- **atm_cash** — ATM and cash withdrawal specific issues, including a card
  swallowed by a machine
- **account_identity** — identity verification, personal details, account
  status
- **fees_charges_rates** — a fee, charge, or rate question or complaint that
  isn't specific to topping up
- **disputes_fraud** — unrecognized, duplicate, or fraudulent charges; lost,
  stolen, or compromised cards/phones
- **refunds_cancellations** — refund requests and their status
- **app_pin_access** — PIN and passcode issues
- **currency_crypto** — currency exchange rates, supported
  currencies/cards/payment methods, country support (the "compatibility"
  bucket)

<!-- COARSE_TABLE_START -->
### `account_identity` (7)

- `age_limit`
- `edit_personal_details`
- `terminate_account`
- `unable_to_verify_identity`
- `verify_my_identity`
- `verify_source_of_funds`
- `why_verify_identity`

### `app_pin_access` (3)

- `change_pin`
- `passcode_forgotten`
- `pin_blocked`

### `atm_cash` (6)

- `atm_support`
- `card_swallowed`
- `declined_cash_withdrawal`
- `pending_cash_withdrawal`
- `wrong_amount_of_cash_received`
- `wrong_exchange_rate_for_cash_withdrawal`

### `card` (15)

- `activate_my_card`
- `card_about_to_expire`
- `card_acceptance`
- `card_arrival`
- `card_delivery_estimate`
- `card_linking`
- `card_not_working`
- `contactless_not_working`
- `disposable_card_limits`
- `get_disposable_virtual_card`
- `get_physical_card`
- `getting_spare_card`
- `getting_virtual_card`
- `order_physical_card`
- `virtual_card_not_working`

### `currency_crypto` (7)

- `apple_pay_or_google_pay`
- `country_support`
- `exchange_rate`
- `exchange_via_app`
- `fiat_currency_support`
- `supported_cards_and_currencies`
- `visa_or_mastercard`

### `disputes_fraud` (7)

- `card_payment_not_recognised`
- `cash_withdrawal_not_recognised`
- `compromised_card`
- `direct_debit_payment_not_recognised`
- `lost_or_stolen_card`
- `lost_or_stolen_phone`
- `transaction_charged_twice`

### `fees_charges_rates` (6)

- `card_payment_fee_charged`
- `card_payment_wrong_exchange_rate`
- `cash_withdrawal_charge`
- `exchange_charge`
- `extra_charge_on_statement`
- `transfer_fee_charged`

### `refunds_cancellations` (2)

- `Refund_not_showing_up`
- `request_refund`

### `top_up` (12)

- `automatic_top_up`
- `balance_not_updated_after_bank_transfer`
- `balance_not_updated_after_cheque_or_cash_deposit`
- `pending_top_up`
- `top_up_by_bank_transfer_charge`
- `top_up_by_card_charge`
- `top_up_by_cash_or_cheque`
- `top_up_failed`
- `top_up_limits`
- `top_up_reverted`
- `topping_up_by_card`
- `verify_top_up`

### `transfers_payments` (12)

- `beneficiary_not_allowed`
- `cancel_transfer`
- `declined_card_payment`
- `declined_transfer`
- `failed_transfer`
- `pending_card_payment`
- `pending_transfer`
- `receiving_money`
- `reverted_card_payment?`
- `transfer_into_account`
- `transfer_not_received_by_recipient`
- `transfer_timing`
<!-- COARSE_TABLE_END -->

`refunds_cancellations` (2 intents) and `app_pin_access` (3 intents) are
genuinely small groups in the source data — Banking77 just doesn't have many
refund- or PIN-specific intents. That's a fact about the dataset, not a
mapping error; `tests/test_coarse_map.py` still checks every group is used at
least once and every intent is mapped to exactly one valid group.

## License

Code: MIT (see `LICENSE`). Data: Banking77 is CC BY 4.0 from PolyAI — see
`data/ATTRIBUTION.md` for the full citation.
