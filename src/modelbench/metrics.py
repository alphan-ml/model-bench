"""Pure metric functions over a list of row dicts.

Per SPEC-model-bench.md section 6.2. Rows passed in here are the "enriched"
rows report.py builds by joining outputs/<model>.jsonl with data/golden.jsonl
(so intent_fine/intent_coarse — the true labels — are present alongside the
runner's own correct_fine/correct_coarse/confidence/latency_ms/error fields).
Rows with invalid=True already count as wrong in correct_fine/correct_coarse
(computed by the runner at write time, per section 4); these functions trust
that and do not re-derive correctness themselves.
"""

from __future__ import annotations

from collections import defaultdict


def accuracy_fine(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r["correct_fine"]) / len(rows)


def accuracy_coarse(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r["correct_coarse"]) / len(rows)


def cost_per_1k(rows: list[dict], price: dict) -> float:
    """price: {"input_per_1m": float, "output_per_1m": float, ...}.

    (mean_in * in_price + mean_out * out_price) / 1e6 * 1000, in dollars,
    exactly as SPEC-model-bench.md section 6.2 gives the formula.
    """
    if not rows:
        return 0.0
    mean_in = sum(r["input_tokens"] for r in rows) / len(rows)
    mean_out = sum(r["output_tokens"] for r in rows) / len(rows)
    return (mean_in * price["input_per_1m"] + mean_out * price["output_per_1m"]) / 1e6 * 1000


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile over an already-sorted list (matches
    the common "linear" method — e.g. numpy's default). pct is 0-100."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


def latency_p50_p95(rows: list[dict]) -> tuple[float, float]:
    """p50/p95 of latency_ms, over non-error rows only."""
    values = sorted(r["latency_ms"] for r in rows if not r["error"])
    return _percentile(values, 50), _percentile(values, 95)


def brier(rows: list[dict]) -> float:
    """Mean of (confidence/100 - correct_fine)^2 over rows with a confidence
    value (rows where confidence is None are excluded, per spec)."""
    scored = [r for r in rows if r["confidence"] is not None]
    if not scored:
        return 0.0
    total = sum(
        (r["confidence"] / 100 - (1.0 if r["correct_fine"] else 0.0)) ** 2 for r in scored
    )
    return total / len(scored)


def reliability_bins(rows: list[dict]) -> list[dict]:
    """10 bins of confidence: [0,10), [10,20), ..., [90,100]. Each bin:
    {"bin": "0-10", "n", "mean_confidence", "observed_accuracy"}. Rows
    without a confidence value are excluded. A confidence of 100 falls in
    the last bin (index 9), same as 90-99.
    """
    scored = [r for r in rows if r["confidence"] is not None]
    bins: list[list[dict]] = [[] for _ in range(10)]
    for r in scored:
        idx = min(r["confidence"] // 10, 9)
        bins[idx].append(r)

    result = []
    for i, bucket in enumerate(bins):
        label = f"{i * 10}-{i * 10 + 10}"
        if not bucket:
            result.append(
                {"bin": label, "n": 0, "mean_confidence": 0.0, "observed_accuracy": 0.0}
            )
            continue
        mean_confidence = sum(r["confidence"] for r in bucket) / len(bucket)
        observed_accuracy = sum(1 for r in bucket if r["correct_fine"]) / len(bucket)
        result.append(
            {
                "bin": label,
                "n": len(bucket),
                "mean_confidence": mean_confidence,
                "observed_accuracy": observed_accuracy,
            }
        )
    return result


def per_intent(rows: list[dict], level: str) -> list[dict]:
    """level: "fine" or "coarse". Accuracy and n per intent/group, grouped by
    the TRUE label (rows must carry intent_fine/intent_coarse from the golden
    join) and sorted worst (lowest accuracy) first.
    """
    if level not in ("fine", "coarse"):
        raise ValueError(f"level must be 'fine' or 'coarse', got {level!r}")
    key_field = "intent_fine" if level == "fine" else "intent_coarse"
    correct_field = "correct_fine" if level == "fine" else "correct_coarse"

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r[key_field]].append(r)

    result = []
    for name, group_rows in groups.items():
        n = len(group_rows)
        acc = sum(1 for r in group_rows if r[correct_field]) / n
        result.append({"name": name, "n": n, "accuracy": acc})

    result.sort(key=lambda x: x["accuracy"])
    return result
