"""Integration tests for face matching (V1) — real temp DB, synthetic
embeddings, no face model involved (that stays out of CI)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import numpy as np
import pytest
from server.exceptions import EnrollmentRejectedError
from server.memory.declarative import upsert_entity
from server.settings import settings
from server.vision.faces import (
    DetectedFace,
    enroll_face,
    enroll_person,
    match_face,
    recognize,
)

from server import db


@pytest.fixture
async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Provide a clean temporary DB (runs migration v3) for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)

    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
    await db.close_db()
    db._conn = None


def _unit_vector(axis: int) -> np.ndarray:
    """Return a 512-d unit vector along *axis* — a synthetic 'face'."""
    vec = np.zeros(512, dtype=np.float32)
    vec[axis] = 1.0
    return vec


@pytest.mark.integration
async def test_migration_v3_creates_face_tables(memory_db: Path) -> None:
    """face_profiles and vec_faces must exist after migrations."""
    conn = db.get_conn()
    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE name IN ('face_profiles', 'vec_faces')"
    )
    names = {row[0] for row in await cur.fetchall()}
    await cur.close()

    assert names == {"face_profiles", "vec_faces"}


@pytest.mark.integration
async def test_enroll_and_match_same_face(memory_db: Path) -> None:
    """An enrolled embedding must match itself with ~zero distance."""
    entity_id = await upsert_entity(name="Felipe", type="person")
    await enroll_face(entity_id, _unit_vector(0), label="Felipe")

    found = await match_face(_unit_vector(0))

    assert found is not None
    assert found.name == "Felipe"
    assert found.entity_id == entity_id
    assert found.distance == pytest.approx(0.0, abs=1e-6)


@pytest.mark.integration
async def test_unknown_face_does_not_match(memory_db: Path) -> None:
    """An orthogonal embedding (cosine distance 1.0) is over the 0.4
    threshold — an unknown face, never a false positive."""
    entity_id = await upsert_entity(name="Felipe", type="person")
    await enroll_face(entity_id, _unit_vector(0), label="Felipe")

    assert await match_face(_unit_vector(1)) is None


@pytest.mark.integration
async def test_match_respects_threshold_boundary(memory_db: Path) -> None:
    """A face just INSIDE the cosine-distance threshold still matches."""
    entity_id = await upsert_entity(name="Felipe", type="person")
    await enroll_face(entity_id, _unit_vector(0), label="Felipe")
    # cos_sim = 0.8 → cosine distance 0.2 < 0.4 → match.
    near = np.zeros(512, dtype=np.float32)
    near[0], near[1] = 0.8, 0.6

    found = await match_face(near)

    assert found is not None
    assert found.distance == pytest.approx(0.2, abs=1e-3)


@pytest.mark.integration
async def test_empty_enrollment_matches_nothing(memory_db: Path) -> None:
    """With nothing enrolled, every face is unknown — no crash."""
    assert await match_face(_unit_vector(0)) is None


@pytest.mark.integration
async def test_recognize_dedupes_and_counts_unknowns(memory_db: Path) -> None:
    """Two frames of the same person + one stranger → 1 match, 1 unknown."""
    entity_id = await upsert_entity(name="Felipe", type="person")
    await enroll_face(entity_id, _unit_vector(0), label="Felipe")

    with patch(
        "server.vision.faces.extract_faces",
        new_callable=AsyncMock,
        return_value=[_unit_vector(0), _unit_vector(0), _unit_vector(5)],
    ):
        matches, unknown = await recognize(b"\xff\xd8fake")

    assert [m.name for m in matches] == ["Felipe"]
    assert unknown == 1


# --- V1.1: enrollment business rules (enroll_person) ---


def _detected(score: float = 0.9, width: float = 200.0) -> object:
    return DetectedFace(embedding=_unit_vector(0), score=score, width=width)


@pytest.mark.integration
async def test_enroll_person_happy_path(memory_db: Path) -> None:
    """One good face → entity person + face profile, name title-cased."""
    with patch(
        "server.vision.faces.detect_faces",
        new_callable=AsyncMock,
        return_value=[_detected()],
    ):
        outcome = await enroll_person("felipe", b"\xff\xd8fake")

    assert outcome.name == "Felipe"
    found = await match_face(_unit_vector(0))
    assert found is not None
    assert found.entity_id == outcome.entity_id


@pytest.mark.integration
@pytest.mark.parametrize(
    "faces,expected_code",
    [
        ([], "no_face"),
        (["two"], "multiple_faces"),
        ("low_score", "low_quality"),
        ("tiny", "face_too_small"),
    ],
)
async def test_enroll_person_rejections(memory_db: Path, faces: object, expected_code: str) -> None:
    """Business rules: exactly ONE sharp, big-enough face — or a clear reason."""
    detected = {
        (): [],
        ("two",): [_detected(), _detected()],
        "low_score": [_detected(score=0.2)],
        "tiny": [_detected(width=40.0)],
    }[tuple(faces) if isinstance(faces, list) else faces]

    with (
        patch(
            "server.vision.faces.detect_faces",
            new_callable=AsyncMock,
            return_value=detected,
        ),
        pytest.raises(EnrollmentRejectedError) as exc_info,
    ):
        await enroll_person("Felipe", b"\xff\xd8fake")

    assert exc_info.value.code == expected_code
