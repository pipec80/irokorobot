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

from pathlib import Path
import sys

# Direct execution (just cm4-voice-rate) puts scripts/ on sys.path[0]; the
# from-scripts imports below need the repo root (pytest adds it via pyproject).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
import asyncio
from collections.abc import Awaitable, Callable, Sequence
import json
import logging
import math

import aiosqlite
import numpy as np
from server.cognition.identity import HouseholdRole
from server.cognition.speaker_authentication import (
    SpeakerVerdict,
    evaluate_speaker_verification,
)
from server.exceptions import AudioContractError, BrainMemoryError
from server.settings import settings
from server.voice.speaker_embedding import (
    SpeakerBackendError,
    clip_duration_s,
    has_voiced_energy,
    meets_verification_duration,
)
from server.voice.voiceprints import CentroidMatch

from scripts import cm4_stats
from scripts.cm4_models import ClipVerdict, CountTable, DurationBucket

logger = logging.getLogger(__name__)

__all__ = ["aggregate", "build_report", "duration_bucket", "main", "score_clip"]

type Embedder = Callable[[bytes], Awaitable[np.ndarray]]
type CentroidMatcher = Callable[[int, np.ndarray, str], Awaitable[CentroidMatch | None]]
type ReferenceCounter = Callable[[int, str], Awaitable[int]]

_GATE_OK = "ok"
_SUB_FLOOR_BUCKET = "lt_1_5"
_MID_BUCKET_MAX_S = 3.0
_VERIFIED = SpeakerVerdict.VERIFIED.value
_CENTROID_SOURCES = ("real_voiceprint", "in_session_references")
# The production resolver (speaker_authentication._resolve) degrades a clip to
# "unavailable" on any of these; a clip the contract rejects (for example one
# longer than the 30 s cap, seen in a real conversation) must not crash the run.
_BACKEND_FAILURES = (AudioContractError, BrainMemoryError, SpeakerBackendError, aiosqlite.Error)


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
    backend_available: bool,
    reference_count: int,
    energy_ok: bool,
    duration_ok: bool,
    distance: float | None,
) -> str:
    """Name the first gate that stopped a VERIFIED verdict, in the resolver's order.

    Consent and role are forced for the measurement; the backend gate fires when
    embedding or the store failed (a clip the contract rejects, for example one
    too long), mirroring the production resolver.
    """
    failures = (
        (not backend_available, "unavailable"),
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
    backend_available = True
    if enough and energy_ok and duration_ok:
        try:
            result = await match(owner_person_id, await embed(wav_bytes), model_id)
        except _BACKEND_FAILURES:
            backend_available = False
            result = None
        if result is not None:
            distance = result.distance
            reference_count = result.reference_count
    verdict = evaluate_speaker_verification(
        reference_count=reference_count,
        distance=distance,
        consent_active=True,
        role=HouseholdRole.OWNER,
        backend_available=backend_available,
    )
    gate = _first_failed_gate(
        backend_available=backend_available,
        reference_count=reference_count,
        energy_ok=energy_ok,
        duration_ok=duration_ok,
        distance=distance,
    )
    no_floor_distance: float | None = None
    no_floor_would_match: bool | None = None
    if bucket == _SUB_FLOOR_BUCKET and energy_ok and enough:
        try:
            diagnostic = await match(owner_person_id, await embed(wav_bytes), model_id)
        except _BACKEND_FAILURES:
            diagnostic = None
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


def build_report(
    scored: Sequence[tuple[str, ClipVerdict]], *, centroid_source: str
) -> dict[str, object]:
    """Aggregate scored clips into the tracked report structure (counts and rates only).

    Args:
        scored: ``(session, verdict)`` for every corpus clip.
        centroid_source: Which centroid the verdicts were scored against
            (``real_voiceprint`` or ``in_session_references``).

    Returns:
        A JSON-ready dict: per-bucket and per-phrase-type counts, the per-turn
        verified rate with its Wilson interval, the per-conversation aggregate
        with a by-conversation bootstrap interval, and the sub-1.5 s no-floor
        diagnostic. No per-clip distance and no session id ever appear.
    """
    verdicts = [verdict for _session, verdict in scored]
    table = aggregate(verdicts)
    verified = sum(1 for verdict in verdicts if verdict.verdict == _VERIFIED)
    n = len(verdicts)
    per_conversation: dict[str, list[int]] = {}
    for session, verdict in scored:
        slot = per_conversation.setdefault(session, [0, 0])
        slot[1] += 1
        if verdict.verdict == _VERIFIED:
            slot[0] += 1
    conversations = [(ok, total) for ok, total in per_conversation.values()]
    with_verified = sum(1 for ok, _total in conversations if ok > 0)
    return {
        "centroid_source": centroid_source,
        "total_clips": n,
        "by_bucket": table.by_bucket,
        "by_phrase_type": table.by_phrase_type,
        "per_turn": {
            "verified": verified,
            "n": n,
            "rate": cm4_stats.pooled_rate(verified, n),
            "ci95": list(cm4_stats.wilson_interval(verified, n)),
        },
        "per_conversation": {
            "conversations": len(conversations),
            "with_at_least_one_verified": with_verified,
            "share_with_verified": cm4_stats.pooled_rate(with_verified, len(conversations)),
            "pooled_rate_ci95_by_conversation": list(
                cm4_stats.bootstrap_by_conversation(conversations)
            ),
        },
        "no_floor_diagnostic": {
            "assessed": table.no_floor_assessed,
            "would_match": table.no_floor_would_match,
            "note": "distance if the 1.5 s floor did not exist; a diagnostic, not a proposal",
        },
    }


async def _score_corpus(root: Path, owner_id: int) -> list[tuple[str, ClipVerdict]]:
    """Score every manifest clip against the owner voiceprint read from the DB copy."""
    from server.voice.speaker_embedding import embed_wav, model_id  # noqa: PLC0415
    from server.voice.voiceprints import centroid_match, count_voiceprints  # noqa: PLC0415

    from scripts.cm4_corpus import MANIFEST_NAME, load_clips  # noqa: PLC0415 -- CLI-only dep
    from scripts.speaker_calibration_corpus import resolve_corpus_path  # noqa: PLC0415

    current_model = model_id()
    scored: list[tuple[str, ClipVerdict]] = []
    for record in load_clips(root / MANIFEST_NAME, root):
        clip = resolve_corpus_path(root, f"clips/{record.clip_id}.wav").read_bytes()
        verdict = await score_clip(
            clip,
            record.phrase_type,
            owner_person_id=owner_id,
            model_id=current_model,
            embed=embed_wav,
            match=centroid_match,
            count_refs=count_voiceprints,
        )
        scored.append((record.session, verdict))
    return scored


async def _run_report(root: Path, owner_id: int, centroid_source: str) -> dict[str, object]:
    """Open the DB copy, score the corpus, close, and build the report."""
    from server.db import close_db, open_db  # noqa: PLC0415 -- CLI-only dep

    await open_db()
    try:
        scored = await _score_corpus(root, owner_id)
    finally:
        await close_db()
    return build_report(scored, centroid_source=centroid_source)


def _cmd_report(args: argparse.Namespace) -> None:
    from scripts.cm4_corpus import DEFAULT_CM4_CORPUS_ROOT  # noqa: PLC0415 -- CLI-only dep
    from scripts.speaker_calibration_corpus import resolve_corpus_path  # noqa: PLC0415

    root = DEFAULT_CM4_CORPUS_ROOT
    db_path = settings.brain_db_path.resolve()
    if not db_path.is_relative_to(root.resolve()):
        raise SystemExit(
            "Point BRAIN_DB_PATH at a read-only COPY under "
            f"{root} (never the live data/omnibot.db) before running the report."
        )
    report = asyncio.run(_run_report(root, args.owner_id, args.centroid_source))
    (root / "results").mkdir(parents=True, exist_ok=True)
    out = resolve_corpus_path(root, "results/voice_rate.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))  # noqa: T201 -- the operator pastes this aggregate


def main(argv: list[str] | None = None) -> None:
    """Run the voice-rate report CLI."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="CM-4 owner-voice verification rate (Plan 0075).")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    report = subparsers.add_parser("report")
    report.add_argument("--owner-id", type=int, required=True)
    report.add_argument("--centroid-source", choices=_CENTROID_SOURCES, default="real_voiceprint")
    report.set_defaults(handler=_cmd_report)
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
