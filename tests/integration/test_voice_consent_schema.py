"""Integration tests for voice consent and voiceprint storage (Plan 0053,
Task 1) — real temp DB, synthetic vectors, no speaker model involved."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import numpy as np
import pytest
from server.memory.declarative import upsert_entity
from server.memory.voice_consent import (
    grant_voice_consent,
    has_active_voice_consent,
    revoke_voice_consent,
)
from server.settings import settings
from server.voice.voiceprints import (
    VOICEPRINT_DIM,
    centroid_distance,
    count_voiceprints,
    enroll_voiceprint,
)

from server import db

MODEL_ID = "test-model@rev1"


@pytest.fixture
async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Provide a clean temporary DB (runs all migrations) for each test."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "test.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _unit_vector(axis: int) -> np.ndarray:
    """Return a 192-d L2-normalized vector along *axis* — a synthetic voice."""
    vector = np.zeros(VOICEPRINT_DIM, dtype=np.float32)
    vector[axis] = 1.0
    return vector


async def test_grant_is_idempotent(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", type="person")
    first = await grant_voice_consent(person)
    second = await grant_voice_consent(person)
    assert first == second
    assert await has_active_voice_consent(person) is True


async def test_revoke_purges_every_voiceprint(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", type="person")
    await grant_voice_consent(person)
    await enroll_voiceprint(person, _unit_vector(0), "canary-owner", MODEL_ID)
    await enroll_voiceprint(person, _unit_vector(1), "canary-owner", MODEL_ID)

    await revoke_voice_consent(person)

    assert await has_active_voice_consent(person) is False
    assert await count_voiceprints(person, MODEL_ID) == 0


async def test_revoke_is_idempotent_without_a_grant(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", type="person")
    await revoke_voice_consent(person)  # must not raise
    assert await has_active_voice_consent(person) is False


async def test_vectors_from_another_model_are_not_counted(memory_db: None) -> None:
    """Review Focus 2: a model change must invalidate stored references."""
    person = await upsert_entity(name="canary-owner", type="person")
    await enroll_voiceprint(person, _unit_vector(0), "canary-owner", MODEL_ID)
    assert await count_voiceprints(person, "other-model@rev2") == 0
    assert await centroid_distance(person, _unit_vector(0), "other-model@rev2") is None


async def test_centroid_distance_matches_the_study_arithmetic(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", type="person")
    await enroll_voiceprint(person, _unit_vector(0), "canary-owner", MODEL_ID)
    await enroll_voiceprint(person, _unit_vector(1), "canary-owner", MODEL_ID)

    # Centroid of two orthogonal unit vectors, L2-normalized, is 45 degrees
    # from each: cosine similarity sqrt(0.5), so distance 1 - sqrt(0.5).
    distance = await centroid_distance(person, _unit_vector(0), MODEL_ID)
    assert distance == pytest.approx(1.0 - 0.5**0.5, abs=1e-6)


async def test_centroid_distance_is_none_without_references(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", type="person")
    assert await centroid_distance(person, _unit_vector(0), MODEL_ID) is None
