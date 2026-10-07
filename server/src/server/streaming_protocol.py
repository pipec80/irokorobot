"""Pure parsing/validation for the streaming EMOTION-tag output protocol.

llm_streaming.py owns prompt assembly and the Ollama transport; this module
owns only the wire-format rules for what a valid streamed response looks
like. Kept dependency-free of I/O and logging on purpose: Task 3 will call
these functions from the orchestration loop in streaming.py to decide
whether a candidate response is speakable at all, so they must be safe to
unit test in isolation and must never leak raw model output into an
exception message (that text may contain anything the model produced).
"""

import re

from server.exceptions import LLMError
from server.llm import FALLBACK_EMOTION, VALID_EMOTIONS

_EMOTION_TAG_RE = re.compile(r"^EMOTION:\s*(\w+)\s*\n", re.IGNORECASE)

# Bounded, content-free message — never interpolate the raw candidate/model
# output here (it may contain arbitrary, unbounded model text).
_INVALID_PROTOCOL_MESSAGE = "Invalid streaming response protocol"


class StreamProtocolError(LLMError):
    """The model's streamed output broke the protocol (never carries model text)."""


_FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
_TAG = "EMOTION:"
_INVALID_BODY_PREFIXES = ("{", "[", _FENCE)
_UNDECIDED_BODY_PREFIXES = (_TAG, _FENCE)
# A tag mention in speech: **EMOTION**: and a fullwidth colon count; demotion: does not.
_TAG_MENTION_RE = re.compile(r"\bemotion\W{0,3}[:\uff1a]", re.IGNORECASE)


def parse_streaming_emotion(
    buffer: str,
    *,
    final: bool = False,
) -> tuple[str, str] | None:
    """Parse one complete emotion preamble or reject an invalid protocol.

    Args:
        buffer: Text accumulated so far from generate_response_stream.
        final: Whether the stream has ended and no more text will arrive.
            When True, a buffer that still has no complete valid
            "EMOTION:<emotion>\\n" line is treated as a protocol violation
            rather than "keep waiting".

    Returns:
        ``(emotion, remainder)`` once the tag line is fully buffered
        (validated against ``VALID_EMOTIONS``, defaulting to neutral for an
        unknown tag), or ``None`` if the first line hasn't arrived yet and
        more input may still complete it (only possible when
        ``final=False``).

    Raises:
        StreamProtocolError: If ``final`` is True and the buffer never produced a
            complete, valid protocol line.
    """
    match = _EMOTION_TAG_RE.match(buffer)
    if match is None:
        if final:
            raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
        return None
    emotion = match.group(1).lower()
    if emotion not in VALID_EMOTIONS:
        emotion = FALLBACK_EMOTION
    return emotion, buffer[match.end() :]


def is_body_start_undecided(body: str) -> bool:
    """Whether the body so far is a proper prefix of a forbidden start (tag or fence).

    A body that begins ``E`` or a single backtick may still become ``EMOTION:`` or a
    code fence once the next token arrives, so it can be neither spoken nor judged yet.

    Args:
        body: The text after the preamble, as received so far.

    Returns:
        True while more text is needed to know whether the body start is allowed.
    """
    stripped = body.lstrip()
    return bool(stripped) and any(
        len(stripped) < len(prefix) and prefix.startswith(stripped.upper())
        for prefix in _UNDECIDED_BODY_PREFIXES
    )


def validate_streaming_body_start(body: str) -> None:
    """Reject structured metadata or a repeated protocol tag before speech.

    Called once the emotion preamble has been stripped, before the
    remainder is treated as speakable text. Guards against hybrid model
    output that mixes the classic JSON contract or repeats the streaming
    tag instead of answering in plain text.

    Args:
        body: The response text remaining after the emotion preamble.

    Raises:
        StreamProtocolError: If ``body`` (ignoring leading whitespace) starts with
            ``{``, ``[``, a code fence, or another ``EMOTION:`` tag.
    """
    stripped = body.lstrip()
    if stripped.startswith(_INVALID_BODY_PREFIXES) or stripped.upper().startswith(_TAG):
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)


def reject_embedded_tag(text: str) -> None:
    """Reject speech that contains a protocol tag anywhere (ADR 0017, decision 5).

    Args:
        text: One sentence, or the final unfinished tail, about to be spoken.

    Raises:
        StreamProtocolError: If ``text`` mentions ``EMOTION`` followed by a colon, in any
            letter case, with up to three symbols between them (``**EMOTION**:``) and
            either colon width.
    """
    if _TAG_MENTION_RE.search(text):
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
