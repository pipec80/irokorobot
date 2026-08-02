"""Compose the perception block for one visual turn (V1).

Joins face recognition and scene description into the single text block
that ``build_system_prompt`` injects — the character reacts in its own
voice. Faces degrade independently of the description: a broken face
model never blinds the scene, and vice versa. A visual turn NEVER raises
out of this module except ``VisionError`` when nothing at all was seen.
"""

from __future__ import annotations

import logging

from server import db
from server.exceptions import BrainMemoryError, EnrollmentRejectedError, VisionError
from server.vision.describe import PERCEPTION_FAILED, describe_image
from server.vision.faces import enroll_person, recognize

logger = logging.getLogger(__name__)

# Friendly perception lines per enrollment-rejection code — the character
# turns them into its own voice.
_ENROLL_REJECTIONS: dict[str, str] = {
    "no_face": (
        "No lograste ver ninguna cara clara para aprenderla. "
        "Pedile con humor que se ponga frente a la cámara."
    ),
    "multiple_faces": (
        "Ves varias caras a la vez y no sabés cuál aprender. "
        "Pedile que se ponga solo frente a la cámara."
    ),
    "low_quality": (
        "La imagen salió borrosa o con poca luz y no pudiste ver bien la cara. "
        "Pedile que se acerque con mejor luz."
    ),
    "face_too_small": (
        "La cara se ve demasiado lejos para aprenderla bien. Pedile que se acerque a la cámara."
    ),
}

_RECOGNIZED_TEMPLATE = "[Reconocés a {names} frente a vos — saludá por su nombre.]"
_UNKNOWN_LINE = (
    "[También ves a alguien que NO reconocés — podés preguntar su nombre "
    "con naturalidad, sin alarma.]"
)


async def _face_lines(image: bytes) -> list[str]:
    """Return perception lines for recognized/unknown faces, or none.

    Face failures (model missing, DB down) degrade to an empty list — the
    scene description must never be blinded by the face pipeline.

    Args:
        image: Image bytes — contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720.
    """
    try:
        matches, unknown = await recognize(image)
    except (VisionError, BrainMemoryError) as exc:
        logger.warning("Face recognition unavailable this turn: %s", exc)
        return []
    lines: list[str] = []
    if matches:
        names = " y ".join(match.name for match in matches)
        lines.append(_RECOGNIZED_TEMPLATE.format(names=names))
    if unknown:
        lines.append(_UNKNOWN_LINE)
        await _record_unknown_face(unknown)
    return lines


async def _record_unknown_face(count: int) -> None:
    """Log an ``unknown_person`` event — informational, never an alarm."""
    try:
        conn = db.get_conn()
        await conn.execute(
            "INSERT INTO events (event_type, severity, payload) VALUES (?, ?, ?)",
            ("unknown_person", "info", f'{{"count": {count}}}'),
        )
        await conn.commit()
    except Exception as exc:
        logger.warning("Could not record unknown_person event: %s", exc)


async def perceive(image: bytes) -> str:
    """Describe one frame and recognize the faces in it.

    Args:
        image: Image bytes — contract: JPEG/PNG/WebP/GIF/BMP · max
            1280x720 · one frame, processed in memory and discarded.

    Returns:
        The perception block: recognition lines (when any) plus the scene
        description. Falls back to ``PERCEPTION_FAILED`` only when BOTH
        pipelines saw nothing.
    """
    lines = await _face_lines(image)
    try:
        description, _duration_ms = await describe_image(image)
        lines.append(description)
    except VisionError as exc:
        logger.error("Scene description failed: %s", exc)
        if not lines:
            return PERCEPTION_FAILED
    return "\n".join(lines)


async def enroll_from_frame(name: str, image: bytes) -> str:
    """Learn a face conversationally (verbal consent = the spoken phrase).

    Thin wrapper over ``enroll_person`` — the SAME business rules the API
    service applies — translating each outcome into a perception line the
    character speaks in its own voice. Never mute.

    Args:
        name: Person name captured from the user's explicit enroll phrase.
        image: Image bytes per the image contract.

    Returns:
        A perception line telling the character what happened.
    """
    try:
        outcome = await enroll_person(name, image)
    except EnrollmentRejectedError as exc:
        logger.info("Enrollment rejected (%s): %s", exc.code, exc)
        return _ENROLL_REJECTIONS.get(exc.code, PERCEPTION_FAILED)
    except VisionError as exc:
        logger.error("Enroll failed — no usable frame: %s", exc)
        return PERCEPTION_FAILED
    except BrainMemoryError as exc:
        logger.error("Enroll failed — memory unavailable: %s", exc)
        return (
            f"Viste bien la cara de {name} pero tu memoria falló al guardarla. "
            "Discúlpate brevemente."
        )
    return (
        f"Acabás de aprender la cara de {outcome.name} — desde ahora podés "
        "reconocerla al verla. Confirmáselo con calidez."
    )
