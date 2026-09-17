"""Integration test for decision.py's orchestration, against a small
fixture repo layout (golden.jsonl, outputs/*.jsonl, prices.json,
coarse_map.json, and a pre-cached train.jsonl) written to a tmp_path --
never against the real 3,080-row data, and never touching the network
(the fixture train.jsonl already exists, so baseline.download_train_jsonl
takes its cache path)."""

from __future__ import annotations

import json

from modelbench import decision

GOLDEN_ROWS = [
    {
        "id": 0,
        "text": "my card hasn't arrived",
        "intent_fine": "card_arrival",
        "intent_coarse": "card",
    },
    {
        "id": 1,
        "text": "where is my new card",
        "intent_fine": "card_arrival",
        "intent_coarse": "card",
    },
    {
        "id": 2,
        "text": "card still not here",
        "intent_fine": "card_arrival",
        "intent_coarse": "card",
    },
    {
        "id": 3,
        "text": "card delivery is late",
        "intent_fine": "card_arrival",
        "intent_coarse": "card",
    },
    {
        "id": 4,
        "text": "what's today's exchange rate",
        "intent_fine": "exchange_rate",
        "intent_coarse": "currency_crypto",
    },
    {
        "id": 5,
        "text": "current usd to eur rate please",
        "intent_fine": "exchange_rate",
        "intent_coarse": "currency_crypto",
    },
    {
        "id": 6,
        "text": "exchange rate for gbp today",
        "intent_fine": "exchange_rate",
        "intent_coarse": "currency_crypto",
    },
    {
        "id": 7,
        "text": "tell me the exchange rate now",
        "intent_fine": "exchange_rate",
        "intent_coarse": "currency_crypto",
    },
]

COARSE_MAP = {"card_arrival": "card", "exchange_rate": "currency_crypto"}

TRAIN_ROWS = GOLDEN_ROWS  # a tiny, cleanly separable fixture is enough here

PRICES = {
    "as_of": "2026-09-17",
    "models": [
        {"key": "nova", "model_id": "fixture-nova", "input_per_1m": 1.0, "output_per_1m": 2.0},
        {"key": "llama", "model_id": "fixture-llama", "input_per_1m": 3.0, "output_per_1m": 4.0},
        {
            "key": "mistral",
            "model_id": "fixture-mistral",
            "input_per_1m": 5.0,
            "output_per_1m": 6.0,
        },
    ],
}


def _output_row(id_, model_key, pred, confidence, correct_fine, correct_coarse):
    return {
        "id": id_,
        "model_key": model_key,
        "model_id": f"fixture-{model_key}",
        "adapter": "fake",
        "intent_pred": pred,
        "confidence": confidence,
        "invalid": False,
        "correct_fine": correct_fine,
        "correct_coarse": correct_coarse,
        "input_tokens": 100,
        "output_tokens": 10,
        "latency_ms": 200.0,
        "retries": 0,
        "error": None,
        "ts": "2026-09-17T00:00:00+00:00",
    }


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _make_repo(tmp_path):
    data_dir = tmp_path / "data"
    outputs_dir = tmp_path / "outputs"
    data_dir.mkdir()
    outputs_dir.mkdir()

    _write_jsonl(data_dir / "golden.jsonl", GOLDEN_ROWS)
    _write_jsonl(data_dir / "train.jsonl", TRAIN_ROWS)
    with open(data_dir / "coarse_map.json", "w") as f:
        json.dump(COARSE_MAP, f)
    with open(data_dir / "prices.json", "w") as f:
        json.dump(PRICES, f)

    # nova: mostly right, one null-confidence error row.
    nova_rows = [
        _output_row(0, "nova", "card_arrival", 95, True, True),
        _output_row(1, "nova", "card_arrival", 90, True, True),
        _output_row(2, "nova", "exchange_rate", 60, False, False),
        _output_row(3, "nova", None, None, False, False),
        _output_row(4, "nova", "exchange_rate", 95, True, True),
        _output_row(5, "nova", "exchange_rate", 90, True, True),
        _output_row(6, "nova", "exchange_rate", 85, True, True),
        _output_row(7, "nova", "card_arrival", 60, False, False),
    ]
    llama_rows = [
        _output_row(0, "llama", "card_arrival", 100, True, True),
        _output_row(1, "llama", "card_delivery_estimate", 80, False, True),
        _output_row(2, "llama", "card_arrival", 40, False, False),
        _output_row(3, "llama", "card_arrival", 100, True, True),
        _output_row(4, "llama", "exchange_rate", 100, True, True),
        _output_row(5, "llama", "exchange_rate", 90, True, True),
        _output_row(6, "llama", "exchange_rate", 90, True, True),
        _output_row(7, "llama", "exchange_rate", 90, True, True),
    ]
    mistral_rows = [
        _output_row(0, "mistral", "card_arrival", 70, True, True),
        _output_row(1, "mistral", "card_arrival", 70, True, True),
        _output_row(2, "mistral", "card_arrival", 70, False, False),
        _output_row(3, "mistral", "card_arrival", 70, True, True),
        _output_row(4, "mistral", "card_arrival", 70, False, False),
        _output_row(5, "mistral", "exchange_rate", 95, True, True),
        _output_row(6, "mistral", "exchange_rate", 95, True, True),
        _output_row(7, "mistral", "exchange_rate", 95, True, True),
    ]
    _write_jsonl(outputs_dir / "nova.jsonl", nova_rows)
    _write_jsonl(outputs_dir / "llama.jsonl", llama_rows)
    _write_jsonl(outputs_dir / "mistral.jsonl", mistral_rows)

    return data_dir, outputs_dir


def test_build_decision_shape(tmp_path, monkeypatch):
    data_dir, outputs_dir = _make_repo(tmp_path)

    def _boom(*args, **kwargs):
        raise AssertionError("must not touch the network -- train.jsonl fixture is pre-cached")

    monkeypatch.setattr("modelbench.baseline.urllib.request.urlopen", _boom)

    result = decision.build_decision(
        data_dir=data_dir,
        outputs_dir=outputs_dir,
        train_jsonl_path=data_dir / "train.jsonl",
    )

    assert result["seed"] == 26
    assert result["run_date"] == "2026-09-17"
    assert result["n_messages"] == 8
    assert result["source_files"]["golden"] == "data/golden.jsonl"
    assert set(result["source_files"]["outputs"].keys()) == {"nova", "llama", "mistral"}

    assert result["classifier_baseline"]["status"] == "ok"
    assert result["classifier_baseline"]["cost_per_1k_usd"] == 0.0
    assert "rows" not in result["classifier_baseline"]  # per-row detail stripped from the summary

    assert set(result["accuracy_fine"].keys()) == {"nova", "llama", "mistral", "classifier"}
    assert set(result["cost_per_1k_usd"].keys()) == {"nova", "llama", "mistral", "classifier"}
    assert result["cost_per_1k_usd"]["classifier"] == 0.0

    boot = result["bootstrap"]
    assert boot["seed"] == 26
    assert boot["n_messages"] == 8
    assert set(boot["accuracy_fine_ci"].keys()) == {"nova", "llama", "mistral", "classifier"}
    assert "nova_minus_llama" in boot["pairwise_diff_ci"]
    assert "nova_minus_classifier" in boot["pairwise_diff_ci"]

    err = result["error_analysis"]
    assert set(err["top_confused_pairs"].keys()) == {"nova", "llama", "mistral"}
    assert isinstance(err["hardest_intents_all_three_wrong"], list)

    esc = result["escalation"]
    assert set(esc.keys()) == {"nova", "llama", "mistral"}
    for model_esc in esc.values():
        assert set(model_esc["targets"].keys()) == {"95", "98"}

    curve = result["quality_automation_curve"]
    assert set(curve.keys()) == {"nova", "llama", "mistral"}
    for model_curve in curve.values():
        assert [c["threshold"] for c in model_curve] == list(range(50, 101, 5))

    assert "classifier" not in result["escalation"]
    assert "classifier" not in result["quality_automation_curve"]


def test_build_decision_reports_blocked_classifier_without_failing_the_rest(tmp_path, monkeypatch):
    data_dir, outputs_dir = _make_repo(tmp_path)
    missing_train_path = data_dir / "train_missing.jsonl"  # never created -> forces a download

    def _boom(*args, **kwargs):
        raise OSError("Temporary failure in name resolution")

    monkeypatch.setattr("modelbench.baseline.urllib.request.urlopen", _boom)

    result = decision.build_decision(
        data_dir=data_dir,
        outputs_dir=outputs_dir,
        train_jsonl_path=missing_train_path,
    )

    assert result["classifier_baseline"]["status"] == "blocked"
    assert "Temporary failure in name resolution" in result["classifier_baseline"]["error"]
    # Tasks 2-5 still ran, and simply exclude the classifier.
    assert set(result["accuracy_fine"].keys()) == {"nova", "llama", "mistral"}
    assert set(result["bootstrap"]["accuracy_fine_ci"].keys()) == {"nova", "llama", "mistral"}
    assert result["escalation"].keys() == {"nova", "llama", "mistral"}
