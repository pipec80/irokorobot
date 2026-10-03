"""Unit tests for server.llm._parse_llm_output."""

import logging

import pytest
from server.exceptions import LLMError
from server.llm import _parse_llm_output


@pytest.mark.unit
def test_valid_json_returns_response_and_emotion() -> None:
    raw = '{"response": "Hola humano", "emotion": "joy"}'
    response, emotion = _parse_llm_output(raw)
    assert response == "Hola humano"
    assert emotion == "joy"


@pytest.mark.unit
def test_json_wrapped_in_markdown_fence_is_parsed() -> None:
    raw = '```json\n{"response": "ok", "emotion": "neutral"}\n```'
    response, emotion = _parse_llm_output(raw)
    assert response == "ok"
    assert emotion == "neutral"


@pytest.mark.unit
def test_json_with_bare_fence_is_parsed() -> None:
    raw = '```\n{"response": "ok", "emotion": "neutral"}\n```'
    response, emotion = _parse_llm_output(raw)
    assert response == "ok"
    assert emotion == "neutral"


@pytest.mark.unit
def test_malformed_json_falls_back_to_raw_text_and_neutral() -> None:
    raw = "no soy JSON válido"
    response, emotion = _parse_llm_output(raw)
    assert response == raw
    assert emotion == "neutral"


@pytest.mark.unit
def test_missing_response_key_falls_back_to_raw() -> None:
    raw = '{"emotion": "joy"}'
    response, emotion = _parse_llm_output(raw)
    assert response == raw
    assert emotion == "neutral"


@pytest.mark.unit
def test_unknown_emotion_defaults_to_neutral() -> None:
    raw = '{"response": "Hola", "emotion": "euphoria"}'
    response, emotion = _parse_llm_output(raw)
    assert response == "Hola"
    assert emotion == "neutral"


@pytest.mark.unit
@pytest.mark.parametrize("valid_emotion", ["neutral", "joy", "anger", "sadness", "surprise"])
def test_all_valid_emotions_are_accepted(valid_emotion: str) -> None:
    raw = f'{{"response": "ok", "emotion": "{valid_emotion}"}}'
    _, emotion = _parse_llm_output(raw)
    assert emotion == valid_emotion


@pytest.mark.unit
def test_emotion_is_case_normalized() -> None:
    raw = '{"response": "ok", "emotion": "JOY"}'
    _, emotion = _parse_llm_output(raw)
    assert emotion == "joy"


@pytest.mark.unit
def test_missing_emotion_key_defaults_to_neutral() -> None:
    raw = '{"response": "Hola humano"}'
    response, emotion = _parse_llm_output(raw)
    assert response == "Hola humano"
    assert emotion == "neutral"


@pytest.mark.unit
def test_malformed_json_salvages_response_field() -> None:
    """Broken JSON with a readable response field must not reach the TTS raw."""
    raw = '{"response": "Hola, ¿cómo estás?", "emotion": }'
    text, emotion = _parse_llm_output(raw)
    assert text == "Hola, ¿cómo estás?"
    assert emotion == "neutral"


@pytest.mark.unit
def test_salvage_unescapes_json_string() -> None:
    raw = '{"response": "dijo \\"hola\\" fuerte", "emotion":'
    text, _ = _parse_llm_output(raw)
    assert text == 'dijo "hola" fuerte'


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        '{"response": [], "emotion": "joy"}',
        '{"response": null, "emotion": "joy"}',
        '{"response": 7, "emotion": "joy"}',
        '{"response": {"text": "hola"}, "emotion": "joy"}',
        '{"response": "", "emotion": "joy"}',
        '{"response": "   ", "emotion": "joy"}',
    ],
)
def test_a_non_text_or_blank_response_is_rejected(raw: str) -> None:
    with pytest.raises(LLMError):
        _parse_llm_output(raw)


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["[]", '"hola"', "7", "null"])
def test_valid_json_that_is_not_an_object_is_rejected(raw: str) -> None:
    with pytest.raises(LLMError):
        _parse_llm_output(raw)


@pytest.mark.unit
@pytest.mark.parametrize("emotion", ["7", "null", '["joy"]', '{"a": 1}'])
def test_a_non_text_emotion_keeps_the_response_and_defaults_to_neutral(emotion: str) -> None:
    response, got = _parse_llm_output(f'{{"response": "Hola", "emotion": {emotion}}}')
    assert response == "Hola"
    assert got == "neutral"


@pytest.mark.unit
def test_a_response_without_an_emotion_is_still_spoken() -> None:
    assert _parse_llm_output('{"response": "Hola"}') == ("Hola", "neutral")


@pytest.mark.unit
def test_an_unusable_emotion_never_reaches_the_log(caplog: pytest.LogCaptureFixture) -> None:
    """The model's own text must not be logged (Plan 0032): a fixed reason only."""
    with caplog.at_level(logging.DEBUG, logger="server.llm"):
        _parse_llm_output('{"response": "Hola", "emotion": "CANARYZQX"}')
        _parse_llm_output('{"response": "Hola", "emotion": 7}')

    assert "canaryzqx" not in caplog.text.lower()
    assert "defaulting to neutral" in caplog.text
