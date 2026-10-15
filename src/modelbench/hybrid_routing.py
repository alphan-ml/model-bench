"""Paired local-first / hosted-escalation benchmark with cross-fitted routing thresholds.

Only committed hosted runs are used: there are NO additional paid model calls.
Routing thresholds are selected on one half of the labeled test split and
reported on the opposite half. Not a release decision without a fresh cohort.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from modelbench import baseline
from modelbench.escalation import split_halves
from modelbench.report import _load_output_rows, _load_prices

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"
MODELS = ("nova", "llama", "mistral")
THRESHOLDS = tuple(i / 100 for i in range(0, 101, 5))


def policy(rows: list[dict], threshold: float) -> dict:
    """Confidence less than threshold routes to the hosted model."""
    if not rows:
        raise ValueError("empty routing slice")
    escalated = [r for r in rows if r["local_conf"] < threshold]
    hosted_calls = len(escalated)
    correct = sum(
        bool(r["hosted_correct"]) if r["local_conf"] < threshold else bool(r["local_correct"])
        for r in rows
    )
    return {
        "threshold": threshold,
        "n": len(rows),
        "accuracy": correct / len(rows),
        "escalation_fraction": hosted_calls / len(rows),
        "provider_cost_per_1k_usd": (
            sum(float(r["hosted_cost_usd"]) for r in escalated) * 1000 / len(rows)
        ),
        "provider_cost_only": True,
    }


def choose_threshold(rows: list[dict], max_provider_cost_per_1k_usd: float) -> dict:
    if max_provider_cost_per_1k_usd < 0:
        raise ValueError("negative provider cost budget")
    candidates = [
        policy(rows, threshold) for threshold in THRESHOLDS
        if policy(rows, threshold)["provider_cost_per_1k_usd"] <= max_provider_cost_per_1k_usd + 1e-12
    ]
    if not candidates:
        raise RuntimeError("No viable policy, including always-local")
    return min(candidates, key=lambda x: (-x["accuracy"], x["provider_cost_per_1k_usd"], x["threshold"]))


def crossfit(rows: list[dict], max_provider_cost_per_1k_usd=0.20, seed=26) -> dict:
    ids = [int(r["id"]) for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate message IDs")
    a, b = split_halves(ids, seed=seed)
    rows_by_id = {int(r["id"]): r for r in rows}
    left = [rows_by_id[i] for i in a]
    right = [rows_by_id[i] for i in b]
    chosen_a, chosen_b = (
        choose_threshold(left, max_provider_cost_per_1k_usd),
        choose_threshold(right, max_provider_cost_per_1k_usd),
    )
    return {
        "target": "maximize measured intent accuracy subject to a provider-cost budget",
        "max_provider_cost_per_1k_usd": max_provider_cost_per_1k_usd,
        "select_on_a_evaluate_on_b": {
            "selection": chosen_a,
            "opposite_half_evaluation": policy(right, chosen_a["threshold"]),
            "always_local_accuracy": policy(right, 0.0)["accuracy"],
        },
        "select_on_b_evaluate_on_a": {
            "selection": chosen_b,
            "opposite_half_evaluation": policy(left, chosen_b["threshold"]),
            "always_local_accuracy": policy(left, 0.0)["accuracy"],
        },
        "limitations": (
            "Cross-fitted offline test-split simulation, not incremental prospective data. "
            "Provider charges use recorded input/output tokens; local hosting and request "
            "overhead are unpriced, and local latency must be benchmarked separately."
        ),
    }


def main() -> None:
    if not baseline.TRAIN_JSONL_PATH.exists():
        raise SystemExit("Run 'python -m modelbench.decision' to cache the labeled training set first")
    train = baseline.load_jsonl(baseline.TRAIN_JSONL_PATH)
    golden = baseline.load_jsonl(DATA_DIR / "golden.jsonl")
    pipe = baseline.train_classifier(train)
    probs = pipe.predict_proba([r["text"] for r in golden])
    argmax = np.argmax(probs, axis=1)
    local_pred = pipe.classes_[argmax]
    confidence = probs[np.arange(len(golden)), argmax]
    prices = {item["key"]: item for item in _load_prices(DATA_DIR)["models"]}

    comparisons = {}
    for key in MODELS:
        hosted = {r["id"]: r for r in _load_output_rows(key, OUT_DIR)}
        if set(hosted) != {r["id"] for r in golden}:
            raise SystemExit("Hosted results incomplete for " + key + "; no estimated answers")
        price = prices[key]
        rows = []
        for i, row in enumerate(golden):
            h = hosted[row["id"]]
            token_cost = (
                (h["input_tokens"] or 0) * price["input_per_1m"]
                + (h["output_tokens"] or 0) * price["output_per_1m"]
            ) / 1e6
            rows.append({
                "id": row["id"],
                "local_conf": float(confidence[i]),
                "local_correct": bool(local_pred[i] == row["intent_fine"]),
                "hosted_correct": bool(h["correct_fine"]),
                "hosted_cost_usd": float(token_cost),
            })
        comparisons[key] = crossfit(rows)

    result = {
        "n_messages": len(golden),
        "training_size": len(train),
        "policy": "local model first, hosted model for uncertain classifications",
        "routing_evidence": comparisons,
        "status": "research experiment; no model-routing promotion",
    }
    out = OUT_DIR / "local_first_routing_crossfit.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(out), "models": list(comparisons)}))


if __name__ == "__main__":
    main()
