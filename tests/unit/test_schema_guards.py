"""Static schema guards (Plan 0085, Part B): the tables migrations retired stay out of the code."""

import ast
from collections.abc import Mapping
from pathlib import Path
import re

import pytest

import server

_SERVER_ROOT = Path(server.__file__).resolve().parent
_REPOSITORY_ROOT = _SERVER_ROOT.parents[2]

# The eight tables migration 017 dropped (``memories`` stays: a trigger locks it, ADR 0027).
_DEAD_TABLES = (
    "outbox",
    "sensor_current",
    "sensor_readings",
    "sensor_aggregates_hourly",
    "facts",
    "legacy_fact_migration_v4",
    "embeddings_cache",
    "events",
)
# A table named after one of the SQL keywords that takes one. The keyword is upper case on
# purpose: this project writes its SQL that way, and prose ("inferred from facts") does not.
_DEAD_TABLE_SQL = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE|REFERENCES)\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
    rf"(?:{'|'.join(_DEAD_TABLES)})\b"
)


def _python_sources() -> dict[str, str]:
    """Return the text of every module under the server package and of every script."""
    roots = (_SERVER_ROOT, _REPOSITORY_ROOT / "scripts")
    return {
        path.relative_to(_REPOSITORY_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for root in roots
        for path in sorted(root.rglob("*.py"))
    }


def _dead_table_users(sources: Mapping[str, str]) -> list[str]:
    """``file:line`` of every string literal whose SQL names a table migration 017 dropped."""
    return [
        f"{name}:{node.lineno}"
        for name, text in sorted(sources.items())
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _DEAD_TABLE_SQL.search(node.value)
    ]


@pytest.mark.unit
def test_no_python_sql_names_a_dead_table() -> None:
    assert _dead_table_users(_python_sources()) == []


@pytest.mark.unit
def test_the_dead_table_guard_detects_a_violation() -> None:
    leak = {
        "server/memory/a.py": 'SQL = "SELECT predicate FROM facts WHERE entity_id = ?"\n',
        "server/memory/b.py": 'SQL = ("INSERT INTO "\n       "events (event_type) VALUES (?)")\n',
        "server/memory/c.py": 'SQL = "DROP TABLE IF EXISTS outbox"\n',
        "server/memory/d.py": 'SQL = f"DELETE FROM {x} JOIN embeddings_cache"\n',
        "scripts/e.py": 'SQL = "UPDATE sensor_current SET value = 1"\n',
        "scripts/f.py": 'SQL = "SELECT 1 FROM legacy_fact_migration_v4"\n',
        "scripts/g.py": 'SQL = "DELETE FROM sensor_readings"\nSQL2 = "FROM sensor_aggregates_hourly"\n',
        "server/memory/ok.py": (
            'SQL = "SELECT 1 FROM memories"\n'
            'OTHER = "SELECT 1 FROM literal_facts_v4"\n'
            'PROSE = "inferred from the facts, then events"\n'
        ),
    }

    assert _dead_table_users(leak) == [
        "scripts/e.py:1",
        "scripts/f.py:1",
        "scripts/g.py:1",
        "scripts/g.py:2",
        "server/memory/a.py:1",
        "server/memory/b.py:1",
        "server/memory/c.py:1",
        "server/memory/d.py:1",
    ]


# SQL functions newer than the runtime floor `db.SQLITE_FLOOR` (3.42): a statement using one would
# pass the start-up check and then fail on an older SQLite. `octet_length` arrived in 3.43; the
# byte length is `length(CAST(x AS BLOB))`, which every supported version has.
_ABOVE_THE_FLOOR = re.compile(r"\boctet_length\s*\(", re.IGNORECASE)


def _above_the_floor_users(sources: Mapping[str, str]) -> list[str]:
    """Return ``path:line`` for every line that calls an SQL function newer than the floor."""
    return sorted(
        f"{path}:{number}"
        for path, text in sources.items()
        for number, line in enumerate(text.splitlines(), start=1)
        if _ABOVE_THE_FLOOR.search(line)
    )


def _server_sql_and_python() -> dict[str, str]:
    """Return the text of every Python module and migration script of the server package."""
    return {
        path.relative_to(_REPOSITORY_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for pattern in ("*.py", "*.sql")
        for path in sorted(_SERVER_ROOT.rglob(pattern))
    }


@pytest.mark.unit
def test_no_sql_uses_a_function_newer_than_the_runtime_floor() -> None:
    assert _above_the_floor_users(_server_sql_and_python()) == []


@pytest.mark.unit
def test_the_runtime_floor_guard_detects_a_violation() -> None:
    leak = {
        "server/memory/a.py": 'SQL = "SELECT SUM(octet_length(heard)) FROM t"\n',
        "server/memory/b.sql": "SELECT OCTET_LENGTH (said) FROM t;\n",
        "server/memory/ok.py": 'SQL = "SELECT length(CAST(heard AS BLOB)) FROM t"\n',
    }

    assert _above_the_floor_users(leak) == ["server/memory/a.py:1", "server/memory/b.sql:1"]
