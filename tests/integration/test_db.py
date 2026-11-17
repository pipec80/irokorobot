"""Integration tests for `db.py`'s connection lifecycle against a real SQLite DB.

`open_db`, `close_db`, `get_conn`, and `run_migrations` had no direct tests of
their own before Plan 0035 — every existing test only exercised them
indirectly, as setup/teardown for some other module's fixture. This file
closes that gap for the one production file this plan is allowed to touch.
"""

from collections.abc import AsyncIterator
import logging
from pathlib import Path
import sqlite3

import aiosqlite
import pytest
from server.exceptions import BrainMemoryError
from server.settings import settings

from server import db


@pytest.fixture
async def clean_conn_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """Point at a fresh temp DB path without opening it — each test controls open/close."""
    db_path = tmp_path / "lifecycle-test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    yield db_path
    if db._conn is not None:
        await db.close_db()
    db._conn = None


@pytest.mark.integration
async def test_get_conn_before_open_raises(clean_conn_state: Path) -> None:
    """Reading the connection before `open_db()` must fail clearly, not with `None`."""
    with pytest.raises(BrainMemoryError, match="open_db"):
        db.get_conn()


@pytest.mark.integration
async def test_open_db_makes_get_conn_succeed(clean_conn_state: Path) -> None:
    """The documented happy path: open, then read."""
    await db.open_db()

    assert db.get_conn() is not None


@pytest.mark.integration
async def test_open_db_is_idempotent(clean_conn_state: Path) -> None:
    """A second `open_db()` call must not replace or break the existing connection."""
    await db.open_db()
    first_conn = db.get_conn()

    await db.open_db()

    assert db.get_conn() is first_conn


@pytest.mark.integration
async def test_close_db_is_idempotent(clean_conn_state: Path) -> None:
    """A second `close_db()` call on an already-closed module must not raise."""
    await db.open_db()
    await db.close_db()

    await db.close_db()  # must not raise


@pytest.mark.integration
async def test_close_db_leaves_get_conn_raising(clean_conn_state: Path) -> None:
    """After closing, the module must not point at a stale or closed connection."""
    await db.open_db()
    await db.close_db()

    with pytest.raises(BrainMemoryError, match="open_db"):
        db.get_conn()


@pytest.mark.integration
async def test_run_migrations_reaches_the_latest_schema_version(
    clean_conn_state: Path,
) -> None:
    """A fresh DB must end up at the highest known migration version."""
    await db.open_db()
    await db.run_migrations()

    cursor = await db.get_conn().execute("PRAGMA user_version")
    row = await cursor.fetchone()
    await cursor.close()

    assert row is not None
    assert row[0] > 0


@pytest.mark.integration
async def test_run_migrations_is_idempotent(clean_conn_state: Path) -> None:
    """Running migrations twice on an up-to-date DB must be a no-op, not an error."""
    await db.open_db()
    await db.run_migrations()
    cursor = await db.get_conn().execute("PRAGMA user_version")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    first_version = int(row[0])

    await db.run_migrations()  # must not raise, must not change the version

    cursor = await db.get_conn().execute("PRAGMA user_version")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert int(row[0]) == first_version


# ---- The atomic migration runner (Plan 0085, D-5) -------------------------------------------


@pytest.fixture
async def migrated_conn(clean_conn_state: Path) -> int:
    """A database at the latest real version; yields the version a test migration would take."""
    await db.open_db()
    await db.run_migrations()
    return db.latest_schema_version() + 1


async def _scalar(sql: str) -> object:
    cursor = await db.get_conn().execute(sql)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return row[0]


async def _run_new_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: int,
    sql: str,
    *,
    rebuild: bool = False,
) -> None:
    """Add one wrapped migration file after the real ones and run the migrations."""
    folder = tmp_path / "migrations"
    folder.mkdir(exist_ok=True)
    filename = f"migration_{version:03d}_test.sql"
    (folder / filename).write_text(sql, encoding="utf-8")
    new = db.Migration(version, filename, rebuild=rebuild)
    monkeypatch.setattr(db, "_MIGRATIONS_DIR", folder)
    monkeypatch.setattr(db, "_MIGRATIONS", (*db._MIGRATIONS, new))
    await db.run_migrations()


_TRANSACTION_STATEMENTS = (
    "BEGIN;",
    "begin immediate transaction;",
    "COMMIT;",
    "END;",
    "ROLLBACK;",
    "SAVEPOINT a;",
    "RELEASE a;",
    "PRAGMA user_version = 99;",
    # Silent no-ops inside the runner's transaction: only a ``rebuild`` migration toggles them.
    "PRAGMA foreign_keys = OFF;",
    "pragma defer_foreign_keys = on;",
)


@pytest.mark.integration
@pytest.mark.parametrize("statement", _TRANSACTION_STATEMENTS)
async def test_a_new_migration_holding_transaction_statements_is_refused(
    migrated_conn: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, statement: str
) -> None:
    """The runner owns the transaction and the version: a file that touches either never runs."""
    sql = f"CREATE TABLE refused_canary (id INTEGER);\n{statement}\n"

    with pytest.raises(BrainMemoryError, match=r"migration_\d+_test\.sql"):
        await _run_new_migration(tmp_path, monkeypatch, migrated_conn, sql)

    assert await _scalar("SELECT count(*) FROM sqlite_master WHERE name = 'refused_canary'") == 0
    assert await _scalar("PRAGMA user_version") == migrated_conn - 1


@pytest.mark.integration
async def test_comments_and_trigger_bodies_are_not_transaction_statements(
    migrated_conn: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``BEGIN`` and ``END`` inside a trigger body, and the words in comments, are allowed."""
    sql = """
-- BEGIN; COMMIT; user_version
/* ROLLBACK; SAVEPOINT x; */
CREATE TABLE trigger_canary (id INTEGER PRIMARY KEY, note TEXT);
CREATE TABLE trigger_log (note TEXT);
CREATE TRIGGER trigger_canary_ai AFTER INSERT ON trigger_canary
BEGIN
    INSERT INTO trigger_log (note) VALUES (new.note);
END;
"""

    await _run_new_migration(tmp_path, monkeypatch, migrated_conn, sql)

    assert await _scalar("PRAGMA user_version") == migrated_conn
    conn = db.get_conn()
    await conn.execute("INSERT INTO trigger_canary (note) VALUES ('hola')")
    await conn.commit()
    assert await _scalar("SELECT count(*) FROM trigger_log") == 1


@pytest.mark.integration
async def test_a_migration_failing_halfway_leaves_nothing(
    migrated_conn: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A script that fails after creating and filling things leaves no table, index or version."""
    sql = """
CREATE TABLE half_canary (id INTEGER PRIMARY KEY, name TEXT);
CREATE INDEX half_canary_name ON half_canary (name);
INSERT INTO half_canary (name) VALUES ('a'), ('b');
INSERT INTO table_that_does_not_exist (id) VALUES (1);
"""

    with pytest.raises(BrainMemoryError, match=r"Migration \d+ \(migration_\d+_test\.sql\) failed"):
        await _run_new_migration(tmp_path, monkeypatch, migrated_conn, sql)

    assert await _scalar("SELECT count(*) FROM sqlite_master WHERE name LIKE 'half_canary%'") == 0
    assert await _scalar("PRAGMA user_version") == migrated_conn - 1
    assert await _scalar("PRAGMA foreign_keys") == 1
    assert not db.get_conn().in_transaction


_PARENT_CHILD = """
CREATE TABLE rb_parent (id INTEGER PRIMARY KEY);
CREATE TABLE rb_child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES rb_parent (id));
INSERT INTO rb_parent (id) VALUES (1), (2);
INSERT INTO rb_child (id, parent_id) VALUES (10, 1), (20, 2);
"""
_REBUILD_PARENT = """
CREATE TABLE rb_parent_new (id INTEGER PRIMARY KEY, extra TEXT);
INSERT INTO rb_parent_new (id) SELECT id FROM rb_parent;
DROP TABLE rb_parent;
ALTER TABLE rb_parent_new RENAME TO rb_parent;
"""


async def _make_parent_child() -> None:
    conn = db.get_conn()
    await conn.executescript(_PARENT_CHILD)
    await conn.commit()


@pytest.mark.integration
async def test_a_rebuild_migration_runs_with_foreign_keys_off_and_back_on(
    migrated_conn: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping a referenced table works only with foreign keys off; they come back on after."""
    await _make_parent_child()

    await _run_new_migration(tmp_path, monkeypatch, migrated_conn, _REBUILD_PARENT, rebuild=True)

    assert await _scalar("PRAGMA user_version") == migrated_conn
    assert await _scalar("SELECT count(*) FROM rb_parent") == 2
    assert await _scalar("SELECT count(*) FROM rb_child") == 2
    assert await _scalar("SELECT count(*) FROM pragma_table_info('rb_parent')") == 2
    assert await _scalar("PRAGMA foreign_keys") == 1


@pytest.mark.integration
async def test_the_same_rebuild_without_the_flag_fails_with_foreign_keys_on(
    migrated_conn: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag is what makes the rebuild possible: without it the DROP is refused."""
    await _make_parent_child()

    with pytest.raises(BrainMemoryError, match="failed"):
        await _run_new_migration(tmp_path, monkeypatch, migrated_conn, _REBUILD_PARENT)

    assert await _scalar("PRAGMA user_version") == migrated_conn - 1
    assert await _scalar("SELECT count(*) FROM pragma_table_info('rb_parent')") == 1


@pytest.mark.integration
async def test_a_rebuild_leaving_a_foreign_key_violation_is_aborted(
    migrated_conn: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Foreign keys are off during a rebuild, so the guard must catch an orphan and roll back."""
    await _make_parent_child()
    orphaning = "DELETE FROM rb_parent WHERE id = 1;"

    with pytest.raises(BrainMemoryError, match="failed"):
        await _run_new_migration(tmp_path, monkeypatch, migrated_conn, orphaning, rebuild=True)

    assert await _scalar("SELECT count(*) FROM rb_parent") == 2
    assert await _scalar("PRAGMA user_version") == migrated_conn - 1
    assert await _scalar("PRAGMA foreign_keys") == 1
    assert not db.get_conn().in_transaction


@pytest.mark.integration
async def test_a_rebuild_whose_foreign_keys_stay_on_is_refused_before_it_runs(
    migrated_conn: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``PRAGMA foreign_keys = OFF`` is ignored inside an open transaction: read it back."""
    await _make_parent_child()
    conn = db.get_conn()
    await conn.execute("BEGIN IMMEDIATE")

    with pytest.raises(BrainMemoryError, match="foreign keys"):
        await _run_new_migration(
            tmp_path, monkeypatch, migrated_conn, _REBUILD_PARENT, rebuild=True
        )

    assert await _scalar("SELECT count(*) FROM pragma_table_info('rb_parent')") == 1
    assert await _scalar("PRAGMA user_version") == migrated_conn - 1
    assert await _scalar("PRAGMA foreign_keys") == 1
    await conn.rollback()


_ORPHANING = "DELETE FROM rb_parent WHERE id = 1;"


@pytest.mark.integration
async def test_a_failure_to_turn_foreign_keys_back_on_does_not_hide_the_migrations_error(
    migrated_conn: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _make_parent_child()
    conn = db.get_conn()
    real_execute = conn.execute

    async def failing_execute(sql: str, *args: object) -> aiosqlite.Cursor:
        if sql == "PRAGMA foreign_keys = ON":
            raise sqlite3.OperationalError("canary: cannot set")
        return await real_execute(sql, *args)

    monkeypatch.setattr(conn, "execute", failing_execute)

    with (
        caplog.at_level(logging.WARNING, logger="server.db"),
        pytest.raises(BrainMemoryError, match=r"Migration \d+ .* failed") as raised,
    ):
        await _run_new_migration(tmp_path, monkeypatch, migrated_conn, _ORPHANING, rebuild=True)

    assert isinstance(raised.value.__cause__, sqlite3.IntegrityError)
    assert "OperationalError" in caplog.text
    assert "canary" not in caplog.text


@pytest.mark.integration
async def test_a_failing_rollback_does_not_hide_the_migrations_error(
    migrated_conn: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = db.get_conn()

    async def failing_rollback() -> None:
        raise sqlite3.OperationalError("canary: rollback refused")

    monkeypatch.setattr(conn, "rollback", failing_rollback)

    with pytest.raises(BrainMemoryError, match=r"Migration \d+ .* failed") as raised:
        await _run_new_migration(
            tmp_path, monkeypatch, migrated_conn, "INSERT INTO nowhere (id) VALUES (1);"
        )

    assert isinstance(raised.value.__cause__, sqlite3.OperationalError)
    assert "canary" not in str(raised.value)


@pytest.mark.integration
async def test_a_failed_migration_names_the_constraint_that_fired_and_no_value(
    migrated_conn: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An integrity error names its constraint and columns, never a value: it goes in the log."""
    sql = """
CREATE TABLE guard_canary (id INTEGER PRIMARY KEY, code TEXT UNIQUE);
INSERT INTO guard_canary (code) VALUES ('planted-value'), ('planted-value');
"""

    with (
        caplog.at_level(logging.ERROR, logger="server.db"),
        pytest.raises(BrainMemoryError) as raised,
    ):
        await _run_new_migration(tmp_path, monkeypatch, migrated_conn, sql)

    for text in (str(raised.value), caplog.text):
        assert "UNIQUE constraint failed: guard_canary.code" in text
        assert "planted-value" not in text


@pytest.mark.integration
async def test_any_other_failure_class_stays_class_only(
    migrated_conn: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        caplog.at_level(logging.ERROR, logger="server.db"),
        pytest.raises(BrainMemoryError) as raised,
    ):
        await _run_new_migration(
            tmp_path, monkeypatch, migrated_conn, "INSERT INTO nowhere_canary (id) VALUES (1);"
        )

    assert "nowhere_canary" not in str(raised.value)
    assert "nowhere_canary" not in caplog.text
    assert "OperationalError" in caplog.text
