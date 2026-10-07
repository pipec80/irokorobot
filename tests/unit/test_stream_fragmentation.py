"""Fragmentation consistency of the streaming protocol (Plan 0057, Task 2)."""

import pytest

from scripts.eval_stream_protocol import StreamOutcome, classify_deltas
from scripts.stream_fragmentation import (
    fragmentation_outcomes,
    is_fragmentation_consistent,
    reply_fragmentations,
)

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

# Replies production judges the same way however the tokens split.
_CONSISTENT = [
    "EMOTION:joy\nEMOTION:anger\nhola",
    f"EMOTION:joy\n{_FENCE}json\n{{}}\n{_FENCE}",
    "EMOTION:joy\nHola, ¿cómo estás?",
    "EMOTION:joy\n",
    "EMOTION:joy",
    "Hola sin etiqueta",
    'EMOTION:joy\n{"response": "x"}',
    "EMOTION:joy\n[1]",
    "",
]

# Replies whose body starts with a prefix that is still undecidable ("E", "`"): production
# waits for the rest instead of speaking it (Plan 0058, ADR 0017 decision 3).
_SPLIT_PREFIX_REPLIES = [
    "EMOTION:joy\nEMOTION:anger\nhola",
    f"EMOTION:joy\n{_FENCE}json\n{{}}\n{_FENCE}",
]


@pytest.mark.unit
def test_every_fragmentation_re_delivers_the_same_text() -> None:
    text = "EMOTION:joy\nHola. ¿Cómo estás? Muy bien."

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
@pytest.mark.parametrize("reply", _SPLIT_PREFIX_REPLIES)
def test_a_split_forbidden_prefix_is_rejected_under_every_split(reply: str) -> None:
    """The 0057 defect: split inside its first body token, the reply used to be spoken."""
    assert classify_deltas([reply]) is StreamOutcome.INVALID_PROTOCOL
    assert fragmentation_outcomes(reply) == {StreamOutcome.INVALID_PROTOCOL}
    assert is_fragmentation_consistent(reply)
