"""Integration coverage for ``create_third_party`` (Plan 0065, Task 4; ADR 0022 decision 7).

A third party is never created twice and never merged by name alone: the same import key is
an idempotent re-run, any other collision of the folded ``(name, type)`` is refused. Every name
here is an invented canary.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from server.exceptions import AmbiguousEntityError
from server.memory.declarative import create_third_party, find_entities_by_name, upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

_LOGGER_NAME = "server.memory.declarative"


@pytest.fixture
async def third_party_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Open a fresh migrated SQLite database for one test."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "third-parties.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


async def _entity_rows() -> list[tuple[int, str, str, str, str, str, str]]:
    """Return every ``entities`` row, whole, so a test can prove nothing else changed."""
    cur = await db.get_conn().execute(
        "SELECT id, name, type, attributes, aliases, created_at, updated_at "
        "FROM entities ORDER BY id"
    )
    rows = await cur.fetchall()
    await cur.close()
    return [(int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]


@pytest.mark.integration
async def test_new_third_party_stores_the_import_key(third_party_db: None) -> None:
    """A first creation returns a new id and keeps the key in ``attributes``."""
    entity_id = await create_third_party(name="Canary Child", type="person", import_key="c1")

    rows = await _entity_rows()
    assert [(row[0], row[1], row[2]) for row in rows] == [(entity_id, "Canary Child", "person")]
    assert json.loads(rows[0][3]) == {"import_key": "c1"}
    assert json.loads(rows[0][4]) == []


@pytest.mark.integration
async def test_third_party_without_a_key_stores_no_key(third_party_db: None) -> None:
    """A first creation with no key leaves ``attributes`` empty."""
    entity_id = await create_third_party(name="Canary Child", type="person")

    matches = await find_entities_by_name("Canary Child")
    assert [(m["id"], m["attributes"]) for m in matches] == [(entity_id, {})]


@pytest.mark.integration
async def test_same_key_returns_the_same_id_and_changes_nothing(third_party_db: None) -> None:
    """Re-running an import is idempotent: same id, no row created, no row modified."""
    first = await create_third_party(name="Canary Child", type="person", import_key="c1")
    before = await _entity_rows()

    second = await create_third_party(name="Canary Child", type="person", import_key="c1")

    assert second == first
    assert await _entity_rows() == before


@pytest.mark.integration
async def test_same_key_with_another_spelling_is_still_the_same_entity(
    third_party_db: None,
) -> None:
    """The idempotent re-run matches the folded name, so a re-spelled name does not duplicate."""
    first = await create_third_party(name="Joaquín", type="person", import_key="c1")
    before = await _entity_rows()

    second = await create_third_party(name="Joaquin", type="person", import_key="c1")

    assert second == first
    assert await _entity_rows() == before


@pytest.mark.integration
async def test_another_key_for_the_same_name_is_ambiguous(third_party_db: None) -> None:
    """The same folded name and type under another key is refused, and nothing changes."""
    await create_third_party(name="Canary Child", type="person", import_key="c1")
    before = await _entity_rows()

    with pytest.raises(AmbiguousEntityError):
        await create_third_party(name="Canary Child", type="person", import_key="c2")

    assert await _entity_rows() == before


@pytest.mark.integration
async def test_no_key_for_an_existing_name_is_ambiguous(third_party_db: None) -> None:
    """The same folded name and type with no key is refused when the entity has a key."""
    await create_third_party(name="Canary Child", type="person", import_key="c1")
    before = await _entity_rows()

    with pytest.raises(AmbiguousEntityError):
        await create_third_party(name="Canary Child", type="person")

    assert await _entity_rows() == before


@pytest.mark.integration
async def test_a_key_for_an_entity_without_one_is_ambiguous(third_party_db: None) -> None:
    """An entity that has no key cannot be claimed by a later keyed creation."""
    await create_third_party(name="Canary Child", type="person")
    before = await _entity_rows()

    with pytest.raises(AmbiguousEntityError):
        await create_third_party(name="Canary Child", type="person", import_key="c1")

    assert await _entity_rows() == before


@pytest.mark.integration
async def test_a_name_without_a_key_twice_is_ambiguous(third_party_db: None) -> None:
    """Two creations with no key never produce a second entity."""
    await create_third_party(name="Canary Child", type="person")
    before = await _entity_rows()

    with pytest.raises(AmbiguousEntityError):
        await create_third_party(name="Canary Child", type="person")

    assert await _entity_rows() == before


@pytest.mark.integration
async def test_an_entity_from_upsert_entity_is_never_claimed(third_party_db: None) -> None:
    """An entity that already exists for another reason (the owner's setup) is not merged."""
    await upsert_entity(name="Canary Owner", type="person")
    before = await _entity_rows()

    with pytest.raises(AmbiguousEntityError):
        await create_third_party(name="Canary Owner", type="person", import_key="c1")

    assert await _entity_rows() == before


@pytest.mark.integration
@pytest.mark.parametrize(
    "first, second",
    [
        ("Joaquín", "Joaquin"),
        ("Joaquin", "Joaquín"),
        ("Canary Child", "CANARY CHILD"),
    ],
)
async def test_accent_and_case_variants_collide(
    third_party_db: None, first: str, second: str
) -> None:
    """Accent and case folding apply both ways, and the variant is never recorded as an alias."""
    await create_third_party(name=first, type="person", import_key="c1")
    before = await _entity_rows()

    with pytest.raises(AmbiguousEntityError):
        await create_third_party(name=second, type="person", import_key="c2")
    with pytest.raises(AmbiguousEntityError):
        await create_third_party(name=second, type="person")

    rows = await _entity_rows()
    assert rows == before
    assert json.loads(rows[0][4]) == []


@pytest.mark.integration
async def test_a_pet_is_typed_other_and_the_type_is_part_of_the_identity(
    third_party_db: None,
) -> None:
    """A pet is stored as ``other``; the same name under another type is another entity."""
    pet_id = await create_third_party(name="Canary Pet", type="other", import_key="p1")
    person_id = await create_third_party(name="Canary Pet", type="person", import_key="p2")

    assert pet_id != person_id
    rows = await _entity_rows()
    assert [(row[0], row[2]) for row in rows] == [(pet_id, "other"), (person_id, "person")]


@pytest.mark.integration
async def test_upsert_entity_still_merges_a_third_party(third_party_db: None) -> None:
    """``upsert_entity`` is unchanged: it merges attributes and keeps the spelling as an alias."""
    entity_id = await create_third_party(name="Joaquin", type="person", import_key="c1")

    merged_id = await upsert_entity(name="Joaquín", type="person", attributes={"role": "friend"})

    assert merged_id == entity_id
    rows = await _entity_rows()
    assert len(rows) == 1
    assert json.loads(rows[0][3]) == {"import_key": "c1", "role": "friend"}
    assert json.loads(rows[0][4]) == ["Joaquín"]


@pytest.mark.integration
async def test_concurrent_creations_with_one_key_make_one_entity(third_party_db: None) -> None:
    """Two concurrent creations cannot both see «not found»: one entity, one id."""
    first, second = await asyncio.gather(
        create_third_party(name="Canary Child", type="person", import_key="c1"),
        create_third_party(name="Canary Child", type="person", import_key="c1"),
    )

    assert first == second
    assert len(await _entity_rows()) == 1


@pytest.mark.integration
async def test_concurrent_creations_with_two_keys_refuse_exactly_one(third_party_db: None) -> None:
    """Two concurrent creations under different keys: one wins, the other is ambiguous."""
    outcomes = await asyncio.gather(
        create_third_party(name="Canary Child", type="person", import_key="c1"),
        create_third_party(name="Canary Child", type="person", import_key="c2"),
        return_exceptions=True,
    )

    created = [outcome for outcome in outcomes if isinstance(outcome, int)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, AmbiguousEntityError)]
    assert len(created) == 1
    assert len(refused) == 1
    assert [row[0] for row in await _entity_rows()] == created


@pytest.mark.integration
async def test_creation_inside_a_caller_transaction_vanishes_on_rollback(
    third_party_db: None,
) -> None:
    """With ``manage_transaction=False`` the caller owns the rollback (atomic batches)."""

    async def failing_batch() -> None:
        async with db.transaction():
            await create_third_party(
                name="Canary Child",
                type="person",
                import_key="c1",
                manage_transaction=False,
            )
            assert len(await _entity_rows()) == 1  # visible to the caller until it rolls back
            raise RuntimeError("caller gives up")

    with pytest.raises(RuntimeError, match="caller gives up"):
        await failing_batch()

    assert await _entity_rows() == []


@pytest.mark.integration
async def test_creation_inside_a_caller_transaction_commits_with_the_caller(
    third_party_db: None,
) -> None:
    """The joined creation commits when the caller commits, and its lookup sees its own writes."""
    async with db.transaction():
        first = await create_third_party(
            name="Canary Child", type="person", import_key="c1", manage_transaction=False
        )
        again = await create_third_party(
            name="Canary Child", type="person", import_key="c1", manage_transaction=False
        )
        with pytest.raises(AmbiguousEntityError):
            await create_third_party(
                name="Canary Child", type="person", import_key="c2", manage_transaction=False
            )

    assert again == first
    assert [row[0] for row in await _entity_rows()] == [first]


@pytest.mark.integration
async def test_a_refusal_never_names_the_third_party_or_the_key(
    third_party_db: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Neither the exception message nor any log record carries a name or an import key."""
    name = "Canary Secret Name"
    key = "import-key-7"
    other_key = "import-key-8"
    caplog.set_level("DEBUG", logger=_LOGGER_NAME)

    await create_third_party(name=name, type="person", import_key=key)
    await create_third_party(name=name, type="person", import_key=key)
    with pytest.raises(AmbiguousEntityError) as refusal:
        await create_third_party(name=name, type="person", import_key=other_key)

    message = str(refusal.value)
    assert name not in message
    assert key not in message
    assert other_key not in message
    records = [record for record in caplog.records if record.name == _LOGGER_NAME]
    assert records, "the creation paths should leave a trace (ids and types only)"
    for record in records:
        rendered = f"{record.getMessage()} {vars(record)}"
        for secret in (name, key, other_key):
            assert secret not in rendered
