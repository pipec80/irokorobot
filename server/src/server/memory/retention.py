"""Background retention jobs — periodic purge of time-bounded rows.

Runs once at startup, then every hour. All errors are logged and swallowed
so a failing purge never crashes the server.

Retention windows (all configurable via settings):
  - ``memory_candidates``:      past ``expires_at`` or out of offers (ADR 0021),
    whatever the candidate kill-switch says; the value is scrubbed and the
    write-ahead log truncated
  - ``conversation_records``:   past ``expires_at`` (1 year with the owner's verified voice,
    30 days without, both settings), then the oldest while over
    ``CONVERSATION_RECORD_MAX_TOTAL_MB`` counted in bytes of what was heard and said; episodes
    and turns go with their records (Plan 0076), whatever the record switch says
"""

from __future__ import annotations

import asyncio
import logging

from server import db
from server.cognition.clock import utc_now
from server.memory.candidates import checkpoint_after_scrub, run_housekeeping
from server.memory.conversation_record import purge_records

logger = logging.getLogger(__name__)

_task: asyncio.Task[None] | None = None


async def _reclaim_candidates() -> None:
    """Expire and scrub lapsed candidates, then truncate the log, apart from the other purges.

    The housekeeping has its own transaction so a failure of the conversation purge cannot roll
    it back (nor the reverse), and the checkpoint runs after the commit with its own error report:
    the scrub has already happened by then and must not be reported as a failed purge.
    """
    try:
        async with db.transaction() as conn:
            scrubbed = await run_housekeeping(conn, utc_now())
    except Exception as exc:
        logger.warning("Candidate housekeeping failed (%s)", type(exc).__name__)
        return
    try:
        await checkpoint_after_scrub(scrubbed)
    except Exception as exc:
        logger.warning("Candidate checkpoint failed after the scrub (%s)", type(exc).__name__)


async def _purge_conversations() -> None:
    """Purge expired and over-cap conversation records in their own transaction."""
    try:
        await purge_records(utc_now())
    except Exception as exc:
        logger.warning("Conversation purge failed (%s)", type(exc).__name__)


async def _run_once() -> None:
    """Run the conversation purge and the candidate reclaim, each in its own transaction.

    Every part catches and logs its own error by exception class (never the message) without
    re-raising, so the background loop continues running on the next tick.
    """
    await _purge_conversations()
    await _reclaim_candidates()


async def _loop() -> None:
    """Run ``_run_once`` at startup, then sleep 1 hour between runs."""
    await _run_once()
    while True:
        await asyncio.sleep(3600)
        await _run_once()


def start_background_job() -> None:
    """Schedule the retention loop as an asyncio Task.

    Idempotent — safe to call multiple times (only one task runs at a time).
    Must be called from within a running event loop (e.g. FastAPI lifespan).
    """
    global _task  # noqa: PLW0603
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(), name="retention_job")
        logger.info("Retention background job started")


async def stop_background_job() -> None:
    """Cancel and await the retention task.

    Idempotent. Called from the FastAPI lifespan shutdown handler.
    """
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
    logger.info("Retention background job stopped")
