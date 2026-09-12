/**
 * JS side of the ONE shared prompt/parser contract with
 * src/modelbench/prompt.py (SPEC-model-bench.md §4 and §2's repo layout:
 * "prompt text is shared via data/prompt.txt, read at build"). Every
 * function here is a faithful, test-verified port of the Python original
 * so the two languages can never silently disagree on what a model was
 * asked or how its answer was scored.
 */

/** Same substitution modelbench.prompt.build_prompt() does in Python,
 * against the exact same data/prompt.txt bytes -- see prompt.py's
 * PROMPT_TEMPLATE comment for why __INTENT_LIST__/__TEXT__ are plain
 * string.replace() tokens rather than a template-literal/format-string
 * mechanism: it lets both languages share one literal template with no
 * brace-escaping rules to keep in sync. */
export function buildPrompt(text, intents, template) {
  const intentList = intents.map((i) => `- ${i}`).join('\n');
  return template.replace('__INTENT_LIST__', intentList).replace('__TEXT__', text);
}

const CODE_FENCE_RE = /```(?:json)?\s*([\s\S]*?)\s*```/i;

export function stripCodeFences(text) {
  const match = text.match(CODE_FENCE_RE);
  return match ? match[1] : text;
}

/** Port of prompt.py's _find_first_json_object: finds the first "{", then
 * tries every closing "}" from the end of the string backwards until one
 * of the substrings parses as a JSON object. Handles both trailing text
 * after a valid object and a single well-formed object with no trailing
 * text, without a full JSON tokenizer -- same approach, same behavior. */
export function findFirstJsonObject(text) {
  const start = text.indexOf('{');
  if (start === -1) return null;
  for (let end = text.length; end > start; end--) {
    if (text[end - 1] !== '}') continue;
    const candidate = text.slice(start, end);
    let obj;
    try {
      obj = JSON.parse(candidate);
    } catch {
      continue;
    }
    if (obj !== null && typeof obj === 'object' && !Array.isArray(obj)) {
      return obj;
    }
  }
  return null;
}

/** Port of prompt.py's _clamp_confidence. A JS boolean is not a "number"
 * by typeof (unlike Python, where bool is an int subclass), so the
 * explicit boolean check below is what makes the two languages agree that
 * confidence: true/false is invalid, not confidence: 1/0. */
function clampConfidence(confidence) {
  if (typeof confidence === 'boolean') return null;
  if (typeof confidence !== 'number' || !Number.isFinite(confidence)) return null;
  const value = Math.round(confidence);
  return Math.max(0, Math.min(100, value));
}

/**
 * Port of prompt.py's parse_response. Never throws on garbage input: any
 * failure to find/parse a JSON object, or a missing/wrong-typed field,
 * returns {intent: null, confidence: null, invalid: true, raw}. An intent
 * that parses but is not in allowedIntents is also invalid, with intent
 * set to null.
 * @returns {{intent: string|null, confidence: number|null, invalid: boolean, raw: string}}
 */
export function parseModelResponse(raw, allowedIntents) {
  const text = raw == null ? '' : String(raw);
  const stripped = stripCodeFences(text);
  const obj = findFirstJsonObject(stripped);

  if (obj === null) {
    return { intent: null, confidence: null, invalid: true, raw: text };
  }

  const { intent, confidence } = obj;
  if (typeof intent !== 'string' || !allowedIntents.includes(intent)) {
    return { intent: null, confidence: clampConfidence(confidence), invalid: true, raw: text };
  }

  return { intent, confidence: clampConfidence(confidence), invalid: false, raw: text };
}
