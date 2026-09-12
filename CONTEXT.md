# CONTEXT

Working notes for whoever (human or agent) picks this repo up next. Read this
before touching anything.

## How to run

```bash
pip install -e ".[dev]"
python3 -m ruff check .
python3 -m pytest -q
```

Use `python3 -m ruff` / `python3 -m pytest`, not the bare `ruff`/`pytest` commands — on
some machines (this build environment included) a separate isolated install of
those tools sits earlier on `PATH` and cannot see the package just installed
into your Python's site-packages, which shows up as a false
`ModuleNotFoundError: No module named 'modelbench'`. `python3 -m` always runs
the module for the same interpreter you installed the package into.

No secrets and no network needed for any of the above — the pulled data is
committed. To re-pull Banking77 from source (optional, not required):

```bash
python3 -m modelbench.cli pull-data
```

## Data facts (from the actual pull, W-A1)

- Rows: 3,080 (matches spec exactly)
- Unique fine intents: 77 (matches spec exactly)
- License: CC BY 4.0 (permissive) — full citation in `data/ATTRIBUTION.md`
- Pulled: 2026-09-12, from `raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets`

## Decisions

- D1 — 2026-09-12 — Pulled Banking77 by direct GitHub file download
  (`PolyAI-LDN/task-specific-datasets`, the original source) instead of the
  `datasets` library. `huggingface.co` is blocked by the build environment's
  egress policy — confirmed from both the cloud workspace and the Mac-VM
  shell. GitHub raw content is reachable and is the same original data. The
  spec explicitly allows direct file download as an alternative to the
  `datasets` library, so this is not a deviation.
- D2 — 2026-09-12 — The 77→10 coarse-group mapping (`data/coarse_map.json`)
  is a hand-built judgment call. The spec names the 10 groups but leaves the
  per-intent assignment to the builder. The classification rule used is
  documented in `README.md` and `scripts_build_coarse_map.py` so it can be
  challenged and changed later without re-deriving the logic from scratch.
  Resulting distribution: card 15, top_up 12, transfers_payments 12,
  account_identity 7, currency_crypto 7, disputes_fraud 7, atm_cash 6,
  fees_charges_rates 6, app_pin_access 3, refunds_cancellations 2. The two
  small groups are a fact about Banking77 (few PIN- or refund-specific
  intents exist in the source data), not a mapping error.
- D3 — 2026-09-12 — The optional Angi files (`pipeline_angi.py`,
  `config.yaml`, `eval_runner.py`, `taxonomy.py`) were not attached to the
  build instruction and are not in Drive HQ (checked). Per the addendum's
  fallback, the W-A2 provider layer will be rebuilt to the same shape (Mock /
  Bedrock / Anthropic direct / OpenAI-compatible) rather than extending
  existing code that doesn't exist here.
- D4 — 2026-09-12 — The `vercel` CLI is not reachable from this Cowork
  session's Mac-VM shell. Per Fable's environment-facts note, it lives in the
  real macOS user home (`~/.local/node/bin/vercel`, logged in) and works from
  the actual Terminal — the Cowork Mac-VM shell is a separate Linux sandbox
  with its own PATH and its own (Linux) Node, so it can't reach that install.
  Deploy steps (task 7 onward, `make deploy`) will run from Leon's Terminal
  directly, or this shell will need the CLI installed fresh plus a Vercel
  token. Not a blocker before Gate 1.
- D5 — 2026-09-12 — `pyproject.toml` targets Python 3.11 per spec. The
  Mac-VM shell's system Python is 3.10.12; the cloud workspace used to build
  this repo has 3.11.15. `uv` is available on the Mac VM if a pinned 3.11
  interpreter is needed there later (`uv python install 3.11`).
- D6 — 2026-09-12 — Two small fixes found while closing out W-A1's own
  "pytest and ruff green" gate: (1) `ruff check .` found an unsorted-imports
  and an unused-import error in `pull_data.py` (`datetime.date` imported but
  never used) — fixed with `ruff check . --fix`, verified clean after. (2)
  Bare `pytest -q` failed in this build environment with
  `ModuleNotFoundError: No module named 'modelbench'` even right after a
  successful `pip install -e ".[dev]"` — the `pytest`/`ruff` binaries earlier
  on `PATH` here are isolated `uv tool` installs that can't see packages
  installed into the system Python's site-packages, so they silently ran
  against the wrong interpreter. `python3 -m pytest -q` / `python3 -m ruff
  check .` route through the same interpreter the package was installed
  into and are unaffected. Switched `CONTEXT.md`, `README.md`, and CI to the
  `python3 -m` form defensively, in case another machine (Leon's Mac
  included) has a similar `PATH` shadowing setup.
- D7 — 2026-09-12 (W-A2) — Two small additions beyond section 2's exact
  repo layout: `src/modelbench/providers/fake.py` and `tests/test_runner.py`.
  The task split (section 10) requires "smoke on a 20-row local fixture
  using a fake provider" and a tested runner; a fake adapter needs to live
  somewhere `get_provider()` and the `smoke` CLI command can both reach it,
  and the runner needed its own resumability tests beyond what
  test_providers_mock.py covers. `fake` is not a real adapter choice: it's
  absent from `.env.example`'s documented `MODELBENCH_ADAPTER` values and
  has no entry in `data/prices.json`; `get_provider()` still accepts it
  (with a docstring/error message saying why) so both `smoke` and the tests
  share one factory function instead of two code paths.
- D8 — 2026-09-12 (W-A2) — `modelbench smoke` never touches `outputs/` or
  `data/prices.json`: it writes to a new gitignored `.smoke_outputs/`
  directory and passes an explicit `model_id="fake-model-v1"` override so
  it can never collide with, or be silently mixed into, a real model's
  committed output file. `runner.run()` accepts `model_id`/`out_path`
  overrides for exactly this reason (and so tests never need real files).
- D9 — 2026-09-12 (W-A2) — `CallResult` already carries `session_id`,
  `use_case`, `step` per SPEC-cost-meter-and-angi-reuse.md section 4
  ("Changes to the base specs" — this is a direct edit to section 5 of the
  model-bench spec, so it applies now, not only when W-M1/W-M2 build the
  cost meter). Nothing in W-A2 reads or writes these three fields; they
  default to `None` and are simply carried through unused.
- D10 — 2026-09-12 (W-A2) — `anthropic_direct.py` and `openai_compatible.py`
  are implemented with the standard library (`urllib`) rather than the
  `anthropic` SDK or an OpenAI client library. Both are fallback-only paths
  (used only if Bedrock access isn't granted for a given model key), so
  adding a dependency for each felt like the wrong trade — `boto3` is the
  one real dependency added this task, for the primary Bedrock path, which
  does need it (hand-rolling AWS SigV4 signing is not worth it).
- D11 — 2026-09-12 (W-A2) — Self-caught bug, found by manually exercising
  the CLI (not by a pre-existing test): `BedrockProvider.call()` used to
  raise `RuntimeError("AWS_REGION is not set")` straight out of the method
  instead of returning a `CallResult(error=...)` like the other adapters do
  for missing configuration. Since `runner._process_one()` had no
  try/except around the provider call, this would have crashed the entire
  run — and lost every already-in-flight row's work along with it — the
  first time anyone ran without `AWS_REGION` set, which directly
  contradicts the "runs are resumable and idempotent" non-negotiable
  (section 1). Fixed two ways: (1) `BedrockProvider.call()` now catches its
  own client-setup failure and returns a normal error `CallResult`; (2)
  `runner._process_one()` now wraps its whole body in a try/except as
  defense in depth, so a bug in *any* adapter (present or future) can only
  ever fail one row, never the batch. Added
  `test_run_survives_a_provider_that_raises_instead_of_returning_a_call_result`
  as a regression test in `tests/test_runner.py`.
- D12 — 2026-09-12 (W-A2) — Also self-caught: the first version of
  `.gitignore`'s `.smoke_outputs/` line had a trailing `# comment` on the
  same line. `.gitignore` does not support inline comments — a `#` only
  starts a comment if it is the first character of the line, so the whole
  line became one (non-matching) literal pattern and `.smoke_outputs/` was
  silently NOT ignored. Caught by running `git status`/`git check-ignore`
  after a real `modelbench smoke` run and seeing the directory show up as
  untracked; fixed by moving the comment to its own line above the pattern.
- D13 — 2026-09-12 (W-A2) — `results.json`'s `worst_intents_fine` and
  `worst_groups_coarse` store the FULL sorted list (all 77 fine intents /
  all 10 coarse groups), not pre-truncated to 10. Section 7.1 item 5's
  "worst 10 intents" is a page-rendering choice (W-A3); the canonical JSON
  keeps the complete data so nothing has to be re-run to change how many
  are displayed later.
- D14 — 2026-09-12 (infra, W-A2 close-out sync) — The Mac-VM shell's mounted
  Claude folder (`~/Claude`, reached via the device bridge) does not support
  the create-lockfile-then-rename-over-an-existing-file pattern that git
  relies on internally for almost every write (`config`, `HEAD`, refs, the
  index) — not just explicit `rm`, which was already known to be blocked.
  The first attempt to sync this task's commits in place (`unzip -o` over
  the existing repo) failed pervasively for the same underlying reason
  (unlink of an existing file denied) and left the old copy in a mixed
  state; a follow-up `git clone`/`git fetch` directly into the mounted
  folder also failed partway (stray `config.lock`/`HEAD.lock` files from a
  failed internal rename). Working pattern going forward, for every future
  task's Mac re-sync: (1) `git clone`/build the fresh commit tree in the
  Mac-VM's own home directory, outside `~/mnt/`, where normal filesystem
  semantics apply and git's internal writes all succeed; (2) verify it
  there (`git log`, `git status`, tip SHA); (3) `cp -r` the finished tree
  into a *new* (non-pre-existing) path under `~/Claude/`, never overwriting
  an existing directory — a plain file-create operation, not a git
  operation, so it isn't subject to the same restriction; (4) verify again
  with a combined `git ls-files | sort | xargs sha256sum | sha256sum`
  compared against the same command run in the cloud workspace. Old/partial
  copies are renamed aside (`mv`, which does succeed) into a holding folder
  rather than deleted, since delete permission on that shell was requested
  once and declined — see the W-A2 report's OPEN section for exactly what
  got left where after this task's recovery.
- D15 — 2026-09-12 (W-M1) — **Spec conflict, quoting both lines** (per the
  BUILD INSTRUCTION's own stop-rule wording): `SPEC-cost-meter-and-angi-reuse.md`
  gives two different lists for `usage_events.step`. §1.1 (Data) says:
  `step: 'text-to-intent' | 'text-to-sql' | 'text-to-plan' | 'compose' |
  'verify' | 'live-box'`. §3 ("text-to-whatever" labeling) says: `Use these
  labels for the step field: text-to-intent, text-to-plan, text-to-sql,
  text-to-forecast-call, text-to-answer`. The two lists overlap (`text-to-intent`,
  `text-to-sql`, `text-to-plan`) but each also has values the other doesn't
  (§1.1 has `compose`, `verify`, `live-box`; §3 has `text-to-forecast-call`,
  `text-to-answer`). Resolved by taking the UNION of both lists (8 distinct
  values total) as the `CHECK` constraint in `web/api/meter/schema.sql`,
  rather than picking one list and silently dropping the other's values —
  a narrower constraint risks rejecting real rows AREA or Model Bench need
  to log later, and nothing in either section says the other list is wrong
  or superseded. This is disclosed here, in `schema.sql`'s own comments, and
  in the W-M1 report's OPEN section below, rather than halting the task —
  the union is safe (it only widens what's accepted) and blocking on this
  would have stopped ~95% of otherwise-unblocked W-M1 work. Flagging for
  Leon: if one of these two lists was meant to replace the other, say so
  and the constraint narrows to match; until then the union stands. Verified
  against a real PostgreSQL 16 database (not just read as text) — see
  `web/tests/schema.test.js`'s "accepts every step value from BOTH spec
  sections" test, which inserts all 8 values and confirms each is accepted,
  and confirms an invalid 9th value is rejected.
- D16 — 2026-09-12 (W-M1) — The cost-ledger page's per-day chart and table
  use "Mon D" date labels (e.g. "Sep 12"), not the spec's literal "Mon YY"
  (`SPEC-cost-meter-and-angi-reuse.md` §1.3: "dates as 'Mon YY'"). Caught
  by visual verification (a real Playwright screenshot of the rendered
  page, not just reading the code): with "Mon YY", every day inside the
  same month renders the SAME label — the fixture's three days (Sep 10,
  11, 12, all 2026) all showed as "Sep 26", making the day chart and table
  unreadable (three bars/rows, one indistinguishable label). "Mon YY" is
  kept (`charts.js`'s `formatMonYy`) for anything coarser than daily; "Mon
  D" (`formatMonD`) is used specifically for the day-grouped chart/table,
  where day-level distinction is the entire point. Flagging for Leon in
  case "Mon YY" was meant for a different chart than the daily one.
- Two more fixes from that same visual pass, not spec conflicts, just bugs
  caught by looking at the rendered output rather than only the code: (1)
  a short bar's value label used to be positioned with `Math.max` where it
  needed `Math.min`, so it could slide past the x-axis line and collide
  with the category label below it — now clamped inside the plot area;
  (2) a bar too short to contain a legible white label used to render it
  straddling the bar and the white page background (unreadable where it
  crossed onto white) — bars shorter than ~20px now get a dark-text label
  ABOVE the bar instead. Both have regression tests in `tests/charts.test.js`.
  Also: the itemized drawer table shows cost to 6 decimals, not the pill's
  4 — a single call can cost $0.00004, and 4-decimal rounding would print
  "$0.0000" for a real, nonzero cost.

- D17 — 2026-09-12 (self-caught, all three reports) — Every task report's
  "TASK: ... ET" timestamp (W-A1, W-A2, W-M1) was actually the commit's
  UTC time with "ET" mislabeled onto it, not a real ET conversion — e.g.
  W-A1 said "19:05 ET" but its commit (`5849e9e`) is timestamped
  `2026-09-12T19:05:59+00:00` UTC, which is 15:05 EDT, four hours earlier.
  Caught while answering Leon's question about session/context state, by
  checking `git log --date=iso-strict` against the reports' stated times
  rather than assuming they were right. Fixed all three headings below to
  the correct EDT time, with the UTC commit timestamp kept alongside for
  verification. No other content in the reports was affected — this was a
  label error on the heading only, not a factual error about what was
  built or tested.
- D18 — 2026-09-12 (W-A3) — `web/package.json` gains its first runtime
  dependency, `@aws-sdk/client-bedrock-runtime`, mirroring D10's `boto3`
  choice on the Python side: hand-rolling AWS SigV4 signing for the
  Bedrock Converse API in plain `fetch` is not a good trade for the one
  real (non-fallback) model path this page has. Everything else in
  `web/` stays zero-runtime-dependency by design.
- D19 — 2026-09-12 (W-A3, disclosed judgment call) — `SPEC-model-bench.md`
  §7 names accuracy, cost, latency, and calibration as the four things
  this page compares, but doesn't name exactly 4 headline chart panels or
  which single latency number (p50 vs p95) to chart. Built as 4 charts —
  accuracy (fine), cost per 1,000 messages, p50 latency, and Brier score
  (calibration's single-number summary; the fuller calibration picture is
  its own scatter chart+tables lower down) — because that is one chart
  per compared dimension and matches the leaderboard's own column order.
  p50 (not p95) was picked as the "typical" number worth a headline
  panel; p95 stays in the leaderboard table for the slow-case reader.
  Flagging for Leon in case a different 4th panel or p95 was intended.
- D20 — 2026-09-12 (W-A3, self-caught bugs) — Two real bugs found by
  Playwright-screenshotting the actual rendered page, not by reading the
  code (same pattern as D16): (1) the page's `/api/health` fetch callback
  was unconditionally overwriting `#methodology-prices-as-of` — which
  `render()` had already set correctly from the embedded results' own
  `prices_as_of`, i.e. the pricing snapshot the leaderboard's cost column
  was actually computed from — with the live health endpoint's current
  `prices_as_of`. Since prices can be updated after a results run, this
  could silently print a date that doesn't match the leaderboard's own
  numbers. Fixed by scoping that fetch callback to only the two
  call-counter fields it's actually needed for. (2) `.calibration-layout`'s
  CSS grid used the default `align-items: stretch`, so the much shorter
  `#chart-calibration` cell was stretched to match the much taller
  `#reliability-tables` column (5 full 10-row tables vs. one chart),
  leaving a large empty gap below a chart with no reason to grow. Fixed
  with `align-items: start` plus `#chart-calibration svg { width: 100%;
  height: auto; }`. Both verified fixed by rebuilding and re-screenshotting
  the page (before/after), not just by re-reading the changed CSS/JS.
- D21 — 2026-09-12 (W-A3) — `web/index.html` (the built page, produced by
  `scripts_build_web_page.py` from a results JSON) is gitignored, not
  committed — it is a build output, not source, the same way `dist/`
  already isn't committed. Before Gate 1 the only results file that
  exists is `results.sample.json` (synthetic per-model numbers, clearly
  marked with a `sample_disclosure` field); committing a built page under
  the real production filename `index.html` risked that sample-data page
  being mistaken for real output sitting in the repo, which conflicts
  with the "no fake/invented numbers ever" rule even though every number
  in it is honestly labeled as sample data. Anyone can reproduce it
  locally with the one command in README.md's new Model Bench section.

## Open items (blocked on Leon / Gate 1)

- Real Bedrock model ids + as-of prices for the 5 models in `data/prices.json`
  (currently all zeros — `report` will refuse to run against zeroed prices).
- AWS IAM key (Bedrock invoke + one S3 bucket), Neon connection strings,
  billing alarms, Vercel project env — none of these exist yet.
- `openpaymentsdata.cms.gov` (CMS Open Payments, needed for W-B1),
  `bedrock-runtime.us-east-1.amazonaws.com` (W-A4/W-B4), `console.neon.tech`
  (W-M2), and `api.vercel.com`/`vercel.com` (deploy) are all blocked by this
  environment's egress policy per Fable's measurement. Each of those steps
  either needs to run from Leon's Mac Terminal directly, or needs the
  relevant token/credential wired in so a different network path is used.
- D15 (above): the `usage_events.step` conflict between
  `SPEC-cost-meter-and-angi-reuse.md` §1.1 and §3 — resolved as a union for
  now; flag if one list should have replaced the other instead.
- D16 (above): the cost-ledger page's day-level chart/table use "Mon D"
  instead of the spec's literal "Mon YY" — flag if "Mon YY" was meant for
  a different (coarser) chart.
- D19 (above): the model-bench page's 4 headline charts (accuracy, cost,
  p50 latency, Brier) — flag if a different 4th panel or p95 was meant.
- Real Bedrock calls from `/api/run-one` can't be tested end-to-end until
  Gate 1 lands: today every model in the live box correctly shows "Model
  not yet configured (Gate 1 pending)" (verified in a real browser), but
  the actual `callBedrockConverse` success path is only exercised by unit
  tests against a fake client, not a real Bedrock call.

## Not yet built

Cost meter's live-Neon wiring (W-M2); the model-bench page's own real
run (needs Gate 1 prices/credentials to call Bedrock for real and
produce a non-sample `results.json` — `report`/the full pipeline itself
was already built in W-A2); AREA (W-B1/W-B2); the full run and deploy
(W-A4, needs Gate 1 credentials first).

## Reports

<!-- Each task's report (per the BUILD INSTRUCTION format) is appended below,
     most recent last. -->

### TASK: W-A1 — 2026-09-12 15:05 ET (commit timestamp 19:05:59 UTC)

TASK: W-A1 — repo scaffold, Banking77 full test split, coarse-intent map,
shared prompt + parser, prices.json skeleton, CI.

STATUS: Done.

BUILT:
- Full Banking77 test split pulled by direct GitHub file download (source
  blocked at huggingface.co, GitHub raw is the same original data) —
  `data/golden.jsonl`, 3,080 rows, each `{id, text, intent_fine,
  intent_coarse}`.
- `data/_labels.json` (77 labels verbatim), `data/ATTRIBUTION.md` (full
  citation, license, pull date).
- `data/coarse_map.json`: hand-built 77→10 coarse-group map, rule documented
  in README.md and `scripts_build_coarse_map.py`.
- `data/prices.json`: zeroed skeleton per spec, 5 model slots, waiting on
  Gate 1 for real Bedrock ids/prices.
- `src/modelbench/prompt.py`: shared prompt builder + a parser that never
  raises (handles fenced JSON, trailing/leading text, out-of-set labels,
  missing/out-of-range/wrong-type confidence).
- `src/modelbench/pull_data.py`: reusable pull with a license-permissiveness
  check that stops the run if the license isn't recognized as permissive.
- `src/modelbench/cli.py`: `pull-data` implemented; `run`/`report`/`smoke`
  registered and stubbed (exit 2) pointing at W-A2.
- `pyproject.toml`, `.gitignore`, `.env.example`, `LICENSE` (MIT + data
  attribution note), `.github/workflows/ci.yml`, `README.md`, `CONTEXT.md`.
- Git repo initialized, 4 commits (scaffold/config, data, code+tests,
  docs), no `.env` ever created or committed.
- Repo copied to `~/Claude/model-bench` on Leon's Mac (git history intact)
  and mirrored to Google Drive HQ/giggit/model-bench (a flattened snapshot
  doc plus standalone CONTEXT.md/README.md — a backup, not the source of
  truth; the Mac copy and its git history are canonical).

TESTED: `python3 -m ruff check .` clean. `python3 -m pytest -q`: 20/20
passing (15 parser tests, 5 data/coarse-map integrity tests). CI workflow
mirrors the same two commands. See D6 below for why the invocation is
`python3 -m X` rather than bare `X`.

SPEC CHECK:
- Full dataset, no sampling: 3,080/3,080 rows, 77/77 labels — matches spec
  exactly. `--limit` exists on the CLI but only for local smoke tests
  (W-A2+), defaults to `None`.
- No fake numbers: every count in this report and in CONTEXT.md/README.md
  comes from the actual pull/test run, not an estimate.
- Secrets only via env: `.env.example` documents every var; no `.env` file
  exists in the repo.
- Prices only from `prices.json` with an `as_of` date: yes, zeroed with
  `as_of: 2026-09-12`, real values blocked on Gate 1.
- Tests for every metric/parser/guard built so far: yes (parser + coarse
  map + data-shape tests). Runner/metrics tests land with W-A2.
- CI green: yes, and it uses the same commands verified locally.
- License stop-rule implemented and exercised in code (not yet triggered,
  since Banking77's license is permissive).

OPEN:
- Gate 1 items unchanged: Bedrock model ids/prices, AWS/Neon/Vercel
  credentials — see CONTEXT.md "Open items".
- Flagging one thing for Leon directly: his own instruction was "add it to
  HQ/giggit for anything giggit to be clear," and that's where this got
  mirrored (`HQ/giggit/model-bench/`). A separate note relayed from Fable
  suggested `HQ/projects/sunshine-audit/` instead. I followed your direct
  instruction since it's the clearer, more recent one from you personally —
  flag me if you actually want it under sunshine-audit too/instead.
- The Mac-VM shell here still can't run `vercel` (D4) or reach
  `bedrock-runtime`/`console.neon.tech`/CMS Open Payments (egress policy) —
  not a blocker for W-A1, will matter starting W-A2/W-B1/deploy.
- Mac-VM system Python is 3.10.12, not the 3.11 this repo targets (D5) —
  not exercised yet since all work so far happened in the cloud workspace's
  3.11 environment; `uv python install 3.11` is the fix path if/when code
  needs to run on the Mac VM directly.

NEXT: W-A2 (provider layer — Mock/Bedrock/Anthropic-direct/OpenAI-compatible
adapters, runner, metrics, report step). Waiting for your "go".

### TASK: W-A2 — 2026-09-12 15:26 ET (commit timestamp 19:26:39 UTC)

TASK: W-A2 — provider layer (Bedrock, Anthropic-direct, OpenAI-compatible,
fake adapters), runner, metrics, report step.

STATUS: Done.

BUILT:
- `src/modelbench/providers/base.py`: `CallResult` dataclass (per spec,
  plus the cost-meter addendum's session_id/use_case/step fields, unused
  for now), `Provider` protocol, and `call_with_retries` — a shared retry
  helper (5 attempts, exponential backoff + jitter, retryable errors only).
- `src/modelbench/providers/bedrock.py`: Converse API via boto3, region
  from `AWS_REGION`, token counts from the service's usage block.
- `src/modelbench/providers/anthropic_direct.py` and
  `openai_compatible.py`: fallback-only adapters, stdlib `urllib` (no SDK
  dependency), same retry contract.
- `src/modelbench/providers/fake.py`: local-smoke-tests-only adapter —
  reads the allowed intents back out of the prompt and returns a
  valid-shaped random answer; never a real run choice.
- `src/modelbench/runner.py`: `run(model_key, ...)` — resumable/idempotent
  (skips ids already in `outputs/<model_key>.jsonl`), bounded worker pool
  (default 10), one JSON line per row, progress every 100 rows. Defense in
  depth: the whole per-row worker is wrapped so a bug in any adapter can
  only ever fail that one row (see D11).
- `src/modelbench/metrics.py`: `accuracy_fine`, `accuracy_coarse`,
  `cost_per_1k`, `latency_p50_p95`, `brier`, `reliability_bins`,
  `per_intent` — all pure functions.
- `src/modelbench/report.py`: `build_report()` joins `outputs/*.jsonl` with
  `golden.jsonl`/`prices.json` into `results.json`; refuses to run against
  zero-priced models (`ZeroPricesError`); `check_results_schema()` is the
  reusable CI-gate logic.
- `cli.py`: `run`/`report`/`smoke` are real now. `smoke` runs 20 real
  Banking77 rows through the fake adapter, no network or secrets, writing
  to a new gitignored `.smoke_outputs/` (never `outputs/`).
- 3 commits (provider layer; runner/metrics/report/cli; docs), on top of
  W-A1's 5. Repo re-synced to `~/Claude/model-bench` on Leon's Mac and
  re-mirrored to Drive HQ/giggit/model-bench.

TESTED: `python3 -m ruff check .` clean. `python3 -m pytest -q`: 60/60
passing (up from 20 — 40 new tests: provider-layer mocks, a hand-computed
metrics toy set, results-schema fixtures, runner resumability). Also ran
the CLI by hand: `modelbench smoke` (20/20 rows, 0 errors, exit 0),
`modelbench report` (correctly refuses with a clear STOP message against
zero prices, exit 1), and `modelbench run --model claude-haiku --limit 2`
with no AWS credentials set (correctly writes 2 clean error rows and exits
1, rather than crashing) — then deleted that manual test's output from
`outputs/claude-haiku.jsonl` so no throwaway data was left committed.

SPEC CHECK:
- "Tests mock the network; no test calls a real API" (section 5): yes —
  boto3's client and `urllib.request.urlopen` are both mocked everywhere.
- Retry policy matches section 5 exactly (5 attempts, backoff+jitter,
  throttling/5xx only) and is shared by all three real adapters.
- "A run is all one adapter" (section 5): yes — `run()` resolves one
  provider for the whole call, never mixes per-row.
- Runner matches section 6.1 field-for-field (the 15 named fields),
  resumable/idempotent (tested), progress every 100 rows, bounded pool.
- Metrics formulas match section 6.2 exactly, verified against a
  hand-computed toy set (values computed independently in the test file,
  not by calling the functions under test).
- Report matches section 6.3's `results.json` shape; zero-price refusal
  implemented and exercised (not just described).
- No fake/illustrative numbers: `modelbench smoke`'s output is clearly
  separated from real results (own directory, own model_id, never
  committed) and this report only cites numbers from the actual test run
  and manual CLI checks above.

OPEN:
- Gate 1 items unchanged (Bedrock ids/prices, AWS/Neon/Vercel creds) — see
  "Open items" above.
- Two bugs I found and fixed myself before reporting this done, since they
  matter for anyone reading this later: (1) `BedrockProvider` used to crash
  the entire run with an uncaught `RuntimeError` if `AWS_REGION` wasn't
  set — fixed, plus added a defense-in-depth try/except around every
  per-row worker so no adapter bug can do that again; caught by manually
  running the CLI, not by a pre-existing test, so I added a regression
  test. (2) A `.gitignore` line with a trailing inline `# comment` doesn't
  work — the whole line becomes one non-matching pattern — so
  `.smoke_outputs/` was silently untracked-but-not-ignored until I fixed
  it. Both are D11/D12 in the Decisions list above.
- Not built yet: the openai_compatible/anthropic_direct adapters are
  untested against a REAL endpoint (mocks only, per spec) — first real
  exercise happens at Gate 1/W-A4 if Bedrock isn't available for a given
  model key.
- Mac re-sync hit real friction this task (see D14) — worth knowing about
  even though it's resolved: `~/Claude/model-bench` on your Mac is now a
  clean, verified copy (git tip `e54cfa7`, same combined sha256 of every
  tracked file as the cloud workspace). Two things are left in `~/Claude/`
  for you to deal with at your convenience, since I can't delete on that
  shell: `model-bench-precloud-backup-20260912-1930/` (the OLD repo
  directory, preserved intact per your "create a copy" instruction — safe
  to inspect for anything you typed there since W-A1 that isn't in the new
  copy, then trash it) and `_sync-cleanup-20260912/` (pure debris — three
  failed partial-sync attempts, the old transfer zip, the git bundle file —
  safe to trash without looking). Also folded the empty leftover
  `_to_delete/` from the W-A1 transfer into that same cleanup folder.

NEXT: per the task order, W-M1 (cost meter: `usage_events` schema, cost
function + tests, meter widget + ledger page against a fixture — no
secrets needed yet) comes before W-A3. Waiting for your "go".

### TASK: W-M1 — 2026-09-12 16:35 ET (commit timestamp 20:34:47 UTC)

TASK: W-M1 — Cost Meter shared module: `usage_events` schema, cost
function, the 3 read-only API endpoints, the client-side widget, and the
standalone `/use-cases/cost-ledger` page — all against fixture data, no
secrets, no live database (per `SPEC-cost-meter-and-angi-reuse.md` §6).

STATUS: Done.

BUILT (all under `web/`, plain Node, zero runtime dependencies):
- `api/meter/cost.js`: `computeCostUsd`/`roundCostUsd`, kept formula-identical
  to `modelbench.metrics.cost_per_1k` (W-A2).
- `api/meter/schema.sql`: the `usage_events` table (§1.1's fields exactly),
  3 indexes (`session_id`, `ts`, `use_case+ts`), CHECK constraints on
  `use_case` and `step` — `step`'s constraint is the D15 union (see OPEN).
- `api/meter/store.js`: fixture-backed `getAllEvents()`/`getEventsForSession()`
  — the one seam W-M2 swaps for a real Neon query.
- `api/meter/rate-limit.js`: per-IP in-memory limiter, 60/10min — abuse
  control only, visitors are never blocked for cost (rule 6).
- `api/meter/session.js`, `ledger.js`, `health.js`: the 3 endpoints from
  §1.2 — `GET /api/meter/session?id=`, `GET /api/meter/ledger?window=&group=`,
  `GET /api/meter/health`.
- `meter-widget.js`: the bottom-right pill + drawer from §1.3 — live
  session total (4 decimals) + call count on the pill; itemized table
  (6-decimal cost, since a single call can be $0.00004 and 4 decimals
  would print "$0.0000" for a real cost) + "Copy as CSV" in the drawer.
  Session id is in-memory only, per spec ("no cookies... reload starts a
  new session").
- `charts.js`: a small hand-built inline-SVG bar chart (title, axis lines,
  tick values, bold axis titles, no gridlines, value labels on/above each
  bar) — no charting library, so it can match page-style rule 11 exactly.
- `cost-ledger.js` + `cost-ledger.html`: the standalone page — "Overall
  insights" card (month-to-date cost, cheapest/dearest step per answer,
  cost share by use case), 4 charts (cost per day, by use case, by model,
  cost-per-answer by step), a cost-by-day table, and the plain-English
  explainer sentence. Every number is fetched live from `/api/meter/health`
  and `/api/meter/ledger` — nothing hard-coded.
- `dev-server.js` + `dev-widget-preview.html`: local-only (never deployed)
  tooling so both the ledger page and the widget could be checked in a
  real browser against the fixtures, not just read as code.
- `.github/workflows/ci.yml`: new `web-test` job — `postgres:16` service
  container + `node --test`, separate from the Python job so neither
  blocks the other.
- `.env.example`: documents `TEST_DATABASE_URL` (schema-test-only, not a
  production secret) and `DATABASE_URL` (unused placeholder for W-M2).
- 3 commits on top of W-A2's 8. Repo re-synced to `~/Claude/model-bench`
  on your Mac (same D14 procedure: built fresh in the Mac-VM's own home,
  verified there, `cp -r`'d into a new path, checksum-matched against the
  cloud workspace, then the old copy renamed aside — never deleted — into
  `_sync-cleanup-20260912/model-bench-pre-wm1-20260912-2035`) and
  re-mirrored to Drive HQ/giggit/model-bench.

TESTED: `python3 -m ruff check .` clean, `python3 -m pytest -q` still
60/60 (Python side untouched by this task). Node side: 109 tests across
33 suites — 97 pass + 12 honestly-skipped (with a stated reason, not
silently green) when `TEST_DATABASE_URL` isn't set; all 109 pass when it
is. Ran both ways, on both the cloud workspace and your Mac. The schema
tests (`tests/schema.test.js`) run `schema.sql`'s real DDL against an
actual PostgreSQL 16 database — not a text/regex check — and confirm the
constraints actually reject bad rows: an unrecognized `use_case`, an
unrecognized `step`, negative `cost_usd`/`input_tokens`/`output_tokens`/
`latency_ms`, and a missing `session_id`; also confirms all 8 D15-union
`step` values are accepted and a 9th, made-up one is rejected. CI now runs
this for real too (a `postgres:16` service container), not just locally.

Beyond unit tests: both the widget and the ledger page were opened in an
actual headless browser (Playwright, against `dev-server.js` serving the
real fixture-backed handlers) and screenshotted for a real visual check —
not just "the code looks right." That caught 3 real bugs no unit test
would have (all now fixed, with regression tests, and logged as part of
D16): a short bar's value label could slide onto the x-axis line and
collide with the category label below it; a bar too short to contain a
legible white label rendered it straddling the bar and the white page
background (unreadable where it crossed onto white); and the day chart's
date format collapsed same-month days to one indistinguishable label.

SPEC CHECK (§5 acceptance additions relevant to W-M1):
- "A visitor... can click the meter and see an itemized cost" (item 1):
  the widget code and its tests are done; not yet wired into a live page,
  since no use-case page exists yet to embed it in (W-A3 is next).
- "`/use-cases/cost-ledger` is live and reads only from the API" (item 2):
  the page itself is done and reads only from `/api/meter/*` — "live"
  (deployed on Vercel) is W-M2/deploy, out of this task's scope.
- Page style (rule 11): Lexend Light 300 body / 600 headings, no grey
  text, `#1a56db` for key terms and cost values, red (`#c81e1e`) only for
  the drawer's error rows, every chart has a title/axis lines/tick
  values/bold axis titles/no gridlines/labels on or in bars — verified
  visually, not just written.
- No fake/illustrative numbers: every number on the ledger page and in
  the widget comes from `/api/meter/*`, fed by the committed fixture file
  — nothing is hard-coded in `cost-ledger.js` or `meter-widget.js`.
- Secrets only via env: none needed for this task; `TEST_DATABASE_URL` is
  test-only (documented in `.env.example`, never committed as a real
  value) and no `.env` file exists in the repo.
- Tests for every metric/parser/guard: yes — cost math, rate limiting,
  all 3 endpoint handlers, the fixture store, both chart-data and
  chart-SVG logic, the CSV/formatting helpers, and the schema's real
  constraints.

OPEN — two things need your call, both already resolved with a disclosed,
reversible default rather than blocking the task:
1. **D15 — exact question**: `SPEC-cost-meter-and-angi-reuse.md` §1.1 says
   `usage_events.step` is `'text-to-intent' | 'text-to-sql' | 'text-to-plan'
   | 'compose' | 'verify' | 'live-box'`; §3 says to use `text-to-intent,
   text-to-plan, text-to-sql, text-to-forecast-call, text-to-answer`. I
   built the CHECK constraint as the union of both (8 values) rather than
   picking one. Was one of these meant to replace the other, or is the
   union correct?
2. **D16 — exact question**: §1.3 says chart dates should read "Mon YY".
   The day-grouped chart/table use "Mon D" instead (e.g. "Sep 12"),
   because "Mon YY" makes every day in the same month print the identical
   label. Was "Mon YY" meant for a different, coarser chart, or should
   the daily chart use a different format than what I chose?

Also open: W-M2 (wiring a real Neon database) is not built — that's this
task's stated scope, not a miss. The widget isn't embedded in any live
page yet since none exist (W-A3 is the model-bench page itself). Gate 1
items (Bedrock ids/prices, AWS/Neon/Vercel credentials) are unchanged —
see "Open items" above.

NEXT: W-A3 (the model-bench use-case page + its two Vercel functions,
`web/index.html` + `web/api/run-one.js` + `web/api/health.js`, per
SPEC-model-bench.md §7 — this is where `meter-widget.js` first gets
embedded in a real page). Waiting for your "go".

### TASK: W-A3 — 2026-09-12 18:07 ET (commit timestamp 21:55:26 UTC)

TASK: W-A3 — Model Bench use-case page (`web/index.html`, built from a
new `web/index.template.html`) and its two Vercel functions: `POST
/api/run-one` and `GET /api/health`, per `SPEC-model-bench.md` §7. This
is the first page where W-M1's `meter-widget.js` is embedded live.

STATUS: Done.

BUILT (all under `web/`, plus 3 small Python-side files):
- `web/index.template.html`: the page shell — title/subtitle with the
  4 blue key terms, "Overall insights" card, leaderboard table, 4
  headline charts (accuracy/cost/p50-latency/Brier — D19, disclosed
  choice), a calibration scatter chart + 5 per-model reliability
  tables, a "worst 10 intents" grid per model, the "try it live" box,
  and the methodology list. `window.__RESULTS__` is inlined at build
  time — the rendered page has no load-bearing network call for its
  own leaderboard/chart numbers.
- `web/model-bench-render.js`: pure, DOM-free rendering functions
  (leaderboard sort, the 4 insight bullets, chart specs, reliability
  series, worst-intents tables, methodology facts) plus `render()` to
  mount them — DOM-free so every function is unit-testable headlessly.
- `web/model-bench-live-box.js`: input validation (1,000-char max),
  `callRunOne()` (POSTs to `/api/run-one`, exact-wording plain-English
  errors including 429/Retry-After), and the 5-model answers table.
- `web/api/model-bench-prompt.js`: a byte-for-byte JS port of
  `src/modelbench/prompt.py`'s prompt-building and response-parsing —
  shares the literal template text via `data/prompt.txt` (exported by
  the new `scripts_export_prompt.py`), so Python and JS substitute
  identically with no escaping rules to keep in sync. `prompt.py`
  itself was refactored from `.format()`/escaped-brace style to
  `__INTENT_LIST__`/`__TEXT__` string-replace tokens to make this
  sharing possible; verified byte-identical in both languages by new
  regression tests.
- `web/api/run-one.js`: validates the message, builds the shared
  prompt, calls all 5 Bedrock models in parallel
  (`@aws-sdk/client-bedrock-runtime` — D18), logs a usage event and
  increments the monthly counter per model (best-effort, in a
  try/catch, so a logging failure never blocks the response — visitors
  are never blocked for cost, rule 6), and returns each model's
  intent/confidence/tokens/cost/latency. A model whose `data/prices.json`
  entry is still a Gate-1 zero/placeholder degrades to a plain-English
  "Model not yet configured (Gate 1 pending)." instead of calling
  Bedrock or erroring — this is also what makes the full handler
  testable for real today, before Gate 1.
- `web/api/health.js`: results-file freshness (`results_as_of`), the
  prices sheet's `as_of` date, and this month's live-box call count +
  estimated cost, all combined for the methodology section's last two
  bullets and the dev/ops health check.
- `web/api/model-bench-counter.js`: the in-memory write-seam for usage
  events + the monthly counter (same pattern as W-M1's `store.js`) —
  the one thing W-M2 replaces with real Neon writes.
- `scripts_build_web_page.py`: embeds a results JSON into the template
  at `window.__RESULTS__`. Defaults to `results.json` and fails closed
  with a clear message if it doesn't exist yet (points at
  `--results results.sample.json` for local dev) — a production build
  can never silently substitute sample data.
- `results.sample.json` (+ `scripts_build_results_sample.py`): real
  Banking77 label/intent data, but clearly-marked synthetic per-model
  numbers (`"sample_disclosure"` field), used only for local
  development/screenshots — never the default build target.
- `web/dev-server.js`: added routes for `/api/run-one` and `/api/health`
  plus a `readJsonBody()` helper (plain Node `http` doesn't auto-parse
  POST bodies the way Vercel's runtime does), and switched the `/`
  default route from the cost-ledger page to the model-bench page.
- README.md: new "Model Bench page (task W-A3)" section documenting
  every file above and how to preview it locally. CONTEXT.md: D18–D21
  logged below plus updated Open items / Not yet built.
- 1 commit on top of W-M1's 3. Repo re-synced to `~/Claude/model-bench`
  on your Mac (same D14 procedure: built fresh in the Mac-VM's own
  home, verified there — including a full `npm test` run — `cp -r`'d
  into a new path after moving the old copy aside into
  `_sync-cleanup-20260912/model-bench-pre-wa3-20260912-2200`, and
  checksum-matched against the cloud workspace) and re-mirrored to
  Drive HQ/giggit/model-bench (`model-bench-MANIFEST-2026-09-12-WA3.md`).

TESTED:
- `python3 -m ruff check .` clean. `python3 -m pytest -q`: 66/66 (up
  from 60 — `prompt.py`'s refactor and `scripts_build_web_page.py` each
  added regression tests).
- Node side: 218 tests across 61 suites — 206 pass, 12 honestly-skipped
  (stated reason: `TEST_DATABASE_URL` not set locally), 0 fail. Ran
  identically on the cloud workspace and on your Mac (`npm ci` +
  `npm test`, real Node v22 there).
- Beyond unit tests, the built page was checked in THREE separate real
  browsers, not just read as code: (1) headless Playwright in the cloud
  sandbox — full-page screenshots before and after each fix; (2) your
  actual Mac's Chrome, driven live against a dev server started for
  real on your Mac's own Node (not the sandboxed VM — a plain VM-hosted
  server isn't reachable from your real browser, so this specifically
  used `osascript`/`do shell script` to launch `node dev-server.js` on
  the real host and `mcp__claude-in-chrome__*` to drive your actual
  Chrome to `http://localhost:3300/`) — confirmed the page, the
  calibration-chart fix, the "Prices as of SAMPLE-NOT-REAL" fix, and a
  full live-box round trip (all 5 models correctly answering "Model not
  yet configured (Gate 1 pending)") all render correctly there, per
  your stated preference for visible-browser verification on your own
  machine, not headless-only. Both dev server processes (VM and real
  Mac) were stopped afterward.
- That visual pass caught 2 real bugs no unit test would have (D20,
  both now fixed with regression coverage where testable, and reverified
  by rebuilding + re-screenshotting): the `/api/health` fetch was
  overwriting the results' own `prices_as_of` with the live current
  value; and `.calibration-layout`'s CSS grid was stretching the small
  calibration chart to match the much-taller reliability-tables column,
  leaving a large empty gap.

SPEC CHECK (§7 acceptance items relevant to W-A3):
- Full test split, no sampling: `results.sample.json` carries real
  Banking77 label/intent data (n=3,080 per model) even though its
  per-model metrics are synthetic — no row count was ever reduced.
- No fake/invented numbers presented as real: `results.sample.json`
  is disclosed as sample data in its own JSON (`sample_disclosure`)
  AND on the rendered page itself (methodology's "Prices as of
  SAMPLE-NOT-REAL"); the default production build path
  (`scripts_build_web_page.py` with no `--results` override) refuses
  to run at all until a real `results.json` exists (Gate 1 + a real
  run, not yet done — see Open items).
- Visitors never blocked for cost: usage-event logging and the monthly
  counter increment are both wrapped in try/catch in `run-one.js` and
  never gate the response; the live box itself has no cost gate.
- Secrets only via env: `AWS_REGION`/`AWS_ACCESS_KEY_ID`/
  `AWS_SECRET_ACCESS_KEY` (already in `.env.example` from W-A2) are the
  only ones `run-one.js` reads; nothing new needed adding.
- Page style (rule 11): Lexend Light 300 body / 600 headings, no grey
  text, `#1a56db` key terms, every "Overall insights" section opens
  with a bullet card, every chart has a title/axis lines/tick
  values/bold axis titles/no gridlines/value labels, text under charts
  is bullets not paragraphs — verified visually in 3 browsers, not
  just written.
- Tests for every metric/parser/guard: yes — prompt building/parsing
  (JS+Python parity), rendering/insight math, live-box validation and
  error formatting, the run-one handler (config-check, cost calc,
  per-model isolation, rate limiting, 400/200/429), the health handler,
  and the counter seam.
- Meter widget embedded live (§5/§1.3 from the cost-meter spec): yes —
  `initMeterWidget()` + `mountLiveBox()` wired into
  `index.template.html`'s module script; confirmed rendering (pill,
  "$0.0000 · 0 calls") in all 3 browser checks above.

OPEN — one thing needs your call, already resolved with a disclosed,
reversible default rather than blocking the task:
1. **D19 — exact question**: `SPEC-model-bench.md` §7 names accuracy,
   cost, latency, and calibration as the 4 things this page compares,
   but doesn't specify exactly 4 headline chart panels or which latency
   percentile to chart. I built 4 charts — accuracy (fine), cost per
   1,000 messages, **p50** latency, and Brier score — one per compared
   dimension, matching the leaderboard's column order (p95 stays in
   the leaderboard table only). Was a different 4th panel or p95
   intended for the headline row?

Also open, not spec conflicts, just disclosed choices:
- D18: `web/package.json` now has one runtime dependency
  (`@aws-sdk/client-bedrock-runtime`), mirroring D10's `boto3` — flag
  if a different Bedrock-calling approach was wanted.
- D21: the built `web/index.html` is gitignored (build output, not
  source) rather than committed — regenerate it locally per README.md;
  flag if you'd rather it were committed anyway (e.g. for a static
  preview link) despite the sample-data-under-a-real-filename risk.
- Real Bedrock calls from `/api/run-one` are exercised only against a
  fake client in unit tests and are not yet reachable for real (Gate 1
  pending) — the live-box round trip that WAS tested (today, correctly)
  is the "not yet configured" path, not the real-model-call path.
- W-M2 (a real Neon database) is still not built — unchanged, that
  task's own stated scope. Gate 1 items (Bedrock ids/prices, AWS/Neon/
  Vercel credentials) are unchanged — see "Open items" above.

NEXT: W-B1 (per the fixed task order). Waiting for your "go" — per the
BUILD INSTRUCTION, I have not started it.
