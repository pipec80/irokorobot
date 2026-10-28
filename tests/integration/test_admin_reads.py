"""Admin reads of the pool (Plan 0073 Task 2): the tool shows rows through the repository.

The command holds no SQL: `list_active_facts` and `list_active_relations` read the owner's active
rows from `relational_v4` (its own SQL). Writing a fact through `admin_local` is classified exactly
as through any other channel — the channel does not change the classification. Canaries only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.relational_v4 import list_active_facts, list_active_relations
from server.memory.write_types import WriteChannel
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-10-27T10:00:00.000000+00:00"
_LATER = "2026-10-27T11:00:00.000000+00:00"


@pytest.fixture
async def reads_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "admin-reads.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        yield owner
    finally:
        await db.close_db()
        db._conn = None


async def test_an_admin_local_write_is_classified_like_any_other_channel(reads_db: int) -> None:
    owner = reads_db
    fact = await write_literal(
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="preferred_name",
        value="Canary",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    # preferred_name is personal/normal; the channel is only recorded, never part of the class.
    assert (fact.visibility, fact.sensitivity) == ("personal", "normal")
    assert fact.channel == "admin_local"


async def test_list_active_facts_returns_active_rows_and_hides_a_superseded_one(
    reads_db: int,
) -> None:
    owner = reads_db
    await write_literal(
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="preferred_name",
        value="Canary Old",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    await write_literal(
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="preferred_name",
        value="Canary New",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_LATER,
    )
    facts = await list_active_facts(owner)
    values = [fact.value_text for fact in facts]
    assert "Canary New" in values
    assert "Canary Old" not in values


async def test_list_active_relations_returns_the_owner_rows(reads_db: int) -> None:
    owner = reads_db
    child = await create_third_party(name="Canary Child", type="person")
    await write_relation(
        owner_entity_id=owner,
        source_entity_id=child,
        predicate="child_of",
        target_entity_id=owner,
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    relations = await list_active_relations(owner)
    assert any(
        relation.predicate == "child_of" and relation.target_entity_id == owner
        for relation in relations
    )
