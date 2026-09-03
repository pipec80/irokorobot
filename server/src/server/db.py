"""SQLite connection, migrations, and the runtime write-transaction owner.

Single async connection (aiosqlite). WAL mode. sqlite-vec loaded once.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite
import sqlite_vec

from server.exceptions import BrainMemoryError
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# Ordered migration scripts: (target_version, filename under memory/).
# run_migrations applies every script whose version exceeds PRAGMA user_version.
_MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, "schema.sql"),
    (2, "migration_002_meta.sql"),
    (3, "migration_003_faces.sql"),
    (4, "migration_004_relational_v4.sql"),
    (5, "migration_005_household_authorization.sql"),
    (6, "migration_006_owner_credentials.sql"),
    (7, "migration_007_biometric_consent.sql"),
)
_conn: aiosqlite.Connection | None = None

# Owns every runtime write transaction (Plan 0035, ADR 0011). Startup
# migrations run before any request can arrive and never touch this lock —
# `run_migrations` keeps its own commit-per-script discipline, unchanged.
#
# Created in `open_db()`, not eagerly at import time: `asyncio.Lock` binds to
# whichever event loop is running the first time it is actually awaited, and
# a lock built at import time can outlive that loop — e.g. two `open_db()`
# cycles in the same test session, each pytest-asyncio test function running
# its own loop. Owning the lock's lifecycle exactly like `_conn`'s keeps a
# `transaction()` call correct for whatever loop is running now.
_write_lock: asyncio.Lock | None = None


async def open_db() -> None:
    """Open the global SQLite connection.

    Idempotent. Loads sqlite-vec extension. Configures WAL mode.

    Raises:
        BrainMemoryError: If the DB file cannot be opened.
    """
    global _conn, _write_lock  # noqa: PLW0603
    if _conn is not None:
        return

    # Resolve to an absolute path: brain_db_path is CWD-relative by default,
    # and an ambiguous log line once produced two DBs in different folders.
    db_path: Path = settings.brain_db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Opening SQLite: %s", db_path)

    try:
        _conn = await aiosqlite.connect(db_path)
        await _conn.enable_load_extension(True)
        await _conn.load_extension(sqlite_vec.loadable_path())
        await _conn.enable_load_extension(False)
        await _conn.execute("PRAGMA journal_mode = WAL")
        await _conn.execute("PRAGMA synchronous = NORMAL")
        await _conn.execute("PRAGMA foreign_keys = ON")
        # Defends against contention from a process outside our own lock
        # (an offline script, an operator's sqlite3 shell) — it does not
        # replace `transaction()`'s coroutine-level ownership, which is what
        # actually serializes writes from within this process. Python's
        # sqlite3 already defaults `connect(timeout=5.0)` to the same 5000ms,
        # so this line changes no observed behavior; it exists so the value
        # is a decision made here, not an implicit stdlib default.
        await _conn.execute("PRAGMA busy_timeout = 5000")
        await _conn.commit()
    except Exception as exc:
        raise BrainMemoryError("Failed to open SQLite") from exc
    _write_lock = asyncio.Lock()


async def close_db() -> None:
    """Close the global connection. Idempotent."""
    global _conn, _write_lock  # noqa: PLW0603
    if _conn is None:
        return
    await _conn.close()
    _conn = None
    _write_lock = None


def get_conn() -> aiosqlite.Connection:
    """Return the open connection.

    Raises:
        BrainMemoryError: If open_db() has not been called.
    """
    if _conn is None:
        raise BrainMemoryError("DB not open — call open_db() first")
    return _conn


async def run_migrations() -> None:
    """Apply every pending migration script, in version order.

    Reads ``PRAGMA user_version`` and executes each ``_MIGRATIONS`` entry
    above it, bumping the version after each script. Idempotent — running
    on an up-to-date DB is a no-op.

    Raises:
        BrainMemoryError: If a migration file is missing or a script fails.
    """
    conn = get_conn()
    cur = await conn.execute("PRAGMA user_version")
    row = await cur.fetchone()
    current = int(row[0]) if row else 0
    await cur.close()

    for version, filename in _MIGRATIONS:
        if version <= current:
            continue
        script_path = Path(__file__).parent / "memory" / filename
        if not script_path.exists():
            raise BrainMemoryError(f"Migration file not found: {script_path}")
        logger.info("Applying migration %d (%s)", version, filename)
        sql = script_path.read_text(encoding="utf-8")
        try:
            await conn.executescript(sql)
            await conn.execute(f"PRAGMA user_version = {version}")
            await conn.commit()
        except Exception as exc:
            raise BrainMemoryError(f"Migration {version} ({filename}) failed") from exc

    logger.info("Schema up-to-date (version %d)", _MIGRATIONS[-1][0])


@asynccontextmanager
async def transaction() -> AsyncIterator[aiosqlite.Connection]:
    """Own one complete runtime write transaction under the module lock.

    Serializes writes at the coroutine level so a multi-`await` transaction
    can no longer interleave with another one — the gap the process-global
    connection left open (ADR 0011). Begins with ``BEGIN IMMEDIATE``, commits
    only on normal exit, and rolls back on any ``BaseException`` — including
    ``asyncio.CancelledError``, which only ``except BaseException`` catches —
    before re-raising it unchanged.

    Not reentrant: the lock has no notion of "the same caller", so calling
    ``transaction()`` again from inside an already-open one on the same task
    hangs forever waiting for itself. A composite write accepts the yielded
    connection and issues further statements directly — the pattern
    ``relational_v4.py``'s ``manage_transaction`` flag already uses, one
    layer up.

    Yields:
        The single open connection, mid-transaction. Callers issue further
        statements on it directly; no nested transaction is needed or safe.

    Raises:
        BaseException: Whatever the caller's body raised, after rollback —
            this primitive never swallows a failure.
    """
    conn = get_conn()
    if _write_lock is None:
        raise BrainMemoryError("DB not open — call open_db() first")
    async with _write_lock:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            await conn.rollback()
            raise
        else:
            await conn.commit()
