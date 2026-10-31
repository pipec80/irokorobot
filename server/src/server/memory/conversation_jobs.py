"""The conversation background loop: close idle segments, then write the diary (Plan 0076).

Runs once at start-up (closing a segment a stopped server left open) and then every
``CONVERSATION_JOB_INTERVAL_S``. The diary is written only with both switches on and **only
while no conversation is open**, at most one episode per tick, so the local model never competes
with a live conversation (Plan 0076 D-9). Every error is logged by class and swallowed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from server.cognition.clock import utc_now
from server.memory.conversation_episodes import write_episode
from server.memory.conversation_record import (
    EpisodeStatus,
    close_idle_records,
    has_open_record,
    next_pending_record,
    set_episode_status,
)
from server.settings import settings

if TYPE_CHECKING:
    from datetime import datetime

    import httpx

logger = logging.getLogger(__name__)

__all__ = ["run_once", "start_background_job", "stop_background_job"]

_task: asyncio.Task[None] | None = None


async def _write_one_episode(client: httpx.AsyncClient, now: datetime) -> None:
    """Skip pending records that are not eligible, then write at most one episode."""
    while (record := await next_pending_record()) is not None:
        if not record.summary.eligible:
            await set_episode_status(record.summary.id, EpisodeStatus.SKIPPED)
            continue
        await write_episode(record, client=client, now=now)
        return


async def run_once(client: httpx.AsyncClient, now: datetime) -> None:
    """Run one tick; never raises.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the summary.
        now: The current time.
    """
    try:
        await close_idle_records(now)
        if not (settings.conversation_record_enabled and settings.conversation_episodes_enabled):
            return
        if await has_open_record():
            return
        await _write_one_episode(client, now)
    except Exception as exc:  # background loop: the next tick tries again
        logger.warning("Conversation job failed (%s)", type(exc).__name__)


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
