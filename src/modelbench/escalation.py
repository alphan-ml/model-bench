"""Escalation policy on model-reported confidence. Task 4 of the decision
pack (see README.md's "The Decision").

Confidence here is always the MODEL's own self-reported number (0-100, or
null when the response was unparseable/empty) -- never a calibrated
probability, and this module labels it that way everywhere it surfaces.

Rows with confidence=None always count as escalated: they can never
satisfy `confidence >= threshold` for any threshold in the grid, so
evaluate_policy needs no special-case branch for them -- this is the
correct behavior falling straight out of the comparison, documented here
rather than hidden in a conditional that does nothing.
"""

from __future__ import annotations

import random

SEED = 26
TARGETS = (95, 98)
THRESHOLD_GRID = range(0, 101)


def split_halves(ids: list[int], seed: int = SEED) -> tuple[list[int], list[int]]:
    """Deterministically splits `ids` into two halves A and B using `seed`.
    For the decision pack's 3,080 messages this is an even split: 1,540
    ids in each half. Both returned lists are sorted for a stable,
    readable ordering; only membership is randomized."""
    shuffled = sorted(ids)
    random.Random(seed).shuffle(shuffled)
    mid = len(shuffled) // 2
    return sorted(shuffled[:mid]), sorted(shuffled[mid:])


def _accuracy(rows: list[dict]) -> float | None:
    if not rows:
        return None
    return sum(1 for r in rows if r["correct_fine"]) / len(rows)


def find_threshold(rows: list[dict], target_pct: float) -> int | None:
    """Smallest integer confidence threshold t in [0, 100] such that the
    auto-routed subset (confidence is not None and confidence >= t) has
    fine accuracy >= target_pct/100 and is non-empty. Returns None if no
    threshold in the grid reaches the target."""
    target = target_pct / 100
    for t in THRESHOLD_GRID:
        subset = [r for r in rows if r["confidence"] is not None and r["confidence"] >= t]
        acc = _accuracy(subset)
        if acc is not None and acc >= target:
            return t
    return None


def evaluate_policy(rows: list[dict], threshold: int | None) -> dict:
    """Applies `threshold` (as returned by find_threshold, possibly None)
    to `rows` and reports the automation rate plus accuracy on each side
    of the split. Null-confidence rows are always escalated."""
    n_total = len(rows)
    if threshold is None:
        auto: list[dict] = []
    else:
        auto = [r for r in rows if r["confidence"] is not None and r["confidence"] >= threshold]
    auto_ids = {r["id"] for r in auto}
    escalated = [r for r in rows if r["id"] not in auto_ids]

    return {
        "threshold": threshold,
        "n_total": n_total,
        "n_auto": len(auto),
        "n_escalated": len(escalated),
        "automation_rate": len(auto) / n_total if n_total else 0.0,
        "accuracy_auto": _accuracy(auto),
        "accuracy_escalated": _accuracy(escalated),
    }


def run_escalation(
    rows: list[dict],
    seed: int = SEED,
    targets: tuple[float, ...] = TARGETS,
) -> dict:
    """rows: one model's enriched rows (id, confidence, correct_fine) for
    every message. Splits into halves A/B (seed), and for each target
    accuracy, fits the threshold on one half and evaluates the policy on
    the OTHER half -- both directions (fit-on-A/eval-on-B and
    fit-on-B/eval-on-A), since one direction alone is a single lucky (or
    unlucky) split.
    """
    ids = [r["id"] for r in rows]
    by_id = {r["id"]: r for r in rows}
    ids_a, ids_b = split_halves(ids, seed=seed)
    rows_a = [by_id[i] for i in ids_a]
    rows_b = [by_id[i] for i in ids_b]

    result: dict = {"seed": seed, "n_a": len(rows_a), "n_b": len(rows_b), "targets": {}}
    for target in targets:
        threshold_from_a = find_threshold(rows_a, target)
        threshold_from_b = find_threshold(rows_b, target)
        result["targets"][str(target)] = {
            "fit_on_a_eval_on_b": {
                "chosen_threshold": threshold_from_a,
                **evaluate_policy(rows_b, threshold_from_a),
            },
            "fit_on_b_eval_on_a": {
                "chosen_threshold": threshold_from_b,
                **evaluate_policy(rows_a, threshold_from_b),
            },
        }
    return result
