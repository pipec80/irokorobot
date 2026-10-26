"""The commissioning session: the biometric notice, the consents, the face and voice sessions.

Plan 0072. The steps here are driven by injected adapters (``read_text``, ``write_text``, and the
unlock/capture/enroll callables of the face and voice sessions) so they test without a real
terminal, camera or microphone. No audio, no frame and no household value is stored by this module;
the enrolment endpoints embed and discard the media.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from server.memory.commissioning import Consents

__all__ = [
    "BIOMETRIC_NOTICE_PATH",
    "BIOMETRIC_NOTICE_VERSION",
    "CommissionError",
    "load_biometric_notice",
    "read_consents",
    "run_face_session",
]

type ReadText = Callable[[str], str]
type WriteText = Callable[[str], None]
type Unlock = Callable[[], Awaitable[str]]
type CaptureFrame = Callable[[], bytes]
type EnrollFrame = Callable[[str, bytes], Awaitable[str]]

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
) -> int:
    """Enrol the owner's face in several frames, one unlock each (ADR 0024 decision 15).

    Guides the poses of :data:`_FACE_POSES`, unlocks once per frame (each token is one-use), and
    stops cleanly if a frame is rejected (``no_face``, ``multiple_faces``, ``low_quality``,
    ``face_too_small``). An ``unlock`` that fails propagates; a rejected frame only stops the session.

    Args:
        unlock: Returns a fresh one-use owner-unlock token for ``biometric_admin``.
        capture: Returns one JPEG frame from the camera.
        enroll: Posts one frame to ``/auth/owner/face/enroll``; raises for a rejected frame.
        write_text: Writes one line of guidance to the terminal.
        frames: How many frames to try (default five).

    Returns:
        How many frames were enrolled before the session ended.
    """
    write_text(f"Enrolamiento de la cara: {frames} tomas.")
    enrolled = 0
    for index in range(frames):
        pose = _FACE_POSES[index] if index < len(_FACE_POSES) else "otra toma"
        write_text(f"Toma {index + 1} de {frames}: mira a la cámara, {pose}.")
        token = await unlock()
        frame = capture()
        try:
            await enroll(token, frame)
        except CommissionError as exc:
            write_text(f"Toma rechazada ({exc}). Se detiene el enrolamiento de la cara.")
            break
        enrolled += 1
    write_text(f"Cara: {enrolled} de {frames} tomas enroladas.")
    return enrolled
