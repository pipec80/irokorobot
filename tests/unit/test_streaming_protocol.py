"""Unit tests for server.streaming_protocol: the guards of a plain-text stream (ADR 0018).

The model answers in plain text and the emotion is decided apart, so this module has no tag
grammar left. ``validate_streaming_body_start``, ``is_body_start_undecided`` and
``reject_embedded_tag`` decide what may be spoken; none of them may leak model text into an
exception message.
"""

from __future__ import annotations

import pytest
from server.exceptions import LLMError
from server.streaming_protocol import (
    StreamProtocolError,
    is_body_start_undecided,
    reject_embedded_tag,
    validate_streaming_body_start,
)

from server import llm_streaming, streaming_protocol

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence
_FULLWIDTH_COLON = chr(0xFF1A)  # built, not written: an ambiguous character in the source
_FULLWIDTH_LATIN_TAG = "".join(chr(ord(letter) + 0xFEE0) for letter in "EMOTION")
_ZERO_WIDTH_SPACE = chr(0x200B)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["parse_streaming_emotion", "Preamble"])
def test_the_tag_start_grammar_is_gone(name: str) -> None:
    """ADR 0018: nobody asks the model for a tag, so nothing parses one at the start."""
    assert not hasattr(streaming_protocol, name)
    assert not hasattr(llm_streaming, name)


@pytest.mark.unit
def test_validate_body_rejects_structured_json() -> None:
    """Hybrid output mixing the JSON contract into the streaming body is invalid."""
    hybrid_bodies = [
        '{"response": "hola", "emotion": "joy"}',
        '{"response":"hola"}',
        '["hola", "chau"]',
        f'{_FENCE}json\n{{"response": "hola"}}\n{_FENCE}',
        '  {"response": "hola"}',  # leading whitespace before the brace
    ]
    for body in hybrid_bodies:
        with pytest.raises(StreamProtocolError) as exc_info:
            validate_streaming_body_start(body)
        assert body not in str(exc_info.value)


@pytest.mark.unit
def test_validate_body_rejects_a_reply_that_starts_with_a_tag() -> None:
    """A tag the model writes anyway at the start is refused (decision D-6)."""
    tagged_bodies = [
        "EMOTION:joy\nhola de nuevo",
        "emotion:joy\nhola",
        "  EMOTION:sadness\nhola",
    ]
    for body in tagged_bodies:
        with pytest.raises(StreamProtocolError) as exc_info:
            validate_streaming_body_start(body)
        assert body not in str(exc_info.value)

    # A normal plain-text body must pass without raising.
    validate_streaming_body_start("hola, como estas?")


@pytest.mark.unit
def test_a_protocol_error_is_an_llm_error() -> None:
    """Callers that catch ``LLMError`` keep working; the streaming loop catches the subclass."""
    assert issubclass(StreamProtocolError, LLMError)


@pytest.mark.unit
@pytest.mark.parametrize("body", ["E", "EM", "emotion", "  EMOTION", "`", "``"])
def test_a_body_that_could_still_become_a_forbidden_start_is_undecided(body: str) -> None:
    """A prefix of ``EMOTION:`` or of a code fence cannot be judged yet: wait for more."""
    assert is_body_start_undecided(body)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body", ["", "   ", "Hola", "Es", "{", "[", "EMOTION:", "emotion:joy", "`x", _FENCE, "Eso."]
)
def test_a_body_that_is_decided_is_not_undecided(body: str) -> None:
    """Decided means allowed (plain text) or already forbidden (``validate`` rejects it)."""
    assert not is_body_start_undecided(body)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "Hola. EMOTION:joy",
        "**EMOTION:** joy",
        "**EMOTION**: joy",
        f"EMOTION{_FULLWIDTH_COLON} joy",
        "EMOTION : joy",
        "emotion: joy",
        "Claro, emotion:joy otra vez.",
        # Underscore wrappers: "_" is a word character, so it needs its own rule (audit A-1).
        "_EMOTION_: joy. Hola.",
        "__EMOTION__: joy",
        "Hola. _EMOTION_: joy.",
        "Hola. EMOTION_: joy.",
        "_EMOTION:joy_",
        # Compatibility forms are normalised first (audit A-4).
        _FULLWIDTH_LATIN_TAG + ": joy",
        "EMOTION" + _ZERO_WIDTH_SPACE * 2 + ": joy",
    ],
)
def test_reject_embedded_tag_refuses_a_tag_anywhere(text: str) -> None:
    with pytest.raises(StreamProtocolError) as exc_info:
        reject_embedded_tag(text)

    assert text not in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "La emoción es alegría.",
        "Emotion es una palabra.",
        "Una demotion: palabra rara.",
        "¿Qué emoción sientes?",
        "El campo emotion_name: vacío",
        "Escribe EMOTIONS: aquí",
        "",
    ],
)
def test_reject_embedded_tag_allows_plain_speech(text: str) -> None:
    reject_embedded_tag(text)
