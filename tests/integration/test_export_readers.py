# ruff: noqa: S608  # the seed statements interpolate fixed canary instants, never input
"""A reader per table for an export, history and archive included (Plan 0087 Task 2, D-5).

Each table's owner module returns every stored row (superseded, revoked, archived beside the
active ones) as ``StoredRows``; a credential and a voiceprint come out as references only, never
the salt, the verifier or the embedding. The store is seeded with raw SQL and canaries only.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from server.memory import (
    admin_audit,
    biometric_consent,
    candidates,
    care_contacts,
    commissioning,
    conversation_consent,
    conversation_episodes,
    conversation_record,
    declarative,
    deletion_register,
    household_authorization,
    meta,
    owner_credentials,
    pending_store,
    recall_store,
    relational_v4,
    voice_consent,
)
from server.memory.export_model import StoredRows, stored_rows
from server.settings import settings
from server.vision import faces
from server.voice import voiceprints

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_T = "2026-11-19T10:00:00.000000+00:00"
_LATER = "2026-11-19T11:00:00.000000+00:00"
_SALT = b"CANARY-SALT-BYTES"
_VERIFIER = b"CANARY-VERIFIER-BYTES"
_EMBEDDING = b"CANARY-EMBEDDING-BYTES"

# Every statement fills only what its CHECKs need; ids are fixed so the expectations can name them.
_SEED = (
    "INSERT INTO entities (id, name, type, created_at, updated_at) VALUES "
    f"(1, 'Canario', 'person', '{_T}', '{_T}'), (2, 'Gaviota', 'person', '{_T}', '{_T}'), "
    f"(3, 'Golondrina', 'person', '{_T}', '{_T}')",
    "INSERT INTO literal_facts_v4 (id, subject_entity_id, predicate, value_text, asserted_at, "
    "lifecycle, superseded_by, superseded_at, archived_at) VALUES "
    f"(1, 1, 'likes', 'el té', '{_T}', 'superseded', NULL, '{_LATER}', NULL), "
    f"(2, 1, 'likes', 'el café', '{_LATER}', 'active', NULL, NULL, NULL), "
    f"(3, 2, 'likes', 'el mar', '{_T}', 'active', NULL, NULL, '{_LATER}')",
    "UPDATE literal_facts_v4 SET superseded_by = 2 WHERE id = 1",
    "INSERT INTO entity_relations_v4 (id, source_entity_id, predicate, target_entity_id, "
    "asserted_at, lifecycle) VALUES "
    f"(1, 1, 'parent_of', 2, '{_T}', 'active'), (2, 1, 'friend_of', 3, '{_T}', 'revoked')",
    "INSERT INTO care_contacts (id, owner_entity_id, contact_entity_id, role, phone, channel, "
    "confirmed_at, created_at, revoked_at) VALUES "
    f"(1, 1, 3, 'doctor', '+56900000000', 'admin_local', '{_T}', '{_T}', NULL), "
    f"(2, 1, 3, 'neighbor', '+56900000001', 'admin_local', '{_T}', '{_T}', '{_LATER}')",
    "INSERT INTO household_role_assignments (id, person_entity_id, role, reason, granted_at, "
    f"revoked_at) VALUES (1, 1, 'owner', 'alta', '{_T}', NULL), "
    f"(2, 3, 'adult', 'alta', '{_T}', '{_LATER}')",
    "INSERT INTO conversation_consent_grants (id, person_entity_id, purpose, notice_version, "
    f"granted_at, revoked_at) VALUES (1, 1, 'conversation_storage', 'v1', '{_T}', '{_LATER}'), "
    f"(2, 1, 'conversation_storage', 'v1', '{_LATER}', NULL)",
    "INSERT INTO face_consent_grants (id, person_entity_id, purpose, granted_at, revoked_at) "
    f"VALUES (1, 1, 'owner_authentication', '{_T}', '{_LATER}'), "
    f"(2, 1, 'owner_authentication', '{_LATER}', NULL)",
    "INSERT INTO voice_consent_grants (id, person_entity_id, purpose, granted_at, revoked_at) "
    f"VALUES (1, 1, 'speaker_evidence', '{_T}', '{_LATER}'), "
    f"(2, 1, 'speaker_evidence', '{_LATER}', NULL)",
    "INSERT INTO face_profiles (id, entity_id, label, created_at) VALUES "
    f"(1, 1, 'Canario', '{_T}')",
    "INSERT INTO conversation_records (id, owner_entity_id, started_at, last_turn_at, closed_at, "
    f"eligible, expires_at, episode_status) VALUES (1, 1, '{_T}', '{_T}', '{_LATER}', 1, "
    f"'{_LATER}', 'done')",
    "INSERT INTO conversation_turns (id, record_id, correlation_id, said_at, verdict, heard, said) "
    f"VALUES (1, 1, 'c-1', '{_T}', 'verified', 'hola', 'hola Canario'), "
    f"(2, 1, 'c-2', '{_T}', 'not_owner', 'soy Gaviota', 'hola')",
    "INSERT INTO conversation_episodes (id, source_record_id, owner_entity_id, visibility, "
    "sensitivity, summary, model, created_at, expires_at) VALUES "
    f"(1, 1, 1, 'personal', 'normal', 'Me contaste que tomaste el té.', 'm', '{_T}', '{_LATER}')",
    "INSERT INTO recall_units (id, owner_entity_id, source_record_id, kind, body, said_at, "
    "visibility, sensitivity, correlation_id, turn_id, archived_at) VALUES "
    f"(1, 1, 1, 'turn', 'hola', '{_T}', 'personal', 'normal', 'c-1', 1, NULL), "
    f"(2, 1, 1, 'turn', 'soy Gaviota', '{_T}', 'personal', 'normal', 'c-2', 2, '{_LATER}')",
    "INSERT INTO pending_topics (id, owner_entity_id, source_record_id, correlation_id, said_day, "
    "due_day, topic, heard, state, sensitivity, created_at, archived_at) VALUES "
    f"(1, 1, 1, 'c-1', '2026-11-19', '2026-11-20', 'el té', NULL, 'open', 'normal', '{_T}', "
    f"'{_LATER}')",
    "INSERT INTO memory_candidates (id, subject_person_id, asserted_by_person_id, predicate, "
    "value_text, value_key, status, channel, source_correlation_id, proposed_at, expires_at) "
    f"VALUES (1, 1, 1, 'likes', 'el té', 'el te', 'proposed', 'voice_stream', 'c-1', '{_T}', "
    f"'{_LATER}'), (2, 1, 1, 'likes', NULL, NULL, 'rejected', 'voice_stream', 'c-2', '{_T}', "
    f"'{_LATER}')",
    "INSERT INTO commissioning_records (id, installation_id, started_at, interviewer_label, "
    "interviewer_role, confirmation_mode, disk_encryption, pool_version, closed_at) VALUES "
    f"(1, '{'0' * 36}', '{_T}', 'Canario', 'builder', 'builder_is_owner', 'unknown', 1, "
    f"'{_LATER}')",
    "INSERT INTO commissioning_sections (commissioning_id, section, status, recorded_at) VALUES "
    f"(1, 'allergies', 'none', '{_T}'), (1, 'conditions', 'declined', '{_T}')",
    "INSERT INTO authorization_audit_events (id, actor_entity_id, target_entity_id, action, "
    "data_categories, decision, policy_id, reason, correlation_id, evaluated_at) VALUES "
    f"(1, 1, 2, 'read', '[]', 'allowed', 'p', 'r', 'c-1', '{_T}')",
    "INSERT INTO admin_audit (id, recorded_at, actor_label, actor_role, channel, operation, "
    "target_kind, field_id, target_entity_id, outcome, reason) VALUES "
    f"(1, '{_T}', 'Canario', 'owner', 'admin_local', 'export', 'household_data', 'all', NULL, "
    "'applied', NULL)",
)


@pytest.fixture
async def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "export-readers.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        conn = db.get_conn()
        for statement in _SEED:
            await conn.execute(statement)
        await conn.execute(
            "INSERT INTO owner_pin_credentials (id, person_entity_id, algorithm, parameters_json, "
            "salt, verifier, created_at, updated_at) VALUES (1, 1, 'scrypt', '{}', ?, ?, ?, ?)",
            (_SALT, _VERIFIER, _T, _T),
        )
        await conn.execute(
            "INSERT INTO voice_profiles (id, entity_id, label, embedding, model_id, created_at) "
            "VALUES (1, 1, 'Canario', ?, 'ecapa', ?)",
            (_EMBEDDING, _T),
        )
        await conn.commit()
        yield
    finally:
        await db.close_db()
        db._conn = None


def _column(rows: StoredRows, key: str) -> list[object]:
    index = rows.columns.index(key)
    return [row[index] for row in rows.rows]


async def test_entities_for_export_holds_every_person(seeded: None) -> None:
    rows = await declarative.entities_for_export()
    assert _column(rows, "id") == [1, 2, 3]
    assert _column(rows, "name") == ["Canario", "Gaviota", "Golondrina"]


async def test_facts_for_export_keeps_the_history_and_the_archive(seeded: None) -> None:
    rows = await relational_v4.facts_for_export()
    assert _column(rows, "id") == [1, 2, 3]
    assert _column(rows, "lifecycle") == ["superseded", "active", "active"]
    assert _column(rows, "superseded_by") == [2, None, None]
    assert _column(rows, "archived_at") == [None, None, _LATER]
    assert "confidence" not in rows.columns


async def test_relations_for_export_keeps_a_revoked_relation(seeded: None) -> None:
    rows = await relational_v4.relations_for_export()
    assert _column(rows, "lifecycle") == ["active", "revoked"]
    assert _column(rows, "target_entity_id") == [2, 3]


async def test_contacts_for_export_keeps_a_revoked_contact_and_its_phone(seeded: None) -> None:
    rows = await care_contacts.contacts_for_export()
    assert _column(rows, "phone") == ["+56900000000", "+56900000001"]
    assert _column(rows, "revoked_at") == [None, _LATER]


async def test_roles_and_decisions_for_export(seeded: None) -> None:
    roles = await household_authorization.roles_for_export()
    assert _column(roles, "revoked_at") == [None, _LATER]
    decisions = await household_authorization.decisions_for_export()
    assert _column(decisions, "actor_entity_id") == [1]
    assert _column(decisions, "decision") == ["allowed"]


@pytest.mark.parametrize(
    "reader",
    [
        conversation_consent.conversation_consents_for_export,
        biometric_consent.face_consents_for_export,
        voice_consent.voice_consents_for_export,
    ],
)
async def test_each_consent_reader_keeps_a_revoked_grant(
    seeded: None, reader: Callable[[], Awaitable[StoredRows]]
) -> None:
    rows = await reader()
    assert rows.columns == ("id", "person_entity_id", "purpose", "granted_at", "revoked_at")
    assert _column(rows, "revoked_at") == [_LATER, None]


async def test_credentials_for_export_is_a_reference_only(seeded: None) -> None:
    rows = await owner_credentials.credentials_for_export()
    assert not {"salt", "verifier", "parameters_json"} & set(rows.columns)
    assert _column(rows, "algorithm") == ["scrypt"]
    assert _SALT.decode() not in repr(rows)
    assert _VERIFIER.decode() not in repr(rows)


async def test_profiles_for_export_hold_no_vector(seeded: None) -> None:
    face_rows = await faces.face_profiles_for_export()
    voice_rows = await voiceprints.voice_profiles_for_export()
    assert _column(face_rows, "label") == ["Canario"]
    assert _column(voice_rows, "model_id") == ["ecapa"]
    assert "embedding" not in voice_rows.columns
    assert _EMBEDDING.decode() not in repr(voice_rows)


async def test_records_and_turns_for_export(seeded: None) -> None:
    records = await conversation_record.records_for_export()
    assert _column(records, "episode_status") == ["done"]
    turns = await conversation_record.turns_for_export()
    assert _column(turns, "verdict") == ["verified", "not_owner"]
    assert _column(turns, "heard") == ["hola", "soy Gaviota"]


async def test_episodes_units_and_topics_keep_the_archive(seeded: None) -> None:
    episodes = await conversation_episodes.episodes_for_export()
    assert _column(episodes, "source_record_id") == [1]
    units = await recall_store.units_for_export()
    assert _column(units, "archived_at") == [None, _LATER]
    assert "embedding_model" not in units.columns
    topics = await pending_store.topics_for_export()
    assert _column(topics, "archived_at") == [_LATER]


async def test_only_live_candidates_are_exported(seeded: None) -> None:
    rows = await candidates.live_candidates_for_export()
    assert _column(rows, "id") == [1]
    assert _column(rows, "status") == ["proposed"]


async def test_the_acta_and_its_sections(seeded: None) -> None:
    records = await commissioning.commissioning_records_for_export()
    assert _column(records, "confirmation_mode") == ["builder_is_owner"]
    sections = await commissioning.commissioning_sections_for_export()
    assert _column(sections, "section") == ["allergies", "conditions"]


async def test_the_admin_audit_for_export(seeded: None) -> None:
    rows = await admin_audit.audit_for_export()
    assert _column(rows, "target_kind") == ["household_data"]
    assert _column(rows, "field_id") == ["all"]


async def test_the_register_lines_as_stored(seeded: None) -> None:
    lines = [
        {"seq": 1, "kind": "turn", "id": 9, "at": _T},
        {"seq": 2, "kind": "entity", "id": 4, "at": _LATER},
    ]
    deletion_register.register_path().write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    rows = deletion_register.lines_for_export()
    assert rows.columns == ("seq", "kind", "id", "at")
    assert rows.rows == ((1, "turn", 9, _T), (2, "entity", 4, _LATER))


async def test_no_register_file_is_no_line(seeded: None) -> None:
    assert deletion_register.lines_for_export().rows == ()


async def test_the_counts_of_what_is_not_exported(seeded: None) -> None:
    fts, vectors = await recall_store.projection_counts()
    assert fts == 2
    assert vectors == 0
    assert await faces.count_face_vectors() == 0
    assert await meta.count_flags() >= 0
    assert await db.count_retired_memories() == 0


def test_a_vector_never_becomes_a_cell() -> None:
    with pytest.raises(TypeError):
        stored_rows(("embedding",), [(_EMBEDDING,)])
    with pytest.raises(TypeError):
        stored_rows(("confidence",), [(0.5,)])
