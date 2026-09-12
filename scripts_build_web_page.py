"""Builds web/index.html from web/index.template.html by inlining a results
JSON file, per SPEC-model-bench.md §7.1: "Reads results.json at build time
(inlined) so the page has no runtime dependency for the tables."

Usage:
    python3 scripts_build_web_page.py                        # real build:
                                                               # results.json -> web/index.html
    python3 scripts_build_web_page.py --results results.sample.json --out web/index.html
                                                               # dev/test build against the
                                                               # disclosed W-A3 sample fixture

Defaults to reading results.json (the real, committed report output) and
writing web/index.html -- NOT results.sample.json. This is deliberate: a
production build with no real results.json yet must fail with a clear
"file not found" error, never silently fall back to sample data (see
results.sample.json's own module docstring in scripts_build_results_sample.py
for why that file exists and where it may/may not be used).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = REPO_ROOT / "web" / "index.template.html"
DEFAULT_RESULTS_PATH = REPO_ROOT / "results.json"
DEFAULT_OUT_PATH = REPO_ROOT / "web" / "index.html"

# Must match the literal placeholder in web/index.template.html exactly.
PLACEHOLDER = "/*__RESULTS_JSON__*/{}"


def build_page(results_path: Path, template_path: Path = TEMPLATE_PATH) -> str:
    with open(results_path) as f:
        results = json.load(f)

    template = template_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise ValueError(
            f"{template_path} does not contain the expected placeholder "
            f"{PLACEHOLDER!r} -- did the template change without updating "
            "this script?"
        )

    return template.replace(PLACEHOLDER, json.dumps(results))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results", type=Path, default=DEFAULT_RESULTS_PATH,
        help="Path to the results JSON to inline (default: results.json)",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT_PATH,
        help="Path to write the built page to (default: web/index.html)",
    )
    args = parser.parse_args()

    if not args.results.exists():
        print(
            f"STOP: {args.results} does not exist. There is no real results.json "
            "yet (Gate 1 -- real Bedrock model ids/prices -- is still open; see "
            "CONTEXT.md 'Open items'). Pass --results results.sample.json for a "
            "local dev/test build against the disclosed sample fixture instead.",
        )
        return 1

    html = build_page(args.results)
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out} (from {args.results})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
