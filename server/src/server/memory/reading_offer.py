"""The read text waiting for «sí, guárdalo», and keeping it as a document (Plan 0088 D-17).

One in-process slot: the last reading, bound to the speaker identified on the reading turn (or to
nobody: holding a paper, the camera may not see the face), for 60 seconds, the offer window of ADR
0021. A new reading replaces it, the next turn takes or empties it, a restart forgets it. Keeping
it stores a ``normal`` document of format ``camera``; the frame was never kept. Nothing here logs
a text, and the module does not import the cognitive core (ADR 0031 decision 11): the route
checks who speaks and names the note.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import hashlib
from typing import TYPE_CHECKING, Final

from server import db
from server.memory.document_extract import ExtractedText
from server.memory.document_sections import SECTION_MAX_CHARS, cut_sections
from server.memory.document_store import DocumentExistsError, NewSource, insert_source
from server.timestamps import instant_text

if TYPE_CHECKING:
    from datetime import datetime

__all__ = ["READING_SLOT", "ReadingSlot", "keep_reading"]

#: How long a reading waits for «sí, guárdalo» (ADR 0021's offer window).
OFFER_WINDOW: Final = timedelta(seconds=60)


@dataclass
class _Reading:
    text: str = field(repr=False)
    speaker: int | None
    at: datetime


class ReadingSlot:
    """One reading waiting to be kept; its ``repr`` never shows the text."""

    def __init__(self) -> None:
        """Start empty."""
        self._reading: _Reading | None = None

    def __repr__(self) -> str:
        """Say whether a reading waits, never what it says."""
        return f"ReadingSlot(open={self._reading is not None})"

    def offer(self, text: str, *, speaker: int | None, now: datetime) -> None:
        """Hold *text* for *speaker* (or for nobody), replacing any earlier reading."""
        self._reading = _Reading(text=text, speaker=speaker, at=now)

    def is_open(self, now: datetime) -> bool:
        """Whether a reading waits and its window has not passed."""
        return self._reading is not None and now - self._reading.at <= OFFER_WINDOW

    def take(self, speaker: int, now: datetime) -> str | None:
        """Give the reading to *speaker* and empty the slot.

        Args:
            speaker: The person who said «sí, guárdalo».
            now: The current time.

        Returns:
            The text, when it waits within its window and is bound to *speaker* or to nobody;
            ``None`` otherwise. The slot is empty afterwards either way.
        """
        reading, self._reading = self._reading, None
        if reading is None or now - reading.at > OFFER_WINDOW:
            return None
        if reading.speaker is not None and reading.speaker != speaker:
            return None
        return reading.text

    def clear(self) -> None:
        """Forget the reading."""
        self._reading = None


#: The server's one slot.
READING_SLOT: Final = ReadingSlot()


async def keep_reading(owner_entity_id: int, text: str, *, title: str, now: datetime) -> int:
    """Store a kept reading as the owner's ``normal`` document (format ``camera``).

    Args:
        owner_entity_id: The owner, identified by the face on the keeping turn (the route checks).
        text: The text read aloud on the turn before.
        title: «Nota del {día}: {primeras palabras}», named by the route.
        now: When it was kept.

    Returns:
        The source id; the existing one when the same text was already kept.
    """
    sections = cut_sections(ExtractedText(format="txt", pages=(text,)), max_chars=SECTION_MAX_CHARS)
    source = NewSource(
        owner_entity_id=owner_entity_id,
        title=title,
        file_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        format="camera",
        level="normal",
        channel="voice_camera",
        loaded_at=instant_text(now),
        loaded_by_entity_id=owner_entity_id,
    )
    try:
        async with db.transaction() as conn:
            return await insert_source(conn, source=source, sections=sections)
    except DocumentExistsError:
        cursor = await db.get_conn().execute(
            "SELECT id FROM document_sources WHERE owner_entity_id = ? AND file_sha256 = ?",
            (owner_entity_id, source.file_sha256),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return 0 if row is None else int(row[0])
