"""Pure speaker verdict and request-scoped speaker evidence (Plan 0053, PC-3B).

`VERIFIED` never means authorized. The resolver below attaches untrusted
`IdentityEvidenceSource.VOICE` evidence, which `resolve_active_person` does not
resolve — fusing voice with face or PIN is PC-4, not this module.

Audio contract for every WAV this module touches: WAV, 16 000 Hz, mono, signed
int16.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
import logging
from uuid import uuid4

import aiosqlite
import numpy as np

from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.response_plan import TextTurnPayload
from server.exceptions import AudioContractError, BrainMemoryError
from server.memory.household_authorization import get_active_role
from server.memory.voice_consent import has_active_voice_consent
from server.settings import settings
from server.voice.speaker_embedding import (
    SpeakerBackendError,
    embed_wav,
    has_voiced_energy,
    meets_verification_duration,
    model_id as _current_model_id,
)
from server.voice.voiceprints import centroid_distance, count_voiceprints

logger = logging.getLogger(__name__)

__all__ = [
    "SpeakerRequestResolver",
    "SpeakerVerdict",
    "build_default_speaker_resolver",
    "evaluate_speaker_verification",
]

_REFERENCE = "in-turn-speaker-evidence"

type Clock = Callable[[], datetime]
type RoleReader = Callable[[int], Awaitable[HouseholdRole]]
type ConsentReader = Callable[[int], Awaitable[bool]]
type ReferenceCounter = Callable[[int, str], Awaitable[int]]
type DistanceComputer = Callable[[int, np.ndarray, str], Awaitable[float | None]]
type Embedder = Callable[[bytes], Awaitable[np.ndarray]]
type EnergyGate = Callable[[bytes], bool]
type DurationGate = Callable[[bytes], bool]


class SpeakerVerdict(StrEnum):
    """Closed outcome of one speaker verification attempt."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


def evaluate_speaker_verification(
    *,
    reference_count: int,
    distance: float | None,
    consent_active: bool,
    role: HouseholdRole,
    backend_available: bool,
) -> SpeakerVerdict:
    """Decide the speaker verdict from pre-computed evidence.

    Pure decision table — no I/O. The caller must already have applied the
    frozen preprocessing and compared against the reference centroid.

    Args:
        reference_count: Stored references for the configured model.
        distance: Cosine distance to the centroid, or `None` when no
            comparison was possible (no reference, unusable audio).
        consent_active: Whether the person has an active voice consent grant.
        role: The person's current household role, re-read this turn.
        backend_available: Whether the embedding backend produced a vector.

    Returns:
        `UNAVAILABLE` when the backend could not run — a degraded sense, not a
        judgement about the speaker. `VERIFIED` only with enough references, a
        distance within `settings.speaker_authentication_match_threshold`,
        active consent and the owner role. `UNKNOWN` for every other case.
    """
    if not backend_available:
        return SpeakerVerdict.UNAVAILABLE
    if reference_count < settings.speaker_min_reference_count:
        return SpeakerVerdict.UNKNOWN
    if distance is None or distance > settings.speaker_authentication_match_threshold:
        return SpeakerVerdict.UNKNOWN
    if not consent_active:
        return SpeakerVerdict.UNKNOWN
    if role is not HouseholdRole.OWNER:
        return SpeakerVerdict.UNKNOWN
    return SpeakerVerdict.VERIFIED


def _unknown_active_person(
    event: CognitiveEvent[TextTurnPayload],
    reason: str,
    *,
    evidence: tuple[IdentityEvidence, ...] = (),
) -> ActivePersonContext:
    """Build the safe public actor, optionally carrying untrusted VOICE evidence.

    Same shape as `face_authentication.py`'s module-private helper of the
    same name, but that one takes only `event` and is private to its own
    module — coupling across the two would violate LoD, so this is a
    separate, small function with the same body shape rather than an import.

    Args:
        event: The protected event this resolution is scoped to.
        reason: Human-readable explanation carried on the confidence record.
        evidence: Untrusted evidence to attach — empty for a failed verdict,
            or exactly one `VOICE` item when verification succeeded. `VOICE`
            is absent from `_RESOLVABLE_SOURCES`, so attaching it here can
            never change `status` or `person_id`.

    Returns:
        The safe, never-identifying actor context.
    """
    return ActivePersonContext(
        person_id=None,
        display_name=None,
        status=ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason=reason,
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=evidence,
        resolved_at=event.occurred_at,
    )


class SpeakerRequestResolver:
    """Request-scoped speaker resolver bound to one turn's audio."""

    def __init__(
        self,
        *,
        wav_bytes: bytes,
        owner_person_id: int,
        clock: Clock,
        read_role: RoleReader,
        read_consent: ConsentReader,
        count_references: ReferenceCounter,
        distance_to_centroid: DistanceComputer,
        embed: Embedder,
        has_energy: EnergyGate,
        has_duration: DurationGate,
        model_id: str,
    ) -> None:
        """Create a resolver for exactly one HTTP request's audio.

        Args:
            wav_bytes: The turn's own audio — WAV, 16 000 Hz, mono, int16.
            owner_person_id: The one person `VOICE` evidence may ever name as
                a candidate — this module verifies against the owner only
                (PC-3B is single-owner by design).
            clock: Source of the evidence's `observed_at` timestamp.
            read_role: Boundary that reads a person's active household role.
            read_consent: Boundary that reads whether a person currently has
                an active voice consent grant.
            count_references: Boundary that counts stored references for the
                configured model.
            distance_to_centroid: Boundary that computes the cosine distance
                from a fresh embedding to the person's reference centroid.
            embed: Boundary that embeds the bound audio into a 192-d vector.
            has_energy: Boundary that rejects near-silent audio before it is
                ever embedded.
            has_duration: Boundary that rejects audio shorter than
                `settings.speaker_min_verification_s` before it is embedded.
            model_id: The currently configured `model@revision` identifier —
                references from any other model are never compared.
        """
        self._wav = wav_bytes
        self._owner_person_id = owner_person_id
        self._clock = clock
        self._read_role = read_role
        self._read_consent = read_consent
        self._count_references = count_references
        self._distance = distance_to_centroid
        self._embed = embed
        self._has_energy = has_energy
        self._has_duration = has_duration
        self._model_id = model_id
        self.last_verdict: SpeakerVerdict | None = None
        self._cached_context: ActivePersonContext | None = None

    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Resolve the in-turn speaker actor, embedding at most once.

        Args:
            event: The protected event this resolution is scoped to.

        Returns:
            The safe unknown actor, carrying untrusted `VOICE` evidence only
            when verification succeeded — this resolver never identifies
            anybody by itself.
        """
        if self._cached_context is not None:
            return self._cached_context
        context = await self._resolve(event)
        self._cached_context = context
        return context

    async def _resolve(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Run the one-shot energy -> embed -> compare -> decide pipeline.

        `evaluate_speaker_verification` stays the ONE place that decides
        VERIFIED/UNKNOWN/UNAVAILABLE — a DB or backend failure sets
        `backend_available=False` and passes safe placeholder values for
        whatever this pipeline never got to read, rather than a second,
        duplicate decision point that bypasses the verdict table.
        """
        reference_count = 0
        distance: float | None = None
        consent_active = False
        role = HouseholdRole.UNKNOWN
        backend_available = True
        try:
            reference_count = await self._count_references(self._owner_person_id, self._model_id)
            enough = reference_count >= settings.speaker_min_reference_count
            usable_clip = self._has_energy(self._wav) and self._has_duration(self._wav)
            if enough and usable_clip:
                embedding = await self._embed(self._wav)
                distance = await self._distance(self._owner_person_id, embedding, self._model_id)
            # `read_consent` is deliberately the LAST await before the
            # decision below, with no other await between it and
            # `evaluate_speaker_verification` — a code reviewer's finding
            # (round 2 of A3) is that an earlier draft read `role` after
            # `consent_active`, leaving a revoke landing in that exact gap
            # unguarded (the captured `consent_active=True` local was never
            # re-checked). Reading role first and consent last means the
            # ONLY state this decision can ever reflect is whichever
            # consent state existed at the moment this resolver's own
            # consent read completed — nothing after that point can change
            # the outcome, because nothing awaits again before it is used.
            role = await self._read_role(self._owner_person_id)
            consent_active = await self._read_consent(self._owner_person_id)
        except (BrainMemoryError, aiosqlite.Error, SpeakerBackendError, AudioContractError) as exc:
            # Any of the four repository/backend reads above can fail this
            # way; whichever ones already succeeded are simply discarded —
            # `backend_available=False` alone forces UNAVAILABLE regardless
            # (Task 2's `test_unavailable_wins_over_a_matching_distance`).
            # `aiosqlite.Error` (== `sqlite3.Error`, verified against the
            # installed package) is caught explicitly because none of Task
            # 1's repository functions wrap a raw SQLite failure into
            # `BrainMemoryError` — that codebase-wide convention lets a DB
            # hiccup surface as a generic 500 at the HTTP boundary
            # elsewhere, which this turn-time boundary cannot afford
            # (round 2 of A4).
            logger.warning("Speaker evidence degraded to unavailable: %s", exc)
            backend_available = False

        verdict = evaluate_speaker_verification(
            reference_count=reference_count,
            distance=distance,
            consent_active=consent_active,
            role=role,
            backend_available=backend_available,
        )
        self.last_verdict = verdict
        logger.info(
            "Speaker verdict: %s",
            verdict.value,
            extra={"event": "speaker.verdict", "verdict": verdict.value},
        )
        if verdict is not SpeakerVerdict.VERIFIED:
            return _unknown_active_person(event, "No speaker evidence")
        evidence = IdentityEvidence(
            evidence_id=uuid4(),
            source=IdentityEvidenceSource.VOICE,
            candidate_person_id=self._owner_person_id,
            confidence=Confidence(
                score=1.0,
                basis=ConfidenceBasis.MEASURED,
                calibrated=True,
                reason="Speaker match within the provisional authentication threshold",
            ),
            observed_at=self._clock(),
            reference=_REFERENCE,
            expires_at=None,
        )
        return _unknown_active_person(event, "Speaker evidence is untrusted", evidence=(evidence,))


def _utc_now() -> datetime:
    """Return the current aware UTC timestamp for production boundaries."""
    return datetime.now(UTC)


def build_default_speaker_resolver(
    wav_bytes: bytes, owner_person_id: int
) -> SpeakerRequestResolver:
    """Compose the production speaker resolver over the real repositories.

    Args:
        wav_bytes: The current turn's own audio — WAV, 16 000 Hz, mono, int16.
        owner_person_id: The household owner's entity id — the only person
            `VOICE` evidence may ever name as a candidate.

    Returns:
        A resolver wired to the real voice consent and voiceprint
        repositories (Task 1), the frozen embedding adapter (Task 3), and
        the existing household role repository.
    """
    return SpeakerRequestResolver(
        wav_bytes=wav_bytes,
        owner_person_id=owner_person_id,
        clock=_utc_now,
        read_role=get_active_role,
        read_consent=has_active_voice_consent,
        count_references=count_voiceprints,
        distance_to_centroid=centroid_distance,
        embed=embed_wav,
        has_energy=has_voiced_energy,
        has_duration=meets_verification_duration,
        model_id=_current_model_id(),
    )
