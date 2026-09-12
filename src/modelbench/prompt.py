"""Builds the one shared prompt used for every model, and parses the response.

Per SPEC-model-bench.md section 4: one prompt for all models, plain words, the
full list of allowed intent labels, and a required output of a single JSON
object {"intent": "<one of the labels>", "confidence": <integer 0-100>} and
nothing else. Temperature 0, max output tokens 60 (set by the caller, not here).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

TEMPERATURE = 0
MAX_OUTPUT_TOKENS = 60

# PROMPT_TEMPLATE is the one prompt every adapter (Python and the W-A3
# Node/Vercel side) must send. It is exported verbatim to data/prompt.txt by
# scripts_export_prompt.py so web/api/run-one.js can read the exact same
# bytes rather than re-typing the wording in JS and risking drift between
# the two languages (SPEC-model-bench.md section 2's repo layout: "prompt
# text is shared via data/prompt.txt, read at build").
#
# __INTENT_LIST__ and __TEXT__ are plain string.replace() tokens, not
# str.format() placeholders — deliberately, so this exact text can be
# dropped into data/prompt.txt and substituted the same way (a JS
# `.replace()` call) on the other side without JS having to reproduce
# Python's `{{`/`}}` format-string brace-escaping rules. Changing this
# constant's substitution mechanism (format -> replace) does not change its
# rendered output for any existing input: the JSON example below already
# reads as literal single braces after either mechanism.
PROMPT_TEMPLATE = (
    "You are sorting a customer's banking message into exactly one category.\n"
    "Read the message. Pick the single best category from the list below.\n"
    "Answer with one JSON object and nothing else. No extra words, no code "
    "fences, no explanation.\n"
    'The JSON object must look exactly like this: {"intent": "<category>", '
    '"confidence": <a whole number from 0 to 100>}\n'
    'The "intent" value must be copied exactly from the category list.\n'
    'The "confidence" value is how sure you are, from 0 (not sure at all) to '
    "100 (fully sure).\n\n"
    "Categories:\n__INTENT_LIST__\n\n"
    "Customer message:\n__TEXT__\n"
)


def build_prompt(text: str, intents: list[str]) -> str:
    """Builds the shared prompt for one message against the full intent list."""
    intent_list = "\n".join(f"- {i}" for i in intents)
    return PROMPT_TEMPLATE.replace("__INTENT_LIST__", intent_list).replace("__TEXT__", text)


@dataclass
class Parsed:
    intent: str | None
    confidence: int | None
    invalid: bool
    raw: str


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_FIRST_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1)
    return text


def _find_first_json_object(text: str) -> dict | None:
    """Finds the first valid JSON object in text, trying progressively shorter
    matches of the first `{...}` span so trailing text after a valid object
    does not break parsing (e.g. `{"intent": "x", "confidence": 1} thanks!`).
    """
    start = text.find("{")
    if start == -1:
        return None
    # Try every closing brace from the end of the string backwards until one
    # of the substrings parses as JSON. This handles both "trailing text
    # after the object" and "a single well-formed object with no trailing
    # text" without needing a full JSON tokenizer.
    for end in range(len(text), start, -1):
        if text[end - 1] != "}":
            continue
        candidate = text[start:end]
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_response(raw: str, allowed_intents: list[str]) -> Parsed:
    """Parses a model's raw text response into a Parsed result.

    Never raises on garbage input: any failure to find/parse a JSON object,
    or a missing/wrong-typed field, returns
    Parsed(intent=None, confidence=None, invalid=True, raw=raw).
    An intent that parses but is not in allowed_intents is also invalid
    (invalid_label case) and intent is set to None so it counts as wrong.
    """
    if raw is None:
        raw = ""
    text = _strip_code_fences(raw)
    obj = _find_first_json_object(text)

    if obj is None:
        return Parsed(intent=None, confidence=None, invalid=True, raw=raw)

    intent = obj.get("intent")
    confidence = obj.get("confidence")

    if not isinstance(intent, str) or intent not in allowed_intents:
        return Parsed(intent=None, confidence=_clamp_confidence(confidence), invalid=True, raw=raw)

    return Parsed(
        intent=intent,
        confidence=_clamp_confidence(confidence),
        invalid=False,
        raw=raw,
    )


def _clamp_confidence(confidence) -> int | None:
    if isinstance(confidence, bool):
        return None
    if not isinstance(confidence, (int, float)):
        return None
    value = int(round(confidence))
    return max(0, min(100, value))
