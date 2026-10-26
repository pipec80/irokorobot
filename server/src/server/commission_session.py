"""The commissioning session: the biometric notice, the consents, the face and voice sessions.

Plan 0072. The steps here are driven by injected adapters (``read_text``, ``write_text``, and the
unlock/capture/enroll callables of the face and voice sessions) so they test without a real
terminal, camera or microphone. No audio, no frame and no household value is stored by this module;
the enrolment endpoints embed and discard the media.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from server.memory.commissioning import Consents

__all__ = [
    "BIOMETRIC_NOTICE_PATH",
    "BIOMETRIC_NOTICE_VERSION",
    "CommissionError",
    "load_biometric_notice",
    "read_consents",
]

type ReadText = Callable[[str], str]
type WriteText = Callable[[str], None]

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
