"""Cross-repository concurrency RED test (Plan 0036, Task 1).

Asserts the real behavioral contract Plan 0036 must deliver: two independent
repository writes — `household_authorization.assign_household_role` and
`owner_credentials.save_owner_pin_credential` — must both complete cleanly
when they overlap on the single shared connection, with no interleaved
`BEGIN IMMEDIATE`.

Before migration, this is RED: each function opens its own
``BEGIN IMMEDIATE``/commit/rollback block directly against `db.get_conn()`
with no lock serializing them, so a second `BEGIN IMMEDIATE` lands while the
first transaction is still open and SQLite rejects it with
"cannot start a transaction within a transaction". After Task 2 migrates
both onto `db.transaction()`, the module lock serializes them and this test
goes GREEN.
"""

import asyncio
from collections.abc import AsyncIterator
import contextlib
from pathlib import Path

import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition.identity import HouseholdRole
from server.cognition.pin_credentials import hash_pin
from server.memory import household_authorization, owner_credentials
from server.memory.declarative import upsert_entity
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.settings import settings
from server.vision import faces

from server import db

# Guards every cross-task `Event.wait()` below — without a bound, a coroutine
# that never reaches the pause point (for instance because a prior fix
# already serializes the two writes) leaves the test hanging instead of
# failing fast. See test_db_transaction.py for the same convention.
_GUARD_TIMEOUT_S = 5.0


@pytest.fixture
async def owner_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """A real temporary DB with an owner, one child, and an active PIN."""
    db_path = tmp_path / "concurrency-test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name="Owner", child_names=("Kid",), pin=SecretStr("482173"))
    )
    yield result
    await db.close_db()
    db._conn = None


@pytest.mark.integration
async def test_concurrent_role_assignment_and_pin_rotation_both_succeed(
    owner_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two overlapping repository writes must both complete, never collide.

    `assign_household_role` inserts its role row, then calls `_record_event`
    for the audit trail, then commits. This test pauses it right after the
    insert — deterministically, via a monkeypatched `_record_event` — then
    starts `save_owner_pin_credential` while that transaction is still open
    on the one shared connection.

    `save_owner_pin_credential` itself opens with a `get_active_role` check
    (a plain SELECT, unrelated to the collision under test) before its own
    `BEGIN IMMEDIATE`. That check is stubbed to return synchronously, with no
    real await, so `BEGIN IMMEDIATE` becomes the pin task's first genuine
    suspension point — the ordering below then only relies on asyncio's
    documented FIFO scheduling of ready callbacks, not on any race.
    """
    role_began = asyncio.Event()
    may_continue = asyncio.Event()
    real_record_event = household_authorization._record_event

    async def paused_record_event(**kwargs: object) -> None:
        role_began.set()
        await asyncio.wait_for(may_continue.wait(), timeout=_GUARD_TIMEOUT_S)
        await real_record_event(**kwargs)  # type: ignore[arg-type]  # kwargs mirror the real signature exactly

    monkeypatch.setattr(household_authorization, "_record_event", paused_record_event)

    async def fast_owner_role_check(_person_entity_id: int) -> HouseholdRole:
        return HouseholdRole.OWNER

    monkeypatch.setattr(owner_credentials, "get_active_role", fast_owner_role_check)

    third_person_id = await upsert_entity(name="ThirdPerson", type="person")

    async def assign_role() -> None:
        await household_authorization.assign_household_role(
            person_entity_id=third_person_id,
            role=HouseholdRole.ADULT,
            grantor_entity_id=owner_db.owner_entity_id,
        )

    role_task = asyncio.create_task(assign_role())
    await asyncio.wait_for(role_began.wait(), timeout=_GUARD_TIMEOUT_S)

    async def rotate_pin() -> None:
        await owner_credentials.save_owner_pin_credential(
            person_entity_id=owner_db.owner_entity_id,
            credential=hash_pin("999999"),
        )

    pin_task = asyncio.create_task(rotate_pin())
    await asyncio.sleep(0)  # let pin_task run synchronously up to its BEGIN IMMEDIATE suspension

    may_continue.set()
    await asyncio.wait_for(asyncio.gather(role_task, pin_task), timeout=_GUARD_TIMEOUT_S)

    active_role = await household_authorization.get_active_role(third_person_id)
    assert active_role == HouseholdRole.ADULT


def _unit_vector(axis: int) -> np.ndarray:
    """Return a 512-d unit vector along *axis* — a synthetic face embedding."""
    vec = np.zeros(512, dtype=np.float32)
    vec[axis] = 1.0
    return vec


@pytest.mark.integration
async def test_unrelated_write_does_not_silently_commit_a_foreign_transaction(
    owner_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write with no transaction of its own must never commit another's.

    `enroll_face` issues two bare INSERTs followed by its own `conn.commit()`
    — no `BEGIN IMMEDIATE`. If `assign_household_role` already holds the
    shared connection's only transaction open, `enroll_face`'s commit
    commits *that* transaction too — early, and out from under its owner.
    When `assign_household_role` then hits its simulated failure and calls
    `conn.rollback()`, there is nothing left open to roll back: its own
    supposedly-failed role assignment survives anyway.

    Once both functions own their writes through `db.transaction()`,
    `enroll_face` instead waits for the lock — it cannot even start until
    `assign_household_role` fully exits — so each ends up correctly isolated:
    the failed role assignment rolls back, and the unrelated face enrollment
    still succeeds on its own.
    """
    role_began = asyncio.Event()
    may_fail = asyncio.Event()

    async def failing_record_event(**kwargs: object) -> None:
        role_began.set()
        await asyncio.wait_for(may_fail.wait(), timeout=_GUARD_TIMEOUT_S)
        raise RuntimeError("simulated failure — assign_role must roll back its own INSERT")

    monkeypatch.setattr(household_authorization, "_record_event", failing_record_event)

    third_person_id = await upsert_entity(name="ThirdPerson", type="person")

    async def assign_role() -> None:
        with contextlib.suppress(RuntimeError):
            await household_authorization.assign_household_role(
                person_entity_id=third_person_id,
                role=HouseholdRole.ADULT,
                grantor_entity_id=owner_db.owner_entity_id,
            )

    role_task = asyncio.create_task(assign_role())
    await asyncio.wait_for(role_began.wait(), timeout=_GUARD_TIMEOUT_S)

    enroll_task = asyncio.create_task(
        faces.enroll_face(third_person_id, _unit_vector(0), "ThirdPerson")
    )
    await asyncio.sleep(0)  # let enroll_task start and block on the shared lock

    may_fail.set()
    await asyncio.wait_for(asyncio.gather(role_task, enroll_task), timeout=_GUARD_TIMEOUT_S)

    active_role = await household_authorization.get_active_role(third_person_id)
    assert active_role is HouseholdRole.UNKNOWN, (
        "assign_household_role raised and must have rolled back its own INSERT, "
        "but an unrelated commit from enroll_face already flushed it to disk"
    )
