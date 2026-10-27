"""The `commission` command core: the guided alta of the robot (Plan 0072, ADR 0024 decision 13).

A status-driven state machine, like ``scripts/onboard.py``: it reads the database and the server
state and tells the exact next step, never asking for the server to be both on and off. It performs
the in-session steps (the biometric notice, the consents, the face and voice sessions, the readiness
report, the baseline backup, the acta and the closing) and **delegates** the three server-stopped,
already-guarded steps by printing their command: ``just reset-db``, ``just setup-personal`` and
``just seed-import``. It enables no capability.

This module is server-only: it never imports the robot (CLAUDE.md hard boundary). The camera and the
microphone are wired by ``scripts/commission.py`` and injected as adapters; the enrol calls here are
loopback HTTP to the server, never the robot.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from pathlib import Path

import httpx

from server import db
from server.commission_session import (
    BIOMETRIC_NOTICE_VERSION,
    CommissionError,
    SpeakerAuthDisabledError,
    load_biometric_notice,
    read_consents,
    run_face_session,
    run_voice_session,
)
from server.exceptions import BrainMemoryError
from server.memory.biometric_consent import has_active_face_consent
from server.memory.commissioning import (
    BackupKind,
    Modality,
    get_open_commissioning,
    importer_window_open,
    list_section_statuses,
    record_backup,
    record_biometric_notice,
    record_consents,
    record_readiness,
)
from server.memory.commissioning_acta import close_session
from server.memory.commissioning_readiness import (
    Capability,
    HardwareStatus,
    evaluate_readiness,
    readiness_to_json,
)
from server.memory.owner_credentials import get_active_owner_pin_credential, get_ready_owner
from server.personal_setup import read_personal_setup_status
from server.settings import settings
from server.voice.speaker_embedding import model_id
from server.voice.voiceprints import count_voiceprints

__all__ = [
    "CommissioningStep",
    "build_face_session",
    "build_voice_session",
    "decide_step",
    "derive_modalities",
    "drive",
    "run_commission",
    "step_guidance",
]

type ReadText = Callable[[str], str]
type WriteText = Callable[[str], None]
type Session = Callable[[], Awaitable[int]]
type CaptureFrame = Callable[[], bytes]
type RecordClip = Callable[[], bytes]
type ReadPin = Callable[[str], str]

_PROBE_TIMEOUT_S = 2.0
# Seconds the owner gets between the PIN (or the prompt) and the capture, to face the camera or
# start reading; the camera and microphone sessions would otherwise fire as Enter is pressed.
_COUNTDOWN_S = 3.0
_UNLOCK_SCOPE = "biometric_admin"
_YES = frozenset({"si", "sí"})
# The acta goes under data/commissioning/, which git ignores (ADR 0024 decision 5).
_ACTA_DIR = Path(__file__).resolve().parents[3] / "data" / "commissioning"


class CommissioningStep(StrEnum):
    """The next action of the alta, in the order of ADR 0024 decision 13."""

    OWNER = "owner"
    ENROL = "enrol"
    LOAD = "load"
    CLOSE = "close"
    DONE = "done"


# Which server state each step needs; ``None`` means either is fine.
_STEP_NEEDS_SERVER: dict[CommissioningStep, bool | None] = {
    CommissioningStep.OWNER: False,
    CommissioningStep.ENROL: True,
    CommissioningStep.LOAD: False,
    CommissioningStep.CLOSE: False,
    CommissioningStep.DONE: None,
}

_GUIDANCE: dict[CommissioningStep, list[str]] = {
    CommissioningStep.OWNER: [
        "Paso: crea a la persona dueña y su PIN (servidor detenido).",
        "Antes, si corresponde: just reset-db (respalda y borra la base).",
        "Ejecuta: just setup-personal",
    ],
    CommissioningStep.ENROL: [
        "Paso: lee el aviso biométrico y enrola la cara y la voz (servidor encendido).",
        "Requiere FACE_AUTHENTICATION_ENABLED=true y SPEAKER_AUTHENTICATION_ENABLED=true en "
        ".env, con el servidor reiniciado después de cambiarlos.",
    ],
    CommissioningStep.LOAD: [
        "Paso: carga el expediente del hogar (servidor detenido).",
        "Ejecuta: just seed-import <archivo> --apply --interviewer <nombre> "
        "--role builder --mode builder_is_owner --disk-encryption yes",
    ],
    CommissioningStep.CLOSE: [
        "Paso: consentimientos, informe de preparación, respaldo base y cierre (servidor detenido).",
    ],
    CommissioningStep.DONE: ["El alta ya está cerrada. No hay más pasos."],
}


async def derive_modalities() -> frozenset[Modality]:
    """Return the modalities enrolled, derived from the database (ADR 0024 decision 15).

    ``pin`` from the active owner credential, ``face`` from an active face consent (granted exactly
    on enrolment and purged on revoke), ``voice`` from voice references at or above
    ``settings.speaker_min_reference_count``.
    """
    modalities: set[Modality] = set()
    if await get_active_owner_pin_credential() is not None:
        modalities.add(Modality.PIN)
    owner = await get_ready_owner()
    if owner is not None:
        if await has_active_face_consent(owner):
            modalities.add(Modality.FACE)
        if await count_voiceprints(owner, model_id()) >= settings.speaker_min_reference_count:
            modalities.add(Modality.VOICE)
    return frozenset(modalities)


async def _next_step() -> CommissioningStep:
    """Read the database and return the next step, ignoring the server state."""
    if not await importer_window_open():
        return CommissioningStep.DONE
    if not (await read_personal_setup_status()).personal_security_ready:
        return CommissioningStep.OWNER
    if not {Modality.FACE, Modality.VOICE} <= await derive_modalities():
        return CommissioningStep.ENROL
    if await get_open_commissioning() is None:
        return CommissioningStep.LOAD
    return CommissioningStep.CLOSE


async def decide_step(*, server_up: bool) -> CommissioningStep:
    """Return the next step, refusing one whose server state is wrong.

    Args:
        server_up: Whether the server answers ``/health`` right now.

    Returns:
        The next :class:`CommissioningStep`.

    Raises:
        CommissionError: If the step needs the server stopped while it is running, or started while
            it is stopped.
    """
    step = await _next_step()
    needed = _STEP_NEEDS_SERVER[step]
    if needed is True and not server_up:
        raise CommissionError(
            f"El paso '{step.value}' necesita el servidor: inicia just run-server."
        )
    if needed is False and server_up:
        raise CommissionError(f"El paso '{step.value}' necesita el servidor detenido: deténlo.")
    return step


def step_guidance(step: CommissioningStep) -> list[str]:
    """Return the lines to print for a step, including the command for a delegated one."""
    return _GUIDANCE[step]


def _ask_yes_no(read_text: ReadText, question: str) -> bool:
    """Ask a yes/no question; only ``si`` (with or without the accent) is a yes."""
    return read_text(f"{question} (si/no): ").strip().lower() in _YES


def _read_hardware(read_text: ReadText, write_text: WriteText) -> dict[Capability, HardwareStatus]:
    """Ask, for each capability that exists today, whether it is supported, configured, verified."""
    write_text("Informe de preparación. Para cada capacidad responde si/no.")
    hardware: dict[Capability, HardwareStatus] = {}
    for capability in Capability:
        write_text(f"Capacidad: {capability.value}")
        hardware[capability] = HardwareStatus(
            supported=_ask_yes_no(read_text, "  ¿El hardware y el software están soportados?"),
            configured=_ask_yes_no(read_text, "  ¿Está configurado?"),
            verified=_ask_yes_no(read_text, "  ¿Lo verificaste con un turno real?"),
        )
    return hardware


async def _record_backups(record_id: int, read_text: ReadText) -> tuple[str, str]:
    """Ask for both backups and record them now, so a typo fails before the long questionnaire.

    The pre-reset backup is optional (Enter when there was none); the baseline one is not.

    Returns:
        The baseline backup's path and destruction date, for the closing.
    """
    pre_reset = read_text("Ruta del respaldo previo al reset (Enter si no hubo): ").strip()
    if pre_reset:
        destroy_by = read_text("Fecha para destruirlo (YYYY-MM-DD): ").strip()
        await record_backup(
            record_id, which=BackupKind.PRE_RESET, reference=pre_reset, destroy_by=destroy_by
        )
    baseline = read_text("Ruta de la copia del respaldo base (offline): ").strip()
    baseline_destroy_by = read_text("Fecha para destruir esa copia (YYYY-MM-DD): ").strip()
    await record_backup(
        record_id, which=BackupKind.BASELINE, reference=baseline, destroy_by=baseline_destroy_by
    )
    return baseline, baseline_destroy_by


async def _run_close(read_text: ReadText, write_text: WriteText, now: str) -> int:
    """Collect backups, consents and hardware, record the readiness and close the alta."""
    record = await get_open_commissioning()
    if record is None:
        raise CommissionError("No hay un alta abierta que cerrar.")
    write_text(
        "Cierre del alta (servidor detenido). Antes debiste verificar un turno real por cara y "
        "voz con el servidor encendido, y hacer una copia del respaldo base de la base de datos."
    )
    baseline_reference, baseline_destroy_by = await _record_backups(record.id, read_text)
    consents = read_consents(read_text=read_text, write_text=write_text)
    hardware = _read_hardware(read_text, write_text)
    statuses = await list_section_statuses(record.id)
    readiness = evaluate_readiness(statuses, hardware)
    await record_biometric_notice(record.id, BIOMETRIC_NOTICE_VERSION)
    await record_consents(record.id, consents)
    await record_readiness(record.id, readiness_to_json(readiness))
    modalities = await derive_modalities()
    acta = await close_session(
        record.id,
        baseline_reference=baseline_reference,
        baseline_destroy_by=baseline_destroy_by,
        modalities=modalities,
        out_dir=_ACTA_DIR,
        now=now,
    )
    write_text(f"Alta cerrada. Acta en {acta}.")
    return 0


async def run_commission(
    step: CommissioningStep,
    *,
    read_text: ReadText,
    write_text: WriteText,
    face_session: Session,
    voice_session: Session,
    now: str,
) -> int:
    """Perform one step of the alta; delegate the server-stopped steps by printing their command.

    Args:
        step: The decided step.
        read_text: Prompts for and returns one line.
        write_text: Prints one line.
        face_session: A pre-wired :func:`server.commission_session.run_face_session`.
        voice_session: A pre-wired :func:`server.commission_session.run_voice_session`.
        now: UTC ISO 8601, used when closing.

    Returns:
        ``0`` on success.
    """
    match step:
        case CommissioningStep.ENROL:
            for line in step_guidance(step):
                write_text(line)
            write_text(load_biometric_notice())
            enrolled = await derive_modalities()
            if Modality.FACE not in enrolled:
                await face_session()
            if Modality.VOICE not in enrolled:
                await voice_session()
            return 0
        case CommissioningStep.CLOSE:
            return await _run_close(read_text, write_text, now)
        case _:
            for line in step_guidance(step):
                write_text(line)
            return 0


def _server_url() -> str:
    """Resolve the server's loopback base URL from settings."""
    host = "localhost" if settings.server_host == "0.0.0.0" else settings.server_host  # noqa: S104
    return f"http://{host}:{settings.server_port}"


def _server_answers() -> bool:
    """Return whether the server answers ``/health`` on this machine (probed once, 2 s)."""
    try:
        httpx.get(f"{_server_url()}/health", timeout=_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return False
    return True


async def _unlock(client: httpx.AsyncClient, read_pin: ReadPin) -> str:
    """Verify the local PIN and return one fresh one-use token for ``biometric_admin``."""
    import asyncio  # noqa: PLC0415 — only this hardware path needs the thread offload

    pin = await asyncio.to_thread(read_pin, "Owner PIN: ")
    response = await client.post(
        f"{_server_url()}/auth/owner/unlock", json={"pin": pin, "scope": _UNLOCK_SCOPE}
    )
    if response.is_error:
        raise CommissionError(f"PIN rechazado: {response.status_code}")
    return str(response.json()["token"])


def _enroll_result(response: httpx.Response) -> str:
    """Return the profile id of a successful enrol, or raise a closed error."""
    if response.is_error:
        raise CommissionError(f"Enrolamiento rechazado: {response.status_code}")
    return str(response.json().get("profile_id", ""))


def build_face_session(
    client: httpx.AsyncClient, read_pin: ReadPin, capture: CaptureFrame
) -> Session:
    """Wire :func:`run_face_session` to the unlock and enroll endpoints and an injected camera.

    Args:
        client: A loopback HTTP client.
        read_pin: Prompts for the owner PIN (one-use per frame).
        capture: Returns one JPEG frame; injected by the robot-aware entry point.

    Returns:
        A no-argument coroutine that runs the whole face session.
    """

    async def unlock() -> str:
        return await _unlock(client, read_pin)

    async def enroll(token: str, frame: bytes) -> str:
        response = await client.post(
            f"{_server_url()}/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": token},
            files={"image": ("frame.jpg", frame, "image/jpeg")},
        )
        return _enroll_result(response)

    async def session() -> int:
        return await run_face_session(
            unlock=unlock,
            capture=capture,
            enroll=enroll,
            write_text=print,
            countdown_s=_COUNTDOWN_S,
        )

    return session


def build_voice_session(
    client: httpx.AsyncClient, read_pin: ReadPin, record: RecordClip
) -> Session:
    """Wire :func:`run_voice_session` to the unlock and enroll endpoints and an injected microphone.

    Args:
        client: A loopback HTTP client.
        read_pin: Prompts for the owner PIN (one-use per reference).
        record: Returns one contract WAV clip; injected by the robot-aware entry point.

    Returns:
        A no-argument coroutine that runs the whole voice session.
    """

    async def unlock() -> str:
        return await _unlock(client, read_pin)

    async def enroll(token: str, clip: bytes) -> str:
        response = await client.post(
            f"{_server_url()}/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": token},
            files={"audio": ("clip.wav", clip, "audio/wav")},
        )
        if response.status_code == 503:  # noqa: PLR2004 — speaker authentication is off
            raise SpeakerAuthDisabledError("speaker authentication disabled")
        return _enroll_result(response)

    async def session() -> int:
        return await run_voice_session(
            unlock=unlock,
            record=record,
            level_check=lambda _: True,
            enroll=enroll,
            write_text=print,
            countdown_s=_COUNTDOWN_S,
        )

    return session


async def drive(
    *,
    read_text: ReadText,
    write_text: WriteText,
    face_session: Session,
    voice_session: Session,
    now: str,
) -> int:
    """Open the database, decide the next step and perform or delegate it.

    Guides the owner step when no database exists yet (the owner is created by ``setup-personal``).

    Args:
        read_text: Prompts for and returns one line.
        write_text: Prints one line.
        face_session: The wired face session (used only by the ENROL step).
        voice_session: The wired voice session (used only by the ENROL step).
        now: UTC ISO 8601.

    Returns:
        The exit code.
    """
    if not settings.brain_db_path.exists():
        for line in step_guidance(CommissioningStep.OWNER):
            write_text(line)
        return 0
    server_up = _server_answers()
    await db.open_db()
    try:
        await db.run_migrations()
        step = await decide_step(server_up=server_up)
        return await run_commission(
            step,
            read_text=read_text,
            write_text=write_text,
            face_session=face_session,
            voice_session=voice_session,
            now=now,
        )
    except (BrainMemoryError, ValueError) as exc:
        # A closed, printable message (a wrong server state, a bad date, a closed alta), the way
        # scripts/onboard.py reports it, instead of a traceback.
        write_text(str(exc))
        return 1
    finally:
        await db.close_db()
