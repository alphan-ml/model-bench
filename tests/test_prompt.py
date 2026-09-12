from modelbench.prompt import build_prompt, parse_response

ALLOWED = ["card_arrival", "top_up_failed", "exchange_rate"]


def test_valid_json():
    raw = '{"intent": "card_arrival", "confidence": 87}'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.intent == "card_arrival"
    assert parsed.confidence == 87
    assert parsed.invalid is False


def test_fenced_json():
    raw = '```json\n{"intent": "top_up_failed", "confidence": 55}\n```'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.intent == "top_up_failed"
    assert parsed.confidence == 55
    assert parsed.invalid is False


def test_fenced_json_no_language_tag():
    raw = '```\n{"intent": "exchange_rate", "confidence": 10}\n```'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.intent == "exchange_rate"
    assert parsed.invalid is False


def test_json_with_trailing_text():
    raw = '{"intent": "card_arrival", "confidence": 90} thanks, hope that helps!'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.intent == "card_arrival"
    assert parsed.confidence == 90
    assert parsed.invalid is False


def test_json_with_leading_text():
    raw = 'Sure, here is my answer: {"intent": "card_arrival", "confidence": 90}'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.intent == "card_arrival"
    assert parsed.invalid is False


def test_label_not_in_set():
    raw = '{"intent": "not_a_real_label", "confidence": 80}'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.intent is None
    assert parsed.invalid is True
    # confidence is still parsed out even though the label is invalid
    assert parsed.confidence == 80


def test_empty_string():
    parsed = parse_response("", ALLOWED)
    assert parsed.intent is None
    assert parsed.confidence is None
    assert parsed.invalid is True
    assert parsed.raw == ""


def test_none_input_does_not_raise():
    parsed = parse_response(None, ALLOWED)
    assert parsed.invalid is True


def test_garbage_non_json_does_not_raise():
    parsed = parse_response("the model refused to answer today", ALLOWED)
    assert parsed.intent is None
    assert parsed.invalid is True


def test_confidence_out_of_range_high_is_clamped():
    raw = '{"intent": "card_arrival", "confidence": 250}'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.intent == "card_arrival"
    assert parsed.confidence == 100
    assert parsed.invalid is False


def test_confidence_out_of_range_negative_is_clamped():
    raw = '{"intent": "card_arrival", "confidence": -30}'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.confidence == 0


def test_confidence_missing_is_none_but_not_invalid():
    raw = '{"intent": "card_arrival"}'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.intent == "card_arrival"
    assert parsed.confidence is None
    assert parsed.invalid is False


def test_confidence_wrong_type_is_none():
    raw = '{"intent": "card_arrival", "confidence": "very sure"}'
    parsed = parse_response(raw, ALLOWED)
    assert parsed.confidence is None
    assert parsed.invalid is False


def test_malformed_json_does_not_raise():
    raw = '{"intent": "card_arrival", "confidence": 80'  # missing closing brace
    parsed = parse_response(raw, ALLOWED)
    assert parsed.invalid is True


def test_build_prompt_contains_all_intents_and_text():
    prompt = build_prompt("Where is my card?", ALLOWED)
    for intent in ALLOWED:
        assert intent in prompt
    assert "Where is my card?" in prompt
    assert "JSON" in prompt
