"""The pre-copy scrub of `just reset-db` (ADR 0021 decision 6): no live value in a backup."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from scripts import scrub_candidates

pytestmark = pytest.mark.unit

_MIGRATION = (
    Path(scrub_candidates.__file__).resolve().parents[1]
    / "server/src/server/memory/migration_009_memory_candidates.sql"
)
_CANARY = "zumo de pomelo rosado"
_RESET_SCRIPT = Path(scrub_candidates.__file__).resolve().with_name("reset_db.ps1")


def _database(path: Path, *, statuses: tuple[str, ...]) -> Path:
    """A database file holding one candidate row per status, with WAL like the server's."""
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(_MIGRATION.read_text(encoding="utf-8"))
    for index, status in enumerate(statuses):
        live = status in {"proposed", "offered"}
        connection.execute(
            "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
            "value_text, value_key, status, channel, source_correlation_id, proposed_at, "
            "expires_at) VALUES (1, 1, 'likes', ?, ?, ?, 'voice_classic', 'c', 'a', 'b')",
            (
                f"{_CANARY} {index}" if live else None,
                f"{_CANARY} {index}" if live else None,
                status,
            ),
        )
    connection.commit()
    connection.close()
    return path


def _bytes(path: Path) -> bytes:
    wal = path.with_name(path.name + "-wal")
    return path.read_bytes() + (wal.read_bytes() if wal.exists() else b"")


def test_every_live_candidate_is_voided_and_its_value_leaves_the_file(tmp_path: Path) -> None:
    db_path = _database(tmp_path / "omnibot.db", statuses=("proposed", "offered", "confirmed"))
    assert _CANARY.encode() in _bytes(db_path)

    voided = scrub_candidates.scrub(db_path)

    assert voided == 2
    assert _CANARY.encode() not in _bytes(db_path)
    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT status, value_text, value_key FROM memory_candidates ORDER BY id"
    ).fetchall()
    connection.close()
    assert rows == [("expired", None, None), ("expired", None, None), ("confirmed", None, None)]


def test_a_database_without_the_table_or_the_file_is_a_clean_no_op(tmp_path: Path) -> None:
    empty = tmp_path / "older.db"
    sqlite3.connect(empty).close()

    assert scrub_candidates.scrub(empty) == 0
    assert scrub_candidates.scrub(tmp_path / "missing.db") == 0


def test_main_prints_counts_only_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = _database(tmp_path / "omnibot.db", statuses=("proposed",))

    status = scrub_candidates.main([str(db_path)])

    out = capsys.readouterr().out
    assert status == 0
    assert "Voided 1 live candidate(s)" in out
    assert "pomelo" not in out


def test_main_fails_when_the_file_is_not_a_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "omnibot.db"
    broken.write_bytes(b"this is not a sqlite database at all" * 20)

    status = scrub_candidates.main([str(broken)])

    assert status == 1
    assert "Could not scrub" in capsys.readouterr().err


def test_reset_db_scrubs_before_it_copies_and_refuses_to_copy_when_it_fails() -> None:
    text = _RESET_SCRIPT.read_text(encoding="utf-8")

    # The calls, not the definitions: the copy lives in `Copy-DbWithSidecars` since Plan 0071.
    scrub_at = text.index("uv run python scripts/scrub_candidates.py $dbPath")
    copy_at = text.index("Copy-DbWithSidecars -DbPath $dbPath")
    assert scrub_at < copy_at
    assert "$LASTEXITCODE" in text[scrub_at:copy_at]


def test_a_reader_that_pins_the_log_makes_the_scrub_fail_so_nothing_is_copied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = _database(tmp_path / "omnibot.db", statuses=("proposed",))
    reader = sqlite3.connect(db_path)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM memory_candidates").fetchall()
    try:
        status = scrub_candidates.main([str(db_path)])
    finally:
        reader.close()

    assert status == 1
    assert "Could not scrub" in capsys.readouterr().err
