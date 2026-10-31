"""The commission command and its status-driven state machine (Plan 0072, ADR 0024 dec 13).

``decide_step`` reads the database and the server state and returns the next step, refusing a step
whose server state is wrong (an off-step while the server answers, an on-step while it does not).
``derive_modalities`` reports what was enrolled. ``run_commission`` performs the in-session steps and
delegates the three server-stopped steps by printing the exact command.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx
import numpy as np
from pydantic import SecretStr
import pytest
from server.commission_cli import (
    CommissioningStep,
    build_face_session,
    build_voice_session,
    decide_step,
    derive_modalities,
    drive,
    run_commission,
    step_guidance,
)
from server.commission_session import CommissionError
from server.memory.biometric_consent import grant_face_consent
from server.memory.commissioning import (
    Backup,
    CommissioningInput,
    ConfirmationMode,
    Consents,
    DiskEncryption,
    InterviewerRole,
    Modality,
    get_open_commissioning,
    importer_window_open,
    open_commissioning,
    read_session_details,
)
from server.memory.conversation_consent import has_active_conversation_consent
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


async def _unused() -> int:
    raise AssertionError("this session must not run in this step")


@pytest.mark.parametrize(
    "enrolled, expected",
    [
        (frozenset({Modality.PIN}), ["face", "voice"]),
        (frozenset({Modality.PIN, Modality.FACE}), ["voice"]),
        (frozenset({Modality.PIN, Modality.VOICE}), ["face"]),
    ],
)
async def test_the_enrol_step_runs_only_the_missing_sessions(
    monkeypatch: pytest.MonkeyPatch, enrolled: frozenset[Modality], expected: list[str]
) -> None:
    _state(monkeypatch, modalities=enrolled)
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
    assert calls == expected
    assert any("cara" in line.lower() for line in lines)  # the notice was shown


async def test_the_enrol_step_names_the_env_flags_it_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    _state(monkeypatch, modalities=frozenset({Modality.PIN}))
    lines: list[str] = []

    async def session() -> int:
        return 1

    await run_commission(
        CommissioningStep.ENROL,
        read_text=lambda _: "si",
        write_text=lines.append,
        face_session=session,
        voice_session=session,
        now=_NOW,
    )

    text = "\n".join(lines)
    assert "FACE_AUTHENTICATION_ENABLED" in text
    assert "SPEAKER_AUTHENTICATION_ENABLED" in text


async def test_the_wired_sessions_give_a_real_countdown(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, dict[str, object]] = {}

    async def fake_face(**kwargs: object) -> int:
        seen["face"] = kwargs
        return 0

    async def fake_voice(**kwargs: object) -> int:
        seen["voice"] = kwargs
        return 0

    monkeypatch.setattr(commission_cli, "run_face_session", fake_face)
    monkeypatch.setattr(commission_cli, "run_voice_session", fake_voice)
    async with httpx.AsyncClient() as client:
        await build_face_session(client, lambda _: "", lambda: b"")()
        await build_voice_session(client, lambda _: "", lambda: b"")()

    assert float(str(seen["face"]["countdown_s"])) > 0
    assert float(str(seen["voice"]["countdown_s"])) > 0


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


# --- the close step and the driver, against a real database -------------------------------------

_HARDWARE_ANSWERS = ["si"] * 21  # seven capabilities, three questions each
# The conversation storage consent is asked last (Plan 0076); most tests decline it.
_NO_RECORD = "no"


async def _open_alta() -> int:
    record = await open_commissioning(
        CommissioningInput(
            interviewer_label="Canary Interviewer",
            interviewer_role=InterviewerRole.BUILDER,
            confirmation_mode=ConfirmationMode.BUILDER_IS_OWNER,
            disk_encryption=DiskEncryption.DECLARED_YES,
        ),
        started_at=_NOW,
    )
    return record.id


async def _close_with(answers: list[str], lines: list[str]) -> int:
    queue = iter(answers)
    return await run_commission(
        CommissioningStep.CLOSE,
        read_text=lambda _: next(queue),
        write_text=lines.append,
        face_session=_unused,
        voice_session=_unused,
        now=_NOW,
    )


async def test_the_close_step_records_everything_and_closes(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commission_cli, "_ACTA_DIR", tmp_path / "actas")
    record_id = await _open_alta()
    answers = [
        "data/backups/pre.db",
        "2027-01-31",
        "data/backups/base.db",
        "2027-02-28",
        "si",
        "no",
        "si",
        "Canary Homelab",
        *_HARDWARE_ANSWERS,
        _NO_RECORD,
    ]
    lines: list[str] = []

    code = await _close_with(answers, lines)

    details = await read_session_details(record_id)
    assert code == 0
    assert details.pre_reset_backup == Backup("data/backups/pre.db", "2027-01-31")
    assert details.baseline_backup == Backup("data/backups/base.db", "2027-02-28")
    assert details.consents == Consents(True, False, True, "Canary Homelab")
    assert details.biometric_notice_version == "v1"
    assert details.modalities == frozenset({Modality.PIN})
    assert details.readiness_json is not None
    assert await importer_window_open() is False
    (acta,) = (tmp_path / "actas").glob("acta-*.md")
    assert "Canary Owner" not in acta.read_text(encoding="utf-8")  # no household value


@pytest.mark.parametrize("answer, granted", [("si", True), ("no", False)])
async def test_the_alta_close_grants_the_conversation_consent_only_on_si(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str, granted: bool
) -> None:
    """Plan 0076 Task 5: the notice is shown and only `si` grants `conversation_storage`."""
    monkeypatch.setattr(commission_cli, "_ACTA_DIR", tmp_path / "actas")
    await _open_alta()
    answers = ["", "data/backups/base.db", "2027-02-28", "no", "no", "no"]
    lines: list[str] = []

    code = await _close_with([*answers, *_HARDWARE_ANSWERS, answer], lines)

    assert code == 0
    assert any("Aviso de registro de conversaciones" in line for line in lines)
    assert await has_active_conversation_consent(owner_db) is granted


async def test_no_pre_reset_backup_is_recorded_when_there_was_none(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commission_cli, "_ACTA_DIR", tmp_path / "actas")
    record_id = await _open_alta()
    answers = [
        "",
        "data/backups/base.db",
        "2027-02-28",
        "no",
        "no",
        "no",
        *_HARDWARE_ANSWERS,
        _NO_RECORD,
    ]

    await _close_with(answers, [])

    details = await read_session_details(record_id)
    assert details.pre_reset_backup is None
    assert details.baseline_backup == Backup("data/backups/base.db", "2027-02-28")


async def test_a_bad_backup_date_fails_before_the_long_questionnaire(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commission_cli, "_ACTA_DIR", tmp_path / "actas")
    record_id = await _open_alta()

    with pytest.raises(ValueError, match="date"):
        await _close_with(["data/backups/pre.db", "31-01-2027"], [])

    assert (await read_session_details(record_id)).consents is None
    assert await get_open_commissioning() is not None  # still open: nothing half-closed


async def test_the_close_step_tells_you_to_copy_the_database_first(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commission_cli, "_ACTA_DIR", tmp_path / "actas")
    await _open_alta()
    lines: list[str] = []

    await _close_with(
        [
            "",
            "data/backups/base.db",
            "2027-02-28",
            "no",
            "no",
            "no",
            *_HARDWARE_ANSWERS,
            _NO_RECORD,
        ],
        lines,
    )

    assert any("copia" in line.lower() and "respaldo" in line.lower() for line in lines)


@pytest.fixture
async def owner_db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A database with a ready owner, closed again so ``drive`` opens it itself."""
    path = tmp_path / "commission.db"
    monkeypatch.setattr(settings, "brain_db_path", path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    await apply_personal_setup(
        PersonalSetupInput(owner_name="Canary Owner", child_names=(), pin=SecretStr("123456"))
    )
    await db.close_db()
    db._conn = None
    return path


async def test_drive_prints_a_wrong_server_state_instead_of_a_traceback(
    owner_db_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commission_cli, "_server_answers", lambda: False)
    lines: list[str] = []

    code = await drive(
        read_text=lambda _: "",
        write_text=lines.append,
        face_session=_unused,
        voice_session=_unused,
        now=_NOW,
    )

    assert code == 1
    assert any("run-server" in line for line in lines)


async def test_drive_without_a_database_points_at_setup_personal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "missing.db")
    lines: list[str] = []

    code = await drive(
        read_text=lambda _: "",
        write_text=lines.append,
        face_session=_unused,
        voice_session=_unused,
        now=_NOW,
    )

    assert code == 0
    assert any("just setup-personal" in line for line in lines)
    assert not (tmp_path / "missing.db").exists()  # nothing was created


# --- the unlock retries a mistyped PIN and the enrol errors say why -----------------------------


def _unlock_client(statuses: list[int]) -> httpx.AsyncClient:
    """A client whose unlock endpoint answers the given statuses in order (200 gives a token)."""
    queue = iter(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(queue)
        if status == 200:
            return httpx.Response(200, json={"token": "fake-token"})
        return httpx.Response(status, json={"detail": "rejected"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_a_mistyped_pin_is_asked_again_instead_of_aborting() -> None:
    pins = iter(["", "123456"])
    lines: list[str] = []

    async with _unlock_client([422, 200]) as client:
        unlocked = await commission_cli._unlock(client, lambda _: next(pins), lines.append)

    assert unlocked == "fake-token"
    assert any("6 a 12" in line for line in lines)  # a 422 says what a PIN looks like


async def test_a_wrong_pin_says_so_and_is_asked_again() -> None:
    pins = iter(["000000", "123456"])
    lines: list[str] = []

    async with _unlock_client([401, 200]) as client:
        unlocked = await commission_cli._unlock(client, lambda _: next(pins), lines.append)

    assert unlocked == "fake-token"
    assert any("incorrecto" in line for line in lines)


async def test_three_rejected_pins_give_up() -> None:
    asked: list[str] = []

    def read_pin(prompt: str) -> str:
        asked.append(prompt)
        return "000000"

    async with _unlock_client([401, 401, 401]) as client:
        with pytest.raises(CommissionError, match="PIN"):
            await commission_cli._unlock(client, read_pin, lambda _: None)

    assert len(asked) == 3


async def test_a_throttled_unlock_is_not_retried() -> None:
    asked: list[str] = []

    def read_pin(prompt: str) -> str:
        asked.append(prompt)
        return "123456"

    async with _unlock_client([429, 200]) as client:
        with pytest.raises(CommissionError, match="429"):
            await commission_cli._unlock(client, read_pin, lambda _: None)

    assert len(asked) == 1


def test_an_enrol_rejection_surfaces_the_servers_reason() -> None:
    response = httpx.Response(422, json={"detail": "no_face: no face found in the frame"})

    with pytest.raises(CommissionError, match="no_face"):
        commission_cli._enroll_result(response)


def test_an_enrol_rejection_without_a_reason_still_names_the_status() -> None:
    with pytest.raises(CommissionError, match="500"):
        commission_cli._enroll_result(httpx.Response(500, text="boom"))


def test_a_very_long_reason_is_cut() -> None:
    response = httpx.Response(422, json={"detail": "x" * 400})

    with pytest.raises(CommissionError) as raised:
        commission_cli._enroll_result(response)

    assert len(str(raised.value)) < 200


# --- the backups are chosen from a list, with a suggested destruction date ----------------------

_RETENTION_DAYS = 90


def _two_backups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A backups folder with ``newer.db`` listed first and ``older.db`` second."""
    folder = tmp_path / "backups"
    folder.mkdir()
    for name, age_s in (("older.db", 1000), ("newer.db", 0)):
        path = folder / name
        path.write_bytes(b"x")
        os.utime(path, (1_800_000_000 - age_s, 1_800_000_000 - age_s))
    monkeypatch.setattr(commission_cli, "_BACKUPS_DIR", folder)
    monkeypatch.setattr(commission_cli, "_ACTA_DIR", tmp_path / "actas")


def _default_day() -> str:
    return (datetime.fromisoformat(_NOW) + timedelta(days=_RETENTION_DAYS)).date().isoformat()


async def test_the_backups_are_picked_by_number_with_a_default_date(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_backups(tmp_path, monkeypatch)
    record_id = await _open_alta()
    lines: list[str] = []

    await _close_with(["2", "", "1", "", "no", "no", "no", *_HARDWARE_ANSWERS, _NO_RECORD], lines)

    details = await read_session_details(record_id)
    assert details.pre_reset_backup == Backup("data/backups/older.db", _default_day())
    assert details.baseline_backup == Backup("data/backups/newer.db", _default_day())
    assert any("1) newer.db" in line for line in lines)  # the list was shown, newest first
    assert any("2) older.db" in line for line in lines)


async def test_an_empty_baseline_is_asked_again_instead_of_aborting(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_backups(tmp_path, monkeypatch)
    record_id = await _open_alta()
    lines: list[str] = []

    await _close_with(["", "", "1", "", "no", "no", "no", *_HARDWARE_ANSWERS, _NO_RECORD], lines)

    assert (await read_session_details(record_id)).baseline_backup is not None
    assert any("obligatorio" in line for line in lines)


async def test_a_number_outside_the_list_is_asked_again(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_backups(tmp_path, monkeypatch)
    record_id = await _open_alta()
    lines: list[str] = []

    await _close_with(["", "9", "1", "", "no", "no", "no", *_HARDWARE_ANSWERS, _NO_RECORD], lines)

    details = await read_session_details(record_id)
    assert details.baseline_backup == Backup("data/backups/newer.db", _default_day())
    assert any("respaldo con ese" in line for line in lines)


async def test_the_prompts_say_what_each_backup_is(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_backups(tmp_path, monkeypatch)
    await _open_alta()
    lines: list[str] = []

    await _close_with(["", "1", "", "no", "no", "no", *_HARDWARE_ANSWERS, _NO_RECORD], lines)

    text = "\n".join(lines)
    assert "reset-db" in text  # what the pre-reset backup is
    assert "paso 7" in text  # what the baseline backup is


async def test_a_listed_file_name_typed_as_is_is_stored_with_its_folder(
    owner_db: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_backups(tmp_path, monkeypatch)
    record_id = await _open_alta()

    await _close_with(
        ["older.db", "", "newer.db", "", "no", "no", "no", *_HARDWARE_ANSWERS, _NO_RECORD], []
    )

    details = await read_session_details(record_id)
    assert details.pre_reset_backup == Backup("data/backups/older.db", _default_day())
    assert details.baseline_backup == Backup("data/backups/newer.db", _default_day())
