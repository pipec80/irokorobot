"""The admin's read-only readiness recompute (Plan 0073 Task 7, ADR 0025, C-2).

`status` never edits the frozen acta: `recompute_readiness` reads the active rows for the data side
and the acta's frozen attestation for the hardware side, and raises nothing on a closed record.
Canaries only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.admin_readiness import derive_section_presence, recompute_readiness
from server.memory.canonical_writer import write_literal
from server.memory.commissioning import (
    CommissioningInput,
    ConfirmationMode,
    DiskEncryption,
    InterviewerRole,
    Section,
    SectionStatus,
    close_commissioning,
    open_commissioning,
    record_readiness,
    set_section_status,
)
from server.memory.commissioning_readiness import (
    Capability,
    HardwareStatus,
    Verdict,
    evaluate_readiness,
    readiness_to_json,
)
from server.memory.declarative import upsert_entity
from server.memory.relational_v4 import revoke_literal_fact
from server.memory.write_types import WriteChannel
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-10-27T10:00:00.000000+00:00"
_LATER = "2026-10-27T12:00:00.000000+00:00"


@pytest.fixture
async def closed_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    """A commissioned robot with a closed acta that froze describe_scene's hardware as ready."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "admin-status.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        record = await open_commissioning(
            CommissioningInput(
                interviewer_label="Canary Interviewer",
                interviewer_role=InterviewerRole.BUILDER,
                confirmation_mode=ConfirmationMode.BUILDER_IS_OWNER,
                disk_encryption=DiskEncryption.UNKNOWN,
            ),
            started_at=_NOW,
        )
        await set_section_status(record.id, Section.FUNCTION, SectionStatus.PROVIDED, _NOW)
        frozen = evaluate_readiness(
            {Section.FUNCTION: SectionStatus.PROVIDED},
            {Capability.DESCRIBE_SCENE: HardwareStatus(True, True, True)},
        )
        await record_readiness(record.id, readiness_to_json(frozen))
        await close_commissioning(record.id, _NOW)
        yield owner
    finally:
        await db.close_db()
        db._conn = None


async def _write_function_fact(owner: int) -> int:
    fact = await write_literal(
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="mobility",
        value="baston",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=_NOW,
    )
    return fact.id


async def test_derive_section_presence_follows_the_active_rows(closed_db: int) -> None:
    owner = closed_db
    assert (await derive_section_presence(owner))[Section.FUNCTION] is False
    fact_id = await _write_function_fact(owner)
    assert (await derive_section_presence(owner))[Section.FUNCTION] is True
    await revoke_literal_fact(fact_id, revoked_at=_LATER)
    assert (await derive_section_presence(owner))[Section.FUNCTION] is False


async def test_recompute_keeps_the_frozen_hardware_and_recomputes_the_data(closed_db: int) -> None:
    owner = closed_db
    fact_id = await _write_function_fact(owner)
    by_capability = {item.capability: item for item in await recompute_readiness(owner)}
    scene = by_capability[Capability.DESCRIBE_SCENE]
    assert scene.hardware == HardwareStatus(True, True, True)  # frozen, not re-attested
    assert scene.data_present is True
    assert scene.verdict is Verdict.READY

    await revoke_literal_fact(fact_id, revoked_at=_LATER)
    after = {item.capability: item for item in await recompute_readiness(owner)}
    scene_after = after[Capability.DESCRIBE_SCENE]
    assert scene_after.data_present is False
    assert scene_after.hardware == HardwareStatus(True, True, True)
    assert scene_after.verdict is Verdict.BLOCKED_BY_DATA  # data recomputed, hardware kept


async def test_recompute_raises_nothing_on_a_closed_record(closed_db: int) -> None:
    owner = closed_db
    report = await recompute_readiness(owner)  # no CommissioningClosedError
    assert len(report) == len(Capability)
