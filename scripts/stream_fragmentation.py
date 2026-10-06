"""How the same streamed reply is judged under different token splits (Plan 0057).

A reply is a protocol property, not a delivery accident: the verdict must not change
with where the model's tokens happen to split. These helpers re-deliver one reply in
several fragmentations through the evaluator that mirrors production's consumer.
"""

from __future__ import annotations

import re

from scripts.eval_stream_protocol import StreamOutcome, classify_deltas

_TOKEN_RE = re.compile(r"\w+|\W")


def reply_fragmentations(text: str) -> list[list[str]]:
    """Several ways a model's tokens could split one reply (empty deltas never occur).

    Args:
        text: One complete reply.

    Returns:
        Fragmentations: whole, one character at a time, pairs, triples, lines, halves
        and word/punctuation tokens.
    """
    ways = [
        [text],
        list(text),
        [text[i : i + 2] for i in range(0, len(text), 2)],
        [text[i : i + 3] for i in range(0, len(text), 3)],
        text.splitlines(keepends=True),
        [text[: len(text) // 2], text[len(text) // 2 :]],
        _TOKEN_RE.findall(text),
    ]
    return [[piece for piece in way if piece] for way in ways]


def fragmentation_outcomes(text: str) -> set[StreamOutcome]:
    """Return the distinct outcomes one reply gets across ``reply_fragmentations``."""
    return {classify_deltas(fragments) for fragments in reply_fragmentations(text)}


def is_fragmentation_consistent(text: str) -> bool:
    """Return whether every fragmentation of ``text`` is judged the same way."""
    return len(fragmentation_outcomes(text)) == 1
