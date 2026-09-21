"""Aggregate analysis for the Plan 0047 speaker-calibration study (Task 6).

Turns a validated manifest plus one embedding per sample into a single
:class:`AggregateSpeakerReport`. Pure: no file, model, microphone or network
access — ``scripts.speaker_calibration`` does the I/O and calls
:func:`build_report`. The numeric rules are the Task 1 layer, unchanged:
individually normalized references are averaged into one centroid; every
non-reference sample is scored by cosine distance to it; matching is
``distance <= threshold``; the threshold is the lowest-FRR one with zero
observed live-impostor accepts, and replay never takes part in choosing it.

Audio contract behind every embedding: WAV, 16 000 Hz, mono, signed int16.
The report holds only aggregates - no sample ids, subjects, hashes or paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from scripts.speaker_calibration import (
    cosine_distance,
    percentile,
    reference_centroid,
    sweep_speaker_thresholds,
    zero_far_speaker_threshold,
)
from scripts.speaker_calibration_corpus import condition_key
from scripts.speaker_calibration_models import (
    SAMPLE_CLASSES,
    AggregateSpeakerReport,
    ConditionSummary,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import numpy as np

    from scripts.speaker_calibration_models import SpeakerManifest, SpeakerSample

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
        sample_counts={
            c: sum(s.sample_class == c for s in manifest.samples) for c in SAMPLE_CLASSES
        },
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
