"""Task 1 (Plan 0075): replay a corpus clip through the production voice pipeline.

The harness mirrors ``SpeakerRequestResolver._resolve`` order with injected
seams (``embed``, ``match``, ``count_refs``) so the owner-voice verification rate
can be measured offline over a private corpus. Consent and role are forced to the
enrolled owner, because the corpus is the owner's own voice scored against the
owner's own database copy, so the verdict isolates the acoustic question. For a
sub-1.5 s clip it also computes the no-floor diagnostic distance (Plan 0075 D-1):
a measurement, never a proposal to lower the floor.

Output is counts only — never a transcript and never a per-clip distance in a
tracked record.

Audio contract of every clip: WAV, 16 000 Hz, mono, int16.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
import math

import numpy as np
from server.cognition.identity import HouseholdRole
from server.cognition.speaker_authentication import (
    evaluate_speaker_verification,
)
from server.settings import settings
from server.voice.speaker_embedding import (
    clip_duration_s,
    has_voiced_energy,
    meets_verification_duration,
)
from server.voice.voiceprints import CentroidMatch

from scripts.cm4_models import ClipVerdict, CountTable, DurationBucket

__all__ = ["aggregate", "duration_bucket", "score_clip"]

type Embedder = Callable[[bytes], Awaitable[np.ndarray]]
type CentroidMatcher = Callable[[int, np.ndarray, str], Awaitable[CentroidMatch | None]]
type ReferenceCounter = Callable[[int, str], Awaitable[int]]

_GATE_OK = "ok"
_SUB_FLOOR_BUCKET = "lt_1_5"
_MID_BUCKET_MAX_S = 3.0


def duration_bucket(duration_s: float) -> DurationBucket:
    """Return the duration bucket for a clip of *duration_s* seconds.

    Args:
        duration_s: Decoded clip length in seconds.

    Returns:
        ``"lt_1_5"`` below the 1.5 s verification floor, ``"1_5_to_3"`` up to and
        including 3 s, ``"gt_3"`` above it.
    """
    if duration_s < settings.speaker_min_verification_s:
        return "lt_1_5"
    if duration_s <= _MID_BUCKET_MAX_S:
        return "1_5_to_3"
    return "gt_3"


def _distance_ok(distance: float | None) -> bool:
    """Mirror ``speaker_authentication._distance_within_threshold`` (fail closed)."""
    return (
        distance is not None
        and math.isfinite(distance)
        and distance <= settings.speaker_authentication_match_threshold
    )


def _first_failed_gate(
    *,
    reference_count: int,
    energy_ok: bool,
    duration_ok: bool,
    distance: float | None,
) -> str:
    """Name the first gate that stopped a VERIFIED verdict, in the resolver's order.

    Consent, role and the backend are forced for the measurement, so only the
    reference, energy, duration and distance gates can fire here.
    """
    failures = (
        (reference_count < settings.speaker_min_reference_count, "references"),
        (not energy_ok, "energy"),
        (not duration_ok, "duration"),
        (not _distance_ok(distance), "distance"),
    )
    return next((name for failed, name in failures if failed), _GATE_OK)


async def score_clip(
    wav_bytes: bytes,
    phrase_type: str,
    *,
    owner_person_id: int,
    model_id: str,
    embed: Embedder,
    match: CentroidMatcher,
    count_refs: ReferenceCounter,
) -> ClipVerdict:
    """Replay one clip through the production voice pipeline and return its verdict.

    Args:
        wav_bytes: The clip — WAV, 16 000 Hz, mono, int16.
        phrase_type: Pipec's coarse annotation for this clip.
        owner_person_id: The enrolled owner the corpus belongs to.
        model_id: The frozen ``model@revision`` of the stored voiceprints.
        embed: Seam that embeds a clip (production ``embed_wav`` or a test double).
        match: Seam that compares an embedding with the owner centroid.
        count_refs: Seam that counts stored references for the owner and model.

    Returns:
        The clip's :class:`ClipVerdict`, with the no-floor diagnostic filled only
        for a sub-1.5 s clip that carried voiced energy and had enough references.
    """
    duration_s = clip_duration_s(wav_bytes)
    bucket = duration_bucket(duration_s)
    reference_count = await count_refs(owner_person_id, model_id)
    enough = reference_count >= settings.speaker_min_reference_count
    energy_ok = has_voiced_energy(wav_bytes)
    duration_ok = energy_ok and meets_verification_duration(wav_bytes)
    distance: float | None = None
    if enough and energy_ok and duration_ok:
        result = await match(owner_person_id, await embed(wav_bytes), model_id)
        if result is not None:
            distance = result.distance
            reference_count = result.reference_count
    verdict = evaluate_speaker_verification(
        reference_count=reference_count,
        distance=distance,
        consent_active=True,
        role=HouseholdRole.OWNER,
        backend_available=True,
    )
    gate = _first_failed_gate(
        reference_count=reference_count,
        energy_ok=energy_ok,
        duration_ok=duration_ok,
        distance=distance,
    )
    no_floor_distance: float | None = None
    no_floor_would_match: bool | None = None
    if bucket == _SUB_FLOOR_BUCKET and energy_ok and enough:
        diagnostic = await match(owner_person_id, await embed(wav_bytes), model_id)
        if diagnostic is not None:
            no_floor_distance = diagnostic.distance
            no_floor_would_match = _distance_ok(diagnostic.distance)
    return ClipVerdict(
        duration_s=duration_s,
        bucket=bucket,
        gate=gate,
        verdict=verdict.value,
        phrase_type=phrase_type,
        no_floor_distance=no_floor_distance,
        no_floor_would_match=no_floor_would_match,
    )


def aggregate(verdicts: Sequence[ClipVerdict]) -> CountTable:
    """Count verdicts by bucket and phrase type, with the no-floor tallies.

    Args:
        verdicts: The scored clips.

    Returns:
        A :class:`CountTable` of pure counts — no distances, no text.
    """
    by_bucket: dict[str, dict[str, int]] = {}
    by_phrase_type: dict[str, dict[str, int]] = {}
    no_floor_assessed = 0
    no_floor_would_match = 0
    for item in verdicts:
        by_bucket.setdefault(item.bucket, {})
        by_bucket[item.bucket][item.verdict] = by_bucket[item.bucket].get(item.verdict, 0) + 1
        by_phrase_type.setdefault(item.phrase_type, {})
        by_phrase_type[item.phrase_type][item.verdict] = (
            by_phrase_type[item.phrase_type].get(item.verdict, 0) + 1
        )
        if item.no_floor_distance is not None:
            no_floor_assessed += 1
            if item.no_floor_would_match:
                no_floor_would_match += 1
    return CountTable(
        by_bucket=by_bucket,
        by_phrase_type=by_phrase_type,
        no_floor_assessed=no_floor_assessed,
        no_floor_would_match=no_floor_would_match,
        total=len(verdicts),
    )
