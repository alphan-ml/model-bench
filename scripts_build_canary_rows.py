"""One-off script (not part of the shipped package) that builds
canary/rows.json: 10 rows deterministically sampled from data/golden.jsonl
(the Banking77 TEST/holdout split) with seed 26, for the Live Eval canary
(`modelbench.canary`). Run once; the output file is what ships and is
never regenerated on a schedule -- the whole point of a canary set is that
it stays fixed so a metric drift is comparable run over run.
"""

import json
from pathlib import Path

from modelbench.canary import GOLDEN_PATH, build_canary_rows, load_jsonl

CANARY_ROWS_PATH = Path(__file__).resolve().parent / "canary" / "rows.json"


def main() -> None:
    golden_rows = load_jsonl(GOLDEN_PATH)
    canary_rows = build_canary_rows(golden_rows)
    CANARY_ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CANARY_ROWS_PATH, "w") as f:
        json.dump(canary_rows, f, indent=2)
        f.write("\n")
    print(f"wrote {CANARY_ROWS_PATH} ({len(canary_rows)} rows)")


if __name__ == "__main__":
    main()
