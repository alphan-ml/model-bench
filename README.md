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

Not yet built (later tasks): the cost meter (W-M1/W-M2), the web page and its
two functions (W-A3), and the full 5-model × 3,080-row run against real
Bedrock (W-A4, needs Gate 1 credentials first).

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
