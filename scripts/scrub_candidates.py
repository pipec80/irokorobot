"""Void every live memory candidate in a database file before the file is copied (ADR 0021).

``just reset-db`` copies the live database to ``data/backups`` before deleting it. A live
candidate holds a value the owner said about themselves, so the copy must not carry one: this
script voids them in place, overwrites the freed bytes (``secure_delete``) and truncates the
write-ahead log, and only then does the caller copy.

It talks to the file through the standard library's ``sqlite3`` (no ``aiosqlite``, no
extension, no model) and must run with the server stopped. It prints counts, never a value.

Usage:
    uv run python scripts/scrub_candidates.py
    uv run python scripts/scrub_candidates.py path/to/omnibot.db

Exit status: 0 when no live candidate remains (including a database that has no candidate
table yet, or no file at all); 1 when the database could not be scrubbed or its log could not
be truncated (another process holds it) — the caller must not copy it.
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import sys

from server.memory.candidates import VOID_LIVE_SQL, iso_utc

_DEFAULT_DB = Path("data/omnibot.db")
_LOCK_WAIT_S = 1.0


def scrub(db_path: Path) -> int:
    """Void the live candidates of *db_path* and truncate its write-ahead log.

    Args:
        db_path: A SQLite database file of this project. The server must be stopped.

    Returns:
        How many live candidates were voided (0 when there is no file or no candidate table).

    Raises:
        sqlite3.Error: If the file cannot be opened or updated, or (``OperationalError``) the
            write-ahead log could not be truncated because another connection holds it.
    """
    if not db_path.exists():
        return 0
    connection = sqlite3.connect(db_path, timeout=_LOCK_WAIT_S)
    try:
        connection.execute("PRAGMA secure_delete = ON")
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory_candidates'"
        ).fetchone()
        if table is None:
            return 0
        cursor = connection.execute(VOID_LIVE_SQL, (iso_utc(datetime.now(UTC)),))
        voided = cursor.rowcount
        connection.commit()
        busy = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if busy is None or busy[0] != 0:
            # A reader pins the log: a copy of the main file could still carry a stale page.
            raise sqlite3.OperationalError("the write-ahead log could not be truncated")
    finally:
        connection.close()
    return voided


def main(argv: list[str] | None = None) -> int:
    """Run the scrub from the command line.

    Args:
        argv: Arguments after the program name; ``None`` reads ``sys.argv``.

    Returns:
        The process exit status.
    """
    parser = argparse.ArgumentParser(description="Void live memory candidates in a database file.")
    parser.add_argument("db_path", nargs="?", type=Path, default=_DEFAULT_DB)
    args = parser.parse_args(argv)
    try:
        voided = scrub(args.db_path)
    except sqlite3.Error as exc:
        sys.stderr.write(f"Could not scrub {args.db_path}: {type(exc).__name__}\n")
        return 1
    sys.stdout.write(f"Voided {voided} live candidate(s) in {args.db_path}.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
