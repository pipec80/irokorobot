"""The deleting and counting functions a replacement needs (Plan 0071 Task 5a, ADR 0024 decision 8).

Each one lives in the repository that owns its table and joins the caller's transaction. Every
name and value is an invented canary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import SecretStr
import pytest
from server.memory import candidates
from server.memory.candidate_types import CandidateChannel, ProposedCandidate
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.care_contacts import (
    ContactRole,
    count_active_contacts,
    delete_contacts_by_channel,
    entity_has_contact_rows,
    write_contact,
)
from server.memory.commissioning import (
    CommissioningInput,
    ConfirmationMode,
    DiskEncryption,
    InterviewerRole,
    Section,
    SectionStatus,
    clear_section_statuses,
    list_section_statuses,
    open_commissioning,
    set_section_status,
)
from server.memory.declarative import (
    count_entities,
    create_third_party,
    delete_orphan_import_entities,
)
from server.memory.relational_v4 import (
    count_rows_by_channel,
    count_v4_rows,
    delete_rows_by_channel,
    entity_has_rows,
)
from server.memory.write_types import IMPORT_CHANNELS, VOICE_CHANNELS, WriteChannel
from server.personal_setup import PersonalSetupInput, apply_personal_setup
from server.settings import settings

from server import db
from tests.integration.seed_household import NOW, owner, scalar, seed_db

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = ["owner", "seed_db"]

pytestmark = pytest.mark.integration

_IMPORT = WriteChannel.IMPORT_ASSISTED
_VOICE = WriteChannel.VOICE_STREAM


async def _taste(owner_id: int, value: str, channel: WriteChannel) -> None:
    await write_literal(
        owner_entity_id=owner_id,
        subject_entity_id=owner_id,
        predicate="likes",
        value=value,
        channel=channel,
        confirmed_at=NOW,
    )


async def _relative(owner_id: int, name: str, key: str | None) -> int:
    relative = await create_third_party(name=name, type="person", import_key=key)
    await write_relation(
        owner_entity_id=owner_id,
        source_entity_id=owner_id,
        predicate="has_parent",
        target_entity_id=relative,
        channel=_IMPORT,
        confirmed_at=NOW,
    )
    return relative


async def test_rows_are_deleted_and_counted_by_channel(owner: int) -> None:
    await _taste(owner, "el té", _IMPORT)
    await _taste(owner, "el mar", _VOICE)
    await _relative(owner, "Canary Parent", "seed-v1:parent:canary parent")

    assert await count_rows_by_channel(IMPORT_CHANNELS) == 2
    assert await count_rows_by_channel(VOICE_CHANNELS) == 1

    async with db.transaction():
        deleted = await delete_rows_by_channel(IMPORT_CHANNELS, manage_transaction=False)

    assert deleted == 2
    assert await count_rows_by_channel(IMPORT_CHANNELS) == 0
    assert await count_rows_by_channel(VOICE_CHANNELS) == 1
    counts = await count_v4_rows()
    assert (counts.literals, counts.relations) == (1, 0)


async def test_rows_without_a_channel_are_never_deleted(seed_db: object) -> None:
    del seed_db
    await apply_personal_setup(
        PersonalSetupInput(
            owner_name="Canary Owner", child_names=("Canary Kid",), pin=SecretStr("482173")
        )
    )

    assert await delete_rows_by_channel(IMPORT_CHANNELS) == 0
    assert await scalar("SELECT COUNT(*) FROM entity_relations_v4") == 1


async def test_an_entity_has_rows_as_a_subject_or_on_either_end(owner: int) -> None:
    relative = await _relative(owner, "Canary Parent", None)
    lonely = await create_third_party(name="Canary Lonely", type="person")

    assert await entity_has_rows(owner) is True
    assert await entity_has_rows(relative) is True
    assert await entity_has_rows(lonely) is False


async def test_contacts_are_deleted_by_channel(owner: int) -> None:
    friend = await create_third_party(name="Canary Friend", type="person")
    for role, channel, phone in (
        (ContactRole.TRUSTED, _IMPORT, "+56900000001"),
        (ContactRole.NEIGHBOR, WriteChannel.VOICE_CLASSIC, "+56900000002"),
    ):
        await write_contact(
            owner_entity_id=owner,
            contact_entity_id=friend,
            role=role,
            phone=phone,
            channel=channel,
            confirmed_at=NOW,
        )

    async with db.transaction():
        deleted = await delete_contacts_by_channel(IMPORT_CHANNELS, manage_transaction=False)

    assert deleted == 1
    assert await count_active_contacts() == 1
    assert await entity_has_contact_rows(friend) is True


async def test_only_live_candidates_are_counted(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    stored = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_STREAM,
        correlation_id=uuid4(),
        now=now,
    )
    assert stored.candidate_id is not None

    assert await candidates.count_live_candidates() == 1

    await candidates.void_live_candidates(now)

    assert await candidates.count_live_candidates() == 0


async def test_the_section_statuses_of_a_record_are_cleared(owner: int) -> None:
    del owner
    record = await open_commissioning(
        CommissioningInput(
            interviewer_label="Canary Interviewer",
            interviewer_role=InterviewerRole.FAMILY,
            confirmation_mode=ConfirmationMode.OWNER_IN_PERSON,
            disk_encryption=DiskEncryption.UNKNOWN,
        ),
        started_at=NOW,
    )
    await set_section_status(record.id, Section.DEVICES, SectionStatus.NONE, NOW)

    async with db.transaction():
        await clear_section_statuses(record.id, manage_transaction=False)

    assert set((await list_section_statuses(record.id)).values()) == {SectionStatus.NOT_ASKED}


def _never(_entity_id: int) -> Awaitable[bool]:
    async def answer() -> bool:
        return False

    return answer()


def _always(_entity_id: int) -> Awaitable[bool]:
    async def answer() -> bool:
        return True

    return answer()


async def test_an_orphan_import_entity_is_deleted_and_any_other_is_kept(owner: int) -> None:
    del owner
    await create_third_party(name="Canary Orphan", type="person", import_key="seed-v1:parent:x")
    await create_third_party(name="Canary Local", type="person")
    await create_third_party(name="Canary Other", type="person", import_key="other-v9:x")
    before = await count_entities()

    async with db.transaction():
        deleted = await delete_orphan_import_entities(
            has_rows=_never, has_contacts=_never, manage_transaction=False
        )

    assert deleted == 1
    assert await count_entities() == before - 1


@pytest.mark.parametrize("has_rows, has_contacts", [(_always, _never), (_never, _always)])
async def test_an_import_entity_something_refers_to_is_kept(
    owner: int,
    has_rows: Callable[[int], Awaitable[bool]],
    has_contacts: Callable[[int], Awaitable[bool]],
) -> None:
    del owner
    await create_third_party(name="Canary Kept", type="person", import_key="seed-v1:parent:kept")
    before = await count_entities()

    deleted = await delete_orphan_import_entities(has_rows=has_rows, has_contacts=has_contacts)

    assert deleted == 0
    assert await count_entities() == before
