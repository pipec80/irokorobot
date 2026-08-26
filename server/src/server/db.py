"""SQLite connection and migrations.

Single async connection (aiosqlite). WAL mode. sqlite-vec loaded once.
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite
import sqlite_vec

from server.exceptions import BrainMemoryError
from server.settings import settings

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


async def open_db() -> None:
    """Open the global SQLite connection.

    Idempotent. Loads sqlite-vec extension. Configures WAL mode.

    Raises:
        BrainMemoryError: If the DB file cannot be opened.
    """
    global _conn  # noqa: PLW0603
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
        await _conn.commit()
    except Exception as exc:
        raise BrainMemoryError("Failed to open SQLite") from exc


async def close_db() -> None:
    """Close the global connection. Idempotent."""
    global _conn  # noqa: PLW0603
    if _conn is None:
        return
    await _conn.close()
    _conn = None


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
