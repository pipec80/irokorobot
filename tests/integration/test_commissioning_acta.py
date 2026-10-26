"""The acta of the alta, the baseline backup and the closing (Plan 0072, ADR 0024 dec 13, 14).

The acta is a Markdown rendering of the record with no household value; close_session records the
baseline backup and the modalities, writes the acta under a given directory and closes the window.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.exceptions import CommissioningClosedError
from server.memory.commissioning import (
    Backup,
    CommissioningInput,
    CommissioningRecord,
    ConfirmationMode,
    Consents,
    DiskEncryption,
    InterviewerRole,
    Modality,
    Section,
    SectionStatus,
    SessionDetails,
    importer_window_open,
    list_section_statuses,
    open_commissioning,
    read_session_details,
    record_readiness,
    set_section_status,
)
from server.memory.commissioning_acta import close_session, render_acta, write_acta
from server.memory.commissioning_readiness import (
    Capability,
    HardwareStatus,
    evaluate_readiness,
    readiness_to_json,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_STARTED_AT = "2026-10-26T10:00:00+00:00"
_NOW = "2026-10-26T12:00:00+00:00"
_LABEL = "Canary Interviewer"


@pytest.fixture
async def commissioning_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "commissioning.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield
    finally:
        await db.close_db()
        db._conn = None


async def _open() -> int:
    record = await open_commissioning(
        CommissioningInput(
            interviewer_label=_LABEL,
            interviewer_role=InterviewerRole.BUILDER,
            confirmation_mode=ConfirmationMode.BUILDER_IS_OWNER,
            disk_encryption=DiskEncryption.DECLARED_YES,
        ),
        started_at=_STARTED_AT,
    )
    return record.id


def _readiness() -> tuple:
    return evaluate_readiness(
        {Section.FUNCTION: SectionStatus.PROVIDED},
        {Capability.DESCRIBE_SCENE: HardwareStatus(True, True, True)},
    )


def test_render_acta_has_the_structure_and_no_household_value() -> None:
    record = CommissioningRecord(
        id=1,
        installation_id="11111111-1111-4111-8111-111111111111",
        started_at=_STARTED_AT,
        interviewer_label=_LABEL,
        interviewer_role=InterviewerRole.BUILDER,
        confirmation_mode=ConfirmationMode.BUILDER_IS_OWNER,
        disk_encryption=DiskEncryption.DECLARED_YES,
        pool_version=1,
        seed_file_sha256="ab" * 32,
        counts={"children": 2, "contacts": 3},
        closed_at=None,
    )
    details = SessionDetails(
        biometric_notice_version="v1",
        consents=Consents(True, False, True, "Canary Homelab"),
        modalities=frozenset({Modality.PIN, Modality.FACE, Modality.VOICE}),
        pre_reset_backup=Backup("data/backups/pre.db", "2027-01-31"),
        baseline_backup=Backup("data/backups/base.db", "2027-02-28"),
        readiness_json=readiness_to_json(_readiness()),
    )

    acta = render_acta(record, details, {Section.FUNCTION: SectionStatus.PROVIDED}, _readiness())

    assert record.installation_id in acta
    assert "describe_scene" in acta
    assert "v1" in acta
    for household in ("Canary Child", "Canary Owner", "+56900000001", "té verde"):
        assert household not in acta


async def test_write_acta_writes_a_file_named_by_the_installation_id(
    commissioning_db: None, tmp_path: Path
) -> None:
    record_id = await _open()
    await record_readiness(record_id, readiness_to_json(_readiness()))
    out_dir = tmp_path / "commissioning"

    path = await write_acta(record_id, out_dir=out_dir)

    record = await read_session_details(record_id)
    assert path.parent == out_dir
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("# Acta")
    assert record is not None  # the record is untouched by writing the acta


async def test_close_session_records_the_baseline_the_modalities_the_acta_and_closes(
    commissioning_db: None, tmp_path: Path
) -> None:
    record_id = await _open()
    await set_section_status(record_id, Section.FUNCTION, SectionStatus.PROVIDED, _STARTED_AT)
    await record_readiness(record_id, readiness_to_json(_readiness()))
    modalities = frozenset({Modality.PIN, Modality.FACE})

    path = await close_session(
        record_id,
        baseline_reference="data/backups/base.db",
        baseline_destroy_by="2027-02-28",
        modalities=modalities,
        out_dir=tmp_path / "commissioning",
        now=_NOW,
    )

    assert path.exists()
    details = await read_session_details(record_id)
    assert details.modalities == modalities
    assert details.baseline_backup == Backup("data/backups/base.db", "2027-02-28")
    assert await importer_window_open() is False
    assert await list_section_statuses(record_id)  # statuses still readable after close


async def test_a_second_close_is_refused(commissioning_db: None, tmp_path: Path) -> None:
    record_id = await _open()
    await record_readiness(record_id, readiness_to_json(_readiness()))
    kwargs = {
        "baseline_reference": "data/backups/base.db",
        "baseline_destroy_by": "2027-02-28",
        "modalities": frozenset({Modality.PIN}),
        "out_dir": tmp_path / "commissioning",
        "now": _NOW,
    }
    await close_session(record_id, **kwargs)  # type: ignore[arg-type]

    with pytest.raises(CommissioningClosedError):
        await close_session(record_id, **kwargs)  # type: ignore[arg-type]
