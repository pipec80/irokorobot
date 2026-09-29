"""Local voiceprint storage and centroid comparison (Plan 0053, PC-3B).

A voiceprint is a 192-d float32 ECAPA embedding, L2-normalized, stored as a
BLOB in ``voice_profiles``. Verification compares a fresh embedding with the
CENTROID of that person's references, because that is the quantity Plan 0047
calibrated (threshold 0.4834). No audio is ever stored, and no vector produced
by a different model is ever compared.
"""

from typing import Final

import numpy as np

from server import db
from server.db import get_conn
from server.exceptions import BrainMemoryError

VOICEPRINT_DIM: Final = 192

__all__ = ["VOICEPRINT_DIM", "centroid_distance", "count_voiceprints", "enroll_voiceprint"]


def _pack(embedding: np.ndarray) -> bytes:
    """Serialize a voiceprint as float32 little-endian, like ``vision.faces``."""
    return embedding.astype(np.float32).tobytes()


def _unpack(blob: bytes) -> np.ndarray:
    """Read one stored voiceprint back into a 1-D float32 array.

    Raises:
        BrainMemoryError: If the blob is not exactly one 192-d float32 vector.
    """
    if len(blob) != VOICEPRINT_DIM * 4:
        raise BrainMemoryError("Stored voiceprint has an unexpected size")
    return np.frombuffer(blob, dtype=np.float32)


def _l2_normalized(vector: np.ndarray) -> np.ndarray:
    """Return *vector* scaled to unit length, exactly as the study did."""
    if not np.isfinite(vector).all():
        raise BrainMemoryError("Refusing to store or compare a non-finite voiceprint")
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise BrainMemoryError("Refusing to store or compare an all-zero voiceprint")
    return (vector / norm).astype(np.float32)


async def enroll_voiceprint(
    entity_id: int, embedding: np.ndarray, label: str, model_id: str
) -> int:
    """Store one reference voiceprint for *entity_id*.

    Several references per person are expected: the study used six, captured
    in one quiet session, and the runtime compares against their centroid.

    Args:
        entity_id: Target entity in ``entities``.
        embedding: 192-d embedding; stored L2-normalized.
        label: Human label, normally the entity name.
        model_id: Frozen ``model@revision`` that produced *embedding*.

    Returns:
        The new ``voice_profiles`` row id.

    Raises:
        BrainMemoryError: If the DB is unavailable, the dimension is wrong, or
            the embedding is all zeros.
    """
    if embedding.shape != (VOICEPRINT_DIM,):
        raise BrainMemoryError(f"Expected {VOICEPRINT_DIM}-d voiceprint, got {embedding.shape}")
    normalized = _l2_normalized(embedding)
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO voice_profiles (entity_id, label, embedding, model_id) "
            "VALUES (?, ?, ?, ?)",
            (entity_id, label, _pack(normalized), model_id),
        )
        profile_id = cursor.lastrowid
        await cursor.close()
    return int(profile_id) if profile_id is not None else 0


async def _references(entity_id: int, model_id: str) -> list[np.ndarray]:
    """Read every stored reference for this person and this exact model."""
    cursor = await get_conn().execute(
        "SELECT embedding FROM voice_profiles WHERE entity_id = ? AND model_id = ?",
        (entity_id, model_id),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [_unpack(bytes(row[0])) for row in rows]


async def count_voiceprints(entity_id: int, model_id: str) -> int:
    """Return how many usable references this person has for *model_id*."""
    cursor = await get_conn().execute(
        "SELECT COUNT(*) FROM voice_profiles WHERE entity_id = ? AND model_id = ?",
        (entity_id, model_id),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return int(row[0]) if row is not None else 0


async def centroid_distance(entity_id: int, embedding: np.ndarray, model_id: str) -> float | None:
    """Return the cosine distance from *embedding* to this person's centroid.

    Args:
        entity_id: Person whose references are compared.
        embedding: Fresh 192-d embedding of the current utterance.
        model_id: Frozen ``model@revision`` currently configured. References
            produced by any other model are ignored.

    Returns:
        The cosine distance in ``[0, 2]`` — lower is closer — or ``None`` when
        this person has no reference for *model_id*.

    Raises:
        BrainMemoryError: If the DB is unavailable or a vector is all zeros.
    """
    references = await _references(entity_id, model_id)
    if not references:
        return None
    centroid = _l2_normalized(np.mean(np.stack(references), axis=0))
    return float(1.0 - np.dot(centroid, _l2_normalized(embedding)))
