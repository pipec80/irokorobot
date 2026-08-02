"""Unit tests for server.llm._parse_llm_output."""

import pytest
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
