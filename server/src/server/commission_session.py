"""The commissioning session: the biometric notice, the consents, the face and voice sessions.

Plan 0072. The steps here are driven by injected adapters (``read_text``, ``write_text``, and the
unlock/capture/enroll callables of the face and voice sessions) so they test without a real
terminal, camera or microphone. No audio, no frame and no household value is stored by this module;
the enrolment endpoints embed and discard the media.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from server.memory.commissioning import Consents
from server.settings import settings

__all__ = [
    "BIOMETRIC_NOTICE_PATH",
    "BIOMETRIC_NOTICE_VERSION",
    "READING_SCRIPT",
    "CommissionError",
    "SpeakerAuthDisabledError",
    "load_biometric_notice",
    "read_consents",
    "run_face_session",
    "run_voice_session",
]

type ReadText = Callable[[str], str]
type WriteText = Callable[[str], None]
type Unlock = Callable[[], Awaitable[str]]
type CaptureFrame = Callable[[], bytes]
type EnrollFrame = Callable[[str, bytes], Awaitable[str]]
type RecordClip = Callable[[], bytes]
type LevelCheck = Callable[[bytes], bool]
type EnrollClip = Callable[[str, bytes], Awaitable[str]]
type Sleep = Callable[[float], Awaitable[None]]

# The five face poses of ADR 0024 decision 15 / Plan 0030 (distance, glasses, lighting).
_FACE_POSES = (
    "de frente, a la distancia normal",
    "un poco más lejos",
    "con lentes puestos (si no usas, mira de frente otra vez)",
    "sin lentes",
    "con otra luz: muévete o cambia la iluminación",
)

# The biometric notice read to the owner; its version is stored in the acta (ADR 0024 decision 15).
BIOMETRIC_NOTICE_VERSION = "v1"
BIOMETRIC_NOTICE_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "legal" / "biometric-notice-v1.md"
)
_YES = frozenset({"si", "sí"})


class CommissionError(ValueError):
    """A commissioning session cannot proceed; its message is safe to print."""


class SpeakerAuthDisabledError(CommissionError):
    """Voice enrolment returned 503: ``SPEAKER_AUTHENTICATION_ENABLED`` is off (Plan 0053)."""


# A short Spanish text (tuteo) the owner reads aloud so the recognizer learns their voice; it holds
# no household value. The audio is embedded and discarded by the endpoint, never stored.
READING_SCRIPT = (
    "Hola, soy la persona dueña de este robot y estoy leyendo este texto en voz alta. "
    "Lo hago para que aprendas a reconocer mi voz cuando converse contigo. "
    "Hoy es un buen día y tengo ganas de probar cómo me escuchas. "
    "Cuando termine de leer, ya podrás distinguir mi voz de la de otras personas."
)

# How many extra capture attempts the voice session tolerates before it gives up.
_VOICE_ATTEMPT_SLACK = 5


def load_biometric_notice() -> str:
    """Return the tracked biometric notice.

    Returns:
        The notice's Markdown text.

    Raises:
        CommissionError: If the notice file is missing or unreadable.
    """
    try:
        return BIOMETRIC_NOTICE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise CommissionError(
            f"the biometric notice is missing at {BIOMETRIC_NOTICE_PATH}"
        ) from exc


def _ask_yes_no(read_text: ReadText, question: str) -> bool:
    """Ask a yes/no question; only ``si`` (with or without the accent) is a yes."""
    return read_text(f"{question} (si/no): ").strip().lower() in _YES


def read_consents(*, read_text: ReadText, write_text: WriteText) -> Consents:
    """Collect the operations-plane consents (ADR 0025 decision 10); a consent enables nothing.

    Args:
        read_text: Adapter that prompts for and returns one line.
        write_text: Adapter that writes one line of output.

    Returns:
        The three consents and an optional backup destination label.
    """
    write_text("Consentimientos del plano de operaciones. Puedes decir que no a todo.")
    telemetry = _ask_yes_no(
        read_text, "¿Autorizas enviar el estado de la máquina, sin datos del hogar?"
    )
    remote_support = _ask_yes_no(
        read_text, "¿Autorizas abrir una sesión de soporte remoto cuando tú lo pidas?"
    )
    backup = _ask_yes_no(read_text, "¿Autorizas un respaldo cifrado fuera del robot?")
    destination: str | None = None
    if backup:
        destination = read_text("¿A dónde va el respaldo? Etiqueta opcional: ").strip() or None
    return Consents(
        telemetry=telemetry,
        remote_support=remote_support,
        backup=backup,
        backup_destination=destination,
    )


async def run_face_session(
    *,
    unlock: Unlock,
    capture: CaptureFrame,
    enroll: EnrollFrame,
    write_text: WriteText,
    frames: int = 5,
    countdown_s: float = 0.0,
    sleep: Sleep = asyncio.sleep,
) -> int:
    """Enrol the owner's face in several frames, one unlock each (ADR 0024 decision 15).

    Guides the poses of :data:`_FACE_POSES`, unlocks once per frame (each token is one-use), waits
    ``countdown_s`` after the PIN so the owner can look at the camera, and stops cleanly if a frame
    is rejected (``no_face``, ``multiple_faces``, ``low_quality``, ``face_too_small``). An
    ``unlock`` that fails propagates; a rejected frame only stops the session.

    Args:
        unlock: Returns a fresh one-use owner-unlock token for ``biometric_admin``.
        capture: Returns one JPEG frame from the camera.
        enroll: Posts one frame to ``/auth/owner/face/enroll``; raises for a rejected frame.
        write_text: Writes one line of guidance to the terminal.
        frames: How many frames to try (default five).
        countdown_s: Seconds to wait between the PIN and the capture (0 for none).
        sleep: Awaits the countdown; injected so tests do not really wait.

    Returns:
        How many frames were enrolled before the session ended.
    """
    write_text(f"Enrolamiento de la cara: {frames} tomas.")
    enrolled = 0
    for index in range(frames):
        pose = _FACE_POSES[index] if index < len(_FACE_POSES) else "otra toma"
        write_text(
            f"Toma {index + 1} de {frames}: mira a la cámara, {pose}. Prepárate y, cuando "
            "estés listo, escribe tu PIN (la foto se toma justo después)."
        )
        token = await unlock()
        if countdown_s > 0:
            write_text(f"Capturando en {countdown_s:g} s: mira a la cámara.")
            await sleep(countdown_s)
        frame = capture()
        try:
            await enroll(token, frame)
        except CommissionError as exc:
            write_text(f"Toma rechazada ({exc}). Se detiene el enrolamiento de la cara.")
            break
        enrolled += 1
    write_text(f"Cara: {enrolled} de {frames} tomas enroladas.")
    return enrolled


async def run_voice_session(
    *,
    unlock: Unlock,
    record: RecordClip,
    level_check: LevelCheck,
    enroll: EnrollClip,
    write_text: WriteText,
    references: int | None = None,
    countdown_s: float = 0.0,
    sleep: Sleep = asyncio.sleep,
) -> int:
    """Enrol the owner's voice from several short reads, one unlock each (ADR 0024 decision 15).

    Reads the owner :data:`READING_SCRIPT`, captures clips one at a time, re-captures a clip that
    fails the level and distance check (no reference consumed), unlocks once per reference (each
    token is one-use), and reports the voice modality as not enrolled when the endpoint returns 503
    (``SPEAKER_AUTHENTICATION_ENABLED`` off). An ``unlock`` that fails propagates. Audio is embedded
    and discarded by the endpoint; nothing is stored here.

    Args:
        unlock: Returns a fresh one-use owner-unlock token for ``biometric_admin``.
        record: Returns one contract WAV clip (16 kHz mono int16) from the microphone.
        level_check: Returns whether a clip's level and distance are acceptable.
        enroll: Posts one clip to ``/auth/owner/voice/enroll``; raises
            :class:`SpeakerAuthDisabledError` on 503 and :class:`CommissionError` on a rejected clip.
        write_text: Writes one line of guidance to the terminal.
        references: How many references to enrol (default
            ``settings.speaker_min_reference_count``).
        countdown_s: Seconds to wait before each recording so the owner can start reading.
        sleep: Awaits the countdown; injected so tests do not really wait.

    Returns:
        How many references were enrolled (0 when speaker authentication is off).
    """
    target = references if references is not None else settings.speaker_min_reference_count
    write_text("Enrolamiento de la voz. Lee este texto en voz alta:")
    write_text(READING_SCRIPT)
    enrolled = 0
    attempts = 0
    while enrolled < target:
        attempts += 1
        if attempts > target + _VOICE_ATTEMPT_SLACK:
            write_text("Demasiados intentos; se detiene la sesión de voz.")
            break
        if countdown_s > 0:
            write_text(
                f"Prepárate: se graba en {countdown_s:g} s; cuando empiece, lee la primera "
                "frase del texto en voz alta."
            )
            await sleep(countdown_s)
        write_text("¡Grabando ahora! Habla.")
        clip = record()
        write_text("Grabación lista.")
        if not level_check(clip):
            write_text("El nivel o la distancia no son buenos. Repite y acércate al micrófono.")
            continue
        token = await unlock()
        try:
            await enroll(token, clip)
        except SpeakerAuthDisabledError:
            write_text(
                "La voz no está habilitada (SPEAKER_AUTHENTICATION_ENABLED=false): "
                "no se enroló la voz."
            )
            return 0
        except CommissionError as exc:
            write_text(f"Referencia rechazada ({exc}). Repite.")
            continue
        enrolled += 1
        write_text(f"Referencia {enrolled} de {target} lista.")
    write_text(f"Voz: {enrolled} de {target} referencias enroladas.")
    return enrolled
