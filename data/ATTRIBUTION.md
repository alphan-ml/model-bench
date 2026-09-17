# Attribution

## Banking77

- **Dataset:** BANKING77
- **Source used for this pull:** the original dataset files published by PolyAI at
  `https://github.com/PolyAI-LDN/task-specific-datasets` (`banking_data/test.csv`,
  `banking_data/categories.json`). Pulled directly by script, not hand-copied.
- **Paper:** Casanueva, I., Temčinas, T., Gerz, D., Henderson, M., & Vulić, I. (2020).
  *Efficient Intent Detection with Dual Sentence Encoders.* In Proceedings of the 2nd
  Workshop on Natural Language Processing for Conversational AI, ACL 2020.
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0), as stated
  in the `LICENSE` file of the source repository. This is a permissive open license
  that allows use, reuse, and redistribution with attribution.
- **Split used:** `test` (3,080 examples, 77 unique fine-grained intents). Row and
  label counts were asserted programmatically at pull time (see
  `tests/test_results_schema.py` and `scripts_build_coarse_map.py`).
- **Pulled:** 2026-09-12, via `raw.githubusercontent.com` (huggingface.co was not
  reachable from the build environment's network policy; the GitHub source is the
  same original data PolyAI published and is not a secondary mirror).
- **`train` split** (10,003 examples, same 77 labels) was pulled the same way —
  direct file download of `banking_data/train.csv` from the same source repo —
  for the decision pack's classifier baseline (`src/modelbench/baseline.py`,
  README.md's "The Decision"). Committed at `data/train.jsonl`, pulled
  2026-09-17, same license and citation as the test split above.
- **Modifications:** none to the text or labels. A `coarse_map.json` groups the 77
  fine intents into 10 coarse groups for this project's own reporting; the original
  fine-grained labels are kept unchanged in `data/golden.jsonl`.

No other third-party data is used in this repository at this stage.
