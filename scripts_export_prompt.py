"""One-off/regeneratable script (not part of the shipped package) that writes
data/prompt.txt from modelbench.prompt.PROMPT_TEMPLATE.

Why this exists: SPEC-model-bench.md section 2's repo layout says the
web/api/run-one.js Vercel function uses "the same prompt as the Python side
(prompt text is shared via data/prompt.txt, read at build)." Rather than
hand-typing the wording a second time in JavaScript and risking the two
sides drifting apart, this script exports the literal Python template text
byte-for-byte, and both build_prompt() (Python) and run-one.js (Node) do the
exact same two string substitutions (__INTENT_LIST__, __TEXT__) against it.

Run this whenever PROMPT_TEMPLATE changes in src/modelbench/prompt.py, then
commit the regenerated data/prompt.txt alongside the code change.
tests/test_prompt.py's test_prompt_txt_matches_python_template regression
test fails CI if the two ever go out of sync.
"""

from pathlib import Path

from modelbench.prompt import PROMPT_TEMPLATE

REPO_ROOT = Path(__file__).resolve().parent
OUT_PATH = REPO_ROOT / "data" / "prompt.txt"


def main() -> int:
    OUT_PATH.write_text(PROMPT_TEMPLATE, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(PROMPT_TEMPLATE)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
