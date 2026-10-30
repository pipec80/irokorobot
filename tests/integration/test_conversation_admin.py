"""`iroko-admin conversations` (Plan 0076 Task 11): list, export, delete, consent; PIN and audit.

Canary texts and an invented PIN only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.admin_cli import AdminRequest, run_admin_command
from server.cognition.pin_credentials import hash_pin
from server.conversation_admin import render_record
from server.memory import conversation_record as record
from server.memory.conversation_consent import (
    grant_conversation_consent,
    has_active_conversation_consent,
)
from server.memory.conversation_episodes import Episode
from server.memory.conversation_record import EpisodeStatus, RecordSummary, RecordView
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.owner_credentials import save_owner_pin_credential
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-10-29T12:00:00.000000+00:00"
_PIN = "482173"
_T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
_CANARY = "Zeta canario"


class _Script:
    """A scripted `read_text`: returns queued answers and records the prompts."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)


def _sink() -> tuple[list[str], Callable[[str], None]]:
    lines: list[str] = []
    return lines, lines.append


@pytest.fixture
async def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    """A closed database with an owner, a PIN, a consent and two stored conversations."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "conversations.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    owner = await upsert_entity(name="Canary Owner", type="person")
    await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
    await save_owner_pin_credential(person_entity_id=owner, credential=hash_pin(_PIN))
    await grant_conversation_consent(owner, notice_version="v1", now=_T0)
    for start in (0, 600):
        turn = make_turn(
            f"{_CANARY} {start}",
            "Qué bien.",
            voice=TurnVerdict.VERIFIED,
            correlation_id=UUID(int=start + 1),
            at=_T0 + timedelta(seconds=start),
        )
        await record.append_turn(turn, owner_entity_id=owner, now=turn.at)
    await record.close_idle_records(_T0 + timedelta(hours=1))
    await db.close_db()
    db._conn = None
    yield owner
    if db._conn is not None:
        await db.close_db()
        db._conn = None


async def _run(request: AdminRequest, read_text: _Script, write_text: Callable[[str], None]) -> int:
    return await run_admin_command(
        request, read_text=read_text, read_secret=read_text, write_text=write_text, now=_NOW
    )


async def _count(sql: str) -> int:
    await db.open_db()
    try:
        cursor = await db.get_conn().execute(sql)
        row = await cursor.fetchone()
        await cursor.close()
    finally:
        await db.close_db()
        db._conn = None
    assert row is not None
    return int(row[0])


def _conversations(
    action: str, *, row_id: int | None = None, out: Path | None = None, dry_run: bool = False
) -> AdminRequest:
    return AdminRequest(
        command="conversations", action=action, row_id=row_id, out=out, dry_run=dry_run
    )


async def test_list_needs_no_pin_and_prints_no_text(cli_db: int) -> None:
    lines, write = _sink()
    read = _Script()

    code = await _run(_conversations("list"), read, write)

    assert code == 0
    assert read.prompts == []
    assert sum("intercambios" in line for line in lines) == 2
    assert not any(_CANARY in line for line in lines)


async def test_export_needs_the_pin_and_writes_one_file_per_record(
    cli_db: int, tmp_path: Path
) -> None:
    out = tmp_path / "export"
    read = _Script("SI", _PIN)
    lines, write = _sink()

    code = await _run(_conversations("export", out=out), read, write)

    assert code == 0
    assert any("PIN" in prompt for prompt in read.prompts)
    files = sorted(out.glob("conversacion-*.md"))
    assert len(files) == 2
    assert _CANARY in files[0].read_text(encoding="utf-8")
    assert not any(_CANARY in line for line in lines)


async def test_delete_needs_the_pin_and_removes_the_record(cli_db: int) -> None:
    _lines, write = _sink()

    code = await _run(_conversations("delete", row_id=1), _Script("SI", _PIN), write)

    assert code == 0
    assert await _count("SELECT COUNT(*) FROM conversation_records") == 1


async def test_consent_revoke_deletes_everything(cli_db: int) -> None:
    lines, write = _sink()

    code = await _run(_conversations("consent-revoke"), _Script("SI", _PIN), write)

    assert code == 0
    assert any("2" in line and "borr" in line for line in lines)
    assert await _count("SELECT COUNT(*) FROM conversation_records") == 0


async def test_consent_grant_prints_the_notice_and_grants(cli_db: int) -> None:
    await _run(_conversations("consent-revoke"), _Script("SI", _PIN), _sink()[1])
    lines, write = _sink()

    code = await _run(_conversations("consent-grant"), _Script("SI", _PIN), write)

    assert code == 0
    assert any("Aviso de registro de conversaciones" in line for line in lines)
    await db.open_db()
    try:
        assert await has_active_conversation_consent(cli_db)
    finally:
        await db.close_db()
        db._conn = None


async def test_a_wrong_pin_refuses_and_is_audited_as_refused(cli_db: int) -> None:
    _lines, write = _sink()

    code = await _run(
        _conversations("delete", row_id=1), _Script("SI", "000000", "000000", "000000"), write
    )

    assert code == 1
    assert await _count("SELECT COUNT(*) FROM conversation_records") == 2
    assert (
        await _count(
            "SELECT COUNT(*) FROM admin_audit WHERE operation = 'delete' AND outcome = 'refused'"
        )
        == 1
    )


async def test_dry_run_changes_nothing(cli_db: int) -> None:
    code = await _run(_conversations("delete", row_id=1, dry_run=True), _Script(), _sink()[1])

    assert code == 1
    assert await _count("SELECT COUNT(*) FROM conversation_records") == 2
    assert await _count("SELECT COUNT(*) FROM admin_audit") == 0


async def test_every_mutating_action_writes_one_audit_row_without_text(
    cli_db: int, tmp_path: Path
) -> None:
    await _run(_conversations("export", out=tmp_path / "x"), _Script("SI", _PIN), _sink()[1])
    await _run(_conversations("delete", row_id=1), _Script("SI", _PIN), _sink()[1])
    await _run(_conversations("consent-revoke"), _Script("SI", _PIN), _sink()[1])

    lines, write = _sink()
    await _run(AdminRequest(command="audit"), _Script(), write)
    operations = [line for line in lines if "conversation_" in line]
    assert len(operations) == 3
    assert not any(_CANARY in line for line in lines)


def test_render_record_exact() -> None:
    turns = tuple(
        make_turn(
            heard,
            said,
            voice=voice,
            correlation_id=UUID(int=index + 1),
            at=_T0 + timedelta(seconds=index),
        )
        for index, (heard, said, voice) in enumerate(
            [
                ('dijo "hola"\ny se fue 🙂', "Hola.", TurnVerdict.VERIFIED),
                ("otra cosa", "Bien.", TurnVerdict.NOT_VERIFIED),
                ("una visita", "Hola, visita.", TurnVerdict.NOT_OWNER),
                ("¿qué fecha es hoy?", "Hoy es jueves.", TurnVerdict.NOT_CHECKED),
            ]
        )
    )
    summary = RecordSummary(
        id=3,
        previous_id=None,
        started_at="2026-10-29T10:00:00.000000+00:00",
        closed_at="2026-10-29T10:05:00.000000+00:00",
        turn_count=4,
        byte_count=500,
        eligible=True,
        expires_at="2027-10-29T10:05:00.000000+00:00",
        episode_status=EpisodeStatus.DONE,
    )
    episode = Episode(
        id=1,
        source_record_id=3,
        owner_entity_id=7,
        sensitivity="normal",
        summary="La persona contó que saludó.",
        created_at="2026-10-29T10:10:00.000000+00:00",
        expires_at="2027-10-29T10:05:00.000000+00:00",
    )

    text = render_record(RecordView(summary, 7, turns), episode)

    assert text == (
        "# Conversación 3\n"
        "\n"
        "- Inicio: 2026-10-29T10:00:00.000000+00:00 UTC · "
        "Fin: 2026-10-29T10:05:00.000000+00:00 UTC\n"
        "- Segmento anterior: — · Elegible: sí · Caduca: 2027-10-29T10:05:00.000000+00:00\n"
        "- Resumen (normal): La persona contó que saludó.\n"
        "\n"
        '[10:00:00] Persona (tu voz verificada): dijo "hola"\ny se fue 🙂\n'
        "[10:00:00] Iroko: Hola.\n"
        "[10:00:01] Persona (tu cara, voz no verificada): otra cosa\n"
        "[10:00:01] Iroko: Bien.\n"
        "[10:00:02] Persona (otra persona o sin cara): una visita\n"
        "[10:00:02] Iroko: Hola, visita.\n"
        "[10:00:03] Persona (sin revisar): ¿qué fecha es hoy?\n"
        "[10:00:03] Iroko: Hoy es jueves.\n"
    )
