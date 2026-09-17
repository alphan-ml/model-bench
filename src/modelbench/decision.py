"""Builds outputs/decision.json: the decision pack behind README.md's "The
Decision" section -- everything computed from files already in this repo
(data/golden.jsonl, outputs/*.jsonl, data/prices.json,
data/coarse_map.json), plus a locally trained classifier baseline.

    python3 -m modelbench.decision

No model-provider call and no network call other than the one-time,
cached direct-file download of the Banking77 TRAIN split (see
baseline.py's module docstring) -- everything else here is arithmetic over
already-committed JSON/JSONL files.

Five tasks, one per module:
  1. baseline.py    -- TF-IDF + logistic regression baseline
  2. bootstrap.py   -- paired bootstrap accuracy/difference intervals
  3. errors.py      -- confusion pairs, hardest shared-failure intents
  4. escalation.py  -- confidence-threshold auto-route/escalate policy
  5. routing.py     -- cost per correctly routed message, quality curve
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from modelbench import baseline, bootstrap, errors, escalation, metrics, routing
from modelbench.report import _enrich, _load_golden_by_id, _load_output_rows, _load_prices

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"
DECISION_PATH = OUTPUTS_DIR / "decision.json"

MODEL_KEYS = ["nova", "llama", "mistral"]
SEED = 26
RUN_DATE = "2026-09-17"


def _load_coarse_map(data_dir: Path) -> dict:
    with open(data_dir / "coarse_map.json") as f:
        return json.load(f)


def _load_real_models(data_dir: Path, outputs_dir: Path, model_keys: list[str]) -> dict:
    """Loads + enriches outputs/<key>.jsonl for every real model, and looks
    up each one's price row. Returns {key: {"rows": [...], "price": {...}}}.
    """
    prices = _load_prices(data_dir)
    price_by_key = {m["key"]: m for m in prices["models"]}
    golden_by_id = _load_golden_by_id(data_dir)

    out = {}
    for key in model_keys:
        output_rows = _load_output_rows(key, outputs_dir)
        enriched = _enrich(output_rows, golden_by_id)
        out[key] = {"rows": enriched, "price": price_by_key[key]}
    return out


def build_decision(
    data_dir: Path = DATA_DIR,
    outputs_dir: Path = OUTPUTS_DIR,
    model_keys: list[str] | None = None,
    train_jsonl_path: Path | None = None,
    seed: int = SEED,
) -> dict:
    model_keys = model_keys or MODEL_KEYS

    golden_by_id = _load_golden_by_id(data_dir)
    id_order = sorted(golden_by_id.keys())
    coarse_map = _load_coarse_map(data_dir)
    real_models = _load_real_models(data_dir, outputs_dir, model_keys)

    # ---- Task 1: classifier baseline -----------------------------------
    golden_rows_sorted = [golden_by_id[i] for i in id_order]
    dest_path = train_jsonl_path or baseline.TRAIN_JSONL_PATH
    baseline_result = baseline.run_baseline(golden_rows_sorted, coarse_map, dest_path=dest_path)
    have_baseline = baseline_result["status"] == "ok"

    # ---- correctness arrays, joined by id (paired across models) -------
    correct_by_model: dict[str, list[bool]] = {}
    for key in model_keys:
        rows_by_id = {r["id"]: r for r in real_models[key]["rows"]}
        correct_by_model[key] = [rows_by_id[i]["correct_fine"] for i in id_order]

    if have_baseline:
        baseline_rows_by_id = {r["id"]: r for r in baseline_result["rows"]}
        correct_by_model["classifier"] = [baseline_rows_by_id[i]["correct_fine"] for i in id_order]

    # ---- Task 2: paired bootstrap ---------------------------------------
    bootstrap_result = bootstrap.paired_bootstrap(correct_by_model, seed=seed)

    # ---- Task 3: error analysis ------------------------------------------
    top_confused = {
        key: errors.top_confused_pairs(real_models[key]["rows"]) for key in model_keys
    }
    hardest_intents = errors.hardest_intents_all_wrong(
        {key: real_models[key]["rows"] for key in model_keys}
    )

    # ---- Task 4: escalation policy ---------------------------------------
    escalation_result = {
        key: escalation.run_escalation(real_models[key]["rows"], seed=seed) for key in model_keys
    }

    # ---- Task 5: cost per correct route + quality/automation curve ------
    cost_per_correct_route = {}
    quality_curve = {}
    accuracy_fine_by_model = {}
    cost_per_1k_by_model = {}
    for key in model_keys:
        rows = real_models[key]["rows"]
        price = real_models[key]["price"]
        acc = metrics.accuracy_fine(rows)
        cost_1k = metrics.cost_per_1k(rows, price)
        accuracy_fine_by_model[key] = acc
        cost_per_1k_by_model[key] = cost_1k
        cost_per_correct_route[key] = routing.cost_per_correct_route(cost_1k, acc)
        quality_curve[key] = routing.quality_automation_curve(rows)

    if have_baseline:
        accuracy_fine_by_model["classifier"] = baseline_result["accuracy_fine"]
        cost_per_1k_by_model["classifier"] = baseline.COST_PER_1K_USD
        cost_per_correct_route["classifier"] = routing.cost_per_correct_route(
            baseline.COST_PER_1K_USD, baseline_result["accuracy_fine"]
        )
        # The classifier has no model-reported confidence field, so it has
        # no escalation policy or quality/automation curve (Tasks 4-5 are
        # defined on model-reported confidence, which only the three real
        # models emit) -- deliberately omitted rather than faked.

    # ---- assemble ----------------------------------------------------------
    baseline_out = dict(baseline_result)
    baseline_out.pop("rows", None)  # per-row predictions aren't part of the summary

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_date": RUN_DATE,
        "seed": seed,
        "n_messages": len(id_order),
        "source_files": {
            "golden": "data/golden.jsonl",
            "outputs": {key: f"outputs/{key}.jsonl" for key in model_keys},
            "prices": "data/prices.json",
            "coarse_map": "data/coarse_map.json",
            "train_split": (
                baseline_result.get("train_path")
                if have_baseline
                else "data/train.jsonl (not available)"
            ),
        },
        "classifier_baseline": baseline_out,
        "accuracy_fine": accuracy_fine_by_model,
        "cost_per_1k_usd": cost_per_1k_by_model,
        "cost_per_correct_route_usd": cost_per_correct_route,
        "bootstrap": bootstrap_result,
        "error_analysis": {
            "top_confused_pairs": top_confused,
            "hardest_intents_all_three_wrong": hardest_intents,
        },
        "escalation": escalation_result,
        "quality_automation_curve": quality_curve,
    }


def main() -> int:
    decision = build_decision()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(DECISION_PATH, "w") as f:
        json.dump(decision, f, indent=2)

    status = decision["classifier_baseline"]["status"]
    print(f"wrote {DECISION_PATH}", file=sys.stderr)
    print(f"classifier baseline: {status}", file=sys.stderr)
    if status != "ok":
        print(f"  blocked: {decision['classifier_baseline']['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
