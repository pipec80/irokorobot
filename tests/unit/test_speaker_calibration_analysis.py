"""Tests for the Plan 0047 Task 6 aggregate analysis (pure, no model, no I/O).

Every embedding is a synthetic 192-d unit vector placed at an exact cosine
distance from the reference axis, so thresholds, false accepts and replay
accepts are known by construction. No audio, no model, no microphone.
"""

from __future__ import annotations

import io
from pathlib import Path
import wave

import numpy as np
import pytest

from scripts import speaker_calibration, speaker_calibration_analysis
from scripts.speaker_calibration_analysis import (
    _short_limitations,
    build_report,
    build_short_study_report,
    decode_wav_samples,
    encode_wav_samples,
    trim_silence,
)
from scripts.speaker_calibration_corpus import (
    render_aggregate_report,
    render_short_study_report,
)
from scripts.speaker_calibration_models import (
    CONDITIONS,
    SAMPLE_CLASSES,
    SPEAKER_STUDY_THRESHOLD,
    SPEECH_FRAME_RMS,
    ClipInfo,
    ShortStudyReport,
    SpeakerManifest,
    SpeakerSample,
    VariantCell,
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


# =====================================================================
# Plan 0068 Task 4 - trimming and the short-answer variant comparison
# =====================================================================

_RATE = 16_000
_FRAME = 320  # 20 ms at 16 kHz
_PAD = 1_600  # 100 ms at 16 kHz


def _tone(seconds: float, amplitude: int = 12_000) -> np.ndarray:
    """Return a synthetic sine tone as int16 samples - speech-level, non-biometric."""
    step = np.arange(int(_RATE * seconds), dtype=np.float64) / _RATE
    return (np.sin(2.0 * np.pi * 220.0 * step) * amplitude).astype(np.int16)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(_RATE * seconds), dtype=np.int16)


def _noise_floor(seconds: float) -> np.ndarray:
    """Return room-level noise (frame RMS ~0.0022), below the speech floor."""
    return _tone(seconds, amplitude=100)


def test_trim_removes_leading_and_trailing_silence_but_keeps_a_padded_margin() -> None:
    clip = np.concatenate([_silence(0.5), _tone(0.3), _silence(0.6)])

    trimmed = trim_silence(clip, _RATE)

    assert len(trimmed) == 4_800 + 2 * _PAD
    assert np.array_equal(trimmed, clip[8_000 - _PAD : 8_000 + 4_800 + _PAD])


def test_trim_never_cuts_speech_inside_the_clip() -> None:
    clip = np.concatenate([_silence(0.5), _tone(0.3), _silence(0.4), _tone(0.3), _silence(0.6)])

    trimmed = trim_silence(clip, _RATE)

    # Both bursts and the pause between them survive, sample for sample.
    start, end = 8_000 - _PAD, 8_000 + 4_800 + 6_400 + 4_800 + _PAD
    assert np.array_equal(trimmed, clip[start:end])


def test_trim_of_pure_silence_is_empty() -> None:
    assert trim_silence(_silence(1.5), _RATE).size == 0


def test_trim_of_room_noise_below_the_speech_floor_is_empty() -> None:
    assert trim_silence(_noise_floor(1.5), _RATE).size == 0


def test_trim_of_an_empty_clip_is_empty() -> None:
    assert trim_silence(np.zeros(0, dtype=np.int16), _RATE).size == 0


def test_trim_keeps_a_clip_that_is_speech_end_to_end() -> None:
    clip = _tone(1.2)

    assert np.array_equal(trim_silence(clip, _RATE), clip)


def test_trim_clamps_the_margin_at_both_ends_of_the_clip() -> None:
    clip = np.concatenate([_silence(0.04), _tone(0.5), _silence(0.04)])  # shorter than the margin

    assert np.array_equal(trim_silence(clip, _RATE), clip)


def test_trim_handles_a_final_partial_frame() -> None:
    clip = np.concatenate([_silence(0.5), _tone(0.2), np.full(100, 9_000, dtype=np.int16)])

    trimmed = trim_silence(clip, _RATE)

    assert len(trimmed) <= len(clip)
    assert np.array_equal(trimmed[-100:], clip[-100:])  # the speech-level tail stays


@pytest.mark.parametrize(
    "lead, speech, tail",
    [(0.0, 0.5, 0.0), (0.7, 0.02, 0.7), (0.1, 0.3, 0.9), (1.0, 0.0, 0.0), (0.33, 0.41, 0.07)],
)
def test_trim_is_never_longer_than_its_input(lead: float, speech: float, tail: float) -> None:
    clip = np.concatenate([_silence(lead), _tone(speech), _silence(tail)])

    assert len(trim_silence(clip, _RATE)) <= len(clip)


def test_trim_keeps_a_single_speech_level_frame_inside_silence() -> None:
    clip = np.concatenate([_silence(0.4), _tone(_FRAME / _RATE), _silence(0.4)])

    trimmed = trim_silence(clip, _RATE)

    assert len(trimmed) == _FRAME + 2 * _PAD


def test_trim_does_not_modify_its_input_and_returns_int16() -> None:
    clip = np.concatenate([_silence(0.3), _tone(0.3), _silence(0.3)])
    before = clip.copy()

    trimmed = trim_silence(clip, _RATE)

    assert np.array_equal(clip, before)
    assert trimmed.dtype == np.int16
    trimmed[:] = 0
    assert np.array_equal(clip, before)  # the result is a copy, not a view


def test_trim_rejects_audio_that_is_not_int16_mono() -> None:
    with pytest.raises(ValueError, match="int16"):
        trim_silence(np.zeros(100, dtype=np.float32), _RATE)
    with pytest.raises(ValueError, match="one-dimensional"):
        trim_silence(np.zeros((2, 100), dtype=np.int16), _RATE)
    with pytest.raises(ValueError, match="sample_rate"):
        trim_silence(np.zeros(100, dtype=np.int16), 0)


def test_wav_samples_round_trip_through_the_contract_encoding() -> None:
    clip = np.concatenate([_silence(0.1), _tone(0.2)])

    decoded = decode_wav_samples(encode_wav_samples(clip))

    assert decoded.dtype == np.int16
    assert np.array_equal(decoded, clip)


def test_decode_refuses_a_wav_outside_the_audio_contract() -> None:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 100)

    with pytest.raises(ValueError, match="audio contract"):
        decode_wav_samples(buf.getvalue())


# --- the short-answer report -----------------------------------------


def _plane(angle_deg: float) -> np.ndarray:
    """Return a unit vector at *angle_deg* from axis 0 inside the (0, 1) plane."""
    theta = np.radians(angle_deg)
    vec = np.zeros(_DIM)
    vec[0], vec[1] = np.cos(theta), np.sin(theta)
    return vec


# (raw angle, trimmed angle or None for a clip that is silent once trimmed,
#  raw samples, trimmed samples)
type _Clip = tuple[float, float | None, int, int]


type _Corpus = tuple[
    SpeakerManifest, dict[str, np.ndarray], dict[str, np.ndarray], dict[str, ClipInfo]
]


def _clip(raw: float, trimmed: float | None, raw_n: int = 24_000, trimmed_n: int = 12_000) -> _Clip:
    return (raw, trimmed, raw_n, 0 if trimmed is None else trimmed_n)


def _short_corpus(
    *,
    genuine_short: list[_Clip],
    impostor_short: list[_Clip],
    replay_short: list[_Clip],
    genuine_long: list[_Clip] | None = None,
) -> _Corpus:
    """Build a short-study manifest with raw/trimmed embeddings at known angles.

    Long references sit at 0 degrees, short references at 40 degrees, so the
    long+short centroid sits at 20 degrees; the fixed threshold (0.4834) is at
    about 58.9 degrees from a centroid.
    """
    samples: list[SpeakerSample] = []
    raw: dict[str, np.ndarray] = {}
    trimmed: dict[str, np.ndarray] = {}
    clips: dict[str, ClipInfo] = {}

    def add_reference(prefix: str, sample_class: str, angle: float) -> None:
        for index in range(6):
            sample = _sample(f"{prefix}-{index}", sample_class, "owner", "quiet-near")
            samples.append(sample)
            raw[sample.sample_id] = _plane(angle)

    def add_probes(prefix: str, sample_class: str, subject: str, rows: list[_Clip]) -> None:
        for index, (raw_angle, trim_angle, raw_n, trim_n) in enumerate(rows):
            condition = CONDITIONS[index % len(CONDITIONS)]
            sample = _sample(f"{prefix}-{index}", sample_class, subject, condition)
            samples.append(sample)
            raw[sample.sample_id] = _plane(raw_angle)
            if trim_angle is not None:
                trimmed[sample.sample_id] = _plane(trim_angle)
            clips[sample.sample_id] = ClipInfo(raw_samples=raw_n, trimmed_samples=trim_n)

    add_reference("ref", "reference", 0.0)
    add_reference("sref", "reference-short", 40.0)
    add_probes("ctl", "genuine", "owner", genuine_long or [_clip(10.0, 10.0, 80_000, 70_000)] * 6)
    add_probes("sgen", "genuine-short", "owner", genuine_short)
    add_probes("simp", "impostor-short", "impostor_a", impostor_short)
    add_probes("srep", "replay-short", "owner", replay_short)
    manifest = SpeakerManifest(schema_version=1, samples=tuple(samples))
    return manifest, raw, trimmed, clips


def _build(corpus: _Corpus, **kw: object) -> ShortStudyReport:
    manifest, raw, trimmed, clips = corpus
    return build_short_study_report(
        manifest, raw, trimmed, clips, model_id=_MODEL, package_version=_PACKAGE, **kw
    )


def _variant_corpus() -> _Corpus:
    """Genuine at 65 deg raw / 50 deg trimmed: each of the four variants is distinguishable.

    - raw / long-only        65 deg from 0   -> d 0.577  rejected
    - raw / long+short       45 deg from 20  -> d 0.293  accepted
    - trimmed / long-only    50 deg from 0   -> d 0.357  accepted
    - trimmed / long+short   30 deg from 20  -> d 0.134  accepted
    """
    return _short_corpus(
        genuine_short=[_clip(65.0, 50.0)] * 4,
        impostor_short=[_clip(100.0, 100.0)] * 6,
        replay_short=[_clip(100.0, 100.0)] * 4,
    )


def _genuine(report: ShortStudyReport, clip: str, references: str) -> VariantCell:
    return report.variant(clip, references).cells["genuine-short"]


def test_the_short_report_uses_the_fixed_threshold_and_never_retunes_it() -> None:
    report = _build(_variant_corpus())

    assert report.threshold == SPEAKER_STUDY_THRESHOLD == 0.4834
    # Data that would move a tuned threshold (every genuine at ~0.58) leaves it alone.
    far = _short_corpus(
        genuine_short=[_clip(65.0, 65.0)] * 4,
        impostor_short=[_clip(100.0, 100.0)] * 6,
        replay_short=[_clip(100.0, 100.0)] * 4,
    )
    assert _build(far).threshold == 0.4834


def test_the_report_holds_the_four_raw_and_trimmed_by_long_and_long_plus_short_variants() -> None:
    report = _build(_variant_corpus())

    assert {(v.clip, v.references) for v in report.variants} == {
        ("raw", "long-only"),
        ("raw", "long+short"),
        ("trimmed", "long-only"),
        ("trimmed", "long+short"),
    }


def test_each_variant_scores_genuine_short_against_its_own_centroid() -> None:
    report = _build(_variant_corpus())

    assert _genuine(report, "raw", "long-only").accepted == 0
    assert _genuine(report, "raw", "long+short").accepted == 4
    assert _genuine(report, "trimmed", "long-only").accepted == 4
    assert _genuine(report, "trimmed", "long+short").accepted == 4
    assert _genuine(report, "raw", "long-only").total == 4


def test_genuine_distances_are_the_cosine_distances_to_the_centroid() -> None:
    cell = _genuine(_build(_variant_corpus()), "raw", "long-only")

    assert cell.distance_min == pytest.approx(1.0 - np.cos(np.radians(65.0)), abs=1e-9)
    assert cell.distance_max == pytest.approx(cell.distance_min)  # four identical clips


def test_the_long_control_is_scored_in_every_variant() -> None:
    report = _build(_variant_corpus())

    for variant in report.variants:
        assert variant.cells["genuine"].total == 6
        assert variant.cells["genuine"].accepted == 6  # control sits at 10 degrees


def test_impostor_accepts_make_a_variant_ineligible() -> None:
    corpus = _short_corpus(
        genuine_short=[_clip(30.0, 30.0)] * 4,
        impostor_short=[_clip(100.0, 30.0)] * 6,  # accepted only once trimmed
        replay_short=[_clip(100.0, 100.0)] * 4,
    )

    report = _build(corpus)

    assert report.variant("raw", "long-only").impostor_accepts == 0
    assert report.variant("raw", "long-only").eligible
    assert report.variant("trimmed", "long-only").impostor_accepts == 6
    assert not report.variant("trimmed", "long-only").eligible
    assert not report.variant("trimmed", "long+short").eligible


def test_replay_accepts_are_counted_at_the_fixed_threshold() -> None:
    corpus = _short_corpus(
        genuine_short=[_clip(30.0, 30.0)] * 4,
        impostor_short=[_clip(100.0, 100.0)] * 6,
        replay_short=[_clip(20.0, 20.0), _clip(20.0, 20.0), _clip(100.0, 100.0)],
    )

    cell = _build(corpus).variant("raw", "long+short").cells["replay-short"]

    assert (cell.total, cell.accepted) == (3, 2)


def test_a_clip_that_is_silent_once_trimmed_is_rejected_and_counted_apart() -> None:
    corpus = _short_corpus(
        genuine_short=[_clip(30.0, 30.0)] * 3 + [_clip(30.0, None)],
        impostor_short=[_clip(100.0, 100.0)] * 6,
        replay_short=[_clip(100.0, 100.0)] * 4,
    )

    report = _build(corpus)

    raw = _genuine(report, "raw", "long-only")
    trimmed = _genuine(report, "trimmed", "long-only")
    assert (raw.total, raw.accepted, raw.silent) == (4, 4, 0)
    assert (trimmed.total, trimmed.accepted, trimmed.silent) == (4, 3, 1)


def test_distance_ranges_are_hidden_for_a_cell_of_fewer_than_three_clips() -> None:
    corpus = _short_corpus(
        genuine_short=[_clip(30.0, 30.0)] * 4,
        impostor_short=[_clip(100.0, 100.0)] * 6,
        replay_short=[_clip(20.0, 20.0)] * 2,
    )

    report = _build(corpus)

    hidden = report.variant("raw", "long-only").cells["replay-short"]
    assert (hidden.distance_min, hidden.distance_mean, hidden.distance_max) == (None, None, None)
    shown = report.variant("raw", "long-only").cells["genuine-short"]
    assert shown.distance_mean is not None


def test_length_buckets_split_genuine_short_by_raw_clip_length() -> None:
    corpus = _short_corpus(
        genuine_short=[
            _clip(30.0, 30.0, 20_000),  # 1.25 s
            _clip(30.0, 30.0, 20_800),  # 1.30 s
            _clip(65.0, 65.0, 28_000),  # 1.75 s - rejected raw/long-only
            _clip(30.0, 30.0, 36_000),  # 2.25 s
            _clip(30.0, 30.0, 48_000),  # 3.00 s - outside the three buckets
        ],
        impostor_short=[_clip(100.0, 100.0)] * 6,
        replay_short=[_clip(100.0, 100.0)] * 4,
    )

    buckets = {
        b.bucket: b
        for b in _build(corpus).variant("raw", "long-only").buckets
        if b.sample_class == "genuine-short"
    }

    assert (buckets["1-1.5 s"].total, buckets["1-1.5 s"].accepted) == (2, 2)
    assert (buckets["1.5-2 s"].total, buckets["1.5-2 s"].accepted) == (1, 0)
    assert (buckets["2-2.5 s"].total, buckets["2-2.5 s"].accepted) == (1, 1)
    assert (buckets["other"].total, buckets["other"].accepted) == (1, 1)


def test_buckets_include_impostor_short_accepts() -> None:
    corpus = _short_corpus(
        genuine_short=[_clip(30.0, 30.0)] * 4,
        impostor_short=[_clip(30.0, 100.0, 20_000)] * 3 + [_clip(100.0, 100.0, 20_000)] * 3,
        replay_short=[_clip(100.0, 100.0)] * 4,
    )

    cell = next(
        b
        for b in _build(corpus).variant("raw", "long-only").buckets
        if b.sample_class == "impostor-short" and b.bucket == "1-1.5 s"
    )

    assert (cell.total, cell.accepted) == (6, 3)


def test_the_silence_share_is_the_fraction_of_raw_samples_the_trim_removes() -> None:
    corpus = _short_corpus(
        genuine_short=[_clip(30.0, 30.0, 20_000, 10_000)] * 3 + [_clip(30.0, None, 20_000)],
        impostor_short=[_clip(100.0, 100.0, 20_000, 15_000)] * 6,
        replay_short=[_clip(100.0, 100.0)] * 4,
    )

    share = {s.sample_class: s for s in _build(corpus).silence}

    assert share["genuine-short"].total == 4
    assert share["genuine-short"].silent_clips == 1
    assert share["genuine-short"].mean_share == pytest.approx((3 * 0.5 + 1.0) / 4)
    assert share["impostor-short"].mean_share == pytest.approx(0.25)
    assert share["genuine"].total == 6


def test_a_missing_trimmed_vector_for_an_audible_clip_is_rejected_without_naming_it() -> None:
    manifest, raw, trimmed, clips = _variant_corpus()
    trimmed.pop("sgen-1")

    with pytest.raises(ValueError, match="re-run embed") as excinfo:
        build_short_study_report(
            manifest, raw, trimmed, clips, model_id=_MODEL, package_version=_PACKAGE
        )

    assert "sgen-1" not in str(excinfo.value)


def test_a_trimmed_vector_for_a_silent_clip_is_inconsistent() -> None:
    manifest, raw, trimmed, clips = _short_corpus(
        genuine_short=[_clip(30.0, None)] * 4,
        impostor_short=[_clip(100.0, 100.0)] * 6,
        replay_short=[_clip(100.0, 100.0)] * 4,
    )
    trimmed["sgen-0"] = _plane(30.0)

    with pytest.raises(ValueError, match="re-run embed"):
        build_short_study_report(
            manifest, raw, trimmed, clips, model_id=_MODEL, package_version=_PACKAGE
        )


def test_missing_clip_lengths_are_rejected() -> None:
    manifest, raw, trimmed, clips = _variant_corpus()
    clips.pop("simp-2")

    with pytest.raises(ValueError, match="re-run embed"):
        build_short_study_report(
            manifest, raw, trimmed, clips, model_id=_MODEL, package_version=_PACKAGE
        )


def test_the_short_report_needs_both_reference_classes() -> None:
    manifest, raw, trimmed, clips = _variant_corpus()
    manifest = SpeakerManifest(
        schema_version=1,
        samples=tuple(s for s in manifest.samples if s.sample_class != "reference-short"),
    )

    with pytest.raises(ValueError, match="reference-short"):
        build_short_study_report(
            manifest, raw, trimmed, clips, model_id=_MODEL, package_version=_PACKAGE
        )


def test_the_limitations_state_the_rule_of_three_and_the_in_sample_caveat() -> None:
    report = _build(_variant_corpus())  # 6 short impostor clips -> 3/6 = 50 %

    text = " ".join(report.limitations)

    assert "rule-of-three" in text
    assert "50.0 %" in text
    assert "in-sample" in text
    assert "0.4834" in text
    assert "voice" in text.lower()


def test_the_rendered_short_report_carries_the_cells_and_no_ids_subjects_or_paths() -> None:
    text = render_short_study_report(_build(_variant_corpus()))

    for needle in ("raw", "trimmed", "long-only", "long+short", "0.4834", "1-1.5 s", "1.5-2 s"):
        assert needle in text
    assert "2-2.5 s" in text
    assert "silence" in text.lower()
    assert "sgen-0" not in text
    assert "impostor_a" not in text
    assert ".wav" not in text


def _counts(impostors: int) -> dict[str, int]:
    return {cls: impostors if cls == "impostor-short" else 1 for cls in SAMPLE_CLASSES}


def test_the_rule_of_three_line_is_conditional_on_zero_observed_accepts() -> None:
    lines = _short_limitations(_counts(18))  # type: ignore[arg-type]  # str keys are classes

    assert (
        "For a variant with 0 observed accepts in 18 short impostor clips, the 95 % "
        "rule-of-three bound on the false-accept rate is about 16.7 %." in lines
    )
    assert not any("0 impostor accepts" in line for line in lines)


def test_the_limitations_warn_that_the_trim_is_an_energy_rule() -> None:
    text = " ".join(_short_limitations(_counts(18)))  # type: ignore[arg-type]  # as above

    assert "click" in text
    assert "background noise" in text
    assert "defeats the trim" in text


def test_the_limitations_say_production_refuses_clips_under_the_minimum_length() -> None:
    text = " ".join(_short_limitations(_counts(18)))  # type: ignore[arg-type]  # as above

    assert "SPEAKER_MIN_VERIFICATION_S" in text
    assert "1.5 s" in text
    assert "never reach the embedder" in text
    assert "length-bucket" in text


def test_the_study_threshold_equals_the_server_setting_default() -> None:
    from server.settings import Settings  # noqa: PLC0415 -- server is only needed by this guard

    field = Settings.model_fields["speaker_authentication_match_threshold"]

    assert field.default == SPEAKER_STUDY_THRESHOLD


def test_the_trim_and_the_capture_guard_share_one_speech_floor() -> None:
    assert speaker_calibration.SPEECH_FRAME_RMS is SPEECH_FRAME_RMS
    assert speaker_calibration_analysis.SPEECH_FRAME_RMS is SPEECH_FRAME_RMS
    assert not hasattr(speaker_calibration, "_MIN_SPEECH_FRAME_RMS")
    assert not hasattr(speaker_calibration_analysis, "TRIM_ACTIVE_RMS")


def test_the_trim_keeps_exactly_what_the_capture_guard_accepts() -> None:
    # amplitude 300 -> frame RMS ~0.0065 (guard accepts); amplitude 100 -> ~0.0022 (guard refuses)
    assert trim_silence(_tone(1.0, amplitude=300), _RATE).size > 0
    assert trim_silence(_tone(1.0, amplitude=100), _RATE).size == 0
