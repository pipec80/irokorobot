"""Schema guards (Plan 0085, Part B): retired tables stay out of the code; the live schema is
keyed, indexed, ruled and documented (D-11)."""

# ruff: noqa: S608 - the schema reader quotes names that come from the schema itself; no input reaches the SQL.

import ast
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import re

import pytest
from server.settings import settings

import server
from server import db

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


# --- the live schema: keys, indexes, rules and the data dictionary (Plan 0085 D-11) ---------------

_DICTIONARY = _REPOSITORY_ROOT / "docs" / "architecture" / "data-dictionary.md"
# The tables this plan created or rebuilt: each foreign key states its ON DELETE rule on purpose.
_TOUCHED_TABLES = frozenset(
    {
        "conversation_turns",
        "recall_units",
        "memory_candidates",
        "pending_topics",
        "face_profiles",
        "voice_profiles",
    }
)
_DOMAINS = frozenset({"memory", "identity", "administration"})
_REQUIRED_FIELDS = ("Purpose", "Owner module", "Domain", "Classification", "Retention")
_REQUIRED_HEADINGS = ("Time format", "Deliberate denormalizations", "Not tuned yet", "Naming")


@dataclass(frozen=True)
class _ForeignKey:
    columns: tuple[str, ...]
    on_delete: str


@dataclass(frozen=True)
class _Index:
    columns: tuple[str, ...]
    partial: bool


@dataclass(frozen=True)
class _Table:
    name: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[_ForeignKey, ...] = ()
    indexes: tuple[_Index, ...] = ()
    virtual: bool = False


def _without_primary_key(tables: Sequence[_Table]) -> list[str]:
    """Ordinary tables with no primary key (a virtual table is keyed by its rowid)."""
    return sorted(t.name for t in tables if not t.virtual and not t.primary_key)


def _unindexed_foreign_keys(tables: Sequence[_Table]) -> list[str]:
    """``table(columns)`` of every foreign key no full index starts with.

    A partial index does not count: it covers only some rows, and the cascade scans the rest.
    """
    return sorted(
        f"{t.name}({', '.join(fk.columns)})"
        for t in tables
        for fk in t.foreign_keys
        if not any(
            not index.partial and index.columns[: len(fk.columns)] == fk.columns
            for index in t.indexes
        )
    )


def _foreign_keys_without_rule(tables: Sequence[_Table], touched: frozenset[str]) -> list[str]:
    """``table(columns)`` of every foreign key of a touched table left on SQLite's default."""
    return sorted(
        f"{t.name}({', '.join(fk.columns)})"
        for t in tables
        if t.name in touched
        for fk in t.foreign_keys
        if fk.on_delete == "NO ACTION"
    )


def _tables_section(text: str) -> str:
    """The text between ``## Tables`` and the next ``## `` heading (empty when there is none)."""
    if "\n## Tables\n" not in text:
        return ""
    return text.split("\n## Tables\n", 1)[1].split("\n## ", 1)[0]


def _dictionary_tables(text: str) -> dict[str, dict[str, str]]:
    """Parse the dictionary: per ``### table`` its ``- **Field:** value`` lines and its columns.

    The columns are the first cell of each row of the table whose header starts ``| Column``;
    the result maps a table to its fields plus the key ``columns`` (comma-joined, sorted).
    """
    parsed: dict[str, dict[str, str]] = {}
    for section in re.split(r"^### ", _tables_section(text), flags=re.MULTILINE)[1:]:
        name, _, rest = section.partition("\n")
        fields = dict(re.findall(r"^- \*\*([^*:]+):\*\* (.+)$", rest, flags=re.MULTILINE))
        columns: set[str] = set()
        in_columns = False
        for line in rest.splitlines():
            if line.startswith("| Column"):
                in_columns = True
            elif in_columns and not line.startswith("|"):
                in_columns = False
            elif in_columns and (cell := re.match(r"\| `([^`]+)` \|", line)):
                columns.add(cell.group(1))
        fields["columns"] = ",".join(sorted(columns))
        parsed[name.strip()] = fields
    return parsed


def _dictionary_gaps(tables: Sequence[_Table], text: str) -> list[str]:
    """What the dictionary lacks or invents, in both directions, per table and per column."""
    documented = _dictionary_tables(text)
    gaps = []
    for table in tables:
        if table.name not in documented:
            gaps.append(f"table {table.name} is not documented")
            continue
        listed = set(filter(None, documented[table.name]["columns"].split(",")))
        gaps += [
            f"column {table.name}.{c} is not documented" for c in table.columns if c not in listed
        ]
        gaps += [
            f"column {table.name}.{c} is documented but absent"
            for c in sorted(listed - set(table.columns))
        ]
    known = {t.name for t in tables}
    gaps += [f"table {name} is documented but absent" for name in sorted(set(documented) - known)]
    return sorted(gaps)


def _incomplete_sections(text: str) -> list[str]:
    """``table: field`` for each required field a table section lacks or fills wrongly."""
    problems = []
    for name, fields in _dictionary_tables(text).items():
        problems += [f"{name}: {f}" for f in _REQUIRED_FIELDS if not fields.get(f, "").strip()]
        if fields.get("Domain", "").strip() not in _DOMAINS:
            problems.append(f"{name}: Domain is not one of {sorted(_DOMAINS)}")
        module = fields.get("Owner module", "").strip("` ")
        if module and not (_SERVER_ROOT / module).is_file():
            problems.append(f"{name}: Owner module {module} does not exist")
    return sorted(problems)


_SAMPLE = """# Data dictionary

## Tables

### alpha

- **Purpose:** a canary table
- **Owner module:** `memory/meta.py`
- **Domain:** memory
- **Classification:** system
- **Retention:** kept

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key |
| `ghost` | TEXT | documented, not in the schema |

## Time format
"""


@pytest.mark.unit
def test_a_table_without_a_primary_key_is_found() -> None:
    tables = [
        _Table("keyed", ("id",), primary_key=("id",)),
        _Table("loose", ("a", "b")),
        _Table("virt", ("body",), virtual=True),
    ]

    assert _without_primary_key(tables) == ["loose"]


@pytest.mark.unit
def test_a_foreign_key_needs_a_full_index_that_starts_with_it() -> None:
    fk = (_ForeignKey(("parent_id",), "CASCADE"),)
    tables = [
        _Table("none", ("id", "parent_id"), ("id",), fk),
        _Table("partial", ("id", "parent_id"), ("id",), fk, (_Index(("parent_id",), True),)),
        _Table(
            "second", ("id", "x", "parent_id"), ("id",), fk, (_Index(("x", "parent_id"), False),)
        ),
        _Table("full", ("id", "parent_id"), ("id",), fk, (_Index(("parent_id",), False),)),
        _Table(
            "prefix", ("id", "parent_id", "x"), ("id",), fk, (_Index(("parent_id", "x"), False),)
        ),
    ]

    assert _unindexed_foreign_keys(tables) == [
        "none(parent_id)",
        "partial(parent_id)",
        "second(parent_id)",
    ]


@pytest.mark.unit
def test_a_touched_table_must_state_its_delete_rule() -> None:
    tables = [
        _Table("touched", ("id", "p"), ("id",), (_ForeignKey(("p",), "NO ACTION"),)),
        _Table("ruled", ("id", "p"), ("id",), (_ForeignKey(("p",), "RESTRICT"),)),
        _Table("untouched", ("id", "p"), ("id",), (_ForeignKey(("p",), "NO ACTION"),)),
    ]

    assert _foreign_keys_without_rule(tables, frozenset({"touched", "ruled"})) == ["touched(p)"]


@pytest.mark.unit
def test_the_dictionary_guard_finds_a_missing_and_an_invented_table_and_column() -> None:
    tables = [_Table("alpha", ("id", "label")), _Table("beta", ("id",))]

    assert _dictionary_gaps(tables, _SAMPLE) == [
        "column alpha.ghost is documented but absent",
        "column alpha.label is not documented",
        "table beta is not documented",
    ]
    assert _dictionary_gaps([_Table("alpha", ("id", "ghost"))], _SAMPLE) == []
    assert _dictionary_gaps([], _SAMPLE) == ["table alpha is documented but absent"]


@pytest.mark.unit
def test_the_section_guard_finds_a_missing_field_a_wrong_domain_and_a_missing_module() -> None:
    broken = (
        _SAMPLE.replace("- **Domain:** memory", "- **Domain:** kitchen")
        .replace("- **Retention:** kept\n", "")
        .replace("memory/meta.py", "memory/absent.py")
    )

    assert _incomplete_sections(_SAMPLE) == []
    assert _incomplete_sections(broken) == [
        f"alpha: Domain is not one of {sorted(_DOMAINS)}",
        "alpha: Owner module memory/absent.py does not exist",
        "alpha: Retention",
    ]


async def _rows(sql: str) -> list[tuple[object, ...]]:
    cursor = await db.get_conn().execute(sql)
    found = [tuple(row) for row in await cursor.fetchall()]
    await cursor.close()
    return found


async def _foreign_keys_of(name: str) -> tuple[_ForeignKey, ...]:
    ids = sorted(
        {int(str(r[0])) for r in await _rows(f'SELECT id FROM pragma_foreign_key_list("{name}")')}
    )
    found = []
    for fk_id in ids:
        rows = await _rows(
            f'SELECT "from", on_delete FROM pragma_foreign_key_list("{name}") '
            f"WHERE id = {fk_id} ORDER BY seq"
        )
        found.append(_ForeignKey(tuple(str(r[0]) for r in rows), str(rows[0][1])))
    return tuple(found)


async def _indexes_of(name: str) -> tuple[_Index, ...]:
    found = []
    for index_name, partial in await _rows(
        f'SELECT name, "partial" FROM pragma_index_list("{name}")'
    ):
        columns = await _rows(f'SELECT name FROM pragma_index_info("{index_name}") ORDER BY seqno')
        found.append(_Index(tuple(str(c[0]) for c in columns), bool(partial)))
    return tuple(found)


async def _live_tables() -> list[_Table]:
    """Read the live ordinary and virtual tables of the open database (shadow tables left out)."""
    listed = await _rows(
        "SELECT name, sql LIKE 'CREATE VIRTUAL%' FROM sqlite_master "
        "WHERE type = 'table' AND substr(name, 1, 7) <> 'sqlite_' ORDER BY name"
    )
    virtual = {str(name) for name, is_virtual in listed if is_virtual}
    tables = []
    for name_value, is_virtual in listed:
        name = str(name_value)
        if not is_virtual and any(name.startswith(f"{v}_") for v in virtual):
            continue  # a shadow table of an FTS5 or vec0 table
        info = await _rows(f'SELECT name, pk FROM pragma_table_info("{name}")')
        keys = sorted((int(str(pk)), str(column)) for column, pk in info if pk)
        tables.append(
            _Table(
                name=name,
                columns=tuple(str(r[0]) for r in info),
                primary_key=tuple(column for _, column in keys),
                foreign_keys=await _foreign_keys_of(name),
                indexes=await _indexes_of(name),
                virtual=bool(is_virtual),
            )
        )
    return tables


@pytest.fixture
async def live_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[list[_Table]]:
    """The tables of a clean database at the latest schema version."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "guards.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await _live_tables()
    finally:
        await db.close_db()
        db._conn = None


@pytest.mark.integration
async def test_the_live_schema_is_read_with_its_keys(live_tables: list[_Table]) -> None:
    by_name = {t.name: t for t in live_tables}

    assert by_name["recall_units"].foreign_keys
    assert by_name["commissioning_sections"].primary_key == ("commissioning_id", "section")
    assert by_name["recall_units_fts"].virtual
    assert "recall_units_fts_data" not in by_name
    assert "recall_units_vec_chunks" not in by_name
    assert not any(name.startswith("sqlite_") for name in by_name)


@pytest.mark.integration
async def test_every_table_has_a_primary_key(live_tables: list[_Table]) -> None:
    assert _without_primary_key(live_tables) == []


@pytest.mark.integration
async def test_every_foreign_key_has_a_full_index(live_tables: list[_Table]) -> None:
    assert _unindexed_foreign_keys(live_tables) == []


@pytest.mark.integration
async def test_every_foreign_key_of_a_touched_table_states_its_rule(
    live_tables: list[_Table],
) -> None:
    assert _foreign_keys_without_rule(live_tables, _TOUCHED_TABLES) == []
    assert {t.name for t in live_tables} >= _TOUCHED_TABLES


@pytest.mark.integration
async def test_the_dictionary_covers_every_table_and_column_both_ways(
    live_tables: list[_Table],
) -> None:
    assert _dictionary_gaps(live_tables, _DICTIONARY.read_text(encoding="utf-8")) == []


@pytest.mark.unit
def test_every_dictionary_section_is_complete() -> None:
    assert _incomplete_sections(_DICTIONARY.read_text(encoding="utf-8")) == []


@pytest.mark.unit
def test_the_dictionary_has_its_closing_sections() -> None:
    text = _DICTIONARY.read_text(encoding="utf-8")

    assert [h for h in _REQUIRED_HEADINGS if f"\n## {h}\n" not in text] == []
