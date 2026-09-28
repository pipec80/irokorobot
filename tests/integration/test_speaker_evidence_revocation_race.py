"""Integration test for the revocation-race contract (Plan 0053, Task 4,
finding A3) — a real temporary DB, no mocked repository calls for the parts
under test."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

import numpy as np
import pytest
from server.cognition.identity import HouseholdRole
from server.cognition.models import CognitiveEvent
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import SpeakerRequestResolver, SpeakerVerdict
from server.memory.declarative import upsert_entity
from server.memory.voice_consent import (
    grant_voice_consent,
    has_active_voice_consent,
    revoke_voice_consent,
)
from server.settings import settings
from server.voice.voiceprints import centroid_distance, count_voiceprints, enroll_voiceprint

from server import db

MODEL_ID = "test-model@rev1"
_NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "test.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


async def _owner_role(_person_id: int) -> HouseholdRole:
    return HouseholdRole.OWNER


async def _enrolled_owner(owner_entity_id: int | None = None) -> int:
    """Grant consent and store 3 real, distinct references for a fresh owner."""
    owner = owner_entity_id or await upsert_entity(name="canary-owner", type="person")
    await grant_voice_consent(owner)
    for axis in range(3):
        vector = np.zeros(192, dtype=np.float32)
        vector[axis] = 1.0
        await enroll_voiceprint(owner, vector, "canary-owner", MODEL_ID)
    return owner


async def _async_probe(_wav_bytes: bytes) -> np.ndarray:
    probe = np.zeros(192, dtype=np.float32)
    probe[0] = 1.0
    return probe


def _resolver_over_real_db(owner: int, *, count_references: object) -> SpeakerRequestResolver:
    """Build a resolver whose repository seams are the REAL Task 1 functions,
    except the one seam each test below replaces with a real side effect."""
    return SpeakerRequestResolver(
        wav_bytes=b"canary-wav",
        owner_person_id=owner,
        clock=lambda: _NOW,
        read_role=_owner_role,
        read_consent=has_active_voice_consent,
        count_references=count_references,
        distance_to_centroid=centroid_distance,
        embed=_async_probe,
        has_energy=lambda _wav: True,
        has_duration=lambda _wav: True,
        model_id=MODEL_ID,
    )


async def test_a_revoke_landing_between_count_and_distance_yields_unknown(
    memory_db: None,
) -> None:
    owner = await _enrolled_owner()

    async def _count_then_revoke(entity_id: int, model_id: str) -> int:
        """Real `count_references`, but a real revoke lands right after —
        reproducing another request's revoke completing between this
        resolver's own two awaits, on the same single-threaded loop."""
        count = await count_voiceprints(entity_id, model_id)
        await revoke_voice_consent(entity_id)
        return count

    resolver = _resolver_over_real_db(owner, count_references=_count_then_revoke)
    context = await resolver.resolve_actor(_event())

    assert context.evidence == ()
    assert resolver.last_verdict is SpeakerVerdict.UNKNOWN


async def test_a_revoke_landing_after_role_before_consent_yields_unknown(
    memory_db: None,
) -> None:
    """Round 2 of A3 — the case an earlier draft left unguarded: `role` was
    read before `consent_active`, so a revoke completing in exactly that
    window left a stale `True` uncaught. `read_role` is now the seam that
    performs the real side effect, since `read_consent` is the resolver's
    own final await and must observe whatever `read_role` already changed."""
    owner = await _enrolled_owner()

    async def _role_then_revoke(_person_id: int) -> HouseholdRole:
        await revoke_voice_consent(owner)
        return HouseholdRole.OWNER

    resolver = SpeakerRequestResolver(
        wav_bytes=b"canary-wav",
        owner_person_id=owner,
        clock=lambda: _NOW,
        read_role=_role_then_revoke,
        read_consent=has_active_voice_consent,
        count_references=count_voiceprints,
        distance_to_centroid=centroid_distance,
        embed=_async_probe,
        has_energy=lambda _wav: True,
        has_duration=lambda _wav: True,
        model_id=MODEL_ID,
    )

    context = await resolver.resolve_actor(_event())

    assert context.evidence == ()
    assert resolver.last_verdict is SpeakerVerdict.UNKNOWN


async def test_revoke_then_reconsent_without_reenrolling_stays_unknown(
    memory_db: None,
) -> None:
    """Round 3: an earlier draft of this test asserted `VERIFIED` here, which
    the resolver cannot honestly produce — `revoke_voice_consent` purges
    every `voice_profiles` row by design (Task 1: "consent and biometric
    data share one lifecycle"), and re-granting consent alone does not
    restore them. Zero references is below `speaker_min_reference_count`
    regardless of consent, so the correct, and only honest, outcome is
    `UNKNOWN`. The code was not changed to satisfy the wrong expectation;
    the test was."""
    owner = await _enrolled_owner()
    await revoke_voice_consent(owner)
    await grant_voice_consent(owner)  # consent restored; references were NOT

    resolver = _resolver_over_real_db(owner, count_references=count_voiceprints)
    context = await resolver.resolve_actor(_event())

    assert context.evidence == ()
    assert resolver.last_verdict is SpeakerVerdict.UNKNOWN


async def test_revoke_then_reconsent_and_reenroll_can_verify_again(
    memory_db: None,
) -> None:
    """The real positive case round 3 asked for: once BOTH consent and
    enough fresh references exist again, verification succeeds normally —
    a revoke-then-reconsent is not itself an attack to defend against, it
    is simply the current state by the time this resolver asks."""
    owner = await _enrolled_owner()
    await revoke_voice_consent(owner)
    await grant_voice_consent(owner)
    for axis in range(3):
        vector = np.zeros(192, dtype=np.float32)
        vector[axis] = 1.0
        await enroll_voiceprint(owner, vector, "canary-owner", MODEL_ID)

    resolver = _resolver_over_real_db(owner, count_references=count_voiceprints)
    context = await resolver.resolve_actor(_event())

    assert resolver.last_verdict is SpeakerVerdict.VERIFIED
    assert context.evidence[0].candidate_person_id == owner
