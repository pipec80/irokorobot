"""Closed, content-free classification of a streamed reply (Plan 0057).

The output is one member of a fixed enum, never a slice of the reply: a report can
count shapes without ever holding, logging or storing model text.

Plan 0059 stopped asking the model for the tag, so the server no longer parses one. The
shapes keep Plan 0057's strict reading (a well-formed ``EMOTION:<x>`` line), frozen here,
so their names do not move: they now name what a model wrote although it was not asked
to, and no longer say whether the protocol speaks the reply.
"""

from __future__ import annotations

import enum
import re

_TAG_PREFIX = "EMOTION:"
_TAG_LINE_RE = re.compile(r"^EMOTION:\s*\w+\s*\n", re.IGNORECASE)
_WRAPPERS = "<[({\"'«*_`"
_JSON_STARTS = ("{", "[")
_FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
_LABEL_RE = re.compile(r"^\W*(?:emoci[oó]n|emotion|mood|sentimiento|estado)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"\w+")


class FailureShape(enum.StrEnum):
    """Why a streamed reply is, or is not, speakable. Closed: never carries text."""

    VALID = "valid"
    EMPTY = "empty"
    NO_TAG = "no_tag"
    JSON_START = "json_start"
    FENCE_START = "fence_start"
    LEADING_WHITESPACE = "leading_whitespace"
    TEXT_BEFORE_TAG = "text_before_tag"
    OTHER_LABEL = "other_label"
    TAG_WRAPPED = "tag_wrapped"
    TAG_SAME_LINE = "tag_same_line"
    TAG_PUNCTUATION = "tag_punctuation"
    TAG_TRUNCATED = "tag_truncated"
    TAG_ONLY = "tag_only"
    BODY_JSON = "body_json"
    BODY_FENCE = "body_fence"
    SECOND_TAG = "second_tag"
    OTHER = "other"


def _after_tag_line(text: str) -> str | None:
    """Return the text after a well-formed ``EMOTION:<x>`` line, or ``None`` if there is none."""
    match = _TAG_LINE_RE.match(text)
    return None if match is None else text[match.end() :]


def _body_shape(body: str) -> FailureShape:
    """Classify what follows a well-formed ``EMOTION:<x>`` line."""
    stripped = body.lstrip()
    if not stripped:
        return FailureShape.TAG_ONLY
    if stripped.startswith(_JSON_STARTS):
        return FailureShape.BODY_JSON
    if stripped.startswith(_FENCE):
        return FailureShape.BODY_FENCE
    if stripped.upper().startswith(_TAG_PREFIX):
        return FailureShape.SECOND_TAG
    return FailureShape.VALID


def _malformed_tag_shape(text: str) -> FailureShape:
    """Classify a reply that starts with ``EMOTION:`` but is not a well-formed line."""
    rest = text[len(_TAG_PREFIX) :].lstrip()
    if not rest:
        return FailureShape.TAG_TRUNCATED
    if rest[0] in _WRAPPERS:
        return FailureShape.TAG_WRAPPED
    word = _WORD_RE.match(rest)
    if word is None:
        return FailureShape.OTHER
    tail = rest[word.end() :]
    if not tail.strip():
        return FailureShape.TAG_TRUNCATED
    if tail[0] in " \t":
        return FailureShape.TAG_SAME_LINE
    return FailureShape.TAG_PUNCTUATION


def _tag_prefixed_shape(text: str, stripped: str) -> FailureShape:
    """Classify a reply whose first non-blank text is ``EMOTION:`` but is not a valid line."""
    if stripped != text and _after_tag_line(stripped) is not None:
        return FailureShape.LEADING_WHITESPACE
    return _malformed_tag_shape(stripped)


def _unparsed_shape(text: str) -> FailureShape:
    """Classify a reply that does not open with a well-formed ``EMOTION:<x>`` line."""
    stripped = text.lstrip()
    if stripped.startswith(_JSON_STARTS):
        return FailureShape.JSON_START
    if stripped.startswith(_FENCE):
        return FailureShape.FENCE_START
    if stripped.upper().startswith(_TAG_PREFIX):
        return _tag_prefixed_shape(text, stripped)
    if _TAG_PREFIX in text.upper():
        return FailureShape.TEXT_BEFORE_TAG
    if _LABEL_RE.match(stripped):
        return FailureShape.OTHER_LABEL
    return FailureShape.NO_TAG


def classify_failure_shape(text: str) -> FailureShape:
    """Name the shape of one streamed reply, or the part of it production read.

    Args:
        text: The reply as received (may be partial when production stopped reading).

    Returns:
        A ``FailureShape``. ``VALID`` means the text, taken whole, passes the protocol.
    """
    if not text.strip():
        return FailureShape.EMPTY
    body = _after_tag_line(text)
    if body is not None:
        return _body_shape(body)
    return _unparsed_shape(text)
