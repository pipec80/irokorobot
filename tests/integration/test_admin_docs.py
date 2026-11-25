"""`iroko-admin docs add | list | remove` (Plan 0088 Task B3, D-16, D-19): the owner's documents.

Through ``run_admin_command``: the PIN first, then the extraction, the level, what was found and
``SI``; one audit row per attempt (``document``), never a title or a text. Ollama is a double
(down unless a test says otherwise). Canary files and an invented PIN only.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

import httpx
import pytest
from server.admin_cli import AdminRequest, run_admin_command
from server.cognition.pin_credentials import hash_pin
from server.memory import conversation_jobs, deletion_register, document_store
from server.memory.admin_audit import list_admin_operations
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.owner_credentials import save_owner_pin_credential
from server.settings import settings

from server import admin_cli, db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-11-23T12:00:00.000000+00:00"
_PIN = "482173"
_TITLE = "Manual zzcanario"
_BODY = "# Manual\n\nzzfiltro: gírelo a la izquierda.\n\n## Tambor\n\nzztambor limpio.\n"


class _Script:
    """A scripted reader: returns queued answers in order."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)

    def __call__(self, _prompt: str) -> str:
        return self.answers.pop(0)


def _down(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


def _up(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"embeddings": [[1.0] + [0.0] * 767], "prompt_eval_count": 5})


def _ollama(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    monkeypatch.setattr(
        admin_cli,
        "ollama_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    """An owner with a PIN; the database closed, Ollama down."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "data" / "docs.db")
    monkeypatch.setattr(settings, "embedding_model", "canary-embed")
    (tmp_path / "data").mkdir()
    _ollama(monkeypatch, _down)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    person = await upsert_entity(name="Canario", type="person")
    await bootstrap_initial_owner(person_entity_id=person, confirmed_person_entity_id=person)
    await save_owner_pin_credential(person_entity_id=person, credential=hash_pin(_PIN))
    await db.close_db()
    db._conn = None
    yield person
    await db.close_db()
    db._conn = None


@pytest.fixture
def manual(tmp_path: Path) -> Path:
    path = tmp_path / "manual.md"
    path.write_bytes(_BODY.encode())
    return path


def _add(path: Path, *, level: str | None = "normal") -> AdminRequest:
    return AdminRequest(command="docs", action="add", file=path, title=_TITLE, level=level)


async def _run(request: AdminRequest, *answers: str, pin: str = _PIN) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = await run_admin_command(
        request,
        read_text=_Script(*answers),
        read_secret=_Script(pin, pin, pin),
        write_text=lines.append,
        now=_NOW,
    )
    return code, lines


async def _sources(owner: int) -> list[document_store.DocumentSource]:
    await db.open_db()
    try:
        return await document_store.sources_of(owner_entity_id=owner)
    finally:
        await db.close_db()


async def _audit() -> list[tuple[str, str, str | None, str, str | None]]:
    await db.open_db()
    try:
        rows = await list_admin_operations()
    finally:
        await db.close_db()
    return [
        (r.operation.value, r.target_kind.value, r.field_id, r.outcome.value, r.reason)
        for r in rows
    ]


async def test_add_without_the_pin_stores_nothing_and_audits_the_refusal(
    owner: int, manual: Path
) -> None:
    code, lines = await _run(_add(manual), "SI", pin="000000")

    assert code == 1
    assert await _sources(owner) == []
    assert await _audit() == [("add", "document", None, "refused", "pin")]
    assert not any("zzfiltro" in line for line in lines)


async def test_add_without_si_stores_nothing(owner: int, manual: Path) -> None:
    code, _ = await _run(_add(manual), "no")

    assert code == 1
    assert await _sources(owner) == []


async def test_add_with_pin_and_si_stores_one_source_and_one_clean_audit_row(
    owner: int, manual: Path
) -> None:
    code, lines = await _run(_add(manual), "SI")

    assert code == 0
    (source,) = await _sources(owner)
    assert (source.title, source.level, source.format, source.sections) == (
        _TITLE,
        "normal",
        "md",
        2,
    )
    assert any("zzfiltro" in line for line in lines)  # the first lines, this terminal only
    audit = await _audit()
    assert audit == [("add", "document", str(source.id), "applied", None)]
    assert _TITLE not in json.dumps(audit)


async def test_the_level_is_asked_when_no_flag_gives_it(owner: int, manual: Path) -> None:
    code, _ = await _run(_add(manual, level=None), "sensitive", "SI")

    assert code == 0
    assert [s.level for s in await _sources(owner)] == ["sensitive"]


async def test_a_document_holding_a_code_is_refused(owner: int, tmp_path: Path) -> None:
    path = tmp_path / "wifi.txt"
    path.write_bytes(b"La clave del wifi: zorro4821.")

    code, lines = await _run(_add(path), "SI")

    assert code == 1
    assert "Este documento tiene una clave o un código; no lo guardo." in lines
    assert await _sources(owner) == []
    assert await _audit() == [("add", "document", None, "refused", "secret")]


async def test_an_unreadable_format_is_refused_with_its_reason(owner: int, tmp_path: Path) -> None:
    path = tmp_path / "carta.docx"
    path.write_bytes(b"PK")

    code, lines = await _run(_add(path), "SI")

    assert code == 1
    assert "Ese formato todavía no lo leo." in lines
    assert await _audit() == [("add", "document", None, "refused", "format")]


async def test_with_ollama_up_the_sections_are_embedded_at_once(
    owner: int, manual: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ollama(monkeypatch, _up)

    assert (await _run(_add(manual), "SI"))[0] == 0

    await db.open_db()
    try:
        assert await document_store.sections_without_vector(10) == []
    finally:
        await db.close_db()


async def test_list_shows_counts_and_levels_under_the_pin(owner: int, manual: Path) -> None:
    await _run(_add(manual), "SI")

    code, lines = await _run(AdminRequest(command="docs", action="list"))

    assert code == 0
    assert any("normal" in line and "md" in line and "2 secciones" in line for line in lines)
    assert (await _audit())[0] == ("list", "document", None, "applied", None)


async def test_remove_deletes_everything_and_its_register_line_replays_idempotently(
    owner: int, manual: Path
) -> None:
    await _run(_add(manual), "SI")
    (source,) = await _sources(owner)

    code, _ = await _run(AdminRequest(command="docs", action="remove", row_id=source.id), "SI")

    assert code == 0
    assert await _sources(owner) == []
    register = deletion_register.register_path().read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["kind"] for line in register] == ["document"]
    await db.open_db()
    try:
        cursor = await db.get_conn().execute(
            "SELECT (SELECT COUNT(*) FROM document_sections) "
            "+ (SELECT COUNT(*) FROM document_sections_fts_docsize) "
            "+ (SELECT COUNT(*) FROM document_sections_vec)"
        )
        assert (await cursor.fetchone()) == (0,)
        await cursor.close()
        assert await deletion_register.replay_register() == 0
    finally:
        await db.close_db()
    assert (await _audit())[0] == ("delete", "document", str(source.id), "applied", None)


async def test_remove_of_an_unknown_id_deletes_nothing(owner: int) -> None:
    code, lines = await _run(AdminRequest(command="docs", action="remove", row_id=999), "SI")

    assert code == 1
    assert "No hay un documento con ese id." in lines
    assert not deletion_register.register_path().exists()


async def test_the_job_fills_the_sections_left_without_a_vector(
    owner: int, manual: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _run(_add(manual), "SI")
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "documents_enabled", True)

    await db.open_db()
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_up)) as client:
            await conversation_jobs.run_once(client, datetime(2026, 11, 23, 13, tzinfo=UTC))
        assert await document_store.sections_without_vector(10) == []
    finally:
        await db.close_db()


async def test_a_title_s_control_characters_are_not_stored(owner: int, manual: Path) -> None:
    request = AdminRequest(
        command="docs", action="add", file=manual, title="Manual\x1b[31m zz", level="normal"
    )

    assert (await _run(request, "SI"))[0] == 0

    (source,) = await _sources(owner)
    assert "\x1b" not in source.title
