"""Live Eval canary: calls the live `/api/model-bench-run` endpoint on
giggitai.com once per row in `canary/rows.json`, scores the three hosted
models plus the local classifier baseline, and prints one JSON ledger
record to stdout.

Per the Live Eval spec: no fallback numbers. An endpoint error for a
hosted model is counted as wrong for that row (never silently dropped or
replaced with a recorded value), and any error on the headline model
(nova) forces `match=false` regardless of the tolerance check.

Runnable standalone with no arguments:
    python3 -m modelbench.canary
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Any, Callable

from modelbench import baseline

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
CANARY_DIR = REPO_ROOT / "canary"
CANARY_ROWS_PATH = CANARY_DIR / "rows.json"
GOLDEN_PATH = DATA_DIR / "golden.jsonl"
COARSE_MAP_PATH = DATA_DIR / "coarse_map.json"
RESULTS_PATH = REPO_ROOT / "results.json"

SYSTEM = "model-bench"
ENDPOINT_URL = "https://giggitai.com/api/model-bench-run"
N_CANARY_ROWS = 10
SEED = 26
HEADLINE_MODEL_KEY = "nova"
METRIC_NAME = "accuracy_fine_nova"
# n=10 gives a headline accuracy that can only land on multiples of 0.1 --
# a generous absolute tolerance so ordinary sampling noise never trips the
# canary; it is meant to catch a broken endpoint/model, not to track the
# real 3,080-row run's confidence interval.
TOLERANCE = 0.25
HOSTED_MODEL_KEYS = ("nova", "llama", "mistral")

_REDIRECT_CODES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 3


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def select_canary_row_ids(
    golden_rows: list[dict], n: int = N_CANARY_ROWS, seed: int = SEED
) -> list[int]:
    """Deterministically picks `n` row ids out of the full holdout split,
    seeded so re-running this always returns the exact same rows."""
    ids = sorted(row["id"] for row in golden_rows)
    return sorted(Random(seed).sample(ids, n))


def build_canary_rows(
    golden_rows: list[dict], n: int = N_CANARY_ROWS, seed: int = SEED
) -> list[dict]:
    """Builds the committed canary/rows.json content: the chosen rows,
    sorted by id, with the same fields as data/golden.jsonl."""
    by_id = {row["id"]: row for row in golden_rows}
    chosen_ids = select_canary_row_ids(golden_rows, n=n, seed=seed)
    return [by_id[row_id] for row_id in chosen_ids]


def load_canary_rows(path: Path = CANARY_ROWS_PATH) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def load_recorded_metric(
    results_path: Path = RESULTS_PATH, model_key: str = HEADLINE_MODEL_KEY
) -> float:
    with open(results_path) as f:
        results = json.load(f)
    for model in results["models"]:
        if model["key"] == model_key:
            return round(model["accuracy_fine"], 3)
    raise KeyError(f"no model {model_key!r} in {results_path}")


def get_release_sha(repo_root: Path = REPO_ROOT) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _http_post_json(
    url: str, payload: dict, timeout: int = 30, _redirects_left: int = _MAX_REDIRECTS
) -> dict:
    """POSTs JSON with the stdlib only (no extra dependency for a single
    call site) and follows same-method redirects itself -- urllib's own
    redirect handler does not know how to follow a 308, which is what
    giggitai.com's apex domain sends visitors to www with."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code in _REDIRECT_CODES and _redirects_left > 0:
            location = exc.headers.get("Location")
            if location:
                return _http_post_json(
                    location, payload, timeout=timeout, _redirects_left=_redirects_left - 1
                )
        raise


def call_endpoint(
    text: str,
    url: str = ENDPOINT_URL,
    timeout: int = 30,
    http_post: Callable[[str, dict, int], dict] = _http_post_json,
) -> dict:
    """Calls the live endpoint once. Never raises: any failure (network
    error, timeout, non-JSON body, missing "answers" key) comes back as
    {"answers": [], "latency_ms": ..., "error": "..."} instead -- the
    canary's own no-fallback-numbers rule applies to this call site too."""
    start = time.perf_counter()
    try:
        body = http_post(url, {"text": text}, timeout)
        latency_ms = (time.perf_counter() - start) * 1000
        answers = body["answers"]
        return {"answers": answers, "latency_ms": latency_ms, "error": None}
    except Exception as exc:  # noqa: BLE001 - any failure becomes a recorded error, never a crash
        latency_ms = (time.perf_counter() - start) * 1000
        return {"answers": [], "latency_ms": latency_ms, "error": f"{type(exc).__name__}: {exc}"}


def run_hosted_models(
    canary_rows: list[dict],
    call: Callable[[str], dict] = call_endpoint,
) -> dict:
    """Calls the live endpoint once per canary row and scores every hosted
    model key against the row's true intent_fine. Returns:
      {model_key: {"n_correct": int, "n_errors": int}, ...,
       "cost_usd_total": float, "latencies_ms": [float, ...],
       "request_errors": int}
    An endpoint-level failure (the whole call errored) counts as an error
    for every hosted model on that row -- never skipped, never a fallback
    number standing in for the missing answer.
    """
    scores = {key: {"n_correct": 0, "n_errors": 0} for key in HOSTED_MODEL_KEYS}
    cost_usd_total = 0.0
    latencies_ms: list[float] = []
    request_errors = 0

    for row in canary_rows:
        result = call(row["text"])
        latencies_ms.append(result["latency_ms"])
        answers_by_key = {a["key"]: a for a in result["answers"]}

        if result["error"] is not None:
            request_errors += 1

        for key in HOSTED_MODEL_KEYS:
            answer = answers_by_key.get(key)
            if answer is None or answer.get("error"):
                scores[key]["n_errors"] += 1
                continue
            cost_usd_total += answer.get("cost_usd") or 0.0
            if answer["intent"] == row["intent_fine"]:
                scores[key]["n_correct"] += 1

    return {
        "scores": scores,
        "cost_usd_total": cost_usd_total,
        "latencies_ms": latencies_ms,
        "request_errors": request_errors,
        "n_rows": len(canary_rows),
    }


def run_classifier(canary_rows: list[dict], coarse_map_path: Path = COARSE_MAP_PATH) -> dict:
    """Trains the local TF-IDF + logistic-regression baseline (downloading
    or reusing the cached Banking77 train split, same as
    `modelbench.decision`) and scores it on the canary rows. Never raises:
    a download failure comes back as {"status": "blocked", ...}."""
    with open(coarse_map_path) as f:
        coarse_map = json.load(f)
    result = baseline.run_baseline(canary_rows, coarse_map)
    if result["status"] == "blocked":
        return {"status": "blocked", "error": result["error"], "accuracy_fine": None}
    return {"status": "ok", "error": None, "accuracy_fine": result["accuracy_fine"]}


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


def build_record(
    canary_rows: list[dict],
    hosted: dict,
    classifier: dict,
    recorded: float,
    release: str,
    duration_s: float,
    ts: str | None = None,
) -> dict[str, Any]:
    n = hosted["n_rows"]
    accuracy = {key: hosted["scores"][key]["n_correct"] / n for key in HOSTED_MODEL_KEYS}
    observed = round(accuracy[HEADLINE_MODEL_KEY], 3)
    classifier_accuracy = classifier["accuracy_fine"]
    classifier_accuracy_rounded = (
        round(classifier_accuracy, 3) if classifier_accuracy is not None else None
    )

    total_errors = hosted["request_errors"] + sum(s["n_errors"] for s in hosted["scores"].values())
    headline_has_error = hosted["scores"][HEADLINE_MODEL_KEY]["n_errors"] > 0
    match = (not headline_has_error) and abs(observed - recorded) <= TOLERANCE

    sorted_latencies = sorted(hosted["latencies_ms"])
    p50_ms = round(_percentile(sorted_latencies, 50))
    p95_ms = round(_percentile(sorted_latencies, 95))

    other_models_line = (
        f"llama accuracy_fine {accuracy['llama']:.3f} · "
        f"mistral accuracy_fine {accuracy['mistral']:.3f} · "
    )
    other_models_line += (
        f"classifier accuracy_fine {classifier_accuracy:.3f}"
        if classifier_accuracy is not None
        else f"classifier blocked: {classifier['error']}"
    )

    lines = [
        f"$ canary {SYSTEM} --n {n} --endpoint /api/model-bench-run",
        f"release {release} · {n} canary rows · {total_errors} errors",
        f"nova accuracy_fine {accuracy['nova']:.3f} · recorded {recorded:.3f} · "
        f"tolerance {TOLERANCE:.3f} · {'MATCH' if match else 'NO MATCH'}",
        other_models_line,
        f"run cost ${hosted['cost_usd_total']:.6f} · "
        f"p50 {p50_ms} ms · p95 {p95_ms} ms · {duration_s:.1f} s total",
    ]

    extra = {
        "accuracy_fine_nova": round(accuracy["nova"], 3),
        "accuracy_fine_llama": round(accuracy["llama"], 3),
        "accuracy_fine_mistral": round(accuracy["mistral"], 3),
        "accuracy_fine_classifier": classifier_accuracy_rounded,
        "classifier_error": classifier["error"],
        "cost_usd": round(hosted["cost_usd_total"], 6),
    }

    return {
        "ts": ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "system": SYSTEM,
        "kind": "canary",
        "release": release,
        "endpoint": ENDPOINT_URL,
        "n": n,
        "metric": METRIC_NAME,
        "recorded": recorded,
        "observed": observed,
        "tolerance": TOLERANCE,
        "match": match,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "errors": total_errors,
        "duration_s": round(duration_s, 1),
        "lines": lines,
        "extra": extra,
    }


def run() -> dict:
    start = time.perf_counter()
    canary_rows = load_canary_rows()
    hosted = run_hosted_models(canary_rows)
    classifier = run_classifier(canary_rows)
    recorded = load_recorded_metric()
    release = get_release_sha()
    duration_s = time.perf_counter() - start
    return build_record(canary_rows, hosted, classifier, recorded, release, duration_s)


def main() -> int:
    # Always exits 0: a "NO MATCH" is a real, useful record the ledger
    # step still needs to commit and push, not a script failure. Whether
    # a mismatch should page anyone is a decision for whoever reads the
    # ledger, not for this process's exit code.
    record = run()
    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
