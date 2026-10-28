"""Admin add/change through the writers, with the audit (Plan 0073 Task 4, ADR 0025 decision 4).

`admin_ops` applies one change through a canonical writer with `admin_local` and writes one audit
row, all in one transaction. A sensitive write needs the owner's PIN (passed as `owner_verified`);
without it the write is refused and audited `owner_not_verified`. No audit row or log holds a value.
Canaries and invented phones only.
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
from server.memory.admin_ops import (
    AdminActor,
    ContactTerms,
    apply_contact_edit,
    apply_literal_edit,
    requires_owner_verification,
)
from server.memory.care_contacts import ContactRole, list_active_contacts
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.relational_v4 import list_active_facts
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-10-27T10:00:00.000000+00:00"
_PHONE = "+56900000001"
_ACTOR = AdminActor(label="Canary Admin", role=AdminActorRole.BUILDER)


@pytest.fixture
async def ops_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "admin-ops.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        yield owner
    finally:
        await db.close_db()
        db._conn = None


# --- the verification rule ------------------------------------------------------------------------


def test_requires_owner_verification_rule() -> None:
    assert requires_owner_verification(
        target_kind=TargetKind.CARE_CONTACT, predicate=None, subject_is_owner=True
    )
    assert requires_owner_verification(
        target_kind=TargetKind.POOL_LITERAL, predicate="likes", subject_is_owner=False
    )
    assert requires_owner_verification(
        target_kind=TargetKind.POOL_LITERAL, predicate="medication", subject_is_owner=True
    )
    assert requires_owner_verification(
        target_kind=TargetKind.POOL_LITERAL, predicate="home_address", subject_is_owner=True
    )
    assert not requires_owner_verification(
        target_kind=TargetKind.POOL_LITERAL, predicate="likes", subject_is_owner=True
    )
    assert not requires_owner_verification(
        target_kind=TargetKind.POOL_LITERAL, predicate="preferred_name", subject_is_owner=True
    )


# --- literal add/change ---------------------------------------------------------------------------


async def test_add_a_non_sensitive_literal_applies_and_audits(ops_db: int) -> None:
    owner = ops_db
    outcome = await apply_literal_edit(
        actor=_ACTOR,
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="likes",
        value="el té verde",
        kind=AdminOperationKind.ADD,
        now=_NOW,
        owner_verified=False,
    )
    assert outcome.status is AdminOutcomeStatus.APPLIED
    assert [fact.value_text for fact in await list_active_facts(owner)] == ["el té verde"]
    rows = await list_admin_operations()
    assert len(rows) == 1
    assert rows[0].operation is AdminOperationKind.ADD
    assert rows[0].outcome is AdminOutcomeStatus.APPLIED
    assert rows[0].field_id == "likes"


async def test_change_a_single_value_literal_supersedes(ops_db: int) -> None:
    owner = ops_db
    await apply_literal_edit(
        actor=_ACTOR,
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="preferred_name",
        value="Canary Old",
        kind=AdminOperationKind.ADD,
        now=_NOW,
        owner_verified=False,
    )
    outcome = await apply_literal_edit(
        actor=_ACTOR,
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="preferred_name",
        value="Canary New",
        kind=AdminOperationKind.CHANGE,
        now=_NOW,
        owner_verified=False,
    )
    assert outcome.status is AdminOutcomeStatus.APPLIED
    assert [fact.value_text for fact in await list_active_facts(owner)] == ["Canary New"]


async def test_a_sensitive_literal_without_the_pin_is_refused_and_audited(ops_db: int) -> None:
    owner = ops_db
    outcome = await apply_literal_edit(
        actor=_ACTOR,
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="medication",
        value="Canary pill 10mg",
        kind=AdminOperationKind.ADD,
        now=_NOW,
        owner_verified=False,
    )
    assert outcome.status is AdminOutcomeStatus.REFUSED
    assert outcome.reason == "owner_not_verified"
    assert await list_active_facts(owner) == []
    rows = await list_admin_operations()
    assert rows[0].outcome is AdminOutcomeStatus.REFUSED
    assert rows[0].reason == "owner_not_verified"
    assert "Canary pill 10mg" not in repr(rows[0])


async def test_a_writer_refusal_is_reported_and_audited(ops_db: int) -> None:
    owner = ops_db
    # access_code is unstorable; with the PIN granted the writer still refuses it.
    outcome = await apply_literal_edit(
        actor=_ACTOR,
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="access_code",
        value="1234",
        kind=AdminOperationKind.ADD,
        now=_NOW,
        owner_verified=True,
    )
    assert outcome.status is AdminOutcomeStatus.REFUSED
    assert outcome.reason == "unstorable_value"
    assert await list_active_facts(owner) == []
    assert (await list_admin_operations())[0].reason == "unstorable_value"


# --- contact add ----------------------------------------------------------------------------------


async def test_add_a_contact_needs_the_pin(ops_db: int) -> None:
    owner = ops_db
    contact = await create_third_party(name="Canary Neighbour", type="person")
    terms = ContactTerms(phone=_PHONE, relationship="vecina", call_order=1)
    refused = await apply_contact_edit(
        actor=_ACTOR,
        owner_entity_id=owner,
        contact_entity_id=contact,
        role=ContactRole.NEIGHBOR,
        terms=terms,
        kind=AdminOperationKind.ADD,
        now=_NOW,
        owner_verified=False,
    )
    assert refused.status is AdminOutcomeStatus.REFUSED
    assert refused.reason == "owner_not_verified"
    assert await list_active_contacts(owner) == ()

    applied = await apply_contact_edit(
        actor=_ACTOR,
        owner_entity_id=owner,
        contact_entity_id=contact,
        role=ContactRole.NEIGHBOR,
        terms=terms,
        kind=AdminOperationKind.ADD,
        now=_NOW,
        owner_verified=True,
    )
    assert applied.status is AdminOutcomeStatus.APPLIED
    assert len(await list_active_contacts(owner)) == 1
    audited = await list_admin_operations()
    assert audited[0].target_kind is TargetKind.CARE_CONTACT
    assert _PHONE not in repr(audited[0])


async def test_an_unexpected_failure_rolls_back_the_write_and_the_audit(
    ops_db: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = ops_db

    async def _boom(**_kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("server.memory.admin_ops.write_literal", _boom)
    with pytest.raises(RuntimeError):
        await apply_literal_edit(
            actor=_ACTOR,
            owner_entity_id=owner,
            subject_entity_id=owner,
            predicate="likes",
            value="el té",
            kind=AdminOperationKind.ADD,
            now=_NOW,
            owner_verified=True,
        )
    assert await list_admin_operations() == ()
