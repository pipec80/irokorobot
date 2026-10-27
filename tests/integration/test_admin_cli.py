"""The `iroko-admin` command (Plan 0073 Task 6): dry run, confirmation, PIN, no SQL in the tool.

The command refuses a missing database and a server that answers, reads a value from standard
input, confirms before writing, asks the PIN for sensitive data, and prints values on this
terminal only. Canaries and invented phones only.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest
from server.admin_cli import AdminRequest, run_admin_command
from server.cognition.pin_credentials import hash_pin
from server.memory.canonical_writer import write_literal
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.owner_credentials import save_owner_pin_credential
from server.memory.write_types import WriteChannel
from server.settings import settings

from server import admin_cli, db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-10-27T10:00:00.000000+00:00"
_PIN = "482173"


class _Script:
    """A scripted `read_text`: returns queued answers and records the prompts."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)


def _sink() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


@pytest.fixture
async def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "admin-cli.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    owner = await upsert_entity(name="Canary Owner", type="person")
    await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
    await save_owner_pin_credential(person_entity_id=owner, credential=hash_pin(_PIN))
    await db.close_db()
    db._conn = None
    yield owner
    if db._conn is not None:
        await db.close_db()
        db._conn = None


async def _run(request: AdminRequest, read_text: _Script, write_text: object) -> int:
    return await run_admin_command(
        request,
        read_text=read_text,
        read_secret=read_text,  # same scripted queue; getpass is used only in main()
        write_text=write_text,
        now=_NOW,  # type: ignore[arg-type]
    )


# --- refusals -------------------------------------------------------------------------------------


async def test_a_missing_database_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "absent.db")
    db._conn = None
    lines, write = _sink()
    code = await _run(AdminRequest(command="list"), _Script(), write)
    assert code == 1
    assert any("No existe la base de datos" in line for line in lines)


def test_a_running_server_is_refused(cli_db: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_cli, "_server_answers", lambda: True)
    monkeypatch.setattr(sys, "argv", ["iroko-admin", "list"])
    with pytest.raises(SystemExit) as exit_info:
        admin_cli.main()
    assert exit_info.value.code == 1


# --- reads ----------------------------------------------------------------------------------------


async def test_list_prints_a_stored_fact(cli_db: int) -> None:
    owner = cli_db
    await db.open_db()
    await write_literal(
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="preferred_name",
        value="Canary",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    await db.close_db()
    db._conn = None
    lines, write = _sink()
    code = await _run(AdminRequest(command="list"), _Script(), write)
    assert code == 0
    assert any("Canary" in line for line in lines)


# --- writes ---------------------------------------------------------------------------------------


async def test_add_a_non_sensitive_field_applies_after_confirmation(cli_db: int) -> None:
    read = _Script("el té verde", "SI")
    lines, write = _sink()
    code = await _run(AdminRequest(command="add", field="likes"), read, write)
    assert code == 0
    assert any("aplicada" in line for line in lines)
    # A follow-up list shows the value.
    seen, write2 = _sink()
    await _run(AdminRequest(command="list"), _Script(), write2)
    assert any("el té verde" in line for line in seen)


async def test_a_dry_run_writes_nothing(cli_db: int) -> None:
    read = _Script("el té verde")
    lines, write = _sink()
    code = await _run(AdminRequest(command="add", field="likes", dry_run=True), read, write)
    assert code == 1
    assert any("Prueba en seco" in line for line in lines)
    seen, write2 = _sink()
    await _run(AdminRequest(command="list"), _Script(), write2)
    assert not any("el té verde" in line for line in seen)


async def test_a_cancelled_write_writes_nothing(cli_db: int) -> None:
    read = _Script("el té verde", "no")
    lines, write = _sink()
    code = await _run(AdminRequest(command="add", field="likes"), read, write)
    assert code == 1
    assert any("cancelada" in line for line in lines)


async def test_a_sensitive_field_asks_for_the_pin_and_applies(cli_db: int) -> None:
    read = _Script("Canary pill 10mg", "SI", _PIN)
    lines, write = _sink()
    code = await _run(AdminRequest(command="add", field="medication"), read, write)
    assert code == 0
    assert any("PIN" in prompt for prompt in read.prompts)
    assert any("aplicada" in line for line in lines)


async def test_a_wrong_pin_refuses_the_sensitive_write(cli_db: int) -> None:
    read = _Script("Canary pill 10mg", "SI", "000000", "000000", "000000")
    lines, write = _sink()
    code = await _run(AdminRequest(command="add", field="medication"), read, write)
    assert code == 1
    assert any("Sin verificación" in line for line in lines)


async def test_audit_lists_operations_without_a_value(cli_db: int) -> None:
    read = _Script("el té verde", "SI")
    _, write = _sink()
    await _run(AdminRequest(command="add", field="likes"), read, write)
    lines, write2 = _sink()
    code = await _run(AdminRequest(command="audit"), _Script(), write2)
    assert code == 0
    assert any("add" in line and "likes" in line for line in lines)
    assert not any("el té verde" in line for line in lines)
