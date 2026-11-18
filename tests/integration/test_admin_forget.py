"""`iroko-admin forget` and `archive` (Plan 0086 Task 4, D-13): for good with the PIN, audited.

Canary names and an invented PIN only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.admin_cli import AdminRequest, run_admin_command
from server.cognition.pin_credentials import hash_pin
from server.conversation_admin import render_record
from server.memory import conversation_record as record, relational_v4
from server.memory.care_contacts import ContactRole, write_contact
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.memory.deletion_register import register_path
from server.memory.forget_scope import archive_rows
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.owner_credentials import save_owner_pin_credential
from server.memory.predicate_registry import resolve_predicate
from server.memory.write_types import WriteChannel
from server.settings import settings
from server.timestamps import instant_text

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-11-17T12:00:00.000000+00:00"
_ARCHIVED = "2026-11-17T11:00:00.000000+00:00"
_PIN = "482173"
_T0 = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)


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
async def ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, int]]:
    """An owner with a PIN, a taste, a friend with a care contact, and three told turns.

    The first record (two turns: one names the diary-only canary, one does not) has an episode;
    the second record names the alta friend.
    """
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "forget.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    owner = await upsert_entity(name="Canary Owner", type="person")
    await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
    await save_owner_pin_credential(person_entity_id=owner, credential=hash_pin(_PIN))
    likes = resolve_predicate("likes")
    assert likes is not None
    taste = await relational_v4.assert_literal_fact(
        subject_entity_id=owner, definition=likes, value="el té"
    )
    friend = await upsert_entity(name="Petirroja", type="person")
    contact = await write_contact(
        owner_entity_id=owner,
        contact_entity_id=friend,
        role=ContactRole.TRUSTED,
        phone="+56922222222",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=instant_text(_T0),
    )
    turns: list[int] = []
    for seconds, heard in (
        (0, "fui al cine con Canaria"),
        (60, "hoy llovió mucho"),
        (7200, "almorcé con Petirroja"),
    ):
        turn = make_turn(
            heard,
            "qué bueno",
            voice=TurnVerdict.VERIFIED,
            correlation_id=UUID(int=seconds + 1),
            at=_T0 + timedelta(seconds=seconds),
        )
        await record.append_turn(turn, owner_entity_id=owner, now=turn.at)
        async with db.transaction() as conn:
            turn_id = await record.find_turn_id(conn, turn.correlation_id)
        assert turn_id is not None
        turns.append(turn_id)
    await record.close_idle_records(_T0 + timedelta(hours=4))
    first_record = await record.turn_record_id(turns[0])
    assert first_record is not None
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (?, ?, 'personal', 'normal', 'La persona contó que vio una película.', "
            "'canary', ?, ?)",
            (first_record, owner, instant_text(_T0), instant_text(_T0 + timedelta(days=365))),
        )
        # A candidate confirmed from the first turn: its fact is the taste.
        await conn.execute(
            "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
            "status, channel, source_correlation_id, proposed_at, expires_at, offer_count, "
            "promoted_fact_id, source_turn_id, resolved_at) "
            "VALUES (?, ?, 'likes', 'confirmed', 'voice_stream', ?, ?, ?, 1, ?, ?, ?)",
            (
                owner,
                owner,
                str(UUID(int=1)),
                instant_text(_T0),
                instant_text(_T0),
                taste.id,
                turns[0],
                instant_text(_T0),
            ),
        )
    await db.close_db()
    db._conn = None
    yield {
        "owner": owner,
        "taste": taste.id,
        "friend": friend,
        "contact": contact.id,
        "canary_turn": turns[0],
        "plain_turn": turns[1],
        "friend_turn": turns[2],
        "first_record": first_record,
    }
    if db._conn is not None:
        await db.close_db()
        db._conn = None


async def _run(request: AdminRequest, read: _Script, write: Callable[[str], None]) -> int:
    return await run_admin_command(
        request, read_text=read, read_secret=read, write_text=write, now=_NOW
    )


async def _count(sql: str, *params: object) -> int:
    await db.open_db()
    try:
        cursor = await db.get_conn().execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
    finally:
        await db.close_db()
        db._conn = None
    assert row is not None
    return int(row[0])


def _forget(
    kind: str, row_id: int | None = None, *, name: str | None = None, dry_run: bool = False
) -> AdminRequest:
    return AdminRequest(command="forget", kind=kind, row_id=row_id, name=name, dry_run=dry_run)


async def test_forget_fact_deletes_it_under_the_pin_and_audits_it(ids: dict[str, int]) -> None:
    lines, write = _sink()

    code = await _run(_forget("fact", ids["taste"]), _Script("SI", _PIN), write)

    assert code == 0
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 0
    assert (
        await _count(
            "SELECT COUNT(*) FROM admin_audit WHERE operation = 'delete' AND outcome = 'applied' "
            "AND target_kind = 'pool_literal' AND field_id = ?",
            f"fact:{ids['taste']}",
        )
        == 1
    )
    assert "literal_fact" in register_path().read_text(encoding="utf-8")
    assert any("no se puede deshacer" in line for line in lines)


async def test_a_wrong_pin_deletes_nothing_and_audits_the_refusal(ids: dict[str, int]) -> None:
    code = await _run(
        _forget("fact", ids["taste"]), _Script("SI", "000000", "000000", "000000"), _sink()[1]
    )

    assert code == 1
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 1
    assert (
        await _count(
            "SELECT COUNT(*) FROM admin_audit WHERE outcome = 'refused' AND reason = 'pin'"
        )
        == 1
    )


async def test_a_dry_run_deletes_nothing(ids: dict[str, int]) -> None:
    code = await _run(_forget("fact", ids["taste"], dry_run=True), _Script(), _sink()[1])

    assert code == 1
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 1


async def test_forget_turn_takes_the_whole_episode_and_names_the_kept_fact(
    ids: dict[str, int],
) -> None:
    lines, write = _sink()

    code = await _run(_forget("turn", ids["canary_turn"]), _Script("SI", _PIN), write)

    assert code == 0
    assert (
        await _count("SELECT COUNT(*) FROM conversation_turns WHERE id = ?", ids["canary_turn"])
        == 0
    )
    assert (
        await _count("SELECT COUNT(*) FROM conversation_turns WHERE id = ?", ids["plain_turn"]) == 1
    )
    assert await _count("SELECT COUNT(*) FROM conversation_episodes") == 0
    assert await _count("SELECT COUNT(*) FROM memory_candidates") == 0
    # Forgetting a story keeps a fact the owner confirmed from it (ADR 0038 row 10).
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4 WHERE id = ?", ids["taste"]) == 1
    assert any(f"({ids['taste']})" in line for line in lines)


async def test_forget_person_by_name_deletes_only_what_names_the_canary(
    ids: dict[str, int],
) -> None:
    code = await _run(_forget("person", name="Canaria"), _Script("SI", _PIN), _sink()[1])

    assert code == 0
    assert (
        await _count("SELECT COUNT(*) FROM conversation_turns WHERE id = ?", ids["canary_turn"])
        == 0
    )
    assert (
        await _count("SELECT COUNT(*) FROM conversation_turns WHERE id = ?", ids["plain_turn"]) == 1
    )
    assert (
        await _count("SELECT COUNT(*) FROM conversation_turns WHERE id = ?", ids["friend_turn"])
        == 1
    )
    assert await _count("SELECT COUNT(*) FROM conversation_episodes") == 0
    assert await _count("SELECT COUNT(*) FROM entities WHERE id = ?", ids["friend"]) == 1


async def test_forget_person_by_id_deletes_the_contact_before_the_entity(
    ids: dict[str, int],
) -> None:
    code = await _run(_forget("person", ids["friend"]), _Script("SI", _PIN), _sink()[1])

    assert code == 0
    assert await _count("SELECT COUNT(*) FROM care_contacts") == 0
    assert await _count("SELECT COUNT(*) FROM entities WHERE id = ?", ids["friend"]) == 0
    assert (
        await _count("SELECT COUNT(*) FROM conversation_turns WHERE id = ?", ids["friend_turn"])
        == 0
    )
    lines = register_path().read_text(encoding="utf-8").splitlines()
    assert lines[0].count("care_contact") == 1
    assert "entity" in lines[-1]


async def test_forget_person_refuses_the_owner(ids: dict[str, int]) -> None:
    lines, write = _sink()

    code = await _run(_forget("person", ids["owner"]), _Script(), write)

    assert code == 1
    assert any("enrolada" in line for line in lines)
    assert await _count("SELECT COUNT(*) FROM entities WHERE id = ?", ids["owner"]) == 1


async def test_archive_list_groups_by_instant_and_restore_brings_the_group_back(
    ids: dict[str, int],
) -> None:
    await db.open_db()
    async with db.transaction() as conn:
        await archive_rows(conn, facts=(ids["taste"],), at=_ARCHIVED)
    await db.close_db()
    db._conn = None
    lines, write = _sink()

    assert await _run(AdminRequest(command="archive", action="list"), _Script(_PIN), write) == 0
    assert any(line.startswith(f"{_ARCHIVED}: 1 datos") for line in lines)
    assert any("el té" in line for line in lines)

    code = await _run(
        AdminRequest(command="archive", action="restore", at=_ARCHIVED),
        _Script(_PIN, "SI"),
        _sink()[1],
    )

    assert code == 0
    assert (
        await _count(
            "SELECT COUNT(*) FROM literal_facts_v4 WHERE archived_at IS NULL AND id = ?",
            ids["taste"],
        )
        == 1
    )
    assert (
        await _count(
            "SELECT COUNT(*) FROM admin_audit WHERE operation = 'change' AND field_id = 'archive'"
        )
        == 1
    )


async def test_the_export_names_each_turn_by_its_id(ids: dict[str, int]) -> None:
    await db.open_db()
    try:
        view = await record.read_record(ids["first_record"])
    finally:
        await db.close_db()
        db._conn = None
    assert view is not None

    text = render_record(view, None)

    assert f"turno {ids['canary_turn']} · Persona" in text
