"""Conventional classifier baseline: TF-IDF + logistic regression, trained on
the Banking77 TRAIN split and evaluated on the same 3,080-row TEST split
already committed at data/golden.jsonl.

Task 1 of the decision pack (see README.md's "The Decision" section and
CONTEXT.md's 2026-09-17 note). This is a local scikit-learn fit, not a
hosted model -- no model-provider call of any kind, and the only network
access anywhere in this module is the one-time direct-file download of the
labeled TRAIN split, using the exact same source and technique
data/golden.jsonl's TEST split was already pulled with (see
modelbench.pull_data's module docstring and README.md's "What's here"
list: "pulled by direct file download... not hand-copied").

Caching: data/golden.jsonl (the TEST split) is already committed under
data/ and is NOT gitignored (checked .gitignore: no data/ or *.jsonl
rule exists there), so the TRAIN split gets the same treatment -- once
downloaded it is cached at data/train.jsonl and reused by every later run
instead of re-fetching it every time. If a caller can't reach the network,
download_train_jsonl raises TrainDownloadError with the original error
message; modelbench.decision catches that and reports Task 1 as blocked.
Tasks 2-5 do not import or depend on this module succeeding.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from modelbench.pull_data import _BASE_URL

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

TRAIN_CSV_URL = f"{_BASE_URL}/train.csv"
TRAIN_JSONL_PATH = DATA_DIR / "train.jsonl"

# Same seed used throughout the decision pack (bootstrap, escalation split).
RANDOM_STATE = 26

COST_PER_1K_USD = 0.0
COST_ASSUMPTION = (
    "Assumes zero per-message token cost: the classifier runs locally "
    "(TF-IDF + logistic regression, scikit-learn, CPU inference) with no "
    "hosted-model API call, so there is no per-token price to look up in "
    "data/prices.json. This counts only the absence of a per-message "
    "model-provider charge -- it does not price the compute/hosting needed "
    "to run the classifier as a service."
)


def _relpath(path: Path) -> str:
    """Repo-relative display path, e.g. "data/train.jsonl", so anything
    written into outputs/decision.json never embeds this machine's own
    absolute working-directory path (which can contain anything -- a
    username, a build id, a temp-dir name)."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


class TrainDownloadError(RuntimeError):
    """Raised when the Banking77 TRAIN split can't be downloaded. Callers
    (modelbench.decision) catch this and report Task 1 as blocked with the
    exact message, per the decision-pack spec ("If the train split cannot
    be downloaded, do parts 2-5 and report part 1 as blocked with the
    exact error.")."""


def _rows_from_train_csv_text(csv_text: str) -> list[dict]:
    """Parses train.csv's `text,category` columns into
    {id, text, intent_fine} rows, ids assigned sequentially from 0 -- the
    same shape as data/golden.jsonl, minus intent_coarse (added back by the
    caller via data/coarse_map.json, since that map is keyed by fine
    intent, not a property of the raw source file)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []
    for i, row in enumerate(reader):
        rows.append({"id": i, "text": row["text"], "intent_fine": row["category"]})
    return rows


def download_train_jsonl(
    dest_path: Path = TRAIN_JSONL_PATH,
    timeout: int = 30,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Downloads banking_data/train.csv the same way pull_data.py pulls the
    test split (direct file download from the PolyAI-LDN GitHub source),
    writes it to dest_path as JSON lines, and returns a small summary dict.

    If dest_path already exists and use_cache is True, skips the network
    call entirely and reports the cached file's row count instead -- this
    is what keeps repeated `modelbench.decision` runs (and CI, if it ever
    runs this) from re-downloading the same file every time.

    Raises TrainDownloadError (wrapping the original exception's message
    verbatim) if the download itself fails. Never raises on a row-count
    surprise -- matching pull_data.py's own philosophy of recording actual
    counts rather than hard-failing on a mismatch.
    """
    if use_cache and dest_path.exists():
        with open(dest_path) as f:
            n_rows = sum(1 for line in f if line.strip())
        return {
            "source_url": TRAIN_CSV_URL,
            "dest_path": _relpath(dest_path),
            "n_rows": n_rows,
            "from_cache": True,
        }

    try:
        with urllib.request.urlopen(TRAIN_CSV_URL, timeout=timeout) as resp:
            csv_text = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise TrainDownloadError(f"{type(exc).__name__}: {exc}") from exc

    rows = _rows_from_train_csv_text(csv_text)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    return {
        "source_url": TRAIN_CSV_URL,
        "dest_path": _relpath(dest_path),
        "n_rows": len(rows),
        "from_cache": False,
    }


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_classifier() -> Pipeline:
    """TF-IDF (word uni+bigrams, sublinear term frequency) + multinomial
    logistic regression. Fully deterministic given RANDOM_STATE: no
    network, no external model call, nothing provider-specific."""
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            ("clf", LogisticRegression(max_iter=2000, C=10.0, random_state=RANDOM_STATE)),
        ]
    )


def train_classifier(train_rows: list[dict]) -> Pipeline:
    texts = [r["text"] for r in train_rows]
    labels = [r["intent_fine"] for r in train_rows]
    pipe = build_classifier()
    pipe.fit(texts, labels)
    return pipe


def evaluate_classifier(pipe: Pipeline, test_rows: list[dict], coarse_map: dict) -> dict:
    """Predicts intent_fine for every test row and scores fine/coarse
    accuracy, reusing data/coarse_map.json (the repo's own fine->coarse
    map) rather than deriving a new one. Also returns per-row results (id,
    true/predicted intent, correct_fine/coarse) so bootstrap.py/errors.py
    can join the classifier in by id alongside the three real models."""
    texts = [r["text"] for r in test_rows]
    preds = pipe.predict(texts)

    rows_out = []
    n_correct_fine = 0
    n_correct_coarse = 0
    for row, pred in zip(test_rows, preds, strict=True):
        pred = str(pred)
        true_fine = row["intent_fine"]
        true_coarse = row.get("intent_coarse") or coarse_map.get(true_fine)
        pred_coarse = coarse_map.get(pred)
        correct_fine = pred == true_fine
        correct_coarse = pred_coarse == true_coarse
        n_correct_fine += correct_fine
        n_correct_coarse += correct_coarse
        rows_out.append(
            {
                "id": row["id"],
                "intent_fine": true_fine,
                "intent_pred": pred,
                "correct_fine": bool(correct_fine),
                "correct_coarse": bool(correct_coarse),
            }
        )

    n = len(test_rows)
    return {
        "n_test_rows": n,
        "accuracy_fine": n_correct_fine / n if n else 0.0,
        "accuracy_coarse": n_correct_coarse / n if n else 0.0,
        "rows": rows_out,
    }


def run_baseline(
    test_rows: list[dict],
    coarse_map: dict,
    dest_path: Path = TRAIN_JSONL_PATH,
    use_cache: bool = True,
) -> dict:
    """Orchestrates Task 1 end to end: download (or reuse the cached)
    TRAIN split, fit the classifier, evaluate on test_rows. Returns
    {"status": "blocked", "error": "..."} if the download fails -- never
    raises -- so modelbench.decision can always finish Tasks 2-5.
    """
    try:
        download_summary = download_train_jsonl(dest_path=dest_path, use_cache=use_cache)
    except TrainDownloadError as exc:
        return {"status": "blocked", "error": str(exc)}

    train_rows = load_jsonl(dest_path)
    pipe = train_classifier(train_rows)
    eval_result = evaluate_classifier(pipe, test_rows, coarse_map)

    return {
        "status": "ok",
        "error": None,
        "train_source_url": download_summary["source_url"],
        "train_path": download_summary["dest_path"],
        "train_from_cache": download_summary["from_cache"],
        "n_train_rows": download_summary["n_rows"],
        "n_test_rows": eval_result["n_test_rows"],
        "accuracy_fine": eval_result["accuracy_fine"],
        "accuracy_coarse": eval_result["accuracy_coarse"],
        "cost_per_1k_usd": COST_PER_1K_USD,
        "cost_assumption": COST_ASSUMPTION,
        "rows": eval_result["rows"],
    }
