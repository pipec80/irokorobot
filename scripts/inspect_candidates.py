"""Count what the memory-candidate dialogue left in a database, never a value (Plan 0063).

The hardware acceptance of ADR 0021 records outcomes only. This script answers the questions
the acceptance asks of the database — how many candidates are in each status, which policy
steps were audited and with which decision, and how many personal tastes are confirmed facts —
without printing a value, a name or a transcript. It opens the file read-only, so the server may
keep running.

Usage:
    uv run python scripts/inspect_candidates.py
    uv run python scripts/inspect_candidates.py path/to/omnibot.db

Without a path it reads the database the server uses (``BRAIN_DB_PATH``). A table the file does
not have is named in the report, so a row of zeros is never mistaken for "nothing happened".

Exit status: 0 with a report; 1 when the file does not exist or cannot be read.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys

from server.cognition.models import AuthorizationAction
from server.memory.candidate_types import CandidateStatus
from server.settings import settings

_STATUSES: tuple[str, ...] = tuple(status.value for status in CandidateStatus)
_ACTIONS: tuple[str, ...] = (
    AuthorizationAction.PROPOSE_PERSONAL_MEMORY.value,
    AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY.value,
    AuthorizationAction.CONFIRM_PERSONAL_MEMORY.value,
)
_TABLES: tuple[str, ...] = ("memory_candidates", "authorization_audit_events", "literal_facts_v4")
_DECISIONS: tuple[str, ...] = ("allowed", "denied", "requires_confirmation")
_TASTES: tuple[str, ...] = ("likes", "dislikes", "prefers")


@dataclass(frozen=True)
class Inspection:
    """What the dialogue left in one database: counts only.

    Attributes:
        candidates: Candidates per status.
        audit: Audit rows per (memory action, decision).
        confirmed_facts: Active personal-taste facts that carry who confirmed them.
        missing_tables: Tables the file does not have; their counts are zero by absence.
    """

    candidates: dict[str, int]
    audit: dict[tuple[str, str], int]
    confirmed_facts: int
    missing_tables: tuple[str, ...] = ()


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in rows}


def inspect(db_path: Path) -> Inspection:
    """Count candidates, memory audit rows and confirmed tastes in *db_path*, read-only.

    Args:
        db_path: A SQLite database file of this project; it is never written.

    Returns:
        The counts. A database that predates a table reports zeros for it and names it in
        ``missing_tables``.

    Raises:
        sqlite3.Error: If the file cannot be opened or read.
    """
    # as_uri() percent-encodes the path, so a "#", a "?" or a "%" in it cannot change the URI.
    connection = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = _tables(connection)
        missing = tuple(name for name in _TABLES if name not in tables)
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
    return Inspection(
        candidates=candidates, audit=audit, confirmed_facts=confirmed, missing_tables=missing
    )


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
    if inspection.missing_tables:
        lines.append(f"missing tables: {' '.join(inspection.missing_tables)}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Print the report for one database file.

    Args:
        argv: Arguments after the program name; ``None`` reads ``sys.argv``.

    Returns:
        The process exit status.
    """
    parser = argparse.ArgumentParser(description="Count the memory-candidate dialogue's traces.")
    parser.add_argument("db_path", nargs="?", type=Path, default=settings.brain_db_path)
    args = parser.parse_args(argv)
    if not args.db_path.exists():
        sys.stderr.write(f"No database at {args.db_path}.\n")
        return 1
    try:
        inspection = inspect(args.db_path)
    except sqlite3.OperationalError as exc:
        # The queries select counts, never a value: sqlite's own reason is safe and actionable.
        sys.stderr.write(f"Could not read {args.db_path}: {exc}\n")
        return 1
    except sqlite3.Error as exc:
        sys.stderr.write(f"Could not read {args.db_path}: {type(exc).__name__}\n")
        return 1
    sys.stdout.write(render(inspection))
    return 0


if __name__ == "__main__":
    sys.exit(main())
