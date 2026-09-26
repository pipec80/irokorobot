"""Tests for the Plan 0047 Task 6 aggregate analysis (pure, no model, no I/O).

Every embedding is a synthetic 192-d unit vector placed at an exact cosine
distance from the reference axis, so thresholds, false accepts and replay
accepts are known by construction. No audio, no model, no microphone.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.speaker_calibration_analysis import build_report
from scripts.speaker_calibration_corpus import render_aggregate_report
from scripts.speaker_calibration_models import (
    CONDITIONS,
    SpeakerManifest,
    SpeakerSample,
)

_DIM = 192
_MODEL = "speechbrain/spkrec-ecapa-voxceleb@0000000000000000000000000000000000000000"
_PACKAGE = "speechbrain 1.1.1"


def _at_distance(distance: float) -> np.ndarray:
    """Return a unit vector whose cosine distance to axis 0 is exactly *distance*."""
    theta = float(np.arccos(1.0 - distance))
    vec = np.zeros(_DIM)
    vec[0], vec[1] = np.cos(theta), np.sin(theta)
    return vec


def _sample(sample_id: str, sample_class: str, subject: str, condition: str) -> SpeakerSample:
    return SpeakerSample(
        sample_id=sample_id,
        subject_id=subject,
        sample_class=sample_class,  # type: ignore[arg-type]
        session_id=f"{sample_class}-session",
        phrase_id="phrase-01",
        condition=condition,
        wav_path=Path(f"{sample_id}.wav"),
        sha256="0" * 64,
    )


def _corpus(
    genuine: list[float], impostor: list[float], replay: list[float]
) -> tuple[SpeakerManifest, dict[str, np.ndarray]]:
    """Build a manifest plus embeddings from per-class distances to the reference axis."""
    samples: list[SpeakerSample] = []
    vectors: dict[str, np.ndarray] = {}

    def add(prefix: str, cls: str, subject: str, distances: list[float]) -> None:
        for index, distance in enumerate(distances):
            sample = _sample(f"{prefix}-{index}", cls, subject, CONDITIONS[index % len(CONDITIONS)])
            samples.append(sample)
            vectors[sample.sample_id] = _at_distance(distance)

    add("ref", "reference", "owner", [0.0] * 6)
    add("gen", "genuine", "owner", genuine)
    add("imp", "impostor", "impostor_a", impostor)
    add("rep", "replay", "owner", replay)
    return SpeakerManifest(schema_version=1, samples=tuple(samples)), vectors


def _separable() -> tuple[SpeakerManifest, dict[str, np.ndarray]]:
    genuine = [0.10 + 0.01 * i for i in range(24)]  # 0.10 .. 0.33
    impostor = [0.50 + 0.02 * i for i in range(18)]  # 0.50 .. 0.84
    replay = [0.20, 0.25, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
    return _corpus(genuine, impostor, replay)


def _report(manifest: SpeakerManifest, vectors: dict[str, np.ndarray], **kw: object):
    latencies = kw.pop("latencies", [200.0, 220.0, 240.0])
    return build_report(
        manifest,
        vectors,
        latencies,  # type: ignore[arg-type]
        model_id=_MODEL,
        package_version=_PACKAGE,
    )


def test_separable_corpus_is_a_provisional_pass_with_the_zero_far_threshold() -> None:
    manifest, vectors = _separable()

    report = _report(manifest, vectors)

    assert report.outcome == "provisional_pass"
    assert report.live_false_accepts == 0
    assert report.live_far == 0.0
    assert report.selected_threshold == pytest.approx(0.33, abs=1e-9)  # largest genuine
    assert report.genuine_false_rejects == 0
    assert report.genuine_frr == 0.0


def test_replay_is_scored_at_the_selected_threshold_and_never_picks_it() -> None:
    manifest, vectors = _separable()

    report = _report(manifest, vectors)

    # replay distances <= 0.33 are 0.20 and 0.25 -> 2 of 8 accepted
    assert report.replay_accepts == 2
    assert report.replay_accept_rate == pytest.approx(0.25)
    # the replay at 0.20 sits inside the genuine range, so it cannot move the threshold
    assert report.selected_threshold == pytest.approx(0.33, abs=1e-9)


def test_overlap_is_a_fail_with_no_selected_threshold_but_still_full_metrics() -> None:
    genuine = [0.10 + 0.01 * i for i in range(24)]
    impostor = [0.05] + [0.50 + 0.02 * i for i in range(17)]  # closest sample overall
    manifest, vectors = _corpus(genuine, impostor, [0.6] * 8)

    report = _report(manifest, vectors)

    assert report.outcome == "fail_distance_overlap"
    assert report.selected_threshold is None
    assert report.live_false_accepts is not None
    assert report.live_false_accepts >= 1
    assert any("diagnostic" in item.lower() for item in report.limitations)


def test_sample_counts_cover_all_four_classes() -> None:
    manifest, vectors = _separable()

    report = _report(manifest, vectors)

    assert report.sample_counts == {"reference": 6, "genuine": 24, "impostor": 18, "replay": 8}


def test_by_condition_summarizes_each_scored_class_and_condition() -> None:
    manifest, vectors = _separable()

    report = _report(manifest, vectors)

    cell = report.by_condition["genuine/quiet-near"]
    assert cell.sample_class == "genuine"
    assert cell.total == 6
    assert cell.accepted + cell.rejected == cell.total
    assert cell.distance_min <= cell.distance_mean <= cell.distance_max
    assert not any(key.startswith("reference/") for key in report.by_condition)


def test_latency_percentiles_come_from_the_per_sample_measurements() -> None:
    manifest, vectors = _separable()

    report = _report(manifest, vectors, latencies=[100.0, 200.0, 300.0, 400.0])

    assert report.latency_p50_ms == pytest.approx(200.0)
    assert report.latency_p95_ms == pytest.approx(400.0)


def test_a_per_sample_p95_above_the_budget_is_recorded_as_a_limitation() -> None:
    manifest, vectors = _separable()

    report = _report(manifest, vectors, latencies=[100.0, 900.0])

    assert any("500" in item for item in report.limitations)


def test_zero_far_limitation_states_the_small_sample_bound() -> None:
    manifest, vectors = _separable()

    report = _report(manifest, vectors)

    # rule of three: 0 false accepts in 18 impostor samples -> ~16.7 % upper bound
    assert any("16.7" in item for item in report.limitations)


def test_limitations_keep_voice_untrusted_and_replay_out_of_far() -> None:
    manifest, vectors = _separable()

    text = " ".join(_report(manifest, vectors).limitations).lower()

    assert "voice" in text
    assert "replay" in text


def test_a_missing_embedding_is_rejected_without_naming_the_sample() -> None:
    manifest, vectors = _separable()
    vectors.pop("gen-3")

    with pytest.raises(ValueError, match="re-run embed") as excinfo:
        _report(manifest, vectors)

    assert "gen-3" not in str(excinfo.value)


def test_missing_latency_measurements_are_rejected() -> None:
    manifest, vectors = _separable()

    with pytest.raises(ValueError, match="latency"):
        _report(manifest, vectors, latencies=[])


def test_the_rendered_report_carries_no_sample_ids_subjects_or_paths() -> None:
    manifest, vectors = _separable()

    text = render_aggregate_report(_report(manifest, vectors))

    assert "gen-0" not in text
    assert "impostor_a" not in text
    assert ".wav" not in text
    assert "provisional_pass" in text
