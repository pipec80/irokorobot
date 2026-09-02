"""Face recognition: detect → embed → match → enroll (V1, docs/audit/05 §3).

InsightFace ``buffalo_l`` (ONNX, CPU) produces 512-d L2-normalized
embeddings; matching runs as KNN in sqlite-vec (``vec_faces``), linked to
the SAME memory entities the conversation already knows.

Privacy (docs/audit/05 §5): frames NEVER persist — only embeddings do,
and an embedding cannot reconstruct a face. Biometric data lives
exclusively in the local ``omnibot.db``.

Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame per request.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import logging
from typing import Any
import warnings

import numpy as np

from server import db
from server.exceptions import EnrollmentRejectedError, VisionError
from server.memory.declarative import upsert_entity
from server.settings import settings

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 512
# CPU face inference is not thread-safe per analyzer — serialize it.
_executor = ThreadPoolExecutor(max_workers=1)
_analyzer: Any = None  # Any: insightface.app.FaceAnalysis, imported lazily


def _get_analyzer() -> Any:  # noqa: ANN401 — FaceAnalysis is imported lazily below
    """Return the FaceAnalysis singleton, loading models on first use.

    Lazy on purpose: buffalo_l is ~300 MB downloaded to
    ``settings.models_dir/insightface`` on the very first call, and the
    import itself is heavy. Runs inside the executor thread.

    Raises:
        VisionError: If insightface or its models cannot be loaded.
    """
    global _analyzer  # noqa: PLW0603
    if _analyzer is not None:
        return _analyzer
    try:
        # Lazy: importing insightface costs seconds and vision may be off.
        from insightface.app import FaceAnalysis  # noqa: PLC0415

        # insightface's own face_align.py calls a scikit-image API deprecated
        # since 0.26 (removal in 2.2) on every alignment — harmless upstream
        # noise, not something we can fix here. Scoped to that exact module
        # so a real FutureWarning from our own code still surfaces.
        warnings.filterwarnings(
            "ignore", category=FutureWarning, module=r"insightface\.utils\.face_align"
        )

        logger.info("Loading face model %s (first call downloads it)...", settings.face_model)
        analyzer = FaceAnalysis(
            name=settings.face_model,
            root=str(settings.models_dir / "insightface"),
            providers=["CPUExecutionProvider"],
        )
        analyzer.prepare(ctx_id=-1, det_size=(640, 640))
    except Exception as exc:
        raise VisionError(f"Face model unavailable: {exc}") from exc
    _analyzer = analyzer
    logger.info("Face model ready: %s", settings.face_model)
    return _analyzer


@dataclass(frozen=True)
class DetectedFace:
    """One face found in a frame, with the quality signals enrollment needs.

    Attributes:
        embedding: 512-d L2-normalized float32 embedding.
        score: Detector confidence in ``[0, 1]``.
        width: Face bounding-box width in pixels.
    """

    embedding: np.ndarray
    score: float
    width: float


def _detect_sync(image: bytes) -> list[DetectedFace]:
    """Decode a frame and return every detected face with metadata.

    Args:
        image: Image bytes — contract: JPEG/PNG/WebP/GIF/BMP, max
            1280x720. Decoded in memory and discarded.

    Returns:
        Detected faces, largest first.

    Raises:
        VisionError: If the frame cannot be decoded or the model fails.
    """
    # Lazy: cv2 is heavy and only needed when vision actually runs.
    import cv2  # noqa: PLC0415

    frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise VisionError("Could not decode image frame")
    faces = _get_analyzer().get(frame)
    faces.sort(
        key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        reverse=True,
    )
    return [
        DetectedFace(
            embedding=np.asarray(face.normed_embedding, dtype=np.float32),
            score=float(face.det_score),
            width=float(face.bbox[2] - face.bbox[0]),
        )
        for face in faces
    ]


async def detect_faces(image: bytes) -> list[DetectedFace]:
    """Async face detection with metadata — inference off the event loop.

    Args:
        image: Image bytes per the image contract.

    Returns:
        Detected faces, largest first; empty list when no face.

    Raises:
        VisionError: If decoding or the face model fails.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _detect_sync, image)


async def extract_faces(image: bytes) -> list[np.ndarray]:
    """Return only the embeddings of every face in a frame (recognition path).

    Args:
        image: Image bytes per the image contract.

    Returns:
        512-d embeddings, largest face first; empty list when no face.

    Raises:
        VisionError: If decoding or the face model fails.
    """
    return [face.embedding for face in await detect_faces(image)]


def _pack(embedding: np.ndarray) -> bytes:
    """Serialize an embedding for sqlite-vec (float32, little-endian)."""
    return embedding.astype(np.float32).tobytes()


@dataclass(frozen=True)
class FaceMatch:
    """A recognized face linked to a memory entity.

    Attributes:
        entity_id: Row id in ``entities`` — the same entity memory uses.
        name: Entity name ("Felipe").
        distance: Cosine distance in ``[0, 2]`` — lower is closer.
    """

    entity_id: int
    name: str
    distance: float


async def enroll_face(entity_id: int, embedding: np.ndarray, label: str) -> int:
    """Store one face profile for *entity_id*.

    Several profiles per entity are welcome — re-enrolling on another day
    (different light, glasses on/off) makes matching more robust.

    Args:
        entity_id: Target entity in ``entities``.
        embedding: 512-d L2-normalized embedding.
        label: Human label, normally the entity name.

    Returns:
        The new ``face_profiles`` row id.

    Raises:
        BrainMemoryError: If the DB is unavailable.
        VisionError: If the embedding has the wrong dimension.
    """
    if embedding.shape != (_EMBEDDING_DIM,):
        raise VisionError(f"Expected {_EMBEDDING_DIM}-d embedding, got {embedding.shape}")
    conn = db.get_conn()
    cur = await conn.execute(
        "INSERT INTO face_profiles (entity_id, label) VALUES (?, ?)",
        (entity_id, label),
    )
    profile_id = cur.lastrowid
    await cur.close()
    await conn.execute(
        "INSERT INTO vec_faces (rowid, embedding) VALUES (?, ?)",
        (profile_id, _pack(embedding)),
    )
    await conn.commit()
    logger.info(
        "Face enrolled: profile=%s entity=%s",
        profile_id,
        entity_id,
        extra={"event": "face.enrolled", "profile_id": profile_id, "entity_id": entity_id},
    )
    return int(profile_id) if profile_id is not None else 0


async def match_face(embedding: np.ndarray) -> FaceMatch | None:
    """Return the closest enrolled face within the match threshold.

    sqlite-vec KNN returns L2 distance; on L2-normalized vectors the
    cosine distance is ``L2² / 2`` — that is what
    ``settings.face_match_threshold`` bounds (default 0.4, to calibrate
    with the real family).

    Args:
        embedding: 512-d L2-normalized embedding to look up.

    Returns:
        The best ``FaceMatch``, or ``None`` when nobody is close enough
        (an unknown face) or nothing is enrolled yet.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    conn = db.get_conn()
    cur = await conn.execute(
        "SELECT p.entity_id, e.name, v.distance "
        "FROM vec_faces AS v "
        "JOIN face_profiles AS p ON p.id = v.rowid "
        "JOIN entities AS e ON e.id = p.entity_id "
        "WHERE v.embedding MATCH ? AND k = ? "
        "ORDER BY v.distance LIMIT 1",
        (_pack(embedding), 1),
    )
    row = await cur.fetchone()
    await cur.close()
    if row is None:
        return None
    cosine_distance = float(row[2]) ** 2 / 2
    if cosine_distance > settings.face_match_threshold:
        logger.debug(
            "Closest face too far: %.3f > %.3f", cosine_distance, settings.face_match_threshold
        )
        return None
    return FaceMatch(entity_id=int(row[0]), name=str(row[1]), distance=cosine_distance)


@dataclass(frozen=True)
class EnrollOutcome:
    """Result of a successful enrollment.

    Attributes:
        name: Person name as stored (title-cased).
        entity_id: The memory entity the face now links to.
        profile_id: The new ``face_profiles`` row.
    """

    name: str
    entity_id: int
    profile_id: int


async def enroll_person(name: str, image: bytes) -> EnrollOutcome:
    """Enroll ONE person from one frame — the single source of enrollment.

    Business rules (owner decision 2026-07-14, docs/audit/05 §5): exactly
    ONE face in the frame, sharp enough and big enough to produce a
    reliable profile. Used identically by the API service
    (``POST /vision/enroll`` — dashboards, photo uploads, phone cameras)
    and by the conversational flow ("aprende mi cara, soy Felipe").

    Args:
        name: Person name — linked to the memory entity via upsert, so an
            already-known person reuses their entity.
        image: Image bytes — contract: JPEG/PNG/WebP/GIF/BMP · max
            1280x720 · one frame, processed in memory and discarded.

    Returns:
        The enrollment outcome with entity and profile ids.

    Raises:
        EnrollmentRejectedError: With ``code`` in ``no_face`` /
            ``multiple_faces`` / ``low_quality`` / ``face_too_small``.
        VisionError: If the face model or the frame fails.
        BrainMemoryError: If the DB is unavailable.
    """
    detected = await detect_faces(image)
    if not detected:
        raise EnrollmentRejectedError("no_face", "No face found in the frame")
    if len(detected) > 1:
        raise EnrollmentRejectedError(
            "multiple_faces",
            f"Found {len(detected)} faces — enrollment needs exactly one person in frame",
        )
    face = detected[0]
    if face.score < settings.face_enroll_min_score:
        raise EnrollmentRejectedError(
            "low_quality",
            f"Face detection score {face.score:.2f} below {settings.face_enroll_min_score}"
            " — photo too blurry or badly lit",
        )
    if face.width < settings.face_enroll_min_width:
        raise EnrollmentRejectedError(
            "face_too_small",
            f"Face is {face.width:.0f}px wide, minimum {settings.face_enroll_min_width}px"
            " — get closer to the camera or use a portrait photo",
        )
    clean_name = name.strip().title()
    entity_id = await upsert_entity(name=clean_name, type="person")
    profile_id = await enroll_face(entity_id, face.embedding, label=clean_name)
    return EnrollOutcome(name=clean_name, entity_id=entity_id, profile_id=profile_id)


async def recognize(image: bytes) -> tuple[list[FaceMatch], int]:
    """Recognize every face in one frame.

    Args:
        image: Image bytes per the image contract.

    Returns:
        Tuple ``(matches, unknown_count)`` — matches deduped by entity,
        plus how many detected faces matched nobody.

    Raises:
        VisionError: If the frame or the face model fails.
        BrainMemoryError: If the DB is unavailable.
    """
    matches: dict[int, FaceMatch] = {}
    unknown = 0
    for embedding in await extract_faces(image):
        found = await match_face(embedding)
        if found is None:
            unknown += 1
        elif found.entity_id not in matches:
            matches[found.entity_id] = found
    names = ", ".join(m.name for m in matches.values()) or "—"
    logger.info(
        "Faces recognized: %d match(es) [%s], %d unknown",
        len(matches),
        names,
        unknown,
    )
    return list(matches.values()), unknown
