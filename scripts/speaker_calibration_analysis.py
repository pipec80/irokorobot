"""Aggregate analysis for the Plan 0047 speaker-calibration study (Task 6).

Turns a validated manifest plus one embedding per sample into a single
:class:`AggregateSpeakerReport`. Pure: no file, model, microphone or network
access — ``scripts.speaker_calibration`` does the I/O and calls
:func:`build_report`. The numeric rules are the Task 1 layer, unchanged:
individually normalized references are averaged into one centroid; every
non-reference sample is scored by cosine distance to it; matching is
``distance <= threshold``; the threshold is the lowest-FRR one with zero
observed live-impostor accepts, and replay never takes part in choosing it.

Plan 0068 adds the short-answer comparison to this module: :func:`trim_silence`
(a fixed energy rule) and :func:`build_short_study_report`, which scores every
clip raw and trimmed against a long-only and a long+short reference centroid at
the fixed Plan 0047 threshold. It retunes nothing.

Audio contract behind every embedding: WAV, 16 000 Hz, mono, signed int16.
The report holds only aggregates - no sample ids, subjects, hashes or paths.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import math
from typing import TYPE_CHECKING, Final
import wave

import numpy as np

from scripts.speaker_calibration import (
    cosine_distance,
    percentile,
    reference_centroid,
    sweep_speaker_thresholds,
    zero_far_speaker_threshold,
)
from scripts.speaker_calibration_corpus import condition_key, validate_wav_bytes
from scripts.speaker_calibration_models import (
    CLIP_VARIANTS,
    LONG_CLASSES,
    MIN_CELL_FOR_RANGE,
    REFERENCE_SETS,
    SAMPLE_CLASSES,
    SHORT_STUDY_PROBES,
    SPEAKER_STUDY_THRESHOLD,
    SPEECH_FRAME_RMS,
    AggregateSpeakerReport,
    ClipInfo,
    ConditionSummary,
    LengthBucketCell,
    ShortStudyReport,
    SilenceShare,
    VariantCell,
    VariantResult,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from scripts.speaker_calibration_models import (
        ClipVariant,
        ReferenceSet,
        SampleClass,
        SpeakerManifest,
        SpeakerSample,
    )

# Precommitted feasibility budget (Plan 0047 block 4). The gating measurement is
# the frozen Task 3 protocol; the per-sample figure here is informational only.
_LATENCY_BUDGET_MS: Final = 500.0
_RULE_OF_THREE: Final = 3.0  # ~95 % upper bound on a rate after zero observed events
_SCORED_CLASSES: Final = ("genuine", "impostor", "replay")

Scored = tuple["SpeakerSample", float]


@dataclass(frozen=True)
class _Measurement:
    """Counts at one operating point."""

    threshold: float
    selected: bool
    false_accepts: int
    false_rejects: int
    replay_accepts: int
    n_genuine: int
    n_impostor: int
    n_replay: int
    separation: float  # closest impostor distance minus farthest genuine distance


def build_report(
    manifest: SpeakerManifest,
    embeddings: Mapping[str, np.ndarray],
    latencies_ms: Sequence[float],
    *,
    model_id: str,
    package_version: str,
) -> AggregateSpeakerReport:
    """Score every sample against the reference centroid and summarize.

    Args:
        manifest: A corpus-validated manifest (all four classes present).
        embeddings: One finite 192-d embedding per ``sample_id``, produced from
            WAV audio at 16 000 Hz, mono, signed int16.
        latencies_ms: Per-sample embedding latencies in milliseconds.
        model_id: Frozen model identifier and revision.
        package_version: Backend package name and version.

    Returns:
        A report whose outcome is ``provisional_pass`` when a zero-observed-FAR
        threshold exists, otherwise ``fail_distance_overlap`` with no selected
        threshold (metrics are then a diagnostic at the lowest-FAR point).

    Raises:
        ValueError: If an embedding, a scored class or the latencies are missing.
    """
    _require_complete(manifest, embeddings, latencies_ms)
    scored = _score_samples(manifest, embeddings)
    measured = _measure(scored)
    p50 = percentile(latencies_ms, 0.5)
    p95 = percentile(latencies_ms, 0.95)
    return _assemble(manifest, scored, measured, model_id, package_version, p50, p95)


def _require_complete(
    manifest: SpeakerManifest, embeddings: Mapping[str, np.ndarray], latencies_ms: Sequence[float]
) -> None:
    missing = sum(1 for s in manifest.samples if s.sample_id not in embeddings)
    if missing:
        raise ValueError(f"embeddings missing for {missing} manifest sample(s) - re-run embed")
    if not latencies_ms:
        raise ValueError("no latency measurements - re-run embed")
    for cls in ("reference", *_SCORED_CLASSES):
        if not any(s.sample_class == cls for s in manifest.samples):
            raise ValueError(f"the corpus has no {cls} samples")


def _score_samples(
    manifest: SpeakerManifest, embeddings: Mapping[str, np.ndarray]
) -> dict[str, list[Scored]]:
    references = [
        embeddings[s.sample_id] for s in manifest.samples if s.sample_class == "reference"
    ]
    centroid = reference_centroid(references)
    scored: dict[str, list[Scored]] = {cls: [] for cls in _SCORED_CLASSES}
    for sample in manifest.samples:
        if sample.sample_class != "reference":
            distance = cosine_distance(embeddings[sample.sample_id], centroid)
            scored[sample.sample_class].append((sample, distance))
    return scored


def _measure(scored: Mapping[str, list[Scored]]) -> _Measurement:
    genuine = [d for _, d in scored["genuine"]]
    impostor = [d for _, d in scored["impostor"]]
    replay = [d for _, d in scored["replay"]]
    chosen = zero_far_speaker_threshold(genuine, impostor)
    threshold = chosen[0] if chosen is not None else _diagnostic_threshold(genuine, impostor)
    return _Measurement(
        threshold=threshold,
        selected=chosen is not None,
        false_accepts=_accepted(impostor, threshold),
        false_rejects=len(genuine) - _accepted(genuine, threshold),
        replay_accepts=_accepted(replay, threshold),
        n_genuine=len(genuine),
        n_impostor=len(impostor),
        n_replay=len(replay),
        separation=min(impostor) - max(genuine),
    )


def _diagnostic_threshold(genuine: Sequence[float], impostor: Sequence[float]) -> float:
    """Return the lowest-FAR (then lowest-FRR) genuine-distance threshold.

    Used only when no zero-observed-FAR threshold exists; it is reported as a
    diagnostic and is never selected.
    """
    results = sweep_speaker_thresholds(genuine, impostor, sorted(set(genuine)))
    best = min(results, key=lambda r: (r.false_accepts, r.false_rejects, r.threshold))
    return best.threshold


def _accepted(distances: Sequence[float], threshold: float) -> int:
    return sum(1 for distance in distances if distance <= threshold)


def _assemble(
    manifest: SpeakerManifest,
    scored: Mapping[str, list[Scored]],
    m: _Measurement,
    model_id: str,
    package_version: str,
    p50: float,
    p95: float,
) -> AggregateSpeakerReport:
    return AggregateSpeakerReport(
        model_id=model_id,
        package_version=package_version,
        sample_counts={c: sum(s.sample_class == c for s in manifest.samples) for c in LONG_CLASSES},
        selected_threshold=m.threshold if m.selected else None,
        live_false_accepts=m.false_accepts,
        live_far=m.false_accepts / m.n_impostor,
        genuine_false_rejects=m.false_rejects,
        genuine_frr=m.false_rejects / m.n_genuine,
        replay_accepts=m.replay_accepts,
        replay_accept_rate=m.replay_accepts / m.n_replay,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        by_condition=_condition_summaries(scored, m.threshold),
        outcome="provisional_pass" if m.selected else "fail_distance_overlap",
        limitations=_limitations(m, p95),
    )


def _condition_summaries(
    scored: Mapping[str, list[Scored]], threshold: float
) -> dict[str, ConditionSummary]:
    summaries: dict[str, ConditionSummary] = {}
    for cls, rows in scored.items():
        for condition in sorted({s.condition for s, _ in rows}):
            cell = [d for s, d in rows if s.condition == condition]
            accepted = _accepted(cell, threshold)
            summaries[condition_key(cls, condition)] = ConditionSummary(
                sample_class=cls,  # type: ignore[arg-type]  # keys come from _SCORED_CLASSES
                condition=condition,
                total=len(cell),
                accepted=accepted,
                rejected=len(cell) - accepted,
                distance_min=min(cell),
                distance_max=max(cell),
                distance_mean=sum(cell) / len(cell),
            )
    return summaries


def _limitations(m: _Measurement, p95: float) -> tuple[str, ...]:
    items = [
        "Small consented corpus: counts and ranges are provisional evidence, "
        "not population-level security.",
        "VOICE stays untrusted identity evidence; PC-3B enrollment/runtime and "
        "PC-4 fusion remain open.",
        "Replay is scored at the operating threshold but never chooses it and is "
        "not part of FAR; anti-spoofing belongs to PC-4.",
        "analyze applies no exclusions; any excluded capture is recorded in the plan.",
        "Latency is measured per sample over the real clips and is informational; "
        "the gating result is the frozen Task 3 protocol.",
    ]
    if m.selected:
        bound = _RULE_OF_THREE / m.n_impostor * 100.0
        items.append(
            f"0 false accepts in {m.n_impostor} live-impostor samples bounds the true "
            f"FAR only to about {bound:.1f} % (95 % rule of three)."
        )
        items.append(
            "FRR and FAR are in-sample: the threshold is picked from these same "
            "samples (the largest genuine distance below the closest impostor), so "
            "FRR is zero by construction and there is no held-out check. The "
            f"informative figure is the separation between the farthest genuine and "
            f"the closest impostor distance: {m.separation:.4f}."
        )
    else:
        items.append(
            "No zero-observed-FAR threshold exists: the figures are a diagnostic at "
            "the lowest-FAR operating point and no threshold is selected."
        )
    if m.replay_accepts:
        items.append(
            f"{m.replay_accepts} of {m.n_replay} replay probes were accepted: voice "
            "must not be treated as standalone high-assurance evidence."
        )
    if p95 > _LATENCY_BUDGET_MS:
        items.append(
            f"Per-sample p95 {p95:.0f} ms exceeds the {_LATENCY_BUDGET_MS:.0f} ms budget "
            "(informational; the gate is the frozen protocol)."
        )
    return tuple(items)


# --- Plan 0068: silence trimming ---------------------------------------------

# The fixed trim rule (Plan 0068 D-6). 20 ms frames; a frame is speech-level when
# its RMS is at least SPEECH_FRAME_RMS (the same floor ``capture`` uses to refuse a
# take with no speech: above empty-room noise, under the quietest legitimate
# far-field voice). Everything before the first and after the last speech-level
# frame is dropped, except a margin of TRIM_MARGIN_SECONDS kept on each side so a
# soft onset or release is not clipped. Interior audio is never touched.
TRIM_FRAME_SECONDS: Final = 0.02
TRIM_MARGIN_SECONDS: Final = 0.1
CLIP_SAMPLE_RATE: Final = 16_000  # the audio contract
_INT16_FULL_SCALE: Final = 32768.0


def trim_silence(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Drop the silence around the speech of one clip, by a fixed energy rule.

    Args:
        samples: One mono clip as int16 PCM (the audio contract: 16 000 Hz, mono,
            signed int16).
        sample_rate: Sampling rate of *samples* in Hz.

    Returns:
        A copy of the contiguous slice from ``TRIM_MARGIN_SECONDS`` before the
        first speech-level 20 ms frame to ``TRIM_MARGIN_SECONDS`` after the last
        one, clamped to the clip. Speech inside is never cut and the result is
        never longer than the input. A clip with no speech-level frame (pure
        silence or room noise) returns an empty array; callers report it.

    Raises:
        ValueError: If *samples* is not a one-dimensional int16 array or
            *sample_rate* is not positive.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if samples.ndim != 1:
        raise ValueError("samples must be one-dimensional (mono)")
    if samples.dtype != np.int16:
        raise ValueError("samples must be int16 PCM")
    if samples.size == 0:
        return samples.copy()
    frame = max(1, round(sample_rate * TRIM_FRAME_SECONDS))
    margin_frames = math.ceil(round(sample_rate * TRIM_MARGIN_SECONDS) / frame)
    energy = (samples.astype(np.float64) / _INT16_FULL_SCALE) ** 2
    starts = np.arange(0, samples.size, frame)
    lengths = np.minimum(frame, samples.size - starts)
    rms = np.sqrt(np.add.reduceat(energy, starts) / lengths)
    active = np.flatnonzero(rms >= SPEECH_FRAME_RMS)
    if active.size == 0:
        return samples[:0].copy()
    first = max(0, int(active[0]) - margin_frames) * frame
    last = min(samples.size, (int(active[-1]) + 1 + margin_frames) * frame)
    return samples[first:last].copy()


def decode_wav_samples(wav_bytes: bytes) -> np.ndarray:
    """Decode a contract WAV into int16 samples.

    Args:
        wav_bytes: Raw WAV bytes - 16 000 Hz, mono, signed int16.

    Returns:
        A writable 1-D int16 array.

    Raises:
        ValueError: If the bytes break the audio contract.
    """
    validate_wav_bytes(wav_bytes)
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).copy()


def encode_wav_samples(samples: np.ndarray) -> bytes:
    """Encode int16 samples as a contract WAV.

    Args:
        samples: 1-D int16 PCM.

    Returns:
        WAV bytes - 16 000 Hz, mono, signed int16.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(CLIP_SAMPLE_RATE)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


# --- Plan 0068: the short-answer comparison ----------------------------------

_BUCKETS: Final = (("1-1.5 s", 1.0, 1.5), ("1.5-2 s", 1.5, 2.0), ("2-2.5 s", 2.0, 2.5))
_OTHER_BUCKET: Final = "other"
_BUCKETED_CLASSES: Final[tuple[SampleClass, ...]] = ("genuine-short", "impostor-short")
_REFERENCE_CLASSES: Final = {
    "long-only": ("reference",),
    "long+short": ("reference", "reference-short"),
}
_PERCENT: Final = 100.0
# Distances of one (variant, class) cell: ``None`` is a clip with nothing left to embed.
type _Distances = list[tuple[SpeakerSample, float | None]]


def build_short_study_report(
    manifest: SpeakerManifest,
    embeddings: Mapping[str, np.ndarray],
    trimmed: Mapping[str, np.ndarray],
    clips: Mapping[str, ClipInfo],
    *,
    model_id: str,
    package_version: str,
) -> ShortStudyReport:
    """Score every clip raw and trimmed against both reference centroids.

    References are always the raw enrollment clips; only the probes are trimmed
    (the question is what a trimmed probe would do at runtime). Every variant is
    judged at ``SPEAKER_STUDY_THRESHOLD``; nothing is retuned.

    Args:
        manifest: A corpus-validated short-study manifest.
        embeddings: One 192-d embedding per ``sample_id`` of the raw clip.
        trimmed: The embedding of the trimmed clip, for every probe whose trim left
            audio; absent for a clip that was silent after trimming.
        clips: Raw and trimmed length of every probe clip.
        model_id: Frozen model identifier and revision.
        package_version: Backend package name and version.

    Returns:
        The aggregate report: four variants (raw/trimmed by long-only/long+short),
        the silence share per class and the limitations.

    Raises:
        ValueError: If a class is missing or an embedding or clip length is absent
            or inconsistent (counts only, never sample ids).
    """
    _require_complete_short(manifest, embeddings, trimmed, clips)
    probes = {
        cls: [s for s in manifest.samples if s.sample_class == cls] for cls in SHORT_STUDY_PROBES
    }
    variants = tuple(
        _variant_result(clip, references, manifest, embeddings, trimmed, clips, probes)
        for clip in CLIP_VARIANTS
        for references in REFERENCE_SETS
    )
    counts = {c: sum(s.sample_class == c for s in manifest.samples) for c in SAMPLE_CLASSES}
    return ShortStudyReport(
        model_id=model_id,
        package_version=package_version,
        threshold=SPEAKER_STUDY_THRESHOLD,
        sample_counts=counts,
        variants=variants,
        silence=tuple(_silence_share(cls, rows, clips) for cls, rows in probes.items()),
        limitations=_short_limitations(counts),
    )


def _require_complete_short(
    manifest: SpeakerManifest,
    embeddings: Mapping[str, np.ndarray],
    trimmed: Mapping[str, np.ndarray],
    clips: Mapping[str, ClipInfo],
) -> None:
    for cls in ("reference", "reference-short", *SHORT_STUDY_PROBES):
        if not any(s.sample_class == cls for s in manifest.samples):
            raise ValueError(f"the corpus has no {cls} samples")
    missing = sum(1 for s in manifest.samples if s.sample_id not in embeddings)
    if missing:
        raise ValueError(f"embeddings missing for {missing} manifest sample(s) - re-run embed")
    probes = [s for s in manifest.samples if s.sample_class in SHORT_STUDY_PROBES]
    if any(s.sample_id not in clips for s in probes):
        raise ValueError("clip lengths missing for some probe sample(s) - re-run embed")
    inconsistent = sum(1 for s in probes if not _trim_is_consistent(s.sample_id, trimmed, clips))
    if inconsistent:
        raise ValueError(
            f"trimmed embeddings are inconsistent for {inconsistent} sample(s) - re-run embed"
        )


def _trim_is_consistent(
    sample_id: str, trimmed: Mapping[str, np.ndarray], clips: Mapping[str, ClipInfo]
) -> bool:
    """A clip has a trimmed vector exactly when audio is left after trimming."""
    clip = clips[sample_id]
    if clip.raw_samples <= 0 or not 0 <= clip.trimmed_samples <= clip.raw_samples:
        return False
    return (clip.trimmed_samples > 0) == (sample_id in trimmed)


def _variant_result(
    clip: ClipVariant,
    references: ReferenceSet,
    manifest: SpeakerManifest,
    embeddings: Mapping[str, np.ndarray],
    trimmed: Mapping[str, np.ndarray],
    clips: Mapping[str, ClipInfo],
    probes: Mapping[SampleClass, list[SpeakerSample]],
) -> VariantResult:
    classes = _REFERENCE_CLASSES[references]
    centroid = reference_centroid(
        [embeddings[s.sample_id] for s in manifest.samples if s.sample_class in classes]
    )
    source = embeddings if clip == "raw" else trimmed
    scored: dict[SampleClass, _Distances] = {
        cls: [
            (s, cosine_distance(source[s.sample_id], centroid) if s.sample_id in source else None)
            for s in rows
        ]
        for cls, rows in probes.items()
    }
    return VariantResult(
        clip=clip,
        references=references,
        cells={cls: _cell(cls, rows) for cls, rows in scored.items()},
        buckets=tuple(
            _bucket_cell(cls, label, scored[cls], clips)
            for cls in _BUCKETED_CLASSES
            for label in (*(name for name, _, _ in _BUCKETS), _OTHER_BUCKET)
        ),
    )


def _cell(sample_class: SampleClass, rows: _Distances) -> VariantCell:
    distances = [d for _, d in rows if d is not None]
    shown = len(distances) >= MIN_CELL_FOR_RANGE
    return VariantCell(
        sample_class=sample_class,
        total=len(rows),
        accepted=_accepted(distances, SPEAKER_STUDY_THRESHOLD),
        silent=len(rows) - len(distances),
        distance_min=min(distances) if shown else None,
        distance_mean=sum(distances) / len(distances) if shown else None,
        distance_max=max(distances) if shown else None,
    )


def _bucket_of(raw_samples: int) -> str:
    seconds = raw_samples / CLIP_SAMPLE_RATE
    for label, low, high in _BUCKETS:
        if low <= seconds < high:
            return label
    return _OTHER_BUCKET


def _bucket_cell(
    sample_class: SampleClass, label: str, rows: _Distances, clips: Mapping[str, ClipInfo]
) -> LengthBucketCell:
    inside = [d for s, d in rows if _bucket_of(clips[s.sample_id].raw_samples) == label]
    return LengthBucketCell(
        sample_class=sample_class,
        bucket=label,
        total=len(inside),
        accepted=_accepted([d for d in inside if d is not None], SPEAKER_STUDY_THRESHOLD),
    )


def _silence_share(
    sample_class: SampleClass, rows: Sequence[SpeakerSample], clips: Mapping[str, ClipInfo]
) -> SilenceShare:
    infos = [clips[s.sample_id] for s in rows]
    shares = [1.0 - info.trimmed_samples / info.raw_samples for info in infos]
    return SilenceShare(
        sample_class=sample_class,
        total=len(infos),
        silent_clips=sum(1 for info in infos if info.trimmed_samples == 0),
        mean_share=sum(shares) / len(shares) if len(shares) >= MIN_CELL_FOR_RANGE else None,
    )


def _short_limitations(counts: Mapping[SampleClass, int]) -> tuple[str, ...]:
    impostors = counts["impostor-short"]
    return (
        f"Every variant is judged at the fixed threshold {SPEAKER_STUDY_THRESHOLD} of Plan 0047; "
        "nothing is retuned and no enrollment or runtime setting changes.",
        "Small consented corpus: genuine rates are in-sample - the same genuine clips judge every "
        "variant and there is no held-out set - so differences between variants are provisional.",
        f"For a variant with 0 observed accepts in {impostors} short impostor clips, the 95 % "
        "rule-of-three bound on the false-accept rate is about "
        f"{_RULE_OF_THREE / impostors * _PERCENT:.1f} %.",
        "References are the raw enrollment clips in every variant; only probe clips are trimmed.",
        f"Trim rule: {TRIM_FRAME_SECONDS * 1000:.0f} ms frames, speech-level at RMS >= "
        f"{SPEECH_FRAME_RMS}, {TRIM_MARGIN_SECONDS * 1000:.0f} ms margin kept on each side.",
        "The trim treats any frame at or above the RMS floor as speech, so a click or steady "
        "background noise above that floor defeats the trim.",
        "The runtime refuses clips under SPEAKER_MIN_VERIFICATION_S (1.5 s), so raw 1-1.5 s clips "
        "and trimmed clips under 1.5 s would never reach the embedder in production; read the "
        "length-bucket table with that in mind.",
        "A clip with no audio left after trimming counts as rejected and has no distance.",
        "Distance ranges and silence shares are hidden for a cell of fewer than "
        f"{MIN_CELL_FOR_RANGE} clips.",
        "VOICE stays untrusted identity evidence; replay is scored only, anti-spoofing belongs "
        "to PC-4.",
    )
