"""The commission command and its status-driven state machine (Plan 0072, ADR 0024 dec 13).

``decide_step`` reads the database and the server state and returns the next step, refusing a step
whose server state is wrong (an off-step while the server answers, an on-step while it does not).
``derive_modalities`` reports what was enrolled. ``run_commission`` performs the in-session steps and
delegates the three server-stopped steps by printing the exact command.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
from pydantic import SecretStr
import pytest
from server.commission_cli import (
    CommissioningStep,
    decide_step,
    derive_modalities,
    run_commission,
    step_guidance,
)
from server.commission_session import CommissionError
from server.memory.biometric_consent import grant_face_consent
from server.memory.commissioning import Modality
from server.personal_setup import PersonalSetupInput, apply_personal_setup
from server.settings import settings
from server.voice.speaker_embedding import model_id
from server.voice.voiceprints import VOICEPRINT_DIM, enroll_voiceprint

from server import commission_cli, db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-10-26T12:00:00+00:00"


def _state(
    monkeypatch: pytest.MonkeyPatch,
    *,
    window_open: bool = True,
    owner_ready: bool = True,
    modalities: frozenset[Modality] = frozenset({Modality.PIN, Modality.FACE, Modality.VOICE}),
    open_record: bool = False,
) -> None:
    async def _window() -> bool:
        return window_open

    async def _status() -> SimpleNamespace:
        return SimpleNamespace(personal_security_ready=owner_ready)

    async def _modalities() -> frozenset[Modality]:
        return modalities

    async def _record() -> object | None:
        return SimpleNamespace(id=1) if open_record else None

    monkeypatch.setattr(commission_cli, "importer_window_open", _window)
    monkeypatch.setattr(commission_cli, "read_personal_setup_status", _status)
    monkeypatch.setattr(commission_cli, "derive_modalities", _modalities)
    monkeypatch.setattr(commission_cli, "get_open_commissioning", _record)


async def test_no_owner_is_the_owner_step_with_the_server_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _state(monkeypatch, owner_ready=False)

    assert await decide_step(server_up=False) is CommissioningStep.OWNER


async def test_the_owner_step_refuses_a_running_server(monkeypatch: pytest.MonkeyPatch) -> None:
    _state(monkeypatch, owner_ready=False)

    with pytest.raises(CommissionError, match="detén"):
        await decide_step(server_up=True)


async def test_missing_biometrics_is_the_enrol_step_with_the_server_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _state(monkeypatch, modalities=frozenset({Modality.PIN}))

    assert await decide_step(server_up=True) is CommissioningStep.ENROL


async def test_the_enrol_step_refuses_a_stopped_server(monkeypatch: pytest.MonkeyPatch) -> None:
    _state(monkeypatch, modalities=frozenset({Modality.PIN, Modality.FACE}))

    with pytest.raises(CommissionError, match="inicia"):
        await decide_step(server_up=False)


async def test_biometrics_but_no_record_is_the_load_step(monkeypatch: pytest.MonkeyPatch) -> None:
    _state(monkeypatch, open_record=False)

    assert await decide_step(server_up=False) is CommissioningStep.LOAD


async def test_an_open_record_is_the_close_step(monkeypatch: pytest.MonkeyPatch) -> None:
    _state(monkeypatch, open_record=True)

    assert await decide_step(server_up=False) is CommissioningStep.CLOSE


async def test_a_closed_window_is_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _state(monkeypatch, window_open=False)

    assert await decide_step(server_up=True) is CommissioningStep.DONE


def test_the_delegated_steps_print_the_exact_command() -> None:
    assert any("just setup-personal" in line for line in step_guidance(CommissioningStep.OWNER))
    assert any("just seed-import" in line for line in step_guidance(CommissioningStep.LOAD))


async def test_the_enrol_step_shows_the_notice_and_runs_both_sessions() -> None:
    calls: list[str] = []
    lines: list[str] = []

    async def face() -> int:
        calls.append("face")
        return 5

    async def voice() -> int:
        calls.append("voice")
        return 3

    code = await run_commission(
        CommissioningStep.ENROL,
        read_text=lambda _: "si",
        write_text=lines.append,
        face_session=face,
        voice_session=voice,
        now=_NOW,
    )

    assert code == 0
    assert calls == ["face", "voice"]
    assert any("cara" in line.lower() for line in lines)  # the notice was shown


# --- derive_modalities against a real database --------------------------------------------------


@pytest.fixture
async def owner_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "commission.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    try:
        result = await apply_personal_setup(
            PersonalSetupInput(owner_name="Canary Owner", child_names=(), pin=SecretStr("123456"))
        )
        yield result.owner_entity_id
    finally:
        await db.close_db()
        db._conn = None


async def test_derive_modalities_reports_pin_then_face_then_voice(owner_db: int) -> None:
    assert await derive_modalities() == frozenset({Modality.PIN})

    await grant_face_consent(owner_db)
    assert await derive_modalities() == frozenset({Modality.PIN, Modality.FACE})

    vector = np.ones(VOICEPRINT_DIM, dtype=np.float32)
    for _ in range(settings.speaker_min_reference_count):
        await enroll_voiceprint(owner_db, vector, "Canary Owner", model_id())
    assert await derive_modalities() == frozenset({Modality.PIN, Modality.FACE, Modality.VOICE})
