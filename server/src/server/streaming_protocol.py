"""Pure guards for a plain-text streamed reply (ADR 0018).

The model answers in plain text and the emotion of the turn is decided apart from the reply,
so this module has no tag grammar: it only decides what may be spoken. ``llm_streaming.py``
owns prompt assembly and the Ollama transport; ``streaming_render.py`` owns the consume loop.
Kept dependency-free of I/O and logging on purpose, so every rule is unit testable in
isolation and none of them can leak raw model output into an exception message (that text
may contain anything the model produced).
"""

import re
import unicodedata

from server.exceptions import LLMError

_TAG = "EMOTION:"
_FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
_INVALID_BODY_PREFIXES = ("{", "[", _FENCE)
_UNDECIDED_BODY_PREFIXES = (_TAG, _FENCE)
# A tag mention in speech, after NFKC (so a fullwidth colon or fullwidth letters are plain):
# **EMOTION**: and _EMOTION_: count; demotion:, 1EMOTION: and emotion_name: do not. "_" is a
# word character, hence the explicit lookbehind and the [\W_] gap.
_TAG_MENTION_RE = re.compile(r"(?<![^\W_])emotion[\W_]{0,3}:", re.IGNORECASE)

# Bounded, content-free message — never interpolate the raw candidate/model
# output here (it may contain arbitrary, unbounded model text).
_INVALID_PROTOCOL_MESSAGE = "Invalid streaming response protocol"


class StreamProtocolError(LLMError):
    """The model's streamed output broke the protocol (never carries model text)."""


def _is_proper_prefix(text: str, target: str) -> bool:
    """Whether ``text`` could still grow into ``target`` (ignoring letter case)."""
    return len(text) < len(target) and target.startswith(text.upper())


def is_body_start_undecided(body: str) -> bool:
    """Whether the body so far is a proper prefix of a forbidden start (tag or fence).

    A body that begins ``E`` or a single backtick may still become ``EMOTION:`` or a
    code fence once the next token arrives, so it can be neither spoken nor judged yet.

    Args:
        body: The reply text received so far.

    Returns:
        True while more text is needed to know whether the body start is allowed.
    """
    stripped = body.lstrip()
    return bool(stripped) and any(
        _is_proper_prefix(stripped, prefix) for prefix in _UNDECIDED_BODY_PREFIXES
    )


def validate_streaming_body_start(body: str) -> None:
    """Reject structured metadata or a protocol tag before speech.

    Called on the start of the reply, before it is treated as speakable text. Guards
    against hybrid model output that mixes the classic JSON contract, or that writes a
    tag although none was asked for.

    Args:
        body: The reply text received so far (leading whitespace is ignored).

    Raises:
        StreamProtocolError: If ``body`` starts with ``{``, ``[``, a code fence, or an
            ``EMOTION:`` tag.
    """
    stripped = body.lstrip()
    if stripped.startswith(_INVALID_BODY_PREFIXES) or stripped.upper().startswith(_TAG):
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)


def reject_embedded_tag(text: str) -> None:
    """Reject speech that contains a protocol tag anywhere (ADR 0018).

    Args:
        text: One sentence, or the final unfinished tail, about to be spoken.

    Text is first normalised with NFKC and stripped of invisible format characters, so
    fullwidth letters or colons and zero-width characters do not hide a tag.

    Known limits (they need output no model is asked for): more than three symbols between
    ``EMOTION`` and the colon, and a sentence terminator between them (``EMOTION.:``, the
    sentence splitter cuts there before this check sees the colon) are not caught.

    Raises:
        StreamProtocolError: If ``text`` mentions ``EMOTION`` followed by a colon, in any
            letter case, with up to three symbols between them (``**EMOTION**:``,
            ``_EMOTION_:``).
    """
    if _TAG_MENTION_RE.search(_visible_text(text)):
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)


def _visible_text(text: str) -> str:
    """Return ``text`` in NFKC form without invisible format characters (Unicode Cf)."""
    normalised = unicodedata.normalize("NFKC", text)
    return "".join(char for char in normalised if unicodedata.category(char) != "Cf")
