import numpy as np
import pytest

from modelbench.hybrid_routing import choose_threshold, crossfit, policy
from modelbench.local_benchmark import assumed_hosting_cost, selective_accuracy


def test_hosting_cost_requires_explicit_assumptions():
    estimate = assumed_hosting_cost(120, 20_000)
    assert estimate["estimated_cost_per_1k_usd"] == 6
    assert "scenario" in estimate["status"]
    with pytest.raises(ValueError):
        assumed_hosting_cost(100, 0)


def test_selective_automation_reports_missed_failures_and_coverage():
    curve = selective_accuracy(
        np.array([0.92, 0.8, 0.6, 0.5]),
        np.array([True, False, True, False]),
        thresholds=(0.8,),
    )
    assert curve[0]["automation_fraction"] == 0.5
    assert curve[0]["accepted_accuracy"] == 0.5
    assert curve[0]["error_recall_in_escalated"] == 0.5


def test_routing_no_escalation_has_no_hosted_provider_cost():
    rows = [
        {"id": 0, "local_conf": 0.91, "local_correct": True,
         "hosted_correct": False, "hosted_cost_usd": 0.001},
        {"id": 1, "local_conf": 0.3, "local_correct": True,
         "hosted_correct": False, "hosted_cost_usd": 0.001},
    ]
    p = policy(rows, 0.0)
    assert p["accuracy"] == 1.0
    assert p["provider_cost_per_1k_usd"] == 0
    assert choose_threshold(rows, 0.5)["threshold"] == 0.0


def test_crossfit_threshold_selection_is_opposite_half():
    rows = [
        {
            "id": i, "local_conf": 0.25 if i % 3 == 0 else 0.95,
            "local_correct": i % 3 != 0, "hosted_correct": True,
            "hosted_cost_usd": 0.00002,
        }
        for i in range(30)
    ]
    out = crossfit(rows, max_provider_cost_per_1k_usd=0.20)
    assert out["select_on_a_evaluate_on_b"]["opposite_half_evaluation"]["n"] == 15
    assert out["select_on_b_evaluate_on_a"]["opposite_half_evaluation"]["n"] == 15
    assert out["select_on_a_evaluate_on_b"]["selection"]["threshold"] > 0.25
