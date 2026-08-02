"""Pure sentence-boundary splitting for sentence-streaming TTS (R3).

No I/O here on purpose: the LLM streaming pipeline (``streaming.py``) feeds
this function tokens as they arrive and synthesizes speech as soon as a
sentence closes, without waiting for the full response.
"""

import re

# Matches the shortest run of non-terminator text ending in one of . ? ! —
# greedy alternatives would swallow multiple sentences into one match.
_SENTENCE_END_RE = re.compile(r"[^.?!]*[.?!]+")


def split_first_sentence(buffer: str) -> tuple[str, str] | None:
    """Split the first closed sentence off the front of a text buffer.

    A sentence is "closed" once it ends in ``.``, ``?``, or ``!`` (one or
    more, to tolerate ``"..."`` / ``"?!"``). Leading whitespace is stripped
    from both the returned sentence and the remainder, so a chained call on
    the remainder never sees a stray leading space.

    Args:
        buffer: Accumulated text streamed so far from the LLM.

    Returns:
        ``(sentence, remainder)`` where ``sentence`` is the first closed
        sentence (trimmed) and ``remainder`` is everything after it. ``None``
        if no sentence has closed yet in ``buffer``.
    """
    stripped = buffer.lstrip()
    match = _SENTENCE_END_RE.match(stripped)
    if match is None:
        return None
    sentence = match.group(0).strip()
    if not sentence:
        return None
    remainder = stripped[match.end() :].lstrip()
    return sentence, remainder
