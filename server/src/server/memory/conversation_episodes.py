"""The diary: the only SQL on ``conversation_episodes`` (ADR 0027 decision 8, Plan 0076).

One episode per eligible record: a short summary of the owner's part, visibility ``personal``, a
sensitivity the model classified, the record's owner and expiry, and ``source_record_id`` so it
is deleted with its record and can be recomputed from it. The job only writes episodes (Plan 0076
D-2): candidates keep coming from the live path. Nothing here logs a text.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import logging
from typing import TYPE_CHECKING, Final

import aiosqlite
import httpx

from server import db
from server.exceptions import LLMError
from server.memory.candidate_limits import limiter
from server.memory.conversation_record import (
    EpisodeStatus,
    RecordView,
    count_failed_attempt,
    set_episode_status,
)
from server.memory.conversation_summary import (
    NOTHING_TO_REMEMBER,
    EpisodeDraft,
    EpisodeSensitivity,
    summarize_owner_part,
)
from server.settings import settings

if TYPE_CHECKING:
    from server.memory.conversation_types import RecordedTurn

logger = logging.getLogger(__name__)

__all__ = ["Episode", "EpisodeOutcome", "get_episode", "write_episode"]

type Summarizer = Callable[[httpx.AsyncClient, Sequence[RecordedTurn]], Awaitable[EpisodeDraft]]

#: Failed attempts after which a record is given up on.
MAX_EPISODE_ATTEMPTS: Final = 3


class EpisodeOutcome(StrEnum):
    """What one diary attempt did, in closed terms."""

    WRITTEN = "written"
    SKIPPED = "skipped"
    BUSY = "busy"
    RETRY = "retry"
    FAILED = "failed"
    GONE = "gone"


@dataclass(frozen=True)
class Episode:
    """One diary entry; its ``repr`` never shows the summary."""

    id: int
    source_record_id: int
    owner_entity_id: int
    sensitivity: EpisodeSensitivity
    summary: str = field(repr=False)
    created_at: str
    expires_at: str


async def get_episode(record_id: int) -> Episode | None:
    """Return the episode written from *record_id*, or ``None``."""
    cursor = await db.get_conn().execute(
        "SELECT id, source_record_id, owner_entity_id, sensitivity, summary, created_at, "
        "expires_at FROM conversation_episodes WHERE source_record_id = ?",
        (record_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return None
    sensitivity: EpisodeSensitivity = row[3]
    return Episode(
        id=int(row[0]),
        source_record_id=int(row[1]),
        owner_entity_id=int(row[2]),
        sensitivity=sensitivity,
        summary=str(row[4]),
        created_at=str(row[5]),
        expires_at=str(row[6]),
    )


def _logged(outcome: EpisodeOutcome, record_id: int) -> EpisodeOutcome:
    logger.info(
        "Conversation episode: %s",
        outcome.value,
        extra={"event": "conversation.episode", "outcome": outcome, "record_id": record_id},
    )
    return outcome


async def _failed(record_id: int) -> EpisodeOutcome:
    attempts = await count_failed_attempt(record_id)
    if attempts >= MAX_EPISODE_ATTEMPTS:
        await set_episode_status(record_id, EpisodeStatus.FAILED)
        return _logged(EpisodeOutcome.FAILED, record_id)
    return _logged(EpisodeOutcome.RETRY, record_id)


async def _summarize(
    record: RecordView, client: httpx.AsyncClient, summarize: Summarizer
) -> EpisodeDraft | EpisodeOutcome:
    """Take the extraction slot, call the model once and always release the slot."""
    if limiter.try_acquire() is not None:
        return EpisodeOutcome.BUSY
    try:
        return await summarize(client, record.turns)
    except (LLMError, httpx.HTTPError) as exc:
        logger.warning("Conversation episode: summary failed (%s)", type(exc).__name__)
        return EpisodeOutcome.RETRY
    finally:
        limiter.release()


async def write_episode(
    record: RecordView,
    *,
    client: httpx.AsyncClient,
    now: datetime,
    summarize: Summarizer = summarize_owner_part,
) -> EpisodeOutcome:
    """Write the diary entry of one closed record, or say why not.

    Args:
        record: A closed record still ``pending``.
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        now: The episode's creation time.
        summarize: The model seam; tests inject doubles.

    Returns:
        The closed outcome. ``RETRY`` and ``BUSY`` leave the record pending for the next tick.
    """
    record_id = record.summary.id
    if not record.summary.eligible or record.summary.expires_at is None:
        await set_episode_status(record_id, EpisodeStatus.SKIPPED)
        return _logged(EpisodeOutcome.SKIPPED, record_id)
    draft = await _summarize(record, client, summarize)
    if draft is EpisodeOutcome.BUSY:
        return _logged(EpisodeOutcome.BUSY, record_id)
    if not isinstance(draft, EpisodeDraft):
        return await _failed(record_id)
    if draft.summary == NOTHING_TO_REMEMBER:
        await set_episode_status(record_id, EpisodeStatus.SKIPPED)
        return _logged(EpisodeOutcome.SKIPPED, record_id)
    try:
        async with db.transaction() as conn:
            await conn.execute(
                "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, "
                "visibility, sensitivity, summary, model, created_at, expires_at) "
                "VALUES (?, ?, 'personal', ?, ?, ?, ?, ?)",
                (
                    record_id,
                    record.owner_entity_id,
                    draft.sensitivity,
                    draft.summary,
                    settings.consolidation_model or settings.ollama_model,
                    now.astimezone(UTC).isoformat(timespec="microseconds"),
                    record.summary.expires_at,
                ),
            )
            await set_episode_status(record_id, EpisodeStatus.DONE, conn=conn)
    except aiosqlite.IntegrityError:
        # The record was deleted (purge, `delete`, a revoked consent) while it was summarized.
        return _logged(EpisodeOutcome.GONE, record_id)
    return _logged(EpisodeOutcome.WRITTEN, record_id)
