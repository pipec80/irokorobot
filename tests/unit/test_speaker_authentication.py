"""Unit tests for the pure speaker verdict table (Plan 0053, Task 2) and the
request-scoped speaker resolver (Plan 0053, Task 4)."""

from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite
import numpy as np
import pytest
from server.cognition.identity import ActivePersonStatus, HouseholdRole, IdentityEvidenceSource
from server.cognition.models import CognitiveEvent
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import (
    SpeakerRequestResolver,
    SpeakerVerdict,
    evaluate_speaker_verification,
)
from server.exceptions import BrainMemoryError
from server.settings import settings
from server.voice.speaker_embedding import SpeakerBackendError


def _evaluate(**overrides: object) -> SpeakerVerdict:
    """Evaluate the table from the all-satisfied case with named overrides."""
    kwargs: dict[str, object] = {
        "reference_count": settings.speaker_min_reference_count,
        "distance": settings.speaker_authentication_match_threshold - 0.01,
        "consent_active": True,
        "role": HouseholdRole.OWNER,
        "backend_available": True,
    }
    kwargs.update(overrides)
    return evaluate_speaker_verification(**kwargs)  # type: ignore[arg-type]


def test_all_conditions_satisfied_verifies() -> None:
    assert _evaluate() is SpeakerVerdict.VERIFIED


def test_distance_exactly_at_the_threshold_verifies() -> None:
    """The study's rule is `distance <= threshold`, not `<`."""
    assert _evaluate(distance=settings.speaker_authentication_match_threshold) is (
        SpeakerVerdict.VERIFIED
    )


def test_backend_unavailable_is_unavailable_not_unknown() -> None:
    assert _evaluate(backend_available=False) is SpeakerVerdict.UNAVAILABLE


@pytest.mark.parametrize(
    "override",
    [
        {"reference_count": 0},
        {"reference_count": 2},
        {"distance": None},
        {"distance": 0.9},
        {"consent_active": False},
        {"role": HouseholdRole.ADULT},
        {"role": HouseholdRole.UNKNOWN},
    ],
)
def test_every_other_failure_is_unknown(override: dict[str, object]) -> None:
    assert _evaluate(**override) is SpeakerVerdict.UNKNOWN


def test_unavailable_wins_over_a_matching_distance() -> None:
    """A dead backend is never reported as a match, whatever else is true."""
    assert _evaluate(backend_available=False, distance=0.0) is SpeakerVerdict.UNAVAILABLE


# ---- Resolver behaviour (Plan 0053, Task 4) ----

_OWNER_ID = 42


def _event() -> CognitiveEvent[TextTurnPayload]:
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=now,
        recorded_at=now,
        source="audio.transcribe",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


async def _default_read_role(_person_id: int) -> HouseholdRole:
    return HouseholdRole.OWNER


async def _default_read_consent(_person_id: int) -> bool:
    return True


async def _default_count_references(_entity_id: int, _model_id: str) -> int:
    return settings.speaker_min_reference_count


async def _default_distance_to_centroid(
    _person_id: int, _embedding: np.ndarray, _model_id: str
) -> float:
    return settings.speaker_authentication_match_threshold - 0.01


async def _default_embed(_wav_bytes: bytes) -> np.ndarray:
    return np.ones(192, dtype=np.float32)


def _default_has_energy(_wav_bytes: bytes) -> bool:
    return True


def _default_has_duration(_wav_bytes: bytes) -> bool:
    return True


def _false_sync(*_args: object) -> bool:
    return False


async def _false(*_args: object) -> bool:
    return False


async def _zero(*_args: object) -> int:
    return 0


async def _none(*_args: object) -> float | None:
    return None


def _raise(exc: Exception) -> object:
    """Return an async double that raises *exc* regardless of arity."""

    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise exc

    return _boom


class _CountingEmbed:
    """Async `embed` double that counts how many times it was called."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, _wav_bytes: bytes) -> np.ndarray:
        self.calls += 1
        return np.ones(192, dtype=np.float32)


class _CountingRole:
    """Async `read_role` double that counts how many times it was called."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, _person_id: int) -> HouseholdRole:
        self.calls += 1
        return HouseholdRole.OWNER


def _resolver(**overrides: object) -> SpeakerRequestResolver:
    """Build a resolver whose every boundary is a controllable double."""
    kwargs: dict[str, object] = {
        "wav_bytes": b"canary-wav",
        "owner_person_id": _OWNER_ID,
        "clock": lambda: datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
        "read_role": _default_read_role,
        "read_consent": _default_read_consent,
        "count_references": _default_count_references,
        "distance_to_centroid": _default_distance_to_centroid,
        "embed": _default_embed,
        "has_energy": _default_has_energy,
        "has_duration": _default_has_duration,
        "model_id": "test-model@rev1",
    }
    kwargs.update(overrides)
    return SpeakerRequestResolver(**kwargs)  # type: ignore[arg-type]


# `embed` is `async def embed_wav` (Task 3) and is awaited as such in
# `_resolve` — every double bound to it here (the default, `_CountingEmbed`,
# `_raise(...)`) must itself be an async callable (`async def` or an
# `async def __call__`), not a plain function returning a value.


async def test_a_verified_speaker_produces_untrusted_voice_evidence() -> None:
    resolver = _resolver()
    context = await resolver.resolve_actor(_event())
    assert context.status is ActivePersonStatus.UNKNOWN  # VOICE never identifies
    assert context.person_id is None
    assert [item.source for item in context.evidence] == [IdentityEvidenceSource.VOICE]
    assert context.evidence[0].candidate_person_id == _OWNER_ID


async def test_a_failed_verdict_produces_no_evidence_at_all() -> None:
    resolver = _resolver(read_consent=_false)
    context = await resolver.resolve_actor(_event())
    assert context.evidence == ()


async def test_the_embedding_runs_at_most_once_per_request() -> None:
    counter = _CountingEmbed()
    resolver = _resolver(embed=counter)
    await resolver.resolve_actor(_event())
    await resolver.resolve_actor(_event())
    assert counter.calls == 1


async def test_a_dead_backend_degrades_instead_of_raising() -> None:
    resolver = _resolver(embed=_raise(SpeakerBackendError("down")))
    context = await resolver.resolve_actor(_event())
    assert context.evidence == ()
    assert resolver.last_verdict is SpeakerVerdict.UNAVAILABLE


@pytest.mark.parametrize("seam", ["count_references", "read_consent", "read_role"])
@pytest.mark.parametrize(
    "exc",
    [
        BrainMemoryError("db unavailable"),
        aiosqlite.OperationalError("database is locked"),
    ],
    ids=["BrainMemoryError", "real-sqlite-error"],
)
async def test_any_repository_read_failing_degrades_instead_of_raising(
    seam: str, exc: Exception
) -> None:
    """A code reviewer's Important finding (A4), extended in round 2: only
    `embed` was ever guarded, and the round-1 fix only caught
    `BrainMemoryError` — but none of Task 1's repository functions actually
    raise that type on a real SQLite failure (verified against
    `memory/household_authorization.py`'s `get_active_role` and Task 1's own
    `voiceprints.py`, neither of which wraps `execute()`/`fetchone()` in
    anything). The real type, `aiosqlite.Error` (== `sqlite3.Error`,
    confirmed against the installed package), is what this parametrization
    adds — the case that actually matters, since it is what a genuine DB
    hiccup raises."""
    resolver = _resolver(**{seam: _raise(exc)})
    context = await resolver.resolve_actor(_event())
    assert context.evidence == ()
    assert resolver.last_verdict is SpeakerVerdict.UNAVAILABLE


async def test_silence_is_never_verified() -> None:
    """Review Focus 1."""
    resolver = _resolver(has_energy=_false_sync)
    assert (await resolver.resolve_actor(_event())).evidence == ()


async def test_a_too_short_clip_is_never_verified() -> None:
    """Finding A6 — energy alone is not a sufficient verification gate."""
    resolver = _resolver(has_duration=_false_sync)
    assert (await resolver.resolve_actor(_event())).evidence == ()


async def test_a_reference_from_another_model_is_ignored() -> None:
    """Review Focus 2 — `count_references` is asked for the CONFIGURED model."""
    resolver = _resolver(count_references=_zero)
    assert (await resolver.resolve_actor(_event())).evidence == ()


async def test_revocation_mid_turn_loses_the_references() -> None:
    """Review Focus 3, unit level — a mocked double proves the resolver reads
    `evaluate_speaker_verification`'s `distance=None` branch correctly. The
    REAL interleaving, against a real DB, is Step 4b's integration test —
    a code reviewer's finding (A3) that this mock alone does not reproduce
    an actual concurrent revoke."""
    resolver = _resolver(distance_to_centroid=_none)
    assert (await resolver.resolve_actor(_event())).evidence == ()


async def test_the_role_is_read_on_every_request() -> None:
    """Review Focus 5 — a role change takes effect on the next turn."""
    role_reader = _CountingRole()
    await _resolver(read_role=role_reader).resolve_actor(_event())
    await _resolver(read_role=role_reader).resolve_actor(_event())
    assert role_reader.calls == 2
