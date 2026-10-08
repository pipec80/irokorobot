"""Fragmentation consistency of the streaming protocol (Plans 0057 and 0059)."""

import pytest

from scripts.eval_stream_protocol import StreamOutcome, classify_deltas
from scripts.stream_fragmentation import (
    fragmentation_outcomes,
    is_fragmentation_consistent,
    reply_fragmentations,
)

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

# Replies production judges the same way however the tokens split. The two that Plan 0057
# pinned as split-dependent (a tag or a fence split inside the first body token) joined this
# list when the guards learned to wait on an undecided body start.
_CONSISTENT = [
    "Hola, ¿cómo estás?",
    "Hola. ¿Cómo estás? Muy bien.",
    "Hola sin etiqueta",
    "E",
    "`",
    "",
    '{"response": "x"}',
    "[1]",
    "EMOTION:joy\nHola",
    "emotion: joy\nHola",
    "EMOTION:joy\nEMOTION:anger\nhola",
    f"{_FENCE}json\n{{}}\n{_FENCE}",
    "Hola. EMOTION:joy",
    "Hola. EMOTION:joy. Adiós.",
    "Hola. **EMOTION**: joy. Adiós.",
    f"Hola. EMOTION{chr(0xFF1A)} joy",
    "La emoción es alegría. Demotion: no cuenta.",
]


@pytest.mark.unit
def test_every_fragmentation_re_delivers_the_same_text() -> None:
    text = "Hola. ¿Cómo estás? Muy bien."

    for fragments in reply_fragmentations(text):
        assert "".join(fragments) == text
        assert all(fragments)


@pytest.mark.unit
def test_the_family_includes_word_and_punctuation_tokens() -> None:
    assert ["EMOTION", ":", "joy", "\n", "Hola"] in reply_fragmentations("EMOTION:joy\nHola")


@pytest.mark.unit
@pytest.mark.parametrize("reply", _CONSISTENT)
def test_a_reply_judged_the_same_under_every_split_is_consistent(reply: str) -> None:
    assert is_fragmentation_consistent(reply)
    assert len(fragmentation_outcomes(reply)) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "reply",
    ["EMOTION:joy\nEMOTION:anger\nhola", f"{_FENCE}json\n{{}}\n{_FENCE}", "Hola. EMOTION:joy"],
)
def test_a_forbidden_prefix_is_rejected_under_every_split(reply: str) -> None:
    """The whole text and every fragmentation of it share the INVALID verdict (decision D-6)."""
    assert classify_deltas([reply]) is StreamOutcome.INVALID_PROTOCOL
    assert fragmentation_outcomes(reply) == {StreamOutcome.INVALID_PROTOCOL}
