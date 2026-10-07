"""Unit tests for server.streaming_protocol: the streaming wire format (ADR 0017).

``parse_streaming_emotion`` decides how a reply starts as soon as the text allows it;
``validate_streaming_body_start``, ``is_body_start_undecided`` and ``reject_embedded_tag``
decide what may be spoken. None of them may leak model text into an exception message.
"""

from __future__ import annotations

import pytest
from server.exceptions import LLMError
from server.streaming_protocol import (
    Preamble,
    StreamProtocolError,
    is_body_start_undecided,
    parse_streaming_emotion,
    reject_embedded_tag,
    validate_streaming_body_start,
)

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

# Buffers that may still become a valid start: wait for the next delta.
_UNDECIDED = [
    "",
    "   ",
    "E",
    "EMO",
    "emotion",
    "EMOTION:",
    "EMOTION:jo",
    "EMOTION:joy",
    "EMOTION:joy  ",
    "EMOTION: joy",
]

# Buffers whose tag can never become valid: refuse as soon as that is known.
_REJECTED = [
    "EMOTION: Hola, ¿cómo estás?",
    "EMOTION: Hola cómo estás",
    "EMOTION:joy. Hola",
    "EMOTION:joy,Hola",
    "EMOTION:<joy>\nHola",
    "EMOTION: [joy]\nHola",
    "EMOTION: -\nHola",
]


@pytest.mark.unit
@pytest.mark.parametrize("buffer", _UNDECIDED)
def test_an_undecided_start_waits_for_more_text(buffer: str) -> None:
    assert parse_streaming_emotion(buffer) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer, expected",
    [
        ("EMOTION:joy\n", Preamble("joy", "")),
        ("EMOTION:joy\nhola", Preamble("joy", "hola")),
        ("EMOTION: joy \nhola", Preamble("joy", "hola")),
        ("emotion: sadness\nLo siento.", Preamble("sadness", "Lo siento.")),
        ("EMOTION:cosmic\nhola", Preamble("neutral", "hola")),
        ("EMOTION:\njoy\nhola", Preamble("joy", "hola")),
        ("\n EMOTION:anger\nCalma.", Preamble("anger", "Calma.")),
        ("EMOTION:joy\r\nhola", Preamble("joy", "hola")),
    ],
)
def test_a_tag_on_its_own_line_is_parsed(buffer: str, expected: Preamble) -> None:
    assert parse_streaming_emotion(buffer) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer, expected",
    [
        ("EMOTION:joy ¡Hola! ¿Qué tal?", Preamble("joy", "¡Hola! ¿Qué tal?")),
        ("emotion: sadness Lo siento mucho.", Preamble("sadness", "Lo siento mucho.")),
        ("EMOTION:joy\tHola", Preamble("joy", "Hola")),
        ("EMOTION:joy H", Preamble("joy", "H")),
        ('EMOTION: joy {"response":"hola"}', Preamble("joy", '{"response":"hola"}')),
    ],
)
def test_a_known_emotion_on_the_same_line_as_the_text_is_parsed(
    buffer: str, expected: Preamble
) -> None:
    assert parse_streaming_emotion(buffer) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer",
    [
        "Hola sin etiqueta",
        "  Eso es genial.",
        "Emoción pura.",
        "Claro. EMOTION:joy\nHola",
        '{"response": "x"}',
    ],
)
def test_text_without_a_leading_tag_is_rescued_as_neutral(buffer: str) -> None:
    preamble = parse_streaming_emotion(buffer)

    assert preamble == Preamble("neutral", buffer.lstrip(), rescued=True)


@pytest.mark.unit
@pytest.mark.parametrize("buffer", _REJECTED)
def test_a_tag_that_can_never_be_valid_is_refused_at_once(buffer: str) -> None:
    with pytest.raises(StreamProtocolError) as exc_info:
        parse_streaming_emotion(buffer)

    assert buffer not in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.parametrize("buffer", _UNDECIDED)
def test_an_undecided_start_at_the_end_of_the_stream_is_a_violation(buffer: str) -> None:
    with pytest.raises(StreamProtocolError) as exc_info:
        parse_streaming_emotion(buffer, final=True)

    message = str(exc_info.value)
    assert message  # bounded, non-empty
    if buffer.strip():
        assert buffer not in message


@pytest.mark.unit
def test_a_decided_start_is_the_same_at_the_end_of_the_stream() -> None:
    assert parse_streaming_emotion("EMOTION:joy\nhola", final=True) == Preamble("joy", "hola")
    assert parse_streaming_emotion("Hola", final=True) == Preamble("neutral", "Hola", rescued=True)


@pytest.mark.unit
def test_a_tag_and_a_json_body_on_one_line_is_parsed_then_refused_by_the_body_check() -> None:
    preamble = parse_streaming_emotion('EMOTION: joy {"response":"hola"}')

    assert preamble is not None
    assert preamble.emotion == "joy"
    with pytest.raises(StreamProtocolError):
        validate_streaming_body_start(preamble.remainder)


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
def test_validate_body_rejects_repeated_protocol() -> None:
    """A second EMOTION: tag inside the body means the model repeated the preamble."""
    repeated_bodies = [
        "EMOTION:joy\nhola de nuevo",
        "emotion:joy\nhola",
        "  EMOTION:sadness\nhola",
    ]
    for body in repeated_bodies:
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
        "EMOTION\uff1a joy",
        "EMOTION : joy",
        "emotion: joy",
        "Claro, emotion:joy otra vez.",
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
        "",
    ],
)
def test_reject_embedded_tag_allows_plain_speech(text: str) -> None:
    reject_embedded_tag(text)
