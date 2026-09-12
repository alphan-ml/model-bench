"""Builds results.json from outputs/*.jsonl + data/golden.jsonl +
data/prices.json.

Per SPEC-model-bench.md section 6.3. Refuses to build a report for any model
still carrying data/prices.json's zero-price placeholders — a report over
$0 prices would be silently meaningless, and the spec requires this to fail
loudly instead (the non-negotiables in section 1: "Code never contains a
price" and "no fake numbers" apply here too).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from modelbench import metrics

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"
RESULTS_PATH = REPO_ROOT / "results.json"


class ZeroPricesError(RuntimeError):
    """Raised when data/prices.json still has placeholder zero prices for a
    model being reported on. Per spec section 3.3: this must fail with a
    clear error, not silently proceed."""


def _load_golden_by_id(data_dir: Path = DATA_DIR) -> dict[int, dict]:
    rows: dict[int, dict] = {}
    with open(data_dir / "golden.jsonl") as f:
        for line in f:
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def _load_prices(data_dir: Path = DATA_DIR) -> dict:
    with open(data_dir / "prices.json") as f:
        return json.load(f)


def _load_output_rows(model_key: str, outputs_dir: Path) -> list[dict]:
    path = outputs_dir / f"{model_key}.jsonl"
    rows = []
    if not path.exists():
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _enrich(output_rows: list[dict], golden_by_id: dict[int, dict]) -> list[dict]:
    enriched = []
    for row in output_rows:
        golden_row = golden_by_id[row["id"]]
        enriched.append(
            {
                **row,
                "intent_fine": golden_row["intent_fine"],
                "intent_coarse": golden_row["intent_coarse"],
            }
        )
    return enriched


def build_report(
    model_keys: list[str] | None = None,
    data_dir: Path = DATA_DIR,
    outputs_dir: Path = OUTPUTS_DIR,
) -> dict:
    prices = _load_prices(data_dir)
    golden_by_id = _load_golden_by_id(data_dir)
    n_rows_expected = len(golden_by_id)

    price_by_key = {m["key"]: m for m in prices["models"]}
    if model_keys is None:
        model_keys = list(price_by_key.keys())

    models_out = []
    for key in model_keys:
        price = price_by_key.get(key)
        if price is None:
            raise ValueError(f"model key {key!r} not found in data/prices.json")
        if price["input_per_1m"] == 0.0 and price["output_per_1m"] == 0.0:
            raise ZeroPricesError(
                f"data/prices.json has zero prices for {key!r}. Fill in real "
                "prices (Gate 1) before running the report."
            )

        output_rows = _load_output_rows(key, outputs_dir)
        enriched = _enrich(output_rows, golden_by_id)

        n_rows = len(enriched)
        n_errors = sum(1 for r in enriched if r["error"])
        p50, p95 = metrics.latency_p50_p95(enriched)

        models_out.append(
            {
                "key": key,
                "model_id": price["model_id"],
                "adapter": enriched[0]["adapter"] if enriched else None,
                "n_rows": n_rows,
                "n_errors": n_errors,
                "accuracy_fine": metrics.accuracy_fine(enriched),
                "accuracy_coarse": metrics.accuracy_coarse(enriched),
                "cost_per_1k_usd": metrics.cost_per_1k(enriched, price),
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
                "brier": metrics.brier(enriched),
                "reliability": metrics.reliability_bins(enriched),
                # Full sorted lists (not pre-truncated): the page (W-A3)
                # decides how many to show ("worst 10" per section 7.1).
                "worst_intents_fine": metrics.per_intent(enriched, "fine"),
                "worst_groups_coarse": metrics.per_intent(enriched, "coarse"),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prices_as_of": prices["as_of"],
        "n_rows_expected": n_rows_expected,
        "models": models_out,
    }


def check_results_schema(results: dict) -> list[str]:
    """Returns a list of violation messages (empty list = passes). Per
    SPEC-model-bench.md section 6.3: every model must have
    n_rows == n_rows_expected and n_errors / n_rows <= 2%.
    """
    violations = []
    n_rows_expected = results["n_rows_expected"]
    for model in results["models"]:
        key = model["key"]
        if model["n_rows"] != n_rows_expected:
            violations.append(
                f"{key}: n_rows={model['n_rows']} != n_rows_expected={n_rows_expected}"
            )
        if model["n_rows"] > 0:
            error_rate = model["n_errors"] / model["n_rows"]
            if error_rate > 0.02:
                violations.append(
                    f"{key}: error rate {error_rate:.1%} exceeds 2% "
                    f"({model['n_errors']}/{model['n_rows']})"
                )
    return violations


def main() -> int:
    try:
        report = build_report()
    except ZeroPricesError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1

    violations = check_results_schema(report)
    if violations:
        print("WARNING: results.json does not pass the schema check yet:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "(this is expected before a full run exists — e.g. W-A2 has no "
            "real run yet; CI's hard gate is test_results_schema.py against "
            "a committed results.json once one exists)",
            file=sys.stderr,
        )

    with open(RESULTS_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"wrote {RESULTS_PATH}")
    return 0
