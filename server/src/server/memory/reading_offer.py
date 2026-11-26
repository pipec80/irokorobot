"""The paper read by the camera, waiting while its reader asks about it (ADR 0041, Plan 0090).

One in-process slot holds the last reading: the **whole** text (at most ``PAPER_MAX_CHARS``),
bound to the person identified on the reading turn. It follows the short-term session's rules
(ADR 0020): another identified person, ``WORKING_MEMORY_IDLE_SECONDS`` of silence since the last
paper turn, a new reading or a restart ends it; an unknown or ambiguous turn neither reads nor
extends it. Questions about the paper read it (``paper_for``), and «sí, guárdalo» keeps it
(``take``) while it lives, even after questions (ADR 0041 decision 6). A reading with no
identified speaker keeps **no text**, only that it happened (Plan 0088 B10: anyone on the network
could plant one for the owner's next «sí»). Keeping stores a ``normal`` document of format
``camera``; the frame was never kept. Nothing here logs a text, and the module does not import the
cognitive core (ADR 0031 decision 11): the route checks who speaks and names the note.
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
from server.settings import settings
from server.timestamps import instant_text

if TYPE_CHECKING:
    from datetime import datetime

__all__ = ["PAPER_MAX_CHARS", "READING_SLOT", "ReadingSlot", "keep_reading"]

#: The most characters of a paper held for questions (ADR 0041 decision 3).
PAPER_MAX_CHARS: Final = 4000


@dataclass
class _Reading:
    text: str | None = field(repr=False)
    speaker: int | None
    at: datetime
    # The turn number of the last paper turn (the reading, a paper question or a keep).
    paper_turn: int


class ReadingSlot:
    """The one paper waiting for questions and «sí, guárdalo»; its ``repr`` never shows the text."""

    def __init__(self) -> None:
        """Start empty."""
        self._reading: _Reading | None = None
        self._turns = 0

    def __repr__(self) -> str:
        """Say whether a paper waits, never what it says."""
        return f"ReadingSlot(open={self._reading is not None})"

    def begin_turn(self) -> None:
        """Count one voice turn; the keeper calls it once at the start of every turn."""
        self._turns += 1

    def offer(self, text: str, *, speaker: int | None, now: datetime) -> None:
        """Hold *text* for *speaker*, replacing any earlier paper; bound to nobody, keep no text."""
        kept = text[:PAPER_MAX_CHARS] if speaker is not None else None
        self._reading = _Reading(text=kept, speaker=speaker, at=now, paper_turn=self._turns)

    def is_open(self, now: datetime) -> bool:
        """Whether a reading waits and its silence has not run out (dropping it when it has)."""
        reading = self._reading
        if reading is None:
            return False
        if now - reading.at >= timedelta(seconds=settings.working_memory_idle_seconds):
            self._reading = None
            return False
        return True

    def observe(self, person_id: int | None, now: datetime) -> None:
        """Apply one turn's speaker: another identified person ends the paper; unknown leaves it.

        Args:
            person_id: The person identified on the turn, or ``None`` (unknown or ambiguous).
            now: The current time.
        """
        reading = self._reading
        if not self.is_open(now) or reading is None or person_id is None:
            return
        if reading.speaker != person_id:
            self._reading = None

    def paper_for(self, speaker: int, now: datetime) -> str | None:
        """Return the paper's text to its own speaker, marking a paper turn; else ``None``.

        A paper turn restarts the paper's silence and lets «sí, guárdalo» keep it on the next turn.
        """
        reading = self._reading
        if not self.is_open(now) or reading is None or reading.speaker != speaker:
            return None
        if reading.text is None:
            return None
        reading.at = now
        reading.paper_turn = self._turns
        return reading.text

    def take(self, speaker: int, now: datetime) -> str | None:
        """Give the paper to *speaker* to keep, when the talk is still about it.

        «Sí, guárdalo» keeps the paper only right after a paper turn (the reading or a question
        about it): once the talk moved on, the same words may answer a memory offer (Plan 0090
        review, Pipec 2026-11-26). The paper stays for more questions.

        Args:
            speaker: The person who said «sí, guárdalo».
            now: The current time.

        Returns:
            The whole text, when a paper bound to *speaker* waits and the turn before was about
            it; ``None`` otherwise (a reading bound to nobody is never given).
        """
        reading = self._reading
        if reading is None or reading.paper_turn < self._turns - 1:
            return None
        return self.paper_for(speaker, now)

    def clear(self) -> None:
        """Forget the paper."""
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
