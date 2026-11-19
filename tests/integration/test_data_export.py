# ruff: noqa: S608  # the seed statements interpolate fixed canary instants, never input
"""The content of «todo» and of one person (Plan 0087 Task 3, D-5 and D-6).

A seeded store: the owner Canario, a child Gaviota, a second adult Golondrina (Gaviota's other
parent) with a ``medical`` fact, a care contact Pelícano, a canary Canaria only talked about, a
``not_owner`` turn naming Gaviota, an owner fact naming Gaviota, an archived unit and two lines of
the deletion register. Canaries only.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from server.memory.data_export import SECTION_KEYS, export_counts, gather_export, holds_nothing
from server.memory.export_model import ExportDocument, ExportScope, ExportScopeKind
from server.memory.forget_scope import person_scope
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T = "2026-11-19T10:00:00.000000+00:00"
_LATER = "2026-11-19T11:00:00.000000+00:00"
_NOW = "2026-11-19T12:00:00.000000+00:00"
_OWNER, _CHILD, _ADULT, _DOCTOR = 1, 2, 3, 4
_MEDICAL = "la insulina de Golondrina"
_OWNER_FACT = "llevar a Gaviota al colegio"
_OTHER_VOICE = "Gaviota tiene fiebre, dijo otra voz"

_SEED = (
    "INSERT INTO entities (id, name, type, created_at, updated_at) VALUES "
    f"(1, 'Canario', 'person', '{_T}', '{_T}'), (2, 'Gaviota', 'person', '{_T}', '{_T}'), "
    f"(3, 'Golondrina', 'person', '{_T}', '{_T}'), (4, 'Pelícano', 'person', '{_T}', '{_T}')",
    "INSERT INTO household_role_assignments (id, person_entity_id, role, reason, granted_at) "
    f"VALUES (1, 1, 'owner', 'alta', '{_T}')",
    "INSERT INTO literal_facts_v4 (id, subject_entity_id, predicate, value_text, asserted_at, "
    "lifecycle, visibility, sensitivity, superseded_by, superseded_at) VALUES "
    f"(1, 1, 'likes', 'el té', '{_T}', 'superseded', 'personal', 'normal', NULL, '{_LATER}'), "
    f"(2, 1, 'likes', 'el café', '{_LATER}', 'active', 'personal', 'normal', NULL, NULL), "
    f"(3, 1, 'routine', '{_OWNER_FACT}', '{_T}', 'active', 'personal', 'normal', NULL, NULL), "
    f"(4, 2, 'likes', 'el mar', '{_T}', 'active', 'household', 'normal', NULL, NULL), "
    f"(5, 3, 'medication', '{_MEDICAL}', '{_T}', 'active', 'private', 'medical', NULL, NULL)",
    "UPDATE literal_facts_v4 SET superseded_by = 2 WHERE id = 1",
    "INSERT INTO entity_relations_v4 (id, source_entity_id, predicate, target_entity_id, "
    "asserted_at, lifecycle, visibility) VALUES "
    f"(1, 1, 'parent_of', 2, '{_T}', 'active', 'personal'), "
    f"(2, 3, 'parent_of', 2, '{_T}', 'active', 'personal'), "
    f"(3, 3, 'member_of_household', 1, '{_T}', 'active', 'personal')",
    "INSERT INTO care_contacts (id, owner_entity_id, contact_entity_id, role, phone, channel, "
    f"confirmed_at, created_at) VALUES (1, 1, 4, 'doctor', '+56900000000', 'admin_local', "
    f"'{_T}', '{_T}')",
    "INSERT INTO conversation_records (id, owner_entity_id, started_at, last_turn_at, closed_at, "
    f"eligible, expires_at, episode_status) VALUES (1, 1, '{_T}', '{_T}', '{_LATER}', 1, "
    f"'2027-01-01T00:00:00.000000+00:00', 'done')",
    "INSERT INTO conversation_turns (id, record_id, correlation_id, said_at, verdict, heard, said) "
    f"VALUES (1, 1, 'c-1', '{_T}', 'verified', 'Ayer almorcé con Canaria', 'Qué rico'), "
    f"(2, 1, 'c-2', '{_T}', 'not_owner', '{_OTHER_VOICE}', 'Lo siento'), "
    f"(3, 1, 'c-3', '{_T}', 'verified', 'Gaviota juega en el patio', 'Qué bien')",
    "INSERT INTO conversation_episodes (id, source_record_id, owner_entity_id, visibility, "
    "sensitivity, summary, model, created_at, expires_at) VALUES (1, 1, 1, 'personal', 'normal', "
    f"'Me contaste que almorzaste con Canaria.', 'm', '{_T}', "
    "'2027-01-01T00:00:00.000000+00:00')",
    "INSERT INTO recall_units (id, owner_entity_id, source_record_id, kind, body, said_at, "
    "visibility, sensitivity, correlation_id, turn_id, archived_at) VALUES "
    f"(1, 1, 1, 'turn', 'Ayer almorcé con Canaria', '{_T}', 'personal', 'normal', 'c-1', 1, "
    f"'{_LATER}'), "
    f"(2, 1, 1, 'turn', '{_OTHER_VOICE}', '{_T}', 'personal', 'normal', 'c-2', 2, NULL)",
    "INSERT INTO admin_audit (id, recorded_at, actor_label, actor_role, channel, operation, "
    "target_kind, field_id, target_entity_id, outcome, reason) VALUES "
    f"(1, '{_T}', 'Canario', 'owner', 'admin_local', 'add', 'pool_literal', 'likes', 2, "
    "'applied', NULL), "
    f"(2, '{_T}', 'Canario', 'owner', 'admin_local', 'add', 'care_contact', 'doctor', 4, "
    "'applied', NULL)",
    "INSERT INTO authorization_audit_events (id, actor_entity_id, target_entity_id, action, "
    "data_categories, decision, policy_id, reason, correlation_id, evaluated_at) VALUES "
    f"(1, 1, 2, 'read', '[]', 'allowed', 'p', 'r', 'c-1', '{_T}'), "
    f"(2, 3, 3, 'read', '[]', 'denied', 'p', 'r', 'c-2', '{_T}')",
)


@pytest.fixture
async def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "data-export.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        conn = db.get_conn()
        for statement in _SEED:
            await conn.execute(statement)
        await conn.commit()
        (tmp_path / "deletions.jsonl").write_text(
            json.dumps({"seq": 1, "kind": "turn", "id": 9, "at": _T})
            + "\n"
            + json.dumps({"seq": 2, "kind": "entity", "id": 8, "at": _LATER})
            + "\n",
            encoding="utf-8",
        )
        yield
    finally:
        await db.close_db()
        db._conn = None


async def _gather(
    kind: ExportScopeKind, entity_id: int | None = None, words: str | None = None
) -> ExportDocument:
    scope = ExportScope(kind=kind, entity_id=entity_id, words=words)
    return await gather_export(scope, owner_entity_id=_OWNER, now=_NOW)


def _rows(document: ExportDocument, key: str) -> list[dict[str, object]]:
    (section,) = [s for s in document.sections if s.key == key]
    keys = [column.key for column in section.columns]
    return [dict(zip(keys, row, strict=True)) for row in section.rows]


def _ids(document: ExportDocument, key: str) -> list[object]:
    return [row["id"] for row in _rows(document, key)]


def _text(document: ExportDocument) -> str:
    return repr([section.rows for section in document.sections])


async def test_all_holds_every_section_in_order(seeded: None) -> None:
    document = await _gather(ExportScopeKind.ALL)
    assert tuple(section.key for section in document.sections) == SECTION_KEYS
    assert document.schema_version == db.latest_schema_version()
    assert document.generated_at == _NOW
    assert _ids(document, "datos") == [1, 2, 3, 4, 5]
    assert _ids(document, "turnos") == [1, 2, 3]
    assert all(column.label for section in document.sections for column in section.columns)


async def test_the_owner_export_leaves_out_other_voices(seeded: None) -> None:
    document = await _gather(ExportScopeKind.PERSON, entity_id=_OWNER)
    assert _ids(document, "turnos") == [1, 3]
    assert _ids(document, "recuerdos") == [1]
    assert _OTHER_VOICE not in _text(document)
    assert _ids(document, "datos") == [1, 2, 3]
    assert _ids(document, "contactos") == [1]
    assert _ids(document, "auditoria_admin") == [1, 2]


async def test_a_child_export_holds_no_other_adults_private_fact(seeded: None) -> None:
    document = await _gather(ExportScopeKind.PERSON, entity_id=_CHILD)
    assert _ids(document, "datos") == [4]
    assert _MEDICAL not in _text(document)
    assert _ids(document, "relaciones") == [1, 2]
    names = {row["source_name"] for row in _rows(document, "relaciones")}
    assert names == {"Canario", "Golondrina"}


async def test_a_person_export_leaves_out_owner_facts_naming_them(seeded: None) -> None:
    document = await _gather(ExportScopeKind.PERSON, entity_id=_CHILD)
    assert _OWNER_FACT not in _text(document)
    assert _ids(document, "personas") == [_CHILD]
    assert _ids(document, "auditoria_admin") == [1]
    assert _ids(document, "decisiones") == [1]


async def test_a_not_owner_turn_is_only_in_all(seeded: None) -> None:
    everything = await _gather(ExportScopeKind.ALL)
    child = await _gather(ExportScopeKind.PERSON, entity_id=_CHILD)
    owner = await _gather(ExportScopeKind.PERSON, entity_id=_OWNER)
    assert _OTHER_VOICE in _text(everything)
    assert _OTHER_VOICE not in _text(child)
    assert _OTHER_VOICE not in _text(owner)
    assert _ids(child, "turnos") == [3]


async def test_a_person_export_holds_what_forget_would_delete(seeded: None) -> None:
    scope = await person_scope(_OWNER, now=_NOW, entity_id=_CHILD, for_deletion=True)
    document = await _gather(ExportScopeKind.PERSON, entity_id=_CHILD)
    assert set(_ids(document, "datos")) == set(scope.facts)
    assert set(_ids(document, "relaciones")) == set(scope.relations)
    assert set(_ids(document, "turnos")) == set(scope.turns) - {2}
    assert {row["source_record_id"] for row in _rows(document, "diario")} == set(scope.episodes)


async def test_a_name_only_export_holds_the_turns_that_name_it(seeded: None) -> None:
    document = await _gather(ExportScopeKind.PERSON, words="Canaria")
    assert _ids(document, "turnos") == [1]
    assert _ids(document, "diario") == [1]
    assert _ids(document, "personas") == []
    assert _ids(document, "conversaciones") == [1]


async def test_an_archived_row_is_exported_with_its_instant(seeded: None) -> None:
    document = await _gather(ExportScopeKind.ALL)
    units = _rows(document, "recuerdos")
    assert [row["archived_at"] for row in units] == [_LATER, None]


async def test_the_register_is_only_in_all(seeded: None) -> None:
    everything = await _gather(ExportScopeKind.ALL)
    child = await _gather(ExportScopeKind.PERSON, entity_id=_CHILD)
    assert [row["seq"] for row in _rows(everything, "borrados")] == [1, 2]
    assert _rows(child, "borrados") == []


async def test_no_sale_counts_each_excluded_class(seeded: None) -> None:
    child = await _gather(ExportScopeKind.PERSON, entity_id=_CHILD)
    counts = {row["what"]: row["rows"] for row in _rows(child, "no_sale")}
    assert counts["turnos de otra voz"] == 1
    assert counts["datos tuyos que la nombran"] == 1
    assert counts["registro de borrados"] == 2
    everything = await _gather(ExportScopeKind.ALL)
    counts = {row["what"]: row["rows"] for row in _rows(everything, "no_sale")}
    assert counts["índice de texto de los recuerdos"] == 2
    assert "turnos de otra voz" not in counts


async def test_a_name_only_export_holds_no_decision_without_an_actor(seeded: None) -> None:
    await db.get_conn().execute(
        "INSERT INTO authorization_audit_events (id, actor_entity_id, target_entity_id, action, "
        "data_categories, decision, policy_id, reason, correlation_id, evaluated_at) VALUES "
        f"(3, NULL, NULL, 'read', '[]', 'denied', 'p', 'r', 'c-3', '{_T}')"
    )
    await db.get_conn().commit()
    document = await _gather(ExportScopeKind.PERSON, words="Canaria")
    assert _rows(document, "decisiones") == []
    assert _rows(document, "auditoria_admin") == []


async def test_an_episode_reached_only_by_another_voice_stays_out(seeded: None) -> None:
    conn = db.get_conn()
    await conn.execute(
        "INSERT INTO conversation_records (id, owner_entity_id, started_at, last_turn_at, "
        f"closed_at, eligible, expires_at, episode_status) VALUES (2, 1, '{_T}', '{_T}', "
        f"'{_LATER}', 1, '2027-01-01T00:00:00.000000+00:00', 'done')"
    )
    await conn.execute(
        "INSERT INTO conversation_turns (id, record_id, correlation_id, said_at, verdict, heard, "
        f"said) VALUES (4, 2, 'c-4', '{_T}', 'not_owner', 'Gaviota se cayó', 'Uy')"
    )
    await conn.execute(
        "INSERT INTO conversation_episodes (id, source_record_id, owner_entity_id, visibility, "
        "sensitivity, summary, model, created_at, expires_at) VALUES (2, 2, 1, 'personal', "
        f"'normal', 'Alguien contó una caída.', 'm', '{_T}', '2027-01-01T00:00:00.000000+00:00')"
    )
    await conn.commit()
    document = await _gather(ExportScopeKind.PERSON, entity_id=_CHILD)
    assert {row["source_record_id"] for row in _rows(document, "diario")} == {1}
    assert _ids(document, "conversaciones") == [1]
    assert "Alguien contó una caída." not in _text(document)


async def test_nothing_found_is_empty(seeded: None) -> None:
    document = await _gather(ExportScopeKind.PERSON, words="Albatros")
    assert holds_nothing(document)
    assert not holds_nothing(await _gather(ExportScopeKind.PERSON, words="Canaria"))


async def test_the_counts_say_one_line_per_section(seeded: None) -> None:
    document = await _gather(ExportScopeKind.ALL)
    lines = export_counts(document)
    assert len(lines) == len(SECTION_KEYS)
    assert lines[0] == "Personas: 4 filas"
