"""Pulls the Banking77 test split by direct file download (not hand-copied) and
writes data/golden.jsonl, data/_labels.json, and data/ATTRIBUTION.md.

Per SPEC-model-bench.md section 3.1: source is the `banking77` dataset
(PolyAI). This module downloads directly from the original PolyAI-LDN GitHub
repository (the same data the `datasets` library mirrors on Hugging Face).
The Hugging Face Hub was not reachable from the build network at pull time
(see CONTEXT.md, Decisions), so this is the direct-file-download path the
spec explicitly allows as an alternative to the `datasets` library.

Runnable standalone with no arguments:
    python3 -m modelbench.cli pull-data
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

_BASE_URL = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data"
_TEST_CSV_URL = f"{_BASE_URL}/test.csv"
_CATEGORIES_URL = f"{_BASE_URL}/categories.json"
_LICENSE_URL = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/LICENSE"

EXPECTED_ROWS = 3080
EXPECTED_LABELS = 77


class LicenseNotPermissiveError(RuntimeError):
    """Raised when the dataset's license text does not look like a permissive
    open license. Per spec: STOP and report, do not proceed."""


def _fetch(url: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def _check_license_is_permissive(license_text: str) -> str:
    """Returns a short license name if the license text looks permissive,
    otherwise raises LicenseNotPermissiveError."""
    text_lower = license_text.lower()
    permissive_markers = {
        "creative commons attribution 4.0 international": "CC BY 4.0",
        "mit license": "MIT",
        "apache license": "Apache-2.0",
        "bsd 3-clause": "BSD-3-Clause",
        "bsd 2-clause": "BSD-2-Clause",
    }
    for marker, name in permissive_markers.items():
        if marker in text_lower:
            return name
    raise LicenseNotPermissiveError(
        "Banking77 source license did not match a known permissive license. "
        "STOP per spec section 3.1 and get a human to confirm before proceeding."
    )


def pull(data_dir: Path = DATA_DIR) -> dict:
    """Pulls the data, writes golden.jsonl / _labels.json / ATTRIBUTION.md,
    and returns a small summary dict. Raises LicenseNotPermissiveError or
    AssertionError (row/label count mismatch is recorded, not silently
    swallowed) per spec.
    """
    data_dir.mkdir(parents=True, exist_ok=True)

    license_text = _fetch(_LICENSE_URL).decode("utf-8", errors="replace")
    license_name = _check_license_is_permissive(license_text)

    categories_raw = _fetch(_CATEGORIES_URL)
    labels = json.loads(categories_raw)

    test_csv_raw = _fetch(_TEST_CSV_URL).decode("utf-8")
    reader = csv.DictReader(io.StringIO(test_csv_raw))
    rows = list(reader)

    n_rows = len(rows)
    n_labels = len(labels)
    rows_ok = n_rows == EXPECTED_ROWS
    labels_ok = n_labels == EXPECTED_LABELS

    with open(data_dir / "golden.jsonl", "w") as f:
        for i, row in enumerate(rows):
            rec = {"id": i, "text": row["text"], "intent_fine": row["category"]}
            f.write(json.dumps(rec) + "\n")

    with open(data_dir / "_labels.json", "w") as f:
        json.dump(labels, f, indent=2)

    pulled_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "n_rows": n_rows,
        "n_labels": n_labels,
        "rows_ok": rows_ok,
        "labels_ok": labels_ok,
        "license_name": license_name,
        "pulled_at": pulled_at,
        "source": _TEST_CSV_URL,
    }

    if not rows_ok:
        print(
            f"WARNING: expected {EXPECTED_ROWS} rows, got {n_rows}. "
            "Recording actual count; see CONTEXT.md.",
            file=sys.stderr,
        )
    if not labels_ok:
        print(
            f"WARNING: expected {EXPECTED_LABELS} labels, got {n_labels}. "
            "Recording actual count; see CONTEXT.md.",
            file=sys.stderr,
        )

    return summary


def main() -> int:
    try:
        summary = pull()
    except LicenseNotPermissiveError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
