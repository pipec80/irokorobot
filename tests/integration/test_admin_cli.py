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
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.owner_credentials import save_owner_pin_credential
from server.memory.write_types import WriteChannel
from server.settings import settings

from server import admin_cli, db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
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


def _sink() -> tuple[list[str], Callable[[str], None]]:
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


async def _run(request: AdminRequest, read_text: _Script, write_text: Callable[[str], None]) -> int:
    return await run_admin_command(
        request,
        read_text=read_text,
        read_secret=read_text,  # same scripted queue; getpass is used only in main()
        write_text=write_text,
        now=_NOW,
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


# --- label-parent and label-child (Plan 0080 Task 6) ----------------------------------------------


async def _seed_relation(owner: int, predicate: str, name: str) -> int:
    """Store one relation the way the alta did and return its id (the db is closed again)."""
    await db.open_db()
    try:
        person = await create_third_party(name=name, type="person")
        member = predicate == "child_of"
        relation = await write_relation(
            owner_entity_id=owner,
            source_entity_id=person if member else owner,
            predicate=predicate,
            target_entity_id=owner if member else person,
            channel=WriteChannel.ADMIN_LOCAL,
            confirmed_at=_NOW,
        )
    finally:
        await db.close_db()
        db._conn = None
    return relation.id


async def _listing() -> list[str]:
    lines, write = _sink()
    await _run(AdminRequest(command="list"), _Script(), write)
    return lines


async def test_label_parent_asks_confirmation_and_the_pin_and_applies(cli_db: int) -> None:
    row = await _seed_relation(cli_db, "has_parent", "Zeta Parent")
    read = _Script("SI", _PIN)
    lines, write = _sink()
    request = AdminRequest(command="label-parent", row_id=row, side="mother")
    assert await _run(request, read, write) == 0
    assert any("PIN" in prompt for prompt in read.prompts)
    assert any("aplicada" in line for line in lines)
    seen = await _listing()
    assert any("has_mother" in line and "Zeta Parent" in line for line in seen)
    assert not any("has_parent" in line for line in seen)
    assert not any("Zeta Parent" in line for line in lines)  # the name stays out of the writes


async def test_label_child_applies_beside_the_child_row(cli_db: int) -> None:
    row = await _seed_relation(cli_db, "child_of", "Omega Child")
    read = _Script("SI", _PIN)
    lines, write = _sink()
    request = AdminRequest(command="label-child", row_id=row, side="son")
    assert await _run(request, read, write) == 0
    assert any("aplicada" in line for line in lines)
    seen = await _listing()
    assert any("son_of" in line and "Omega Child" in line for line in seen)
    assert any("child_of" in line and "Omega Child" in line for line in seen)


@pytest.mark.parametrize(
    "command, predicate, side",
    [("label-parent", "has_parent", "father"), ("label-child", "child_of", "daughter")],
)
async def test_a_dry_run_of_a_label_writes_nothing_and_asks_nothing(
    cli_db: int, command: str, predicate: str, side: str
) -> None:
    row = await _seed_relation(cli_db, predicate, "Zeta Person")
    read = _Script()
    lines, write = _sink()
    request = AdminRequest(command=command, row_id=row, side=side, dry_run=True)
    assert await _run(request, read, write) == 1
    assert any("Prueba en seco" in line for line in lines)
    assert read.prompts == []
    assert any(predicate in line for line in await _listing())


async def test_a_wrong_pin_leaves_the_label_unwritten(cli_db: int) -> None:
    row = await _seed_relation(cli_db, "has_parent", "Zeta Parent")
    read = _Script("SI", "000000", "000000", "000000")
    lines, write = _sink()
    request = AdminRequest(command="label-parent", row_id=row, side="mother")
    assert await _run(request, read, write) == 1
    assert any("Sin verificación" in line for line in lines)
    assert any("has_parent" in line for line in await _listing())


async def test_a_label_on_the_wrong_row_prints_the_closed_reason(cli_db: int) -> None:
    row = await _seed_relation(cli_db, "child_of", "Zeta Child")
    read = _Script("SI", _PIN)
    lines, write = _sink()
    request = AdminRequest(command="label-parent", row_id=row, side="mother")
    assert await _run(request, read, write) == 1
    assert any("rechazada" in line and "wrong_relation_kind" in line for line in lines)
    assert any("child_of" in line for line in await _listing())


def test_the_parser_takes_the_two_verbs_with_a_closed_side(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["iroko-admin", "label-parent", "7", "mother", "--dry-run"])
    request = admin_cli._request(admin_cli._parser().parse_args())
    assert (request.command, request.row_id, request.side, request.dry_run) == (
        "label-parent",
        7,
        "mother",
        True,
    )
    for argv in (["label-parent", "7", "daughter"], ["label-child", "7", "mother"]):
        with pytest.raises(SystemExit):
            admin_cli._parser().parse_args(argv)


async def test_audit_lists_operations_without_a_value(cli_db: int) -> None:
    read = _Script("el té verde", "SI")
    _, write = _sink()
    await _run(AdminRequest(command="add", field="likes"), read, write)
    lines, write2 = _sink()
    code = await _run(AdminRequest(command="audit"), _Script(), write2)
    assert code == 0
    assert any("add" in line and "likes" in line for line in lines)
    assert not any("el té verde" in line for line in lines)
