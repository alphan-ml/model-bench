"""Per SPEC-model-bench.md section 3.2: every one of the 77 intents must appear
in data/coarse_map.json exactly once, mapped to exactly one of the 10 named
coarse groups.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

GROUPS = {
    "card",
    "transfers_payments",
    "top_up",
    "atm_cash",
    "account_identity",
    "fees_charges_rates",
    "disputes_fraud",
    "refunds_cancellations",
    "app_pin_access",
    "currency_crypto",
}


def _load_coarse_map():
    with open(DATA_DIR / "coarse_map.json") as f:
        return json.load(f)


def _load_golden_intents():
    intents = set()
    with open(DATA_DIR / "golden.jsonl") as f:
        for line in f:
            row = json.loads(line)
            intents.add(row["intent_fine"])
    return intents


def test_coarse_map_has_77_entries():
    coarse_map = _load_coarse_map()
    assert len(coarse_map) == 77


def test_every_golden_intent_is_mapped_exactly_once():
    coarse_map = _load_coarse_map()
    golden_intents = _load_golden_intents()
    assert len(golden_intents) == 77
    assert set(coarse_map.keys()) == golden_intents


def test_every_mapped_group_is_one_of_the_ten_named_groups():
    coarse_map = _load_coarse_map()
    used_groups = set(coarse_map.values())
    assert used_groups <= GROUPS
    unknown = used_groups - GROUPS
    assert not unknown, f"unknown coarse group(s) used: {unknown}"


def test_golden_jsonl_intent_coarse_matches_coarse_map():
    coarse_map = _load_coarse_map()
    with open(DATA_DIR / "golden.jsonl") as f:
        for line in f:
            row = json.loads(line)
            assert row["intent_coarse"] == coarse_map[row["intent_fine"]]


def test_golden_jsonl_row_count_and_fields():
    rows = []
    with open(DATA_DIR / "golden.jsonl") as f:
        for line in f:
            rows.append(json.loads(line))
    assert len(rows) == 3080
    ids = [r["id"] for r in rows]
    assert ids == list(range(3080))
    for r in rows:
        assert set(r.keys()) == {"id", "text", "intent_fine", "intent_coarse"}
        assert isinstance(r["text"], str) and r["text"]
