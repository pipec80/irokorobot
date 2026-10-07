"""Pure parsing/validation for the streaming EMOTION-tag output protocol (ADR 0017).

llm_streaming.py owns prompt assembly and the Ollama transport; this module
owns only the wire-format rules for what a valid streamed response looks
like. Kept dependency-free of I/O and logging on purpose: the orchestration
loop in streaming.py calls these functions to decide whether a candidate
response is speakable at all, so they must be safe to unit test in isolation
and must never leak raw model output into an exception message (that text
may contain anything the model produced).
"""

from dataclasses import dataclass
import re

from server.exceptions import LLMError
from server.llm import FALLBACK_EMOTION, VALID_EMOTIONS

_TAG = "EMOTION:"
_FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
_INVALID_BODY_PREFIXES = ("{", "[", _FENCE)
_UNDECIDED_BODY_PREFIXES = (_TAG, _FENCE)
_INLINE_SPACE = " \t\r"
_WORD_AFTER_TAG_RE = re.compile(r"\s*(\w+)")
# A tag mention in speech: **EMOTION**: and a fullwidth colon count; demotion: does not.
_TAG_MENTION_RE = re.compile(r"\bemotion\W{0,3}[:\uff1a]", re.IGNORECASE)

# Bounded, content-free message — never interpolate the raw candidate/model
# output here (it may contain arbitrary, unbounded model text).
_INVALID_PROTOCOL_MESSAGE = "Invalid streaming response protocol"


class StreamProtocolError(LLMError):
    """The model's streamed output broke the protocol (never carries model text)."""


@dataclass(frozen=True)
class Preamble:
    """The decided start of a streamed reply.

    Attributes:
        emotion: A member of ``VALID_EMOTIONS``: ``neutral`` when the model named an
            unknown one or sent no tag at all.
        remainder: The text after the tag, or the whole reply when it was rescued.
        rescued: True when the reply carried no tag and is spoken as plain text.
    """

    emotion: str
    remainder: str
    rescued: bool = False


def _is_proper_prefix(text: str, target: str) -> bool:
    """Whether ``text`` could still grow into ``target`` (ignoring letter case)."""
    return len(text) < len(target) and target.startswith(text.upper())


def _decide(text: str) -> Preamble | None:
    """Decide the preamble of ``text`` (already left-stripped) or ask for more input.

    Raises:
        StreamProtocolError: If the tag is present but can never become valid.
    """
    if not text or _is_proper_prefix(text, _TAG):
        return None
    if not text.upper().startswith(_TAG):
        return Preamble(FALLBACK_EMOTION, text, rescued=True)
    after_tag = text[len(_TAG) :]
    word = _WORD_AFTER_TAG_RE.match(after_tag)
    if word is None:
        if after_tag.strip():
            raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
        return None  # only whitespace after the colon so far: the word has not started
    rest = after_tag[word.end() :]
    line_rest = rest.lstrip(_INLINE_SPACE)
    if not line_rest:
        return None  # the word may still grow, or the newline may still come
    emotion = word.group(1).lower()
    if line_rest[0] == "\n":
        return Preamble(emotion if emotion in VALID_EMOTIONS else FALLBACK_EMOTION, line_rest[1:])
    if rest[0] not in _INLINE_SPACE or emotion not in VALID_EMOTIONS:
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
    return Preamble(emotion, line_rest)


def parse_streaming_emotion(buffer: str, *, final: bool = False) -> Preamble | None:
    """Decide how a streamed reply starts, as soon as the text allows it.

    A reply may open with ``EMOTION:<emotion>`` on its own line, with the same tag
    followed by the text on the same line (only for a known emotion), or with no tag at
    all (rescued as plain text with the ``neutral`` emotion). Leading whitespace is
    ignored. A tag that can never become valid is refused at once.

    Args:
        buffer: Text accumulated so far from generate_response_stream.
        final: Whether the stream has ended and no more text will arrive. When True,
            a buffer that is still undecided is a protocol violation rather than
            "keep waiting".

    Returns:
        A ``Preamble`` once the start is decided, or ``None`` while more input may
        still decide it (only possible when ``final=False``).

    Raises:
        StreamProtocolError: If the start can never be valid, or ``final`` is True and
            the buffer is still undecided.
    """
    preamble = _decide(buffer.lstrip())
    if preamble is None and final:
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
    return preamble


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
        _is_proper_prefix(stripped, prefix) for prefix in _UNDECIDED_BODY_PREFIXES
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
