"""The vocabulary every writer of the household memory shares (Plan 0070, ADR 0024 decision 6).

The canonical writer, the contacts writer and the commissioning record all name the channel a
write arrived through and the closed reasons a write is refused for. They live here so that no
writer imports another just to speak the same words. A refusal carries the reason, what it
was about and the channel, and never a value.
"""

from __future__ import annotations

from enum import StrEnum
import logging

from server.exceptions import WriteRefusedError

__all__ = [
    "IMPORT_CHANNELS",
    "VOICE_CHANNELS",
    "ConflictPolicy",
    "WriteChannel",
    "WriteRefusal",
    "refusal_error",
]

logger = logging.getLogger(__name__)

_REFUSED_EVENT = "memory.canonical_write_refused"


class WriteChannel(StrEnum):
    """Closed list of the channels a fact can arrive through (Plan 0065 D-6, Plan 0070).

    The first two are the values a memory candidate already carries; ``import_file`` is a load
    made by the owner alone and ``import_assisted`` an interview with an interviewer (ADR 0024
    decision 6). ``admin_local`` is an edit made through the local command-line administration
    after the commissioning closed (ADR 0025 decision 4); it is **not** an import channel. A
    perceptual channel is added when that source exists.
    """

    VOICE_CLASSIC = "voice_classic"
    VOICE_STREAM = "voice_stream"
    IMPORT_FILE = "import_file"
    IMPORT_ASSISTED = "import_assisted"
    ADMIN_LOCAL = "admin_local"


IMPORT_CHANNELS = frozenset({WriteChannel.IMPORT_FILE, WriteChannel.IMPORT_ASSISTED})
VOICE_CHANNELS = frozenset({WriteChannel.VOICE_CLASSIC, WriteChannel.VOICE_STREAM})


class WriteRefusal(StrEnum):
    """Closed reasons a write is refused for."""

    NOT_HOUSEHOLD_MEMBER = "not_household_member"
    OWNER_ONLY_PREDICATE = "owner_only_predicate"
    CLASSIFICATION_CONFLICT = "classification_conflict"
    VALUE_CONFLICT = "value_conflict"
    ORDER_TAKEN = "order_taken"
    NOT_A_PERSON = "not_a_person"
    CONTACT_IS_OWNER = "contact_is_owner"
    ROLE_CONFLICT = "role_conflict"


class ConflictPolicy(StrEnum):
    """What a write does when it meets a different value that is already active."""

    SUPERSEDE = "supersede"
    REFUSE = "refuse"


def refusal_error(reason: WriteRefusal, *, what: str, channel: WriteChannel) -> WriteRefusedError:
    """Log a refusal (the reason, what it was about and the channel only) and build the error.

    Args:
        reason: The closed reason.
        what: A predicate id or a table name; never a value, a name or a phone.
        channel: The channel the write arrived through.

    Returns:
        The error to raise; its message is the reason alone.
    """
    logger.info(
        "Canonical write refused: %s",
        reason.value,
        extra={
            "event": _REFUSED_EVENT,
            "reason": reason.value,
            "predicate": what,
            "channel": channel.value,
        },
    )
    return WriteRefusedError(reason.value)
