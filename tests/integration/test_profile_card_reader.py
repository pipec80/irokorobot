"""The profile card's only query (Plan 0074 Task 2): the allow-listed rows of one subject."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import upsert_entity
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import (
    LiteralFactV4,
    assert_literal_fact,
    list_card_literals,
    revoke_literal_fact,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

_CARD = frozenset({"preferred_name", "address_form", "likes", "dislikes", "prefers"})


@pytest.fixture
async def card_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """A fresh v4 database for the card reader tests."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "profile-card-reader.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield
    finally:
        await db.close_db()
        db._conn = None


def _predicate(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


async def _store(
    subject: int,
    alias: str,
    value: str,
    *,
    visibility: str = "personal",
    sensitivity: str = "normal",
) -> LiteralFactV4:
    return await assert_literal_fact(
        subject_entity_id=subject,
        definition=_predicate(alias),
        value=value,
        visibility=visibility,
        sensitivity=sensitivity,
    )


async def test_returns_only_the_subjects_own_active_personal_normal_rows(card_db: None) -> None:
    owner = await upsert_entity(name="Canary", type="person")
    other = await upsert_entity(name="Zeta", type="person")
    mine = await _store(owner, "likes", "el mate")
    await _store(other, "likes", "la lluvia")

    rows = await list_card_literals(subject_entity_id=owner, predicates=_CARD)

    assert [row.id for row in rows] == [mine.id]


async def test_a_household_private_revoked_or_superseded_row_is_never_returned(
    card_db: None,
) -> None:
    owner = await upsert_entity(name="Canary", type="person")
    child = await upsert_entity(name="Zeta", type="person")
    await _store(child, "likes", "a child's taste", visibility="household")
    await _store(owner, "likes", "a private taste", visibility="private")
    await _store(owner, "likes", "a medical taste", sensitivity="medical")
    revoked = await _store(owner, "dislikes", "a revoked taste")
    await revoke_literal_fact(revoked.id, revoked_at="2026-10-28T10:00:00+00:00")
    await _store(owner, "preferred_name", "Old Canary")  # superseded by the next one
    current = await _store(owner, "preferred_name", "Canary")

    rows = await list_card_literals(subject_entity_id=owner, predicates=_CARD)

    assert [row.id for row in rows] == [current.id]
    assert await list_card_literals(subject_entity_id=child, predicates=_CARD) == []


async def test_only_the_asked_predicates_are_returned(card_db: None) -> None:
    owner = await upsert_entity(name="Canary", type="person")
    await _store(owner, "birth_date", "1990-01-01")
    taste = await _store(owner, "likes", "el mate")

    rows = await list_card_literals(subject_entity_id=owner, predicates=frozenset({"likes"}))

    assert [row.id for row in rows] == [taste.id]


async def test_orders_newest_first_by_id(card_db: None) -> None:
    owner = await upsert_entity(name="Canary", type="person")
    first = await _store(owner, "likes", "el mate")
    second = await _store(owner, "likes", "la lluvia")
    third = await _store(owner, "prefers", "el cafe")

    rows = await list_card_literals(subject_entity_id=owner, predicates=_CARD)

    assert [row.id for row in rows] == [third.id, second.id, first.id]


async def test_an_empty_predicate_set_returns_nothing(card_db: None) -> None:
    owner = await upsert_entity(name="Canary", type="person")
    await _store(owner, "likes", "el mate")

    assert await list_card_literals(subject_entity_id=owner, predicates=frozenset()) == []
