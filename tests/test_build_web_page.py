"""Tests for scripts_build_web_page.py's build_page() -- the function that
inlines a results JSON into web/index.template.html per SPEC-model-bench.md
§7.1 ("Reads results.json at build time (inlined)").

scripts_build_web_page.py lives at the repo root (like scripts_build_coarse_map.py
and scripts_export_prompt.py) rather than in src/modelbench, since it is a
build-time tool, not part of the shipped package -- so it is imported here by
path, the same pattern conftest.py already needs for any repo-root script.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_build_web_page():
    spec = importlib.util.spec_from_file_location(
        "scripts_build_web_page", REPO_ROOT / "scripts_build_web_page.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["scripts_build_web_page"] = module
    spec.loader.exec_module(module)
    return module


build_web_page = _load_build_web_page()


def test_build_page_embeds_the_results_json_verbatim():
    html = build_web_page.build_page(REPO_ROOT / "results.sample.json")
    assert "window.__RESULTS__ = " in html
    assert build_web_page.PLACEHOLDER not in html

    # The embedded blob must parse back to the exact same data, not a
    # mangled or partially-escaped copy.
    with open(REPO_ROOT / "results.sample.json") as f:
        expected = json.load(f)
    start = html.index("window.__RESULTS__ = ") + len("window.__RESULTS__ = ")
    end = html.index(";\n", start)
    embedded = json.loads(html[start:end])
    assert embedded == expected


def test_build_page_keeps_the_rest_of_the_template_intact():
    html = build_web_page.build_page(REPO_ROOT / "results.sample.json")
    assert "<title>Model Bench" in html
    assert 'id="insights-list"' in html
    assert 'id="live-box-submit"' in html


def test_build_page_raises_a_clear_error_if_the_template_placeholder_is_missing(tmp_path):
    bad_template = tmp_path / "index.template.html"
    bad_template.write_text("<html>no placeholder here</html>", encoding="utf-8")
    try:
        build_web_page.build_page(REPO_ROOT / "results.sample.json", template_path=bad_template)
        raise AssertionError("expected a ValueError")
    except ValueError as exc:
        assert "placeholder" in str(exc)


def test_build_page_raises_file_not_found_for_a_missing_results_file(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    try:
        build_web_page.build_page(missing)
        raise AssertionError("expected a FileNotFoundError")
    except FileNotFoundError:
        pass
