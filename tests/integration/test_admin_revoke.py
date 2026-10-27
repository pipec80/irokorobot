"""Admin revoke = supersede to inactive, never a hard delete (Plan 0073 Task 5, ADR 0025 dec 4).

A revoked fact, relation or contact keeps its row (forgetting is CM-6); the readers stop serving
it. A second revoke of the same id is a no-op. `apply_revoke` needs the owner's PIN for a contact
or a non-owner subject and audits one row holding no value. Canaries and invented phones only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.admin_audit import (
    AdminActorRole,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    list_admin_operations,
)
from server.memory.admin_ops import AdminActor, apply_revoke
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.care_contacts import (
    ContactRole,
    list_active_contacts,
    revoke_contact,
    write_contact,
)
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.relational_v4 import (
    list_active_facts,
    list_active_relations,
    revoke_entity_relation,
    revoke_literal_fact,
)
from server.memory.write_types import WriteChannel
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-10-27T10:00:00.000000+00:00"
_LATER = "2026-10-27T12:00:00.000000+00:00"
_PHONE = "+56900000001"
_ACTOR = AdminActor(label="Canary Admin", role=AdminActorRole.BUILDER)


@pytest.fixture
async def revoke_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "admin-revoke.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        yield owner
    finally:
        await db.close_db()
        db._conn = None


async def _count(table: str) -> int:
    cursor = await db.get_conn().execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


# --- repository revoke (history, not deletion) ----------------------------------------------------


async def test_revoke_literal_fact_is_history(revoke_db: int) -> None:
    owner = revoke_db
    fact = await write_literal(
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="preferred_name",
        value="Canary",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    assert await revoke_literal_fact(fact.id, revoked_at=_LATER) is True
    assert await list_active_facts(owner) == []
    assert await _count("literal_facts_v4") == 1  # kept, not deleted
    assert await revoke_literal_fact(fact.id, revoked_at=_LATER) is False  # idempotent


async def test_revoke_entity_relation_is_history(revoke_db: int) -> None:
    owner = revoke_db
    child = await create_third_party(name="Canary Child", type="person")
    relation = await write_relation(
        owner_entity_id=owner,
        source_entity_id=child,
        predicate="child_of",
        target_entity_id=owner,
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    assert await revoke_entity_relation(relation.id, revoked_at=_LATER) is True
    assert await list_active_relations(owner) == []
    assert await _count("entity_relations_v4") == 1
    assert await revoke_entity_relation(relation.id, revoked_at=_LATER) is False


async def test_revoke_contact_is_history(revoke_db: int) -> None:
    owner = revoke_db
    contact = await create_third_party(name="Canary Neighbour", type="person")
    row = await write_contact(
        owner_entity_id=owner,
        contact_entity_id=contact,
        role=ContactRole.NEIGHBOR,
        phone=_PHONE,
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    assert await revoke_contact(row.id, revoked_at=_LATER) is True
    assert await list_active_contacts(owner) == ()
    assert await _count("care_contacts") == 1
    assert await revoke_contact(row.id, revoked_at=_LATER) is False


# --- apply_revoke: the PIN gate and the audit -----------------------------------------------------


async def test_apply_revoke_of_a_contact_needs_the_pin(revoke_db: int) -> None:
    owner = revoke_db
    contact = await create_third_party(name="Canary Neighbour", type="person")
    row = await write_contact(
        owner_entity_id=owner,
        contact_entity_id=contact,
        role=ContactRole.NEIGHBOR,
        phone=_PHONE,
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    refused = await apply_revoke(
        actor=_ACTOR,
        target_kind=TargetKind.CARE_CONTACT,
        target_id=row.id,
        subject_is_owner=True,
        predicate=None,
        now=_LATER,
        owner_verified=False,
    )
    assert refused.status is AdminOutcomeStatus.REFUSED
    assert refused.reason == "owner_not_verified"
    assert len(await list_active_contacts(owner)) == 1

    applied = await apply_revoke(
        actor=_ACTOR,
        target_kind=TargetKind.CARE_CONTACT,
        target_id=row.id,
        subject_is_owner=True,
        predicate=None,
        now=_LATER,
        owner_verified=True,
    )
    assert applied.status is AdminOutcomeStatus.APPLIED
    assert await list_active_contacts(owner) == ()
    audited = await list_admin_operations()
    assert audited[0].operation is AdminOperationKind.REVOKE
    assert _PHONE not in repr(audited[0])
