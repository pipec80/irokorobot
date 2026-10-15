"""Closed vocabulary of memory candidates (ADR 0021): reasons, statuses, channels, shapes.

Pure data, no I/O. The preference gate and the classifier are pure functions over text and
return these types; the store and the writer persist them. Keeping the vocabulary in one
module lets the pure units stay free of any storage import.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CandidateChannel",
    "CandidateReason",
    "CandidateStatus",
    "GateMatch",
    "ProposedCandidate",
    "RawCandidate",
]


class CandidateReason(StrEnum):
    """Closed memory-layer reason: the only explanation any log line or counter may carry.

    These are separate from ADR 0016 §8's identity reasons. None of them carries a value, a
    person's name or an exception message.
    """

    GATE_NO_MATCH = "gate_no_match"
    NOT_A_TASTE = "not_a_taste"
    NEGATION_UNSUPPORTED = "negation_unsupported"
    SENSITIVE_TOPIC = "sensitive_topic"
    GATE_MISMATCH = "gate_mismatch"
    STRONG_UNREACHABLE = "strong_unreachable"
    NOT_GROUNDED = "not_grounded"
    BUSY = "busy"
    BUDGET = "budget"
    CAPACITY = "capacity"
    CONTRADICTION = "contradiction"
    DUPLICATE = "duplicate"
    EXPIRED = "expired"
    DENIED = "denied"


class CandidateStatus(StrEnum):
    """Lifecycle of one stored candidate; the value exists only in the first two."""

    PROPOSED = "proposed"
    OFFERED = "offered"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CandidateChannel(StrEnum):
    """The voice route a candidate came from; `/chat` and `/vision/respond` have none."""

    VOICE_CLASSIC = "voice_classic"
    VOICE_STREAM = "voice_stream"


@dataclass(frozen=True)
class GateMatch:
    """One taste the preference gate accepted, tied to its own trigger.

    Attributes:
        predicate: Canonical registry id the trigger declares (`likes`, `dislikes`, `prefers`).
        words: The folded words that follow the trigger inside its own part of the sentence.
            An object is grounded only here, so the model cannot move a thing to another polarity.
    """

    predicate: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class RawCandidate:
    """One triple as the extractor returned it: untrusted, to be classified.

    Attributes:
        predicate: Whatever predicate word the model chose.
        object: The thing liked, as the model copied it.
        topic: The topic the model placed it in.
    """

    predicate: str
    object: str
    topic: str


@dataclass(frozen=True)
class ProposedCandidate:
    """A candidate that passed the classifier, ready for the policy and the store.

    Attributes:
        predicate: Canonical registry id (`likes`, `dislikes` or `prefers`).
        value_text: The spoken phrase, article included.
        value_key: Comparison key: folded, without a leading article.
    """

    predicate: str
    value_text: str
    value_key: str
