"""Measure real local-classifier inference time and selective accuracy.

Requires the task-trained Banking77 split cached by 'python -m modelbench.decision'.
No hosting price is invented. Optional capacity economics require user-supplied costs.
Run: python -m modelbench.local_benchmark
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time
from pathlib import Path

import numpy as np

from modelbench import baseline

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"


def selective_accuracy(
    confidence: np.ndarray,
    correct: np.ndarray,
    thresholds=(0.5, 0.7, 0.8, 0.9, 0.95),
) -> list[dict]:
    conf = np.asarray(confidence, dtype=float)
    ok = np.asarray(correct, dtype=bool)
    if conf.shape != ok.shape:
        raise ValueError("confidence/correct arrays must have the same shape")
    total_errors = int((~ok).sum())
    result = []
    for threshold in thresholds:
        accepted = conf >= threshold
        escalated = ~accepted
        result.append({
            "threshold": float(threshold),
            "automation_fraction": float(accepted.mean()),
            "accepted_accuracy": float(ok[accepted].mean()) if accepted.any() else None,
            "escalation_fraction": float(escalated.mean()),
            "error_recall_in_escalated": (
                float((~ok[escalated]).sum() / total_errors) if total_errors else None
            ),
            "accepted_n": int(accepted.sum()),
        })
    return result


def assumed_hosting_cost(monthly_hosting_usd: float, monthly_messages: int) -> dict:
    if monthly_hosting_usd < 0 or monthly_messages <= 0:
        raise ValueError("monthly hosting cost must be nonnegative and message count positive")
    return {
        "user_supplied_monthly_hosting_usd": float(monthly_hosting_usd),
        "user_supplied_monthly_messages": int(monthly_messages),
        "estimated_cost_per_1k_usd": float(monthly_hosting_usd * 1000 / monthly_messages),
        "status": "scenario, not measured AWS/Vercel spend",
    }


def measure(pipe, texts: list[str], sample_size=1000) -> dict:
    if not texts:
        raise ValueError("text sample is empty")
    batch_started = time.perf_counter_ns()
    pipe.predict(texts)
    batch_seconds = (time.perf_counter_ns() - batch_started) / 1e9

    count = min(sample_size, len(texts))
    samples = texts[:count]
    for message in samples[:min(25, count)]:
        pipe.predict([message])  # warm-up; no cold-start inference claim
    durations = []
    for message in samples:
        start = time.perf_counter_ns()
        pipe.predict([message])
        durations.append((time.perf_counter_ns() - start) / 1e6)
    return {
        "measured_single_message_n": count,
        "single_message_p50_ms": float(np.percentile(durations, 50)),
        "single_message_p95_ms": float(np.percentile(durations, 95)),
        "batch_messages": len(texts),
        "batch_elapsed_seconds": batch_seconds,
        "batch_throughput_messages_per_second": len(texts) / batch_seconds,
        "platform": {
            "python": platform.python_version(),
            "architecture": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "limits": (
            "Warm CPU Python timings on this machine only; excludes serialization, "
            "HTTP, concurrency, scale-to-zero cold starts and hosting fees."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single-message-sample", type=int, default=1000)
    parser.add_argument("--monthly-hosting-usd", type=float)
    parser.add_argument("--monthly-messages", type=int)
    args = parser.parse_args()
    if bool(args.monthly_hosting_usd is not None) != bool(args.monthly_messages is not None):
        parser.error("provide both --monthly-hosting-usd and --monthly-messages for economics")
    if args.single_message_sample <= 0:
        parser.error("--single-message-sample must be positive")

    if not baseline.TRAIN_JSONL_PATH.exists():
        raise SystemExit("Run modelbench.decision to cache the training data first")
    train = baseline.load_jsonl(baseline.TRAIN_JSONL_PATH)
    test = baseline.load_jsonl(DATA_DIR / "golden.jsonl")
    classifier = baseline.train_classifier(train)
    texts = [item["text"] for item in test]
    probs = classifier.predict_proba(texts)
    pred_index = np.argmax(probs, axis=1)
    classes = classifier.classes_
    prediction = classes[pred_index]
    correct = prediction == np.asarray([item["intent_fine"] for item in test])
    confidence = probs[np.arange(len(test)), pred_index]

    report = {
        "n_train_rows": len(train),
        "n_test_rows": len(test),
        "fine_accuracy": float(correct.mean()),
        "selective_accuracy_curve": selective_accuracy(confidence, correct),
        "local_inference": measure(classifier, texts, args.single_message_sample),
        "hosting": (
            assumed_hosting_cost(args.monthly_hosting_usd, args.monthly_messages)
            if args.monthly_hosting_usd is not None else
            {"status": "not priced; no claim of zero hosting cost"}
        ),
        "release_status": "offline benchmark; not a timed deployed service",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "local_runtime_benchmark.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(out), "accuracy": report["fine_accuracy"]}))


if __name__ == "__main__":
    main()
