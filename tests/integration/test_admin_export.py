"""`iroko-admin export` (Plan 0087 Task 5, D-2, D-3 amended, D-7): all or one person, audited.

Through ``run_admin_command``: the PIN first, then the folder, the counts, ``SI``, the two files
and one audit row per attempt (``export`` / ``household_data``), never a name, a value or a path.
Canary names and an invented PIN only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.admin_cli import AdminRequest, run_admin_command
from server.cognition.pin_credentials import hash_pin
from server.memory import conversation_record as record, export_files, relational_v4
from server.memory.admin_audit import list_admin_operations
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.owner_credentials import save_owner_pin_credential
from server.memory.predicate_registry import resolve_predicate
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-11-19T12:00:00.000000+00:00"
_PIN = "482173"
_T0 = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
_TASTE = "el té con | barra"
_STORY = "fui al cine con Canaria\ny llovió"


class _Script:
    """A scripted reader: returns queued answers in order."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)

    def __call__(self, _prompt: str) -> str:
        return self.answers.pop(0)


def _sink() -> tuple[list[str], Callable[[str], None]]:
    lines: list[str] = []
    return lines, lines.append


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    """An owner with a PIN, a taste and one told turn naming a canary; the database closed."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "data" / "export.db")
    (tmp_path / "data").mkdir()
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    person = await upsert_entity(name="Canario", type="person")
    await bootstrap_initial_owner(person_entity_id=person, confirmed_person_entity_id=person)
    await save_owner_pin_credential(person_entity_id=person, credential=hash_pin(_PIN))
    likes = resolve_predicate("likes")
    assert likes is not None
    await relational_v4.assert_literal_fact(
        subject_entity_id=person,
        definition=likes,
        value=_TASTE,
        visibility="personal",
        sensitivity="normal",
    )
    turn = make_turn(
        _STORY, "qué bueno", voice=TurnVerdict.VERIFIED, correlation_id=UUID(int=1), at=_T0
    )
    await record.append_turn(turn, owner_entity_id=person, now=turn.at)
    await record.close_idle_records(_T0 + timedelta(hours=4))
    await db.close_db()
    db._conn = None
    yield person
    await db.close_db()
    db._conn = None


async def _run(
    request: AdminRequest, *, pin: str = _PIN, confirm: str = "SI"
) -> tuple[int, list[str]]:
    lines, write = _sink()
    code = await run_admin_command(
        request,
        read_text=_Script(confirm),
        read_secret=_Script(pin, pin, pin),
        write_text=write,
        now=_NOW,
    )
    return code, lines


async def _audit() -> list[tuple[str, str, str | None, int | None, str, str | None]]:
    await db.open_db()
    try:
        rows = await list_admin_operations()
    finally:
        await db.close_db()
        db._conn = None
    return [
        (
            row.operation.value,
            row.target_kind.value,
            row.field_id,
            row.target_entity_id,
            row.outcome.value,
            row.reason,
        )
        for row in rows
    ]


def _exports(tmp_path: Path) -> Path:
    return tmp_path / "data" / "exports"


async def test_export_all_writes_both_files_and_one_applied_row(owner: int, tmp_path: Path) -> None:
    code, lines = await _run(AdminRequest(command="export", kind="all"))
    assert code == 0
    folder = _exports(tmp_path) / "20261119T120000Z-todo"
    assert sorted(path.name for path in folder.iterdir()) == ["exportacion.json", "exportacion.md"]
    assert any(line.startswith("Personas: 1 fila") for line in lines)
    assert lines[-1].startswith(f"Exportado a {folder}: exportacion.md y exportacion.json.")
    assert await _audit() == [("export", "household_data", "all", None, "applied", None)]


async def test_the_markdown_and_the_json_of_a_real_export_hold_the_same_rows(
    owner: int, tmp_path: Path
) -> None:
    await _run(AdminRequest(command="export", kind="all"))
    folder = _exports(tmp_path) / "20261119T120000Z-todo"
    parsed = json.loads((folder / "exportacion.json").read_text(encoding="utf-8"))
    markdown = (folder / "exportacion.md").read_text(encoding="utf-8")
    for section in parsed["sections"]:
        count = len(section["rows"])
        expected = "Sin filas." if not count else f"{count} {'fila' if count == 1 else 'filas'}."
        assert f"## {section['title']}\n\n{expected}" in markdown
    datos = next(s for s in parsed["sections"] if s["key"] == "datos")
    assert datos["rows"][0]["value_text"] == _TASTE
    assert "el té con \\| barra" in markdown
    assert "fui al cine con Canaria<br>y llovió" in markdown


async def test_export_one_person_by_id_and_by_name(owner: int, tmp_path: Path) -> None:
    assert (await _run(AdminRequest(command="export", kind="person", row_id=owner)))[0] == 0
    assert (await _run(AdminRequest(command="export", kind="person", name="Canaria")))[0] == 0
    names = sorted(path.name for path in _exports(tmp_path).iterdir())
    assert names == ["20261119T120000Z-persona", f"20261119T120000Z-persona-{owner}"]
    assert await _audit() == [
        ("export", "household_data", "person", None, "applied", None),
        ("export", "household_data", f"person:{owner}", owner, "applied", None),
    ]


async def test_a_wrong_pin_shows_no_count_and_writes_nothing(owner: int, tmp_path: Path) -> None:
    code, lines = await _run(AdminRequest(command="export", kind="all"), pin="000000")
    assert code == 1
    assert not any("filas" in line or "fila" in line for line in lines)
    assert not _exports(tmp_path).exists()
    assert await _audit() == [("export", "household_data", "all", None, "refused", "pin")]


async def test_a_refused_place_is_audited(owner: int, tmp_path: Path) -> None:
    code, lines = await _run(AdminRequest(command="export", kind="all", out=tmp_path / "data"))
    assert code == 1
    assert "base de datos" in lines[-1]
    assert await _audit() == [("export", "household_data", "all", None, "refused", "place")]


async def test_nothing_found_is_audited_empty(owner: int, tmp_path: Path) -> None:
    code, lines = await _run(AdminRequest(command="export", kind="person", name="Albatros"))
    assert code == 1
    assert lines[-1] == "No hay nada guardado de esa persona."
    assert not _exports(tmp_path).exists()
    assert await _audit() == [("export", "household_data", "person", None, "refused", "empty")]


async def test_a_dry_run_prints_the_counts_and_writes_nothing(owner: int, tmp_path: Path) -> None:
    code, lines = await _run(AdminRequest(command="export", kind="all", dry_run=True))
    assert code == 1
    assert any(line.startswith("Personas:") for line in lines)
    assert not _exports(tmp_path).exists()
    assert await _audit() == []


async def test_a_person_without_an_id_or_a_name_is_refused_before_the_pin(owner: int) -> None:
    lines, write = _sink()
    pins = _Script()
    code = await run_admin_command(
        AdminRequest(command="export", kind="person"),
        read_text=_Script(),
        read_secret=pins,
        write_text=write,
        now=_NOW,
    )
    assert code == 1
    assert "persona" in lines[-1]
    assert await _audit() == []


async def test_a_failing_disk_audits_write_and_leaves_nothing(
    owner: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = export_files._write_file

    def _disk_full(path: Path, text: str) -> None:
        if path.name == "exportacion.md":
            raise OSError("disk full")
        real(path, text)

    monkeypatch.setattr(export_files, "_write_file", _disk_full)
    code, lines = await _run(AdminRequest(command="export", kind="all"))
    assert code == 1
    assert lines[-1] == "No se pudo escribir la exportación: no quedó nada a medias."
    assert not (_exports(tmp_path) / "20261119T120000Z-todo").exists()
    assert await _audit() == [("export", "household_data", "all", None, "refused", "write")]


async def test_no_audit_row_or_log_line_holds_a_name_a_value_or_the_path(
    owner: int, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await _run(AdminRequest(command="export", kind="person", name="Canaria"))
    text = caplog.text + repr(await _audit())
    for secret in ("Canaria", "Canario", _TASTE, "llovió", str(_exports(tmp_path))):
        assert secret not in text
