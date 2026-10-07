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
    "EMOTION:joy\nHola, ¿cómo estás?",
    "EMOTION:joy\n",
    "EMOTION:joy",
    "Hola sin etiqueta",
    'EMOTION:joy\n{"response": "x"}',
    "EMOTION:joy\n[1]",
    "",
]

# Replies whose verdict depends on the split TODAY: production validates the start of the
# body once, with the first fragment, so a prefix that is still undecidable ("E", "`")
# is accepted and the rest is never checked. Plan 0057 pins this defect; the repair plan
# flips these into ``_CONSISTENT``.
_INCONSISTENT_TODAY = [
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
@pytest.mark.parametrize("reply", _INCONSISTENT_TODAY)
def test_the_known_fragmentation_defect_is_pinned_until_the_repair_plan(reply: str) -> None:
    """Whole, the reply is rejected; split inside its first body token, it is spoken."""
    assert classify_deltas([reply]) is StreamOutcome.INVALID_PROTOCOL
    assert fragmentation_outcomes(reply) == {StreamOutcome.VALID, StreamOutcome.INVALID_PROTOCOL}
    assert not is_fragmentation_consistent(reply)
