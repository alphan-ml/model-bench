"""Error analysis over the joined per-model output rows: the ten most
confused (true, predicted) fine-intent pairs per model, and the fine
intents all three real models fail on most often. Task 3 of the decision
pack (see README.md's "The Decision")."""

from __future__ import annotations

from collections import Counter, defaultdict

TOP_N_CONFUSED = 10


def top_confused_pairs(rows: list[dict], top_n: int = TOP_N_CONFUSED) -> list[dict]:
    """rows: one model's enriched rows, each carrying intent_fine (the true
    label, from the golden join) and intent_pred (the model's own
    prediction, possibly None for an unparseable response). Counts every
    (true, predicted) pair among the WRONG rows only and returns the
    top_n most frequent pairs, most frequent first."""
    counts: Counter[tuple[str, str | None]] = Counter()
    for r in rows:
        true = r["intent_fine"]
        pred = r["intent_pred"]
        if pred != true:
            counts[(true, pred)] += 1

    ranked = counts.most_common(top_n)
    return [{"true": true, "predicted": pred, "count": count} for (true, pred), count in ranked]


def hardest_intents_all_wrong(rows_by_model: dict[str, list[dict]]) -> list[dict]:
    """rows_by_model: {model_key: [enriched rows]}, each row carrying id,
    intent_fine, correct_fine -- typically the three real models
    (nova/llama/mistral). A row counts toward an intent's "all wrong" tally
    only if EVERY given model got that exact message wrong.

    Returns one entry per fine intent that appears in the shared (joined
    by id) row set, sorted by n_all_wrong descending (ties broken by rate
    descending, then by intent name for determinism):
    {"intent", "n_rows", "n_all_wrong", "rate"}.
    """
    model_keys = list(rows_by_model.keys())
    if not model_keys:
        raise ValueError("rows_by_model must not be empty")

    by_model_by_id: dict[str, dict[int, dict]] = {
        key: {r["id"]: r for r in rows} for key, rows in rows_by_model.items()
    }
    common_ids = set.intersection(*(set(d.keys()) for d in by_model_by_id.values()))

    n_rows_per_intent: dict[str, int] = defaultdict(int)
    n_all_wrong_per_intent: dict[str, int] = defaultdict(int)

    for row_id in common_ids:
        rows = [by_model_by_id[key][row_id] for key in model_keys]
        intent_true = rows[0]["intent_fine"]
        n_rows_per_intent[intent_true] += 1
        if all(not r["correct_fine"] for r in rows):
            n_all_wrong_per_intent[intent_true] += 1

    result = []
    for intent, n_rows in n_rows_per_intent.items():
        n_all_wrong = n_all_wrong_per_intent.get(intent, 0)
        result.append(
            {
                "intent": intent,
                "n_rows": n_rows,
                "n_all_wrong": n_all_wrong,
                "rate": n_all_wrong / n_rows if n_rows else 0.0,
            }
        )

    result.sort(key=lambda x: (-x["n_all_wrong"], -x["rate"], x["intent"]))
    return result
