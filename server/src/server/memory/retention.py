"""Background retention jobs — periodic purge of time-bounded rows.

Runs once at startup, then every hour. All errors are logged and swallowed
so a failing purge never crashes the server.

Retention windows (all configurable via settings):
  - ``sensor_readings``:        ``settings.sensor_retention_hours`` (default 72 h)
  - ``sensor_aggregates_hourly``:  1 year (hardcoded — aggregates are small)
  - ``embeddings_cache``:       30 days (hardcoded)
  - ``outbox`` (synced only):   7 days (hardcoded)
  - ``memory_candidates``:      past ``expires_at`` or out of offers (ADR 0021),
    whatever the candidate kill-switch says; the value is scrubbed and the
    write-ahead log truncated
"""

from __future__ import annotations

import asyncio
import logging

from server import db
from server.cognition.clock import utc_now
from server.memory.candidates import checkpoint_after_scrub, run_housekeeping
from server.settings import settings

logger = logging.getLogger(__name__)

_task: asyncio.Task[None] | None = None

_SQL_SENSOR_READINGS = "DELETE FROM sensor_readings WHERE created_at < datetime('now', ?)"
_SQL_SENSOR_AGGREGATES = (
    "DELETE FROM sensor_aggregates_hourly WHERE hour_bucket < datetime('now', '-365 days')"
)
_SQL_EMBEDDINGS_CACHE = (
    "DELETE FROM embeddings_cache WHERE created_at < datetime('now', '-30 days')"
)
_SQL_OUTBOX = (
    "DELETE FROM outbox WHERE synced_at IS NOT NULL AND synced_at < datetime('now', '-7 days')"
)


async def _purge_time_bounded_rows() -> None:
    """Delete the expired sensor, embedding-cache and outbox rows in one transaction.

    Raises:
        Exception: Whatever the database raised; ``_run_once`` reports it by class.
    """
    sensor_threshold = f"-{settings.sensor_retention_hours} hours"
    async with db.transaction() as conn:
        await conn.execute(_SQL_SENSOR_READINGS, (sensor_threshold,))
        await conn.execute(_SQL_SENSOR_AGGREGATES)
        await conn.execute(_SQL_EMBEDDINGS_CACHE)
        await conn.execute(_SQL_OUTBOX)
    logger.info("Retention purge complete (sensor_threshold=%s)", sensor_threshold)


async def _reclaim_candidates() -> None:
    """Expire and scrub lapsed candidates, then truncate the log, apart from the other purges.

    The housekeeping has its own transaction so a failure of the sensor purge cannot roll it
    back (nor the reverse), and the checkpoint runs after the commit with its own error report:
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


async def _run_once() -> None:
    """Run the time-bounded purge and the candidate reclaim, each in its own transaction.

    Errors are caught and logged by exception class (never the message) without re-raising so
    the background loop continues running on the next tick.
    """
    try:
        await _purge_time_bounded_rows()
    except Exception as exc:
        logger.warning("Retention purge failed (%s)", type(exc).__name__)
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
