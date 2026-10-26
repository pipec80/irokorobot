"""The `seed-import` command (Plan 0071 Task 6a, ADR 0024 decisions 6 and 11).

The command opens an existing database at the latest schema (it never creates nor migrates one),
prints the database it uses, runs a dry run by default and applies only after the review question
is answered with exactly ``SI``. Every name, phone and value is an invented canary.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
from typing import TYPE_CHECKING

from pydantic import SecretStr
import pytest
from server.memory.canonical_writer import write_literal
from server.memory.commissioning import (
    CommissioningInput,
    ConfirmationMode,
    DiskEncryption,
    InterviewerRole,
    close_commissioning,
    get_open_commissioning,
)
from server.memory.write_types import WriteChannel
from server.personal_setup import PersonalSetupInput, apply_personal_setup
from server.settings import settings

from server import db, seed_cli
from tests.integration.seed_household import NOW, OWNER_NAME
from tests.unit.seed_data import Toml, full_seed, minimal_seed, to_toml

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_REVIEW_OWNER = "¿La persona titular revisó este resumen y lo aprueba?"
_REVIEW_REPRESENTATIVE = "¿La persona que representa a la titular revisó este resumen y lo aprueba?"
_CONFIRM = "Escribe SI para aplicar: "


def _details(
    mode: ConfirmationMode = ConfirmationMode.OWNER_IN_PERSON,
    role: InterviewerRole = InterviewerRole.BUILDER,
) -> CommissioningInput:
    return CommissioningInput(
        interviewer_label="Canary Interviewer",
        interviewer_role=role,
        confirmation_mode=mode,
        disk_encryption=DiskEncryption.DECLARED_NO,
    )


async def _with_db[T](action: Callable[[], Awaitable[T]]) -> T:
    """Open the test database, run one action and close it again (the command opens its own)."""
    await db.open_db()
    try:
        return await action()
    finally:
        await db.close_db()


@pytest.fixture
async def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """A closed database at the latest schema, with the owner and a PIN and nothing else."""
    path = tmp_path / "brain.db"
    monkeypatch.setattr(settings, "brain_db_path", path)
    db._conn = None

    async def setup() -> None:
        await db.run_migrations()
        await apply_personal_setup(
            PersonalSetupInput(owner_name=OWNER_NAME, child_names=(), pin=SecretStr("482173"))
        )

    await _with_db(setup)
    yield path
    await db.close_db()
    db._conn = None


class _Terminal:
    """Fake terminal: the prompts asked, the lines printed and the answers to give."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []
        self.lines: list[str] = []

    def read_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)

    def write_text(self, line: str) -> None:
        self.lines.append(line)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _file(tmp_path: Path, data: Toml, name: str = "seed.toml") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_toml(data), encoding="utf-8")
    return path


async def _command(
    path: Path,
    terminal: _Terminal,
    *,
    apply: bool = False,
    replace: bool = False,
    commissioning: CommissioningInput | None = None,
) -> int:
    return await seed_cli.run_seed_command(
        path,
        apply=apply,
        replace=replace,
        commissioning=commissioning,
        read_text=terminal.read_text,
        write_text=terminal.write_text,
        now=NOW,
    )


async def _count(table: str) -> int:
    async def count() -> int:
        cursor = await db.get_conn().execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        return int(row[0])

    return await _with_db(count)


# --- the dry run ------------------------------------------------------------------------------


async def test_a_dry_run_prints_the_database_first_and_writes_nothing(
    prepared: Path, tmp_path: Path
) -> None:
    terminal = _Terminal()

    code = await _command(_file(tmp_path, full_seed()), terminal)

    assert code == 0
    assert terminal.lines[0] == f"Base de datos: {prepared.resolve()}"
    assert "Canary Child" in terminal.text
    assert "+56900000001" in terminal.text
    assert terminal.prompts == []
    assert await _count("literal_facts_v4") == 0
    assert await _count("commissioning_records") == 0


async def test_a_section_without_a_status_is_reported_as_not_asked(
    prepared: Path, tmp_path: Path
) -> None:
    del prepared
    terminal = _Terminal()

    await _command(_file(tmp_path, minimal_seed()), terminal)

    assert "no preguntada" in terminal.text


async def test_the_summary_reminds_what_to_do_with_the_file_and_the_screen(
    prepared: Path, tmp_path: Path
) -> None:
    del prepared
    terminal = _Terminal()

    await _command(_file(tmp_path, full_seed()), terminal)

    assert "no se borró" in terminal.text
    assert "solo en esta máquina" in terminal.text
    assert "limpia la pantalla" in terminal.text


async def test_a_dry_run_with_problems_exits_1(prepared: Path, tmp_path: Path) -> None:
    del prepared
    await _command(
        _file(tmp_path, full_seed()), _Terminal("SI"), apply=True, commissioning=_details()
    )
    data = full_seed()
    data["owner"]["birth_date"] = "1951-05-17"
    terminal = _Terminal()

    code = await _command(_file(tmp_path, data), terminal)

    assert code == 1
    assert "value_conflict" in terminal.text


# --- the apply --------------------------------------------------------------------------------


async def test_an_apply_asks_the_review_and_writes_on_si(prepared: Path, tmp_path: Path) -> None:
    del prepared
    terminal = _Terminal("SI")

    code = await _command(
        _file(tmp_path, full_seed()), terminal, apply=True, commissioning=_details()
    )

    assert code == 0
    assert _REVIEW_OWNER in terminal.text
    assert terminal.prompts == [_CONFIRM]
    assert await _count("care_contacts") == 2
    assert await _count("commissioning_records") == 1


async def test_a_representative_is_asked_the_representative_question(
    prepared: Path, tmp_path: Path
) -> None:
    del prepared
    terminal = _Terminal("SI")

    await _command(
        _file(tmp_path, full_seed()),
        terminal,
        apply=True,
        commissioning=_details(ConfirmationMode.REPRESENTATIVE, InterviewerRole.FAMILY),
    )

    assert _REVIEW_REPRESENTATIVE in terminal.text
    assert _REVIEW_OWNER not in terminal.text


@pytest.mark.parametrize("answer", ["si", "SÍ", "SI ", "", "no"])
async def test_anything_but_si_cancels_and_writes_nothing(
    prepared: Path, tmp_path: Path, answer: str
) -> None:
    del prepared
    terminal = _Terminal(answer)

    code = await _command(
        _file(tmp_path, full_seed()), terminal, apply=True, commissioning=_details()
    )

    assert code == 1
    assert "Carga cancelada." in terminal.lines
    assert await _count("literal_facts_v4") == 0
    assert await _count("commissioning_records") == 0


async def test_a_problem_never_reaches_the_question(prepared: Path, tmp_path: Path) -> None:
    del prepared
    await _command(
        _file(tmp_path, full_seed()), _Terminal("SI"), apply=True, commissioning=_details()
    )
    data = full_seed()
    data["partner"] = {"name": "Canary Other"}
    terminal = _Terminal("SI")

    code = await _command(_file(tmp_path, data), terminal, apply=True)

    assert code == 1
    assert terminal.prompts == []


async def test_a_first_apply_needs_the_interviewers_declaration(
    prepared: Path, tmp_path: Path
) -> None:
    del prepared
    terminal = _Terminal("SI")

    code = await _command(_file(tmp_path, full_seed()), terminal, apply=True)

    assert code == 1
    assert "--interviewer" in terminal.text
    assert terminal.prompts == []
    assert await _count("literal_facts_v4") == 0


async def test_builder_is_owner_needs_the_builder_role(prepared: Path, tmp_path: Path) -> None:
    del prepared
    terminal = _Terminal("SI")

    code = await _command(
        _file(tmp_path, full_seed()),
        terminal,
        apply=True,
        commissioning=_details(ConfirmationMode.BUILDER_IS_OWNER, InterviewerRole.FAMILY),
    )

    assert code == 1
    assert "builder" in terminal.text
    assert terminal.prompts == []
    assert await _count("commissioning_records") == 0


async def test_a_second_apply_reuses_the_record_without_the_declaration(
    prepared: Path, tmp_path: Path
) -> None:
    del prepared
    await _command(
        _file(tmp_path, full_seed()), _Terminal("SI"), apply=True, commissioning=_details()
    )
    terminal = _Terminal("SI")

    code = await _command(_file(tmp_path, full_seed()), terminal, apply=True)

    assert code == 0
    assert await _count("commissioning_records") == 1


# --- refusals ---------------------------------------------------------------------------------


async def test_a_missing_database_is_refused_and_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    absent = tmp_path / "nowhere" / "brain.db"
    monkeypatch.setattr(settings, "brain_db_path", absent)
    db._conn = None
    terminal = _Terminal()

    code = await _command(_file(tmp_path, full_seed()), terminal)

    assert code == 1
    assert "just setup-personal" in terminal.text
    assert not absent.exists()
    assert not absent.parent.exists()


async def test_an_old_schema_is_refused_and_not_migrated(prepared: Path, tmp_path: Path) -> None:
    with sqlite3.connect(prepared) as raw:
        raw.execute("PRAGMA user_version = 10")
    terminal = _Terminal()

    code = await _command(_file(tmp_path, full_seed()), terminal)

    assert code == 1
    assert "just setup-personal status" in terminal.text
    with sqlite3.connect(prepared) as raw:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 10


# A process that writes in WAL mode and exits without closing leaves its committed frames in the
# -wal file; the next read-write connection to close would fold them into the main file.
_CRASHED_WRITER = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute("PRAGMA wal_autocheckpoint = 0")
connection.execute("PRAGMA user_version = 10")
connection.execute("CREATE TABLE IF NOT EXISTS canary_pending (x INTEGER)")
connection.execute("INSERT INTO canary_pending VALUES (1)")
connection.commit()
os._exit(0)
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def test_an_outdated_database_is_refused_without_touching_its_file(
    prepared: Path, tmp_path: Path
) -> None:
    """The refusal reads the version read-only: the main file and its log stay byte for byte."""
    subprocess.run(  # noqa: S603 — this interpreter and a literal script, no outside input
        [sys.executable, "-c", _CRASHED_WRITER, str(prepared)], check=True, timeout=60
    )
    wal = prepared.with_name(prepared.name + "-wal")
    assert wal.stat().st_size > 0
    before = (_sha256(prepared), _sha256(wal))
    terminal = _Terminal()

    code = await _command(_file(tmp_path, full_seed()), terminal)

    assert code == 1
    assert "just setup-personal status" in terminal.text
    assert (_sha256(prepared), _sha256(wal)) == before


async def test_a_file_with_errors_is_refused_before_the_database_is_opened(
    prepared: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del prepared

    async def never() -> None:
        raise AssertionError("the database was opened")

    monkeypatch.setattr(db, "open_db", never)
    data = full_seed()
    data["owner"]["blood_type"] = "Z"
    terminal = _Terminal()

    code = await _command(_file(tmp_path, data), terminal)

    assert code == 1
    assert "owner.blood_type: invalid_value" in terminal.text


async def test_a_database_without_an_owner_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "empty.db"
    monkeypatch.setattr(settings, "brain_db_path", path)
    db._conn = None
    await _with_db(db.run_migrations)
    terminal = _Terminal()

    code = await _command(_file(tmp_path, full_seed()), terminal)

    assert code == 1
    assert "just setup-personal" in terminal.text
    assert await _count("entities") == 0


async def test_another_owner_name_is_refused(prepared: Path, tmp_path: Path) -> None:
    del prepared
    data = full_seed()
    data["owner"]["name"] = "Canary Somebody"
    terminal = _Terminal()

    code = await _command(_file(tmp_path, data), terminal)

    assert code == 1
    assert "no coincide" in terminal.text
    assert "Canary Somebody" not in terminal.text


async def test_a_file_with_an_error_is_refused_with_its_problems(
    prepared: Path, tmp_path: Path
) -> None:
    del prepared
    data = full_seed()
    data["owner"]["blood_type"] = "Z"
    terminal = _Terminal()

    code = await _command(_file(tmp_path, data), terminal)

    assert code == 1
    assert "owner.blood_type: invalid_value" in terminal.text


async def test_the_example_cannot_be_applied(prepared: Path, tmp_path: Path) -> None:
    del prepared
    terminal = _Terminal("SI")

    code = await _command(
        _file(tmp_path, full_seed(), "household.example.toml"),
        terminal,
        apply=True,
        commissioning=_details(),
    )

    assert code == 1
    assert "copia la plantilla a data/seed/" in terminal.text
    assert await _count("literal_facts_v4") == 0


async def test_a_closed_commissioning_is_refused(prepared: Path, tmp_path: Path) -> None:
    del prepared
    await _command(
        _file(tmp_path, full_seed()), _Terminal("SI"), apply=True, commissioning=_details()
    )

    async def close() -> None:
        record = await get_open_commissioning()
        assert record is not None
        await close_commissioning(record.id, NOW)

    await _with_db(close)
    terminal = _Terminal()

    code = await _command(_file(tmp_path, full_seed()), terminal)

    assert code == 1
    assert "cerr" in terminal.text


async def test_a_replacement_after_voice_memory_is_refused(prepared: Path, tmp_path: Path) -> None:
    del prepared
    await _command(
        _file(tmp_path, full_seed()), _Terminal("SI"), apply=True, commissioning=_details()
    )

    async def speak() -> None:
        owner = await db.get_conn().execute("SELECT id FROM entities WHERE name = ?", (OWNER_NAME,))
        row = await owner.fetchone()
        await owner.close()
        assert row is not None
        await write_literal(
            owner_entity_id=int(row[0]),
            subject_entity_id=int(row[0]),
            predicate="likes",
            value="el mar",
            channel=WriteChannel.VOICE_STREAM,
            confirmed_at=NOW,
        )

    await _with_db(speak)
    terminal = _Terminal()

    code = await _command(_file(tmp_path, full_seed()), terminal, replace=True)

    assert code == 1
    assert "por voz" in terminal.text


async def test_a_path_inside_the_repository_outside_data_warns(
    prepared: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del prepared
    monkeypatch.setattr(seed_cli, "_REPOSITORY", tmp_path)
    outside = _Terminal()
    inside = _Terminal()

    await _command(_file(tmp_path, full_seed(), "seed.toml"), outside)
    await _command(_file(tmp_path, full_seed(), "data/seed/seed.toml"), inside)

    assert "fuera de data/" in outside.text
    assert "fuera de data/" not in inside.text


async def test_a_locked_database_prints_the_setup_message(prepared: Path, tmp_path: Path) -> None:
    holder = sqlite3.connect(prepared)
    holder.execute("BEGIN IMMEDIATE")
    terminal = _Terminal()
    try:
        code = await _command(_file(tmp_path, full_seed()), terminal)
    finally:
        holder.rollback()
        holder.close()

    assert code == 1
    assert "Database is locked" in terminal.text


# --- main -------------------------------------------------------------------------------------


def test_main_refuses_when_the_server_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    absent = tmp_path / "brain.db"
    monkeypatch.setattr(settings, "brain_db_path", absent)
    monkeypatch.setattr(seed_cli, "_server_answers", lambda: True)
    monkeypatch.setattr(sys, "argv", ["seed-import", str(_file(tmp_path, full_seed()))])

    with pytest.raises(SystemExit) as caught:
        seed_cli.main()

    assert caught.value.code == 1
    assert "servidor" in capsys.readouterr().out
    assert not absent.exists()


def test_main_prints_the_schema_without_a_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    absent = tmp_path / "brain.db"
    monkeypatch.setattr(settings, "brain_db_path", absent)
    monkeypatch.setattr(seed_cli, "_server_answers", lambda: pytest.fail("probed"))
    monkeypatch.setattr(sys, "argv", ["seed-import", "--print-schema"])

    seed_cli.main()

    assert '"schema_version"' in capsys.readouterr().out
    assert not absent.exists()


def test_main_joins_a_path_split_by_spaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "con espacios"
    path = _file(folder, full_seed())
    seen: list[Path] = []

    async def fake(target: Path, **_kwargs: object) -> int:
        seen.append(target)
        return 0

    monkeypatch.setattr(seed_cli, "_server_answers", lambda: False)
    monkeypatch.setattr(seed_cli, "run_seed_command", fake)
    monkeypatch.setattr(sys, "argv", ["seed-import", *str(path).split(" ")])

    with pytest.raises(SystemExit) as caught:
        seed_cli.main()

    assert caught.value.code == 0
    assert seen == [path]
    capsys.readouterr()
