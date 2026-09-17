"""Cost-per-correctly-routed-message and the quality/automation trade-off
curve. Task 5 of the decision pack (see README.md's "The Decision").

Reuses each model's already-computed cost_per_1k and fine accuracy
(metrics.cost_per_1k / metrics.accuracy_fine, the same formulas behind
results.json) -- nothing here calls a model or the network.
"""

from __future__ import annotations

CURVE_THRESHOLDS = range(50, 101, 5)


def cost_per_correct_route(cost_per_1k_usd: float, accuracy_fine: float) -> float | None:
    """cost_per_1k / accuracy_fine: the cost of 1,000 messages divided by
    the fraction of them that land correctly, i.e. the cost of 1,000
    CORRECTLY routed messages. Returns None (not a number) when accuracy
    is exactly zero -- there is no meaningful cost-per-correct-route value
    when nothing is ever correct."""
    if accuracy_fine == 0:
        return None
    return cost_per_1k_usd / accuracy_fine


def quality_automation_curve(rows: list[dict], thresholds: range = CURVE_THRESHOLDS) -> list[dict]:
    """rows: one model's enriched rows (confidence, correct_fine) over
    every message in the recorded run (no train/test split -- this is a
    descriptive curve over the full run, not a fitted policy; see
    escalation.py for the fitted A/B policy). For each threshold in
    `thresholds`, reports the automation rate (share of all rows with
    confidence >= threshold) and the fine accuracy of that auto-routed
    subset (None if the subset is empty at that threshold)."""
    n_total = len(rows)
    curve = []
    for t in thresholds:
        auto = [r for r in rows if r["confidence"] is not None and r["confidence"] >= t]
        acc = sum(1 for r in auto if r["correct_fine"]) / len(auto) if auto else None
        curve.append(
            {
                "threshold": t,
                "automation_rate": len(auto) / n_total if n_total else 0.0,
                "auto_accuracy": acc,
            }
        )
    return curve
