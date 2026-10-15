"""The acceptance inspector of Plan 0063: counts only, never a value (ADR 0021 §12)."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from server.settings import settings

from scripts import inspect_candidates
from server import db

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

_CANARY = "zumo de pomelo rosado"


@pytest.fixture
async def brain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A database migrated by the server, holding two candidates, audit rows and one fact."""
    path = tmp_path / "brain.db"
    monkeypatch.setattr(settings, "brain_db_path", path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    conn = db.get_conn()
    await conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'Canary', 'person')")
    await conn.execute(
        "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
        "value_text, value_key, status, channel, source_correlation_id, proposed_at, "
        "expires_at) VALUES (1, 1, 'likes', ?, ?, 'proposed', 'voice_classic', 'c', 'a', 'b')",
        (_CANARY, _CANARY),
    )
    await conn.execute(
        "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
        "status, channel, source_correlation_id, proposed_at, expires_at) "
        "VALUES (1, 1, 'likes', 'confirmed', 'voice_stream', 'c', 'a', 'b')"
    )
    for action, decision in (
        ("read_personal_conversation_memory", "allowed"),
        ("confirm_personal_memory", "allowed"),
        ("confirm_personal_memory", "denied"),
    ):
        await conn.execute(
            "INSERT INTO authorization_audit_events (actor_entity_id, target_entity_id, action, "
            "data_categories, decision, policy_id, reason, correlation_id, evaluated_at) "
            "VALUES (1, 1, ?, '[]', ?, 'p', 'r', 'c', 'now')",
            (action, decision),
        )
    await conn.execute(
        "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text, visibility, "
        "sensitivity, lifecycle, confidence, confirmed_by_entity_id, confirmed_at) "
        "VALUES (1, 'likes', ?, 'personal', 'normal', 'active', 1.0, 1, 'now')",
        (_CANARY,),
    )
    await conn.commit()
    await db.close_db()
    db._conn = None
    return path


def test_the_report_counts_statuses_audit_rows_and_confirmed_facts(brain: Path) -> None:
    report = inspect_candidates.inspect(brain)

    assert report.candidates == {
        "proposed": 1,
        "offered": 0,
        "confirmed": 1,
        "rejected": 0,
        "expired": 0,
    }
    assert report.audit[("confirm_personal_memory", "allowed")] == 1
    assert report.audit[("confirm_personal_memory", "denied")] == 1
    assert report.audit[("read_personal_conversation_memory", "allowed")] == 1
    assert report.audit[("propose_personal_memory", "allowed")] == 0
    assert report.audit[("confirm_personal_memory", "requires_confirmation")] == 0
    assert report.confirmed_facts == 1


def test_the_printed_report_never_carries_a_value(
    brain: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert inspect_candidates.main([str(brain)]) == 0

    out = capsys.readouterr().out
    assert "proposed=1" in out
    assert "confirmed facts: 1" in out
    assert "pomelo" not in out


def test_a_database_before_migration_9_reports_zero_candidates(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    sqlite3.connect(path).close()

    report = inspect_candidates.inspect(path)

    assert sum(report.candidates.values()) == 0
    assert report.confirmed_facts == 0


def test_a_missing_file_is_an_error_and_creates_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "absent.db"

    assert inspect_candidates.main([str(path)]) == 1
    assert not path.exists()
    assert "absent.db" in capsys.readouterr().err


def test_the_inspector_opens_the_file_read_only(brain: Path) -> None:
    before = brain.read_bytes()

    inspect_candidates.inspect(brain)

    assert brain.read_bytes() == before


def test_the_inspector_never_creates_a_database(tmp_path: Path) -> None:
    """Read-only mode: a missing file is an error, not a new empty database."""
    path = tmp_path / "absent.db"

    with pytest.raises(sqlite3.OperationalError):
        inspect_candidates.inspect(path)

    assert not path.exists()
