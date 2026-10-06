"""Closed failure shapes of a streamed reply (Plan 0057, Task 1)."""

import pytest

from scripts.eval_stream_protocol import StreamOutcome, classify_deltas
from scripts.stream_failure_shapes import FailureShape, classify_failure_shape

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

_CASES = [
    ("EMOTION:joy\nHola, ¿cómo estás?", FailureShape.VALID),
    ("EMOTION: joy \nHola", FailureShape.VALID),
    ("EMOTION:unknownemotion\nHola", FailureShape.VALID),
    ("", FailureShape.EMPTY),
    ("  \n", FailureShape.EMPTY),
    ("Hola sin etiqueta", FailureShape.NO_TAG),
    ('{"response": "x", "emotion": "joy"}', FailureShape.JSON_START),
    ("[1, 2]", FailureShape.JSON_START),
    (f"{_FENCE}json\n{{}}\n{_FENCE}", FailureShape.FENCE_START),
    ("\nEMOTION:joy\nHola", FailureShape.LEADING_WHITESPACE),
    (" EMOTION:joy\nHola", FailureShape.LEADING_WHITESPACE),
    ("Claro. EMOTION:joy\nHola", FailureShape.TEXT_BEFORE_TAG),
    ("**EMOTION:** joy\nHola", FailureShape.TEXT_BEFORE_TAG),
    ("EMOCIÓN: joy\nHola", FailureShape.OTHER_LABEL),
    ("Emotion - joy\nHola", FailureShape.OTHER_LABEL),
    ("EMOTION:<joy>\nHola", FailureShape.TAG_WRAPPED),
    ("EMOTION: [joy]\nHola", FailureShape.TAG_WRAPPED),
    ("EMOTION: joy ¡Hola!", FailureShape.TAG_SAME_LINE),
    ("EMOTION:joy Hola\nmás", FailureShape.TAG_SAME_LINE),
    ("EMOTION:joy.\nHola", FailureShape.TAG_PUNCTUATION),
    ("EMOTION:joy,Hola", FailureShape.TAG_PUNCTUATION),
    ("EMOTION:joy", FailureShape.TAG_TRUNCATED),
    ("EMOTION:joy  ", FailureShape.TAG_TRUNCATED),
    ("EMOTION:", FailureShape.TAG_TRUNCATED),
    ("EMOTION: -\nHola", FailureShape.OTHER),
    ("EMOTION:joy\n", FailureShape.TAG_ONLY),
    ("EMOTION:joy\n   ", FailureShape.TAG_ONLY),
    ('EMOTION:joy\n{"response": "x"}', FailureShape.BODY_JSON),
    ("EMOTION:joy\n[1]", FailureShape.BODY_JSON),
    (f"EMOTION:joy\n{_FENCE}json\n{{}}\n{_FENCE}", FailureShape.BODY_FENCE),
    ("EMOTION:joy\nEMOTION:anger\nhola", FailureShape.SECOND_TAG),
    ("EMOTION:joy\n  emotion: anger\nhola", FailureShape.SECOND_TAG),
]


@pytest.mark.unit
@pytest.mark.parametrize("text, shape", _CASES)
def test_every_shape_is_named_exactly(text: str, shape: FailureShape) -> None:
    assert classify_failure_shape(text) is shape


@pytest.mark.unit
@pytest.mark.parametrize("text, shape", _CASES)
def test_valid_shape_agrees_with_the_whole_text_protocol(text: str, shape: FailureShape) -> None:
    """The shape table and the protocol never disagree about speakable text."""
    whole = classify_deltas([text] if text else [])

    assert (shape is FailureShape.VALID) == (whole is StreamOutcome.VALID)


@pytest.mark.unit
def test_the_enum_is_closed_and_every_member_is_exercised() -> None:
    assert {case[1] for case in _CASES} == set(FailureShape)


@pytest.mark.unit
def test_the_classifier_returns_only_enum_members_and_never_echoes_text() -> None:
    canary = "CANARIO-INVENTADO-731"
    for text in (canary, f"EMOTION:{canary}\nHola", f"EMOTION:joy {canary}", f"<{canary}>"):
        shape = classify_failure_shape(text)

        assert isinstance(shape, FailureShape)
        assert canary not in shape.value
