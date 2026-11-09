"""Admin add/change through the writers, with the audit (Plan 0073 Task 4, ADR 0025 decision 4).

`admin_ops` applies one change through a canonical writer with `admin_local` and writes one audit
row, all in one transaction. A sensitive write needs the owner's PIN (passed as `owner_verified`);
without it the write is refused and audited `owner_not_verified`. No audit row or log holds a value.
Canaries and invented phones only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from server.exceptions import WriteRefusedError
from server.memory.admin_audit import (
    AdminActorRole,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    list_admin_operations,
)
from server.memory.admin_ops import (
    AdminActor,
    AdminOutcome,
    ContactTerms,
    apply_contact_edit,
    apply_literal_edit,
    apply_side_label,
    requires_owner_verification,
)
from server.memory.canonical_writer import write_relation
from server.memory.care_contacts import ContactRole, list_active_contacts
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.relational_v4 import (
    AssertionLifecycle,
    get_entity_relation,
    list_active_facts,
    revoke_entity_relation,
)
from server.memory.write_types import WriteChannel
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from server.memory.admin_ops import SideLabel
    from server.memory.relational_v4 import EntityRelationV4

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


# --- label a parent or a child (Plan 0080 Task 6, D-7) ---------------------------------------------

_PARENT_SIDES = [("mother", "has_mother"), ("father", "has_father")]
_CHILD_SIDES = [("daughter", "daughter_of"), ("son", "son_of")]
_ALL_SIDES = [*_PARENT_SIDES, *_CHILD_SIDES]
_PERSON = "Zeta Relative"


async def _relation(
    owner: int, predicate: str, *, source: int | None = None, target: int | None = None
) -> EntityRelationV4:
    """Store one relation the way the alta did (the person is a canary third party)."""
    given = source if source is not None else target
    person = given if given is not None else await create_third_party(name=_PERSON, type="person")
    is_membership = predicate in {"child_of", "daughter_of", "son_of"}
    return await write_relation(
        owner_entity_id=owner,
        source_entity_id=source if source is not None else (person if is_membership else owner),
        predicate=predicate,
        target_entity_id=target if target is not None else (owner if is_membership else person),
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )


async def _all_relations() -> list[tuple[int, str, int, int, str]]:
    """Every relation row, active or not: what a refusal must leave exactly as it was."""
    cursor = await db.get_conn().execute(
        "SELECT id, predicate, source_entity_id, target_entity_id, lifecycle "
        "FROM entity_relations_v4 ORDER BY id"
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [(int(r[0]), str(r[1]), int(r[2]), int(r[3]), str(r[4])) for r in rows]


async def _active(predicate: str) -> list[tuple[int, int]]:
    """The (source, target) of every active relation of one predicate."""
    return [
        (source, target)
        for _, name, source, target, lifecycle in await _all_relations()
        if name == predicate and lifecycle == "active"
    ]


async def _label(owner: int, relation_id: int, side: str, *, verified: bool = True) -> AdminOutcome:
    return await apply_side_label(
        actor=_ACTOR,
        owner_entity_id=owner,
        relation_id=relation_id,
        side=cast("SideLabel", side),
        now=_NOW,
        owner_verified=verified,
    )


async def _audit_dump() -> str:
    """Every audit column of every row, as one string (to prove no name is in it)."""
    cursor = await db.get_conn().execute("SELECT * FROM admin_audit")
    rows = await cursor.fetchall()
    await cursor.close()
    return repr([tuple(row) for row in rows])


@pytest.mark.parametrize("side, predicate", _PARENT_SIDES)
async def test_label_a_parent_writes_the_side_and_revokes_the_unlabelled_row(
    ops_db: int, side: str, predicate: str
) -> None:
    owner = ops_db
    row = await _relation(owner, "has_parent")
    outcome = await _label(owner, row.id, side)
    assert outcome.status is AdminOutcomeStatus.APPLIED
    assert await _active(predicate) == [(owner, row.target_entity_id)]
    assert await _active("has_parent") == []
    stored = await get_entity_relation(row.id)
    assert stored is not None
    assert stored.lifecycle is AssertionLifecycle.REVOKED
    (audit,) = await list_admin_operations()
    assert audit.operation is AdminOperationKind.CHANGE
    assert audit.target_kind is TargetKind.POOL_RELATION
    assert audit.field_id == predicate
    assert audit.target_entity_id == row.target_entity_id
    assert audit.outcome is AdminOutcomeStatus.APPLIED
    assert "Zeta" not in await _audit_dump()


@pytest.mark.parametrize("side, predicate", _CHILD_SIDES)
async def test_label_a_child_adds_the_marker_beside_the_child_row(
    ops_db: int, side: str, predicate: str
) -> None:
    owner = ops_db
    row = await _relation(owner, "child_of")
    outcome = await _label(owner, row.id, side)
    assert outcome.status is AdminOutcomeStatus.APPLIED
    assert await _active(predicate) == [(row.source_entity_id, owner)]
    assert await _active("child_of") == [(row.source_entity_id, owner)]
    (audit,) = await list_admin_operations()
    assert audit.operation is AdminOperationKind.CHANGE
    assert audit.target_kind is TargetKind.POOL_RELATION
    assert audit.field_id == predicate
    assert audit.target_entity_id == row.source_entity_id
    assert "Zeta" not in await _audit_dump()


@pytest.mark.parametrize("side, other", [("daughter", "son_of"), ("son", "daughter_of")])
async def test_a_child_with_the_other_marker_is_refused(ops_db: int, side: str, other: str) -> None:
    owner = ops_db
    row = await _relation(owner, "child_of")
    await _relation(owner, other, source=row.source_entity_id, target=owner)
    before = await _all_relations()
    outcome = await _label(owner, row.id, side)
    assert outcome.status is AdminOutcomeStatus.REFUSED
    assert outcome.reason == "already_labelled"
    assert await _all_relations() == before
    assert (await list_admin_operations())[0].reason == "already_labelled"


@pytest.mark.parametrize("side, predicate", _CHILD_SIDES)
async def test_the_same_child_marker_twice_is_a_refusal_that_writes_nothing(
    ops_db: int, side: str, predicate: str
) -> None:
    owner = ops_db
    row = await _relation(owner, "child_of")
    await _label(owner, row.id, side)
    before = await _all_relations()
    again = await _label(owner, row.id, side)
    assert again.status is AdminOutcomeStatus.REFUSED
    assert again.reason == "already_labelled"
    assert await _all_relations() == before
    assert len(await _active(predicate)) == 1


@pytest.mark.parametrize("side, predicate", _PARENT_SIDES)
async def test_the_same_parent_row_twice_leaves_one_active_label(
    ops_db: int, side: str, predicate: str
) -> None:
    owner = ops_db
    row = await _relation(owner, "has_parent")
    await _label(owner, row.id, side)
    before = await _all_relations()
    again = await _label(owner, row.id, side)
    assert again.status is AdminOutcomeStatus.REFUSED
    assert again.reason == "not_an_active_relation"
    assert await _all_relations() == before
    assert len(await _active(predicate)) == 1


@pytest.mark.parametrize("side, predicate", _ALL_SIDES)
async def test_without_the_pin_nothing_is_written_and_it_is_audited(
    ops_db: int, side: str, predicate: str
) -> None:
    owner = ops_db
    row = await _relation(owner, "has_parent" if side in {"mother", "father"} else "child_of")
    before = await _all_relations()
    outcome = await _label(owner, row.id, side, verified=False)
    assert outcome.status is AdminOutcomeStatus.REFUSED
    assert outcome.reason == "owner_not_verified"
    assert await _all_relations() == before
    (audit,) = await list_admin_operations()
    assert audit.outcome is AdminOutcomeStatus.REFUSED
    assert audit.reason == "owner_not_verified"
    assert audit.field_id == predicate
    assert audit.operation is AdminOperationKind.CHANGE
    assert audit.target_kind is TargetKind.POOL_RELATION


async def _wrong_row(owner: int, case: str, side: str) -> int:
    """Build the row a refusal case is about and return the id to label."""
    parent_side = side in {"mother", "father"}
    own_kind = "has_parent" if parent_side else "child_of"
    match case:
        case "sibling":
            return (await _relation(owner, "has_sibling")).id
        case "other_verb":
            return (await _relation(owner, "child_of" if parent_side else "has_parent")).id
        case "revoked":
            row = await _relation(owner, own_kind)
            await revoke_entity_relation(row.id, revoked_at=_NOW)
            return row.id
        case "another_owner":
            other = await upsert_entity(name="Canary Other Owner", type="person")
            return (await _relation(other, own_kind)).id
        case _:
            return 9999


@pytest.mark.parametrize("side, _predicate", _ALL_SIDES)
@pytest.mark.parametrize(
    "case, reason",
    [
        ("sibling", "wrong_relation_kind"),
        ("other_verb", "wrong_relation_kind"),
        ("revoked", "not_an_active_relation"),
        ("another_owner", "not_an_active_relation"),
        ("unknown", "not_an_active_relation"),
    ],
)
async def test_the_wrong_row_is_refused_audited_and_writes_nothing(
    ops_db: int, side: str, _predicate: str, case: str, reason: str
) -> None:
    owner = ops_db
    row_id = await _wrong_row(owner, case, side)
    before = await _all_relations()
    outcome = await _label(owner, row_id, side)
    assert outcome.status is AdminOutcomeStatus.REFUSED
    assert outcome.reason == reason
    assert await _all_relations() == before
    (audit,) = await list_admin_operations()
    assert audit.outcome is AdminOutcomeStatus.REFUSED
    assert audit.reason == reason
    assert audit.operation is AdminOperationKind.CHANGE
    assert audit.target_kind is TargetKind.POOL_RELATION
    assert "Zeta" not in await _audit_dump()


async def test_a_row_that_points_at_the_owner_from_somebody_else_is_not_labelled(
    ops_db: int,
) -> None:
    owner = ops_db
    other = await upsert_entity(name="Canary Other Owner", type="person")
    row = await _relation(other, "has_parent", source=other, target=owner)
    before = await _all_relations()
    outcome = await _label(owner, row.id, "mother")
    assert outcome.status is AdminOutcomeStatus.REFUSED
    assert outcome.reason == "not_an_active_relation"
    assert await _all_relations() == before


async def test_a_closed_writer_refusal_is_reported_and_keeps_the_row(
    ops_db: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = ops_db
    row = await _relation(owner, "has_parent")
    before = await _all_relations()

    async def _refuse(**_kwargs: object) -> object:
        raise WriteRefusedError("not_household_member")

    monkeypatch.setattr("server.memory.admin_ops.write_relation", _refuse)
    outcome = await _label(owner, row.id, "mother")
    assert outcome.status is AdminOutcomeStatus.REFUSED
    assert outcome.reason == "not_household_member"
    assert await _all_relations() == before
    (audit,) = await list_admin_operations()
    assert audit.reason == "not_household_member"
    assert audit.field_id == "has_mother"


async def test_a_failed_write_rolls_the_label_and_the_audit_back(
    ops_db: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = ops_db
    row = await _relation(owner, "has_parent")
    before = await _all_relations()

    async def _boom(**_kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("server.memory.admin_ops.write_relation", _boom)
    with pytest.raises(RuntimeError):
        await _label(owner, row.id, "mother")
    assert await _all_relations() == before
    assert await list_admin_operations() == ()


async def test_a_failed_revoke_rolls_the_new_side_back_too(
    ops_db: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = ops_db
    row = await _relation(owner, "has_parent")
    before = await _all_relations()

    async def _boom(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr("server.memory.admin_ops.revoke_entity_relation", _boom)
    with pytest.raises(RuntimeError):
        await _label(owner, row.id, "father")
    assert await _all_relations() == before
    assert await _active("has_father") == []
    assert await list_admin_operations() == ()
