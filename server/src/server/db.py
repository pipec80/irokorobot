"""SQLite connection, migrations, and the runtime write-transaction owner.

Single async connection (aiosqlite). WAL mode. sqlite-vec loaded once.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

import aiosqlite
import sqlite_vec

from server.exceptions import BrainMemoryError
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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
    (8, "migration_008_voice_consent.sql"),
    (9, "migration_009_memory_candidates.sql"),
    (10, "migration_010_asserter_and_channel.sql"),
    (11, "migration_011_contacts_and_commissioning.sql"),
    (12, "migration_012_admin_audit.sql"),
    (13, "migration_013_conversation_record.sql"),
    (14, "migration_014_recall_units.sql"),
    (15, "migration_015_occurred_interval.sql"),
    (16, "migration_016_pending_topics.sql"),
)
_conn: aiosqlite.Connection | None = None

# The runtime is checked, not upgraded (Plan 0085, D-1). The floor is what the FTS5
# `secure-delete` index this database already uses needs; sqlite-vec is pinned to one version.
SQLITE_FLOOR: Final = (3, 42, 0)
_SQLITE_TOO_OLD: Final = f"SQLite runtime older than {'.'.join(map(str, SQLITE_FLOOR))}"
SQLITE_VEC_VERSION: Final = "v0.1.9"

# SQLite's advice for a long-lived connection: analyze on open what changed.
_OPTIMIZE_ON_OPEN = "PRAGMA optimize=0x10002"

# How long a statement waits for a lock held by another connection. A checkpoint or an optimize
# waits less: giving up only postpones the scrub or the statistics.
_BUSY_TIMEOUT_MS = 5000
_CHECKPOINT_BUSY_MS = 500

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


@dataclass(frozen=True)
class RuntimeReport:
    """The versions of the SQLite runtime a connection actually runs on."""

    sqlite_version: tuple[int, int, int]
    fts5: bool
    vec_version: str


async def _read_runtime(conn: aiosqlite.Connection) -> RuntimeReport:
    """Read the runtime versions from the connection.

    ``vec_version()`` answers only if the sqlite-vec extension loaded, which is what proves
    that extensions are loadable.
    """
    cursor = await conn.execute(
        "SELECT sqlite_version(), sqlite_compileoption_used('ENABLE_FTS5'), vec_version()"
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        raise BrainMemoryError("SQLite runtime unreadable")
    major, minor, patch = (int(part) for part in str(row[0]).split(".")[:3])
    return RuntimeReport((major, minor, patch), bool(row[1]), str(row[2]))


def _require_supported(report: RuntimeReport) -> None:
    """Judge a report; raise a closed ``BrainMemoryError`` for the first failed check."""
    if report.sqlite_version < SQLITE_FLOOR:
        raise BrainMemoryError(_SQLITE_TOO_OLD)
    if not report.fts5:
        raise BrainMemoryError("SQLite built without FTS5")
    if report.vec_version != SQLITE_VEC_VERSION:
        raise BrainMemoryError("sqlite-vec version mismatch")


async def check_runtime(conn: aiosqlite.Connection) -> RuntimeReport:
    """Read the runtime of ``conn`` and refuse one the storage layer does not support.

    Returns:
        The report, so the caller can log the versions.

    Raises:
        BrainMemoryError: SQLite below 3.42, built without FTS5, or a sqlite-vec version other
            than the pinned one (closed messages, one per failed check).
    """
    report = await _read_runtime(conn)
    _require_supported(report)
    return report


async def _abandon_start() -> None:
    """Close a half-opened connection and reset the module state; never raises.

    A close that itself fails is logged by class and swallowed, so the caller's own error is the
    one that propagates.
    """
    global _conn, _write_lock
    conn, _conn, _write_lock = _conn, None, None
    if conn is None:
        return
    try:
        await conn.close()
    except (aiosqlite.Error, ValueError) as exc:
        logger.warning("SQLite connection not closed after a failed start (%s)", type(exc).__name__)


async def _optimize(conn: aiosqlite.Connection, pragma: str, when: str) -> None:
    """Run an ``optimize`` pragma with a short lock wait; never raises.

    It may write statistics, so a lock held by another process (an operator's shell, the seed
    importer's own lock check) only postpones it; waiting the full busy timeout for that would
    delay the open or the close. A failure is logged by class and swallowed.
    """
    try:
        await conn.execute(f"PRAGMA busy_timeout = {_CHECKPOINT_BUSY_MS}")
        await conn.execute(pragma)
    except (aiosqlite.Error, ValueError) as exc:
        logger.warning("PRAGMA optimize skipped on %s (%s)", when, type(exc).__name__)
    finally:
        await _restore_busy_timeout(conn)


async def open_db() -> None:
    """Open the global SQLite connection.

    Idempotent. Loads the sqlite-vec extension, checks the runtime, configures WAL mode. Any
    failure after the connection is made closes it and resets the module state, so the next
    call starts clean.

    Raises:
        BrainMemoryError: If the DB file cannot be opened or the runtime is not supported.
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
        report = await check_runtime(_conn)
        await _conn.execute("PRAGMA journal_mode = WAL")
        await _conn.execute("PRAGMA synchronous = NORMAL")
        await _conn.execute("PRAGMA foreign_keys = ON")
        # ON, not FAST: a scrubbed candidate value must be overwritten with zeros in the file
        # and in every page the write-ahead log re-writes (ADR 0021 decision 6). The cost is a
        # little extra I/O on deletes, and this database is small and local.
        await _conn.execute("PRAGMA secure_delete = ON")
        # Defends against contention from a process outside our own lock
        # (an offline script, an operator's sqlite3 shell) — it does not
        # replace `transaction()`'s coroutine-level ownership, which is what
        # actually serializes writes from within this process. Python's
        # sqlite3 already defaults `connect(timeout=5.0)` to the same 5000ms,
        # so this line changes no observed behavior; it exists so the value
        # is a decision made here, not an implicit stdlib default.
        await _conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        await _conn.commit()
        await _optimize(_conn, _OPTIMIZE_ON_OPEN, "open")
    except BaseException as exc:
        # BaseException on purpose, like `transaction()`: a cancellation is not an `Exception`
        # and would otherwise leave a half-set connection that makes the next `open_db()` return
        # early. Nothing is swallowed: `_abandon_start()` cleans up and the error is re-raised.
        await _abandon_start()
        if isinstance(exc, BrainMemoryError) or not isinstance(exc, Exception):
            raise
        raise BrainMemoryError("Failed to open SQLite") from exc
    logger.info(
        "SQLite runtime: sqlite %d.%d.%d, FTS5 %s, sqlite-vec %s",
        *report.sqlite_version,
        "on" if report.fts5 else "off",
        report.vec_version,
    )
    _write_lock = asyncio.Lock()


async def checkpoint_wal() -> bool:
    """Fold the write-ahead log into the database file and truncate it, if SQLite lets it.

    A scrub overwrites the page it changed, but the write-ahead log keeps the earlier frames
    until a checkpoint copies them out and the log is reset. Callers that erase a protected
    value call this after the transaction that erased it commits (ADR 0021 decision 6).

    The module's write lock is held so no transaction of this connection is open (a checkpoint
    inside one is refused). The checkpoint never raises for a lock or a connection that is no
    longer usable: another connection reading the file (an operator's shell) or a cursor left
    open on this one only postpones it, and the caller must not fail an operation that already
    committed because of it.

    Returns:
        ``True`` when the log was truncated; ``False`` when it was busy or locked (try again at
        the next store entry or retention run).

    Raises:
        BrainMemoryError: If the database is not open.
    """
    conn = get_conn()
    if _write_lock is None:
        raise BrainMemoryError("DB not open — call open_db() first")
    async with _write_lock:
        try:
            await conn.execute(f"PRAGMA busy_timeout = {_CHECKPOINT_BUSY_MS}")
            cursor = await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            row = await cursor.fetchone()
            await cursor.close()
        except (aiosqlite.Error, ValueError) as exc:
            # ValueError: aiosqlite raises it for a connection that is no longer active.
            logger.warning("WAL checkpoint postponed (%s)", type(exc).__name__)
            return False
        finally:
            await _restore_busy_timeout(conn)
    # (busy, log frames, checkpointed frames): busy is 1 when a reader pinned the log.
    if row is None or int(row[0]) != 0:
        logger.warning("WAL checkpoint postponed (busy)")
        return False
    return True


async def _restore_busy_timeout(conn: aiosqlite.Connection) -> None:
    """Put the normal busy timeout back after a checkpoint or an optimize; never raises.

    A restore that fails (the connection closed under us) must not replace the caller's own
    outcome, so it is logged by class and swallowed.
    """
    try:
        await conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    except (aiosqlite.Error, ValueError) as exc:
        logger.warning(
            "Busy timeout not restored after a checkpoint or optimize (%s)", type(exc).__name__
        )


async def close_db() -> None:
    """Close the global connection, after ``PRAGMA optimize``. Idempotent.

    A failing optimize (a lock held by another connection, a connection no longer usable) is
    logged by class and never keeps the connection open (Plan 0078).
    """
    global _conn, _write_lock  # noqa: PLW0603
    if _conn is None:
        return
    await _optimize(_conn, "PRAGMA optimize", "close")
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


def latest_schema_version() -> int:
    """Return the schema version the last migration brings a database to.

    A tool that must not migrate (the seed importer, Plan 0071) compares it with the database's
    ``PRAGMA user_version`` and refuses a database that is behind.
    """
    return _MIGRATIONS[-1][0]


def is_open() -> bool:
    """Return whether the database connection is currently open (Plan 0040).

    Side-effect-free — never opens a connection. Used by `GET /ready` to
    report readiness without raising the way `get_conn()` does.
    """
    return _conn is not None


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
            # A script that opened its own transaction and failed leaves it open: close it, so
            # nothing it half-applied survives and the next start retries it from the same version.
            await conn.rollback()
            raise BrainMemoryError(f"Migration {version} ({filename}) failed") from exc

    logger.info("Schema up-to-date (version %d)", _MIGRATIONS[-1][0])


async def _rollback_after_failed_commit(conn: aiosqlite.Connection) -> None:
    """Roll back after a COMMIT that raised; never raises.

    A rollback that itself fails must not hide the commit's error, so it is logged by class and
    swallowed.
    """
    try:
        await conn.rollback()
    except (aiosqlite.Error, ValueError) as exc:
        # ValueError: aiosqlite raises it for a connection that is no longer active.
        logger.warning("Rollback after a failed COMMIT failed (%s)", type(exc).__name__)


@asynccontextmanager
async def transaction() -> AsyncGenerator[aiosqlite.Connection]:
    """Own one complete runtime write transaction under the module lock.

    Serializes writes at the coroutine level so a multi-`await` transaction
    can no longer interleave with another one — the gap the process-global
    connection left open (ADR 0011). Begins with ``BEGIN IMMEDIATE`` (inside the
    guarded block, so a cancellation during the BEGIN rolls back too), commits
    only on normal exit, and rolls back on any ``BaseException`` — including
    ``asyncio.CancelledError``, which only ``except BaseException`` catches —
    before re-raising it unchanged. A rollback with no open transaction is a no-op.

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
        try:
            # Inside the try: a cancellation that lands while BEGIN is pending still finds the
            # statement queued on the connection thread, and the rollback below closes it.
            await conn.execute("BEGIN IMMEDIATE")
            yield conn
        except BaseException:
            await conn.rollback()
            raise
        else:
            try:
                await conn.commit()
            except BaseException:
                # A COMMIT that raises (disk full, I/O error) leaves the shared connection inside
                # the transaction: close it so the next BEGIN IMMEDIATE works. The commit's own
                # error is the one that propagates, unchanged.
                await _rollback_after_failed_commit(conn)
                raise
