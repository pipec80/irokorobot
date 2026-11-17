"""The exchanges of the conversation record and the owner's part of them (ADR 0027, Plan 0076).

Pure: no I/O. One recorded exchange is what the person said (``heard``, as the speech-to-text
wrote it), what the robot answered (``said``) and the voice verdict of that turn. Only the
``VERIFIED`` exchanges are the owner's part, and only the owner's part may feed memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import json
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

__all__ = [
    "HEARD_MAX_CHARS",
    "SAID_MAX_CHARS",
    "RecordedTurn",
    "TurnVerdict",
    "make_turn",
    "owner_part",
]

#: Caps of one exchange, so a single entry always fits in a segment (Plan 0076 D-6).
HEARD_MAX_CHARS: Final = 2000
SAID_MAX_CHARS: Final = 4000


class TurnVerdict(StrEnum):
    """Whose turn this was, as far as memory is concerned (Plan 0076 D-1)."""

    VERIFIED = "verified"  # the owner's face and the owner's voice on this clip
    NOT_VERIFIED = (
        "not_verified"  # the owner's face; the voice did not verify or was not assessable
    )
    NOT_OWNER = "not_owner"  # no face, an unknown face, a token or another person
    NOT_CHECKED = "not_checked"  # a deterministic reply; no speaker was resolved


@dataclass(frozen=True)
class RecordedTurn:
    """One exchange of the record; its ``repr`` never shows the text.

    Attributes:
        at: When the turn was taken (UTC, timezone-aware).
        heard: What the person said, as transcribed.
        said: What the robot answered.
        voice: The turn's verdict.
        correlation_id: The turn's correlation id; it joins the exchange to the candidates and
            audit rows of the same turn.
    """

    at: datetime
    heard: str = field(repr=False)
    said: str = field(repr=False)
    voice: TurnVerdict
    correlation_id: UUID

    def to_json(self) -> str:
        """Serialize the exchange as one JSON object (non-ASCII kept as is)."""
        return json.dumps(
            {
                "at": self.at.astimezone(UTC).isoformat(timespec="microseconds"),
                "heard": self.heard,
                "said": self.said,
                "voice": self.voice.value,
                "cid": str(self.correlation_id),
            },
            ensure_ascii=False,
        )


def make_turn(
    heard: str, said: str, *, voice: TurnVerdict, correlation_id: UUID, at: datetime
) -> RecordedTurn:
    """Build an exchange with its texts stripped and cut at their caps.

    Args:
        heard: What the person said.
        said: What the robot answered.
        voice: The turn's verdict.
        correlation_id: The turn's correlation id.
        at: When the turn was taken (UTC, timezone-aware).

    Returns:
        The bounded exchange.
    """
    return RecordedTurn(
        at=at,
        heard=heard.strip()[:HEARD_MAX_CHARS],
        said=said.strip()[:SAID_MAX_CHARS],
        voice=voice,
        correlation_id=correlation_id,
    )


def owner_part(turns: Sequence[RecordedTurn]) -> tuple[RecordedTurn, ...]:
    """Return only the owner's verified exchanges, oldest first (ADR 0027 decision 2).

    Args:
        turns: Every exchange of a record, in any order.

    Returns:
        The ``VERIFIED`` exchanges sorted by time; nothing else ever reaches memory.
    """
    return tuple(
        sorted((turn for turn in turns if turn.voice is TurnVerdict.VERIFIED), key=_moment)
    )


def _moment(turn: RecordedTurn) -> datetime:
    return turn.at
