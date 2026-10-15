"""Count what the memory-candidate dialogue left in a database, never a value (Plan 0063).

The hardware acceptance of ADR 0021 records outcomes only. This script answers the questions
the acceptance asks of the database — how many candidates are in each status, which policy
steps were audited and with which decision, and how many personal tastes are confirmed facts —
without printing a value, a name or a transcript. It opens the file read-only, so the server may
keep running.

Usage:
    uv run python scripts/inspect_candidates.py
    uv run python scripts/inspect_candidates.py path/to/omnibot.db

Exit status: 0 with a report; 1 when the file does not exist or cannot be read.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys

_DEFAULT_DB = Path("data/omnibot.db")
_STATUSES: tuple[str, ...] = ("proposed", "offered", "confirmed", "rejected", "expired")
_ACTIONS: tuple[str, ...] = (
    "propose_personal_memory",
    "read_personal_conversation_memory",
    "confirm_personal_memory",
)
_DECISIONS: tuple[str, ...] = ("allowed", "denied", "requires_confirmation")
_TASTES: tuple[str, ...] = ("likes", "dislikes", "prefers")


@dataclass(frozen=True)
class Inspection:
    """What the dialogue left in one database: counts only.

    Attributes:
        candidates: Candidates per status.
        audit: Audit rows per (memory action, decision).
        confirmed_facts: Active personal-taste facts that carry who confirmed them.
    """

    candidates: dict[str, int]
    audit: dict[tuple[str, str], int]
    confirmed_facts: int


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in rows}


def inspect(db_path: Path) -> Inspection:
    """Count candidates, memory audit rows and confirmed tastes in *db_path*, read-only.

    Args:
        db_path: A SQLite database file of this project; it is never written.

    Returns:
        The counts. A database that predates a table reports zeros for it.

    Raises:
        sqlite3.Error: If the file cannot be opened or read.
    """
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        tables = _tables(connection)
        candidates: dict[str, int] = dict.fromkeys(_STATUSES, 0)
        if "memory_candidates" in tables:
            for status, count in connection.execute(
                "SELECT status, COUNT(*) FROM memory_candidates GROUP BY status"
            ):
                candidates[str(status)] = int(count)
        audit = {(action, decision): 0 for action in _ACTIONS for decision in _DECISIONS}
        if "authorization_audit_events" in tables:
            placeholders = ", ".join("?" for _ in _ACTIONS)
            for action, decision, count in connection.execute(
                "SELECT action, decision, COUNT(*) FROM authorization_audit_events "  # noqa: S608
                f"WHERE action IN ({placeholders}) GROUP BY action, decision",
                _ACTIONS,
            ):
                audit[(str(action), str(decision))] = int(count)
        confirmed = 0
        if "literal_facts_v4" in tables:
            placeholders = ", ".join("?" for _ in _TASTES)
            row = connection.execute(
                "SELECT COUNT(*) FROM literal_facts_v4 WHERE lifecycle = 'active' "  # noqa: S608
                f"AND confirmed_by_entity_id IS NOT NULL AND predicate IN ({placeholders})",
                _TASTES,
            ).fetchone()
            confirmed = int(row[0]) if row is not None else 0
    finally:
        connection.close()
    return Inspection(candidates=candidates, audit=audit, confirmed_facts=confirmed)


def render(inspection: Inspection) -> str:
    """Return the report as plain lines: counts, statuses and action names only.

    Args:
        inspection: What ``inspect`` counted.

    Returns:
        The printable report.
    """
    statuses = " ".join(f"{status}={count}" for status, count in inspection.candidates.items())
    lines = [f"candidates: {statuses}"]
    for action in _ACTIONS:
        decisions = " ".join(
            f"{decision}={inspection.audit[(action, decision)]}" for decision in _DECISIONS
        )
        lines.append(f"audit {action}: {decisions}")
    lines.append(f"confirmed facts: {inspection.confirmed_facts}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Print the report for one database file.

    Args:
        argv: Arguments after the program name; ``None`` reads ``sys.argv``.

    Returns:
        The process exit status.
    """
    parser = argparse.ArgumentParser(description="Count the memory-candidate dialogue's traces.")
    parser.add_argument("db_path", nargs="?", type=Path, default=_DEFAULT_DB)
    args = parser.parse_args(argv)
    if not args.db_path.exists():
        sys.stderr.write(f"No database at {args.db_path}.\n")
        return 1
    try:
        inspection = inspect(args.db_path)
    except sqlite3.Error as exc:
        sys.stderr.write(f"Could not read {args.db_path}: {type(exc).__name__}\n")
        return 1
    sys.stdout.write(render(inspection))
    return 0


if __name__ == "__main__":
    sys.exit(main())
