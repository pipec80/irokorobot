"""The conversation background loop: close idle segments, write the diary, fill recall vectors.

Runs once at start-up (closing a segment a stopped server left open) and then every
``CONVERSATION_JOB_INTERVAL_S``. The diary is written only with both switches on and **only
while no conversation is open**, at most one episode per tick, so the local model never competes
with a live conversation (Plan 0076 D-9). With ``RECALL_ENABLED``, under the same rule, it then
embeds the few recall units that have no vector yet (Plan 0078). With the pending topics on, it
deletes the expired ones and names at most one (Plan 0084). Every error is logged by class and
swallowed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
import logging
import time
from typing import TYPE_CHECKING, Final

import httpx

from server.cognition.clock import utc_now
from server.exceptions import LLMError
from server.memory.conversation_episodes import write_episode
from server.memory.conversation_record import (
    EpisodeStatus,
    close_idle_records,
    has_open_record,
    next_pending_record,
    set_episode_status,
)
from server.memory.document_index import backfill_sections
from server.memory.household_time import household_day
from server.memory.pending_naming import name_topic
from server.memory.pending_store import (
    count_naming_failure,
    delete_expired,
    drop,
    next_unnamed,
    pending_topics_on,
    set_topic,
)
from server.memory.recall_index import backfill_vectors
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

logger = logging.getLogger(__name__)

__all__ = ["run_once", "start_background_job", "stop_background_job"]

_task: asyncio.Task[None] | None = None
# A topic whose naming failed this many times is deleted, so one broken row never blocks the rest.
_MAX_NAMING_ATTEMPTS: Final = 3


class NamingOutcome(StrEnum):
    """What one naming step did, in closed terms (Plan 0084 D-15)."""

    NAMED = "named"
    UNNAMED_DROPPED = "unnamed_dropped"
    MODEL_FAILED = "model_failed"


@dataclass(frozen=True)
class _Done:
    """What one piece of the tick did: the row it worked on and its closed outcome."""

    row_id: int | None
    outcome: str


async def _write_one_episode(client: httpx.AsyncClient, now: datetime) -> _Done | None:
    """Skip pending records that are not eligible, then write at most one episode.

    Returns:
        The record attempted and the diary's outcome, or ``None`` when no record was waiting.
    """
    while (record := await next_pending_record()) is not None:
        if not record.summary.eligible:
            await set_episode_status(record.summary.id, EpisodeStatus.SKIPPED)
            continue
        outcome = await write_episode(record, client=client, now=now)
        return _Done(record.summary.id, outcome.value)
    return None


def _text_model() -> str:
    """The model the diary summary and the pending naming call."""
    return settings.consolidation_model or settings.ollama_model


async def _timed(piece: str, model: str, work: Callable[[], Awaitable[_Done | None]]) -> None:
    """Run one piece of the tick and log what it did and cost (Plan 0089 D-13).

    A piece with nothing to do logs nothing. An error or a cancellation is logged, then
    re-raised, so the tick behaves as before.

    Args:
        piece: The closed name of the work (``episode``, ``recall_vectors``, ...).
        model: The Ollama model the piece calls.
        work: The piece; it returns its row and closed outcome, or ``None`` when idle.
    """
    started = time.perf_counter()
    try:
        done = await work()
    except asyncio.CancelledError:
        _log_job(piece, model, started, _Done(None, "cancelled"), "CancelledError")
        raise
    except Exception as exc:
        _log_job(piece, model, started, _Done(None, "failed"), type(exc).__name__)
        raise
    if done is not None:
        _log_job(piece, model, started, done, None)


def _log_job(piece: str, model: str, started: float, done: _Done, error_type: str | None) -> None:
    """Log one piece of the tick: its row id, outcome, model and time, never a text."""
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "Conversation job: piece=%s outcome=%s row_id=%s model=%s elapsed_ms=%d error=%s",
        piece,
        done.outcome,
        done.row_id,
        model,
        elapsed_ms,
        error_type,
        extra={
            "event": "conversation.job",
            "piece": piece,
            "outcome": done.outcome,
            "row_id": done.row_id,
            "model": model,
            "elapsed_ms": elapsed_ms,
            "error_type": error_type,
        },
    )


async def _vectors(client: httpx.AsyncClient) -> _Done | None:
    embedded = await backfill_vectors(client)
    return _Done(None, "embedded") if embedded else None


async def _sections(client: httpx.AsyncClient) -> _Done | None:
    embedded = await backfill_sections(client)
    return _Done(None, "embedded") if embedded else None


async def run_once(client: httpx.AsyncClient, now: datetime) -> None:
    """Run one tick; never raises.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the summary.
        now: The current time.
    """
    try:
        await close_idle_records(now)
        if not settings.conversation_record_enabled or await has_open_record():
            return
        if settings.conversation_episodes_enabled:
            await _timed("episode", _text_model(), lambda: _write_one_episode(client, now))
        if settings.recall_enabled:
            # The recall vectors the live path could not compute (ADR 0028 decision 2).
            await _timed("recall_vectors", settings.embedding_model, lambda: _vectors(client))
        if settings.documents_enabled:
            # The document sections `iroko-admin docs add` left without a vector (Plan 0088 D-16).
            await _timed("document_sections", settings.embedding_model, lambda: _sections(client))
        if settings.memory_enabled:
            # Rows kept while the switch was on expire even after it is turned off.
            await _expire_pending_topics(now)
        if pending_topics_on():
            await _timed("pending_naming", _text_model(), lambda: _name_one_pending_topic(client))
    except Exception as exc:  # background loop: the next tick tries again
        logger.warning("Conversation job failed (%s)", type(exc).__name__)


async def _expire_pending_topics(now: datetime) -> None:
    """Delete the topics more than two days past their due day (Plan 0084 D-5); log a count."""
    expired = await delete_expired(today=household_day(now))
    if expired:
        logger.info(
            "Pending topics expired: %d",
            expired,
            extra={"event": "pending.expired", "count": expired},
        )


async def _name_one_pending_topic(client: httpx.AsyncClient) -> _Done | None:
    """Name at most one unnamed topic with the local model (Plan 0084 D-6).

    An answer that is not the owner's words deletes the topic. A model failure keeps it for a
    later tick, behind the topics not yet tried, and the third failure deletes it. Logs carry a
    closed outcome, the row id and an exception class, never a text.

    Returns:
        The topic tried and its naming outcome, or ``None`` when none was waiting.
    """
    unnamed = await next_unnamed()
    if unnamed is None:
        return None
    topic_id, heard = unnamed
    try:
        topic = await name_topic(client, heard)
    except (httpx.HTTPError, TimeoutError, LLMError) as exc:
        if await count_naming_failure(topic_id) < _MAX_NAMING_ATTEMPTS:
            _log_named(NamingOutcome.MODEL_FAILED, topic_id, error_type=type(exc).__name__)
            return _Done(topic_id, NamingOutcome.MODEL_FAILED.value)
        await drop(topic_id)
        _log_named(NamingOutcome.UNNAMED_DROPPED, topic_id, error_type=type(exc).__name__)
        return _Done(topic_id, NamingOutcome.UNNAMED_DROPPED.value)
    if topic is None:
        await drop(topic_id)
        _log_named(NamingOutcome.UNNAMED_DROPPED, topic_id)
        return _Done(topic_id, NamingOutcome.UNNAMED_DROPPED.value)
    if await set_topic(topic_id, topic):
        _log_named(NamingOutcome.NAMED, topic_id)
        return _Done(topic_id, NamingOutcome.NAMED.value)
    return _Done(topic_id, "unchanged")


def _log_named(outcome: NamingOutcome, topic_id: int, *, error_type: str | None = None) -> None:
    """Log one naming step: a closed outcome and the row id, never the topic."""
    logger.log(
        # A model failure is a warning; a name kept or an answer that is not the owner's is not.
        logging.INFO if error_type is None else logging.WARNING,
        "Pending topic naming: %s",
        outcome.value,
        extra={
            "event": "pending.named",
            "outcome": outcome.value,
            "topic_id": topic_id,
            "error_type": error_type,
        },
    )


async def _loop(client: httpx.AsyncClient) -> None:
    await run_once(client, utc_now())
    while True:
        await asyncio.sleep(settings.conversation_job_interval_s)
        await run_once(client, utc_now())


def start_background_job(client: httpx.AsyncClient) -> None:
    """Schedule the loop as an asyncio task; idempotent.

    Args:
        client: The lifespan's HTTP client.
    """
    global _task  # noqa: PLW0603
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(client), name="conversation_job")
        logger.info("Conversation background job started")


async def stop_background_job() -> None:
    """Cancel and await the loop; idempotent."""
    global _task  # noqa: PLW0603
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    finally:
        _task = None
    logger.info("Conversation background job stopped")
