"""Runs one model against the full (or limited) Banking77 golden set through
one provider adapter, writing outputs/<model_key>.jsonl.

Per SPEC-model-bench.md section 6.1: resumable and idempotent (skips ids
already present in the output file), processes rows with a bounded worker
pool, writes one JSON line per row, prints progress every 100 rows. The CLI
(cli.py) is what turns a >2% error rate into a non-zero exit code; this
module just reports the numbers via RunSummary.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from modelbench.prompt import MAX_OUTPUT_TOKENS, TEMPERATURE, build_prompt, parse_response
from modelbench.providers import get_provider
from modelbench.providers.base import Provider

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"

PROGRESS_EVERY = 100
ERROR_RATE_LIMIT = 0.02


@dataclass
class RunSummary:
    model_key: str
    n_total: int
    n_processed: int
    n_skipped_existing: int
    n_errors: int

    @property
    def error_rate(self) -> float:
        return self.n_errors / self.n_processed if self.n_processed else 0.0


def _load_golden(limit: int | None = None) -> list[dict]:
    rows = []
    with open(DATA_DIR / "golden.jsonl") as f:
        for line in f:
            rows.append(json.loads(line))
    if limit is not None:
        rows = rows[:limit]
    return rows


def _load_prices() -> dict:
    with open(DATA_DIR / "prices.json") as f:
        return json.load(f)


def _model_entry(model_key: str) -> dict:
    prices = _load_prices()
    for m in prices["models"]:
        if m["key"] == model_key:
            return m
    raise ValueError(f"unknown model key {model_key!r}; see data/prices.json")


def _load_labels() -> list[str]:
    with open(DATA_DIR / "_labels.json") as f:
        return json.load(f)


def _load_coarse_map() -> dict:
    with open(DATA_DIR / "coarse_map.json") as f:
        return json.load(f)


def _existing_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    ids: set[int] = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                ids.add(json.loads(line)["id"])
    return ids


def _process_one(
    row: dict,
    provider: Provider,
    model_id: str,
    labels: list[str],
    coarse_map: dict,
    model_key: str,
) -> dict:
    """Never raises: any unexpected exception from the provider or the parser
    (a bug in an adapter, a malformed response, anything not already turned
    into a CallResult(error=...) by the provider itself) is caught here and
    turned into an error row instead. One bad row must never crash — or lose
    the rest of — a batch run; that would violate the "runs are resumable
    and idempotent" non-negotiable just as badly as a real network failure
    would.
    """
    try:
        prompt = build_prompt(row["text"], labels)
        result = provider.call(
            model_id=model_id,
            prompt=prompt,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=TEMPERATURE,
        )
        parsed = parse_response(result.text, labels)
        pred_coarse = coarse_map.get(parsed.intent) if parsed.intent else None
        correct_fine = (not parsed.invalid) and parsed.intent == row["intent_fine"]
        correct_coarse = (not parsed.invalid) and pred_coarse == row["intent_coarse"]

        return {
            "id": row["id"],
            "model_key": model_key,
            "model_id": model_id,
            "adapter": result.adapter,
            "intent_pred": parsed.intent,
            "confidence": parsed.confidence,
            "invalid": parsed.invalid,
            "correct_fine": correct_fine,
            "correct_coarse": correct_coarse,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "latency_ms": result.latency_ms,
            "retries": result.retries,
            "error": result.error,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:  # defense in depth — see docstring above
        return {
            "id": row["id"],
            "model_key": model_key,
            "model_id": model_id,
            "adapter": None,
            "intent_pred": None,
            "confidence": None,
            "invalid": True,
            "correct_fine": False,
            "correct_coarse": False,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": 0.0,
            "retries": 0,
            "error": f"unhandled exception in _process_one: {exc}",
            "ts": datetime.now(timezone.utc).isoformat(),
        }


def run(
    model_key: str,
    rows: list[dict] | None = None,
    *,
    model_id: str | None = None,
    concurrency: int = 10,
    resume: bool = True,
    limit: int | None = None,
    provider: Provider | None = None,
    adapter_name: str | None = None,
    out_path: Path | None = None,
) -> RunSummary:
    """Runs model_key against golden.jsonl (or `rows`, or the first `limit`
    rows — `limit` is for local smoke tests only, never set it for a real
    run) through one provider adapter. Idempotent: on resume (the default),
    ids already present in the output file are skipped.

    `model_id` and `out_path` let a caller (the `smoke` CLI command, or a
    test) bypass data/prices.json entirely and write somewhere other than
    outputs/<model_key>.jsonl — used so a fake/smoke run can never collide
    with or corrupt a real model's committed output file.
    """
    if model_id is None:
        model_id = _model_entry(model_key)["model_id"]

    if provider is None:
        chosen_adapter = adapter_name or os.environ.get("MODELBENCH_ADAPTER", "bedrock")
        provider = get_provider(chosen_adapter)

    labels = _load_labels()
    coarse_map = _load_coarse_map()

    if rows is None:
        rows = _load_golden(limit=limit)
    elif limit is not None:
        rows = rows[:limit]

    out_path = out_path or (OUTPUTS_DIR / f"{model_key}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing_ids = _existing_ids(out_path) if resume else set()
    todo = [r for r in rows if r["id"] not in existing_ids]

    n_errors = 0
    n_processed = 0

    with open(out_path, "a") as out_f:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(_process_one, row, provider, model_id, labels, coarse_map, model_key)
                for row in todo
            ]
            for future in concurrent.futures.as_completed(futures):
                out_row = future.result()
                out_f.write(json.dumps(out_row) + "\n")
                out_f.flush()
                n_processed += 1
                if out_row["error"]:
                    n_errors += 1
                if n_processed % PROGRESS_EVERY == 0:
                    print(
                        f"[{model_key}] {n_processed}/{len(todo)} processed "
                        f"({n_errors} errors so far)",
                        file=sys.stderr,
                    )

    return RunSummary(
        model_key=model_key,
        n_total=len(rows),
        n_processed=n_processed,
        n_skipped_existing=len(existing_ids),
        n_errors=n_errors,
    )
