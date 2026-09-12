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

## Not yet built

Provider layer, runner, metrics, report (W-A2); cost meter (W-M1/W-M2); the
web page and its two functions (W-A3); the full run and deploy (W-A4).

## Reports

<!-- Each task's report (per the BUILD INSTRUCTION format) is appended below,
     most recent last. -->
