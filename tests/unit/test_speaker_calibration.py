"""Tests for the Plan 0047 speaker-calibration harness.

Task 1 scope: the pure numeric layer — L2 normalization, reference centroid,
cosine distance, deterministic threshold sweep, zero-observed-FAR selection and
nearest-rank latency percentiles.

Task 2 scope: the private-corpus layer — WAV-contract validation, strict
manifest I/O, corpus-rule enforcement, safe path resolution, aggregate-report
invariants and the safe CLI. Every test uses synthetic vectors or generated
silent WAV bytes and never loads a model or touches the network or a microphone.
"""

from __future__ import annotations

import io
import json
import math
from typing import TYPE_CHECKING
import wave

import numpy as np
import pytest

from scripts.speaker_calibration import (
    SpeakerThresholdResult,
    _reject_if_too_short,
    cosine_distance,
    l2_normalize,
    parse_cli_args,
    percentile,
    reference_centroid,
    run_cli,
    sweep_speaker_thresholds,
    zero_far_speaker_threshold,
)
from scripts.speaker_calibration_backend import (
    _MODEL_REVISION,
    _MODEL_SOURCE,
    SpeechBrainEcapaBackend,
    _pcm16_wav_to_float32,
)
from scripts.speaker_calibration_corpus import (
    append_sample_atomic,
    load_manifest,
    render_aggregate_report,
    resolve_corpus_path,
    sha256_of_file,
    validate_corpus,
    validate_wav_bytes,
)
from scripts.speaker_calibration_models import (
    CONDITIONS,
    PHRASE_IDS,
    PHRASE_TEXT,
    AggregateSpeakerReport,
    ConditionSummary,
    SpeakerCliOptions,
    SpeakerEmbeddingBackend,
    SpeakerManifest,
    SpeakerSample,
)

if TYPE_CHECKING:
    from pathlib import Path

_DIM = 192


def _axis_vector(axis: int, *, scale: float = 1.0, dim: int = _DIM) -> np.ndarray:
    """Return a `dim`-d vector of `scale` along `axis` — a synthetic embedding."""
    vec = np.zeros(dim, dtype=np.float32)
    vec[axis] = scale
    return vec


# --- l2_normalize ---------------------------------------------------------


def test_l2_normalize_returns_a_unit_vector() -> None:
    """A non-unit finite vector is scaled to euclidean norm 1.0."""
    normalized = l2_normalize(_axis_vector(0, scale=7.5))

    assert normalized.shape == (_DIM,)
    assert math.isclose(float(np.linalg.norm(normalized)), 1.0, rel_tol=1e-6)


def test_l2_normalize_preserves_direction() -> None:
    """Normalization changes magnitude only, not direction."""
    raw = np.zeros(_DIM, dtype=np.float32)
    raw[0], raw[1] = 3.0, 4.0

    normalized = l2_normalize(raw)

    assert math.isclose(float(normalized[0]), 0.6, rel_tol=1e-6)
    assert math.isclose(float(normalized[1]), 0.8, rel_tol=1e-6)


def test_l2_normalize_rejects_the_zero_vector() -> None:
    """A zero vector has no direction and cannot be normalized."""
    with pytest.raises(ValueError, match="zero"):
        l2_normalize(np.zeros(_DIM, dtype=np.float32))


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_l2_normalize_rejects_non_finite_values(bad: float) -> None:
    """NaN or infinite components make the result undefined."""
    vec = _axis_vector(0)
    vec[5] = bad

    with pytest.raises(ValueError, match="finite"):
        l2_normalize(vec)


# --- reference_centroid --------------------------------------------------


def test_reference_centroid_is_a_normalized_mean() -> None:
    """The centroid of two orthogonal unit vectors is their normalized bisector."""
    centroid = reference_centroid([_axis_vector(0), _axis_vector(1)])

    assert math.isclose(float(np.linalg.norm(centroid)), 1.0, rel_tol=1e-6)
    assert math.isclose(float(centroid[0]), float(centroid[1]), rel_tol=1e-6)


def test_reference_centroid_is_order_independent() -> None:
    """Averaging references must not depend on their order."""
    refs = [_axis_vector(0, scale=2.0), _axis_vector(1), _axis_vector(2, scale=0.5)]

    forward = reference_centroid(refs)
    backward = reference_centroid(list(reversed(refs)))

    assert np.allclose(forward, backward, atol=1e-6)


def test_reference_centroid_normalizes_each_reference_first() -> None:
    """A long and a short vector on the same axis average to that axis, not a skew."""
    centroid = reference_centroid([_axis_vector(0, scale=10.0), _axis_vector(0, scale=0.1)])

    assert math.isclose(float(centroid[0]), 1.0, rel_tol=1e-6)


def test_reference_centroid_rejects_an_empty_sequence() -> None:
    with pytest.raises(ValueError, match="empty"):
        reference_centroid([])


def test_reference_centroid_rejects_mismatched_dimensions() -> None:
    with pytest.raises(ValueError, match="dimension"):
        reference_centroid([_axis_vector(0, dim=_DIM), _axis_vector(0, dim=_DIM - 1)])


# --- cosine_distance ----------------------------------------------------


def test_cosine_distance_is_zero_for_identical_direction() -> None:
    """Same direction, any magnitude → distance 0."""
    assert math.isclose(
        cosine_distance(_axis_vector(0, scale=1.0), _axis_vector(0, scale=9.0)),
        0.0,
        abs_tol=1e-6,
    )


def test_cosine_distance_is_one_for_orthogonal_vectors() -> None:
    assert math.isclose(cosine_distance(_axis_vector(0), _axis_vector(1)), 1.0, abs_tol=1e-6)


def test_cosine_distance_is_two_for_opposite_vectors() -> None:
    assert math.isclose(
        cosine_distance(_axis_vector(0), _axis_vector(0, scale=-1.0)), 2.0, abs_tol=1e-6
    )


def test_cosine_distance_rejects_mismatched_dimensions() -> None:
    with pytest.raises(ValueError, match="dimension"):
        cosine_distance(_axis_vector(0, dim=_DIM), _axis_vector(0, dim=_DIM - 1))


def test_cosine_distance_rejects_a_zero_vector() -> None:
    with pytest.raises(ValueError, match="zero"):
        cosine_distance(_axis_vector(0), np.zeros(_DIM, dtype=np.float32))


def test_cosine_distance_rejects_non_finite_input() -> None:
    bad = _axis_vector(0)
    bad[1] = np.nan
    with pytest.raises(ValueError, match="finite"):
        cosine_distance(bad, _axis_vector(0))


# --- sweep_speaker_thresholds -----------------------------------------


def test_sweep_counts_false_accepts_and_rejects_per_candidate() -> None:
    """Accept is distance <= threshold; genuine above / impostor at-or-below count."""
    genuine = [0.10, 0.20, 0.30]
    impostor = [0.35, 0.40, 0.55]

    results = sweep_speaker_thresholds(genuine, impostor, [0.25, 0.38])

    assert results[0] == SpeakerThresholdResult(
        threshold=0.25, false_accepts=0, false_rejects=1, total_genuine=3, total_impostor=3
    )
    assert results[1] == SpeakerThresholdResult(
        threshold=0.38, false_accepts=1, false_rejects=0, total_genuine=3, total_impostor=3
    )


def test_sweep_boundary_is_inclusive_for_impostors() -> None:
    """An impostor exactly at the threshold is a false accept."""
    results = sweep_speaker_thresholds([0.1], [0.30], [0.30])

    assert results[0].false_accepts == 1


def test_sweep_boundary_is_inclusive_for_genuine() -> None:
    """A genuine sample exactly at the threshold is accepted (not a false reject)."""
    results = sweep_speaker_thresholds([0.30], [0.9], [0.30])

    assert results[0].false_rejects == 0


def test_sweep_preserves_candidate_order() -> None:
    results = sweep_speaker_thresholds([0.1], [0.9], [0.5, 0.2, 0.8])

    assert [r.threshold for r in results] == [0.5, 0.2, 0.8]


def test_sweep_rejects_empty_distance_sets() -> None:
    with pytest.raises(ValueError, match="empty"):
        sweep_speaker_thresholds([], [0.3], [0.2])
    with pytest.raises(ValueError, match="empty"):
        sweep_speaker_thresholds([0.3], [], [0.2])


# --- zero_far_speaker_threshold -------------------------------------


def test_zero_far_selection_minimizes_frr_with_no_false_accepts() -> None:
    """The chosen threshold admits as many genuine samples as possible at FAR 0."""
    genuine = [0.10, 0.20, 0.30]
    impostor = [0.45, 0.50, 0.60]

    result = zero_far_speaker_threshold(genuine, impostor)

    assert result is not None
    threshold, frr = result
    assert threshold == 0.30
    assert frr == 0.0


def test_zero_far_selection_leaves_out_genuine_above_every_safe_threshold() -> None:
    """A genuine outlier past the nearest impostor is a forced false reject."""
    genuine = [0.10, 0.20, 0.80]
    impostor = [0.50, 0.55]

    result = zero_far_speaker_threshold(genuine, impostor)

    assert result is not None
    threshold, frr = result
    assert threshold == 0.20
    assert math.isclose(frr, 1 / 3, rel_tol=1e-9)


def test_zero_far_picks_the_low_end_of_the_safe_gap() -> None:
    """When several thresholds all reach FRR 0, the smallest one is returned."""
    genuine = [0.10, 0.20]
    impostor = [0.90]

    result = zero_far_speaker_threshold(genuine, impostor)

    assert result is not None
    threshold, frr = result
    assert threshold == 0.20
    assert frr == 0.0


def test_zero_far_returns_none_when_the_closest_sample_is_an_impostor() -> None:
    """No genuine sample can be admitted without also admitting an impostor."""
    genuine = [0.30, 0.40]
    impostor = [0.20, 0.60]

    assert zero_far_speaker_threshold(genuine, impostor) is None


def test_zero_far_returns_none_for_empty_input() -> None:
    assert zero_far_speaker_threshold([], [0.3]) is None
    assert zero_far_speaker_threshold([0.3], []) is None


# --- percentile ------------------------------------------------------


def test_percentile_uses_nearest_rank_for_p50() -> None:
    """p50 of 1..30 by nearest rank is the 15th value."""
    values = [float(n) for n in range(1, 31)]

    assert percentile(values, 0.5) == 15.0


def test_percentile_uses_nearest_rank_for_p95() -> None:
    """p95 of 1..30 by nearest rank is the 29th value (ceil(0.95 * 30))."""
    values = [float(n) for n in range(1, 31)]

    assert percentile(values, 0.95) == 29.0


def test_percentile_is_order_independent() -> None:
    values = [5.0, 1.0, 4.0, 2.0, 3.0]

    assert percentile(values, 0.5) == 3.0


def test_percentile_rejects_an_empty_sequence() -> None:
    with pytest.raises(ValueError, match="empty"):
        percentile([], 0.5)


# =====================================================================
# Task 2 — WAV contract, manifest, corpus rules, paths, report, CLI
# =====================================================================


def _wav_bytes(
    *, rate: int = 16_000, channels: int = 1, sampwidth: int = 2, frames: int = 16_000
) -> bytes:
    """Return WAV bytes with the given format — silent PCM payload."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sampwidth)
        handle.setframerate(rate)
        handle.writeframes(b"\x00" * (frames * channels * sampwidth))
    return buf.getvalue()


def _write_sample_wav(corpus_root: Path, name: str) -> Path:
    """Write a contract-valid silent WAV under *corpus_root* and return its path."""
    path = corpus_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_wav_bytes())
    return path


def _sample_row(corpus_root: Path, **overrides: str) -> dict[str, str]:
    """Build one manifest row backed by a real WAV, with a correct SHA-256."""
    row = {
        "sample_id": "s1",
        "subject_id": "owner",
        "sample_class": "genuine",
        "session_id": "probe-01",
        "phrase_id": "phrase-01",
        "condition": "quiet-near",
    }
    row.update(overrides)
    wav_name = overrides.get("wav_path", f"{row['sample_id']}.wav")
    wav_path = _write_sample_wav(corpus_root, wav_name)
    row["wav_path"] = wav_name
    row["sha256"] = sha256_of_file(wav_path)
    return row


def _write_manifest(
    corpus_root: Path, rows: list[dict[str, str]], *, schema_version: int = 1
) -> Path:
    """Serialize *rows* to ``manifest.json`` under *corpus_root*."""
    path = corpus_root / "manifest.json"
    path.write_text(
        json.dumps({"schema_version": schema_version, "samples": rows}), encoding="utf-8"
    )
    return path


def _minimum_corpus_rows(corpus_root: Path) -> list[dict[str, str]]:
    """Build the smallest matrix that passes: 6 reference, 24 genuine, 18 impostor, 6 replay."""
    rows: list[dict[str, str]] = []
    for phrase in PHRASE_IDS:
        for rep in (1, 2):
            rows.append(
                _sample_row(
                    corpus_root,
                    sample_id=f"ref-{phrase}-{rep}",
                    sample_class="reference",
                    session_id="reference-01",
                    phrase_id=phrase,
                    condition="quiet-near",
                )
            )
    for session in ("probe-01", "probe-02"):
        for phrase in PHRASE_IDS:
            for condition in CONDITIONS:
                rows.append(
                    _sample_row(
                        corpus_root,
                        sample_id=f"gen-{session}-{phrase}-{condition}",
                        sample_class="genuine",
                        session_id=session,
                        phrase_id=phrase,
                        condition=condition,
                    )
                )
    for who in ("impostor_a", "impostor_b", "impostor_c"):
        for phrase in PHRASE_IDS:
            for rep in (1, 2):
                rows.append(
                    _sample_row(
                        corpus_root,
                        sample_id=f"imp-{who}-{phrase}-{rep}",
                        subject_id=who,
                        sample_class="impostor",
                        session_id=f"{who}-01",
                        phrase_id=phrase,
                        condition="quiet-near",
                    )
                )
    for condition in ("quiet-near", "quiet-far"):
        for phrase in PHRASE_IDS:
            rows.append(
                _sample_row(
                    corpus_root,
                    sample_id=f"rep-{condition}-{phrase}",
                    sample_class="replay",
                    session_id="replay-01",
                    phrase_id=phrase,
                    condition=condition,
                )
            )
    return rows


def _load_minimum_manifest(corpus_root: Path) -> SpeakerManifest:
    return load_manifest(
        _write_manifest(corpus_root, _minimum_corpus_rows(corpus_root)), corpus_root
    )


# --- validate_wav_bytes ------------------------------------------------


def test_wav_accepts_the_contract_format() -> None:
    """16 kHz, mono, int16 passes without raising."""
    validate_wav_bytes(_wav_bytes())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rate": 44_100},
        {"channels": 2},
        {"sampwidth": 1},
        {"sampwidth": 3},
        {"frames": 0},
    ],
)
def test_wav_rejects_off_contract_audio(kwargs: dict[str, int]) -> None:
    """Wrong rate, channel count, bit depth or an empty payload is rejected."""
    with pytest.raises(ValueError, match="contract"):
        validate_wav_bytes(_wav_bytes(**kwargs))


def test_wav_rejects_non_wav_bytes() -> None:
    with pytest.raises(ValueError, match="contract"):
        validate_wav_bytes(b"not a wav file at all")


# --- load_manifest ---------------------------------------------------


def test_manifest_round_trips_a_valid_file(tmp_path: Path) -> None:
    rows = [_sample_row(tmp_path, sample_id="s1"), _sample_row(tmp_path, sample_id="s2")]
    manifest = load_manifest(_write_manifest(tmp_path, rows), tmp_path)

    assert manifest.schema_version == 1
    assert [s.sample_id for s in manifest.samples] == ["s1", "s2"]


def test_manifest_rejects_an_unknown_schema_version(tmp_path: Path) -> None:
    rows = [_sample_row(tmp_path)]
    with pytest.raises(ValueError, match="schema"):
        load_manifest(_write_manifest(tmp_path, rows, schema_version=2), tmp_path)


def test_manifest_rejects_extra_top_level_fields(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"schema_version": 1, "samples": [], "notes": "extra"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"unknown|extra"):
        load_manifest(path, tmp_path)


def test_manifest_rejects_extra_sample_fields(tmp_path: Path) -> None:
    row = _sample_row(tmp_path)
    row["captured_by"] = "someone"
    with pytest.raises(ValueError, match=r"unknown|extra"):
        load_manifest(_write_manifest(tmp_path, [row]), tmp_path)


def test_manifest_rejects_duplicate_sample_ids(tmp_path: Path) -> None:
    rows = [_sample_row(tmp_path, sample_id="dup"), _sample_row(tmp_path, sample_id="dup")]
    with pytest.raises(ValueError, match="duplicate"):
        load_manifest(_write_manifest(tmp_path, rows), tmp_path)


def test_manifest_rejects_a_sha256_mismatch(tmp_path: Path) -> None:
    row = _sample_row(tmp_path, sample_id="s1")
    (tmp_path / row["wav_path"]).write_bytes(_wav_bytes(frames=8_000))  # file changed after hashing
    with pytest.raises(ValueError, match=r"sha256|hash"):
        load_manifest(_write_manifest(tmp_path, [row]), tmp_path)


# --- resolve_corpus_path / path safety ------------------------------


def test_path_accepts_a_file_inside_the_corpus_root(tmp_path: Path) -> None:
    _write_sample_wav(tmp_path, "sub/s1.wav")
    resolved = resolve_corpus_path(tmp_path, "sub/s1.wav")

    assert resolved.is_relative_to(tmp_path.resolve())


def test_path_rejects_a_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"escape|corpus|outside"):
        resolve_corpus_path(tmp_path / "root", "../secret.wav")


def test_path_rejects_an_absolute_path_outside_the_root(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere" / "s1.wav"
    with pytest.raises(ValueError, match=r"escape|corpus|outside"):
        resolve_corpus_path(tmp_path / "root", str(outside))


def test_path_rejects_a_symlink_escaping_the_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "outside.wav"
    target.write_bytes(_wav_bytes())
    link = root / "link.wav"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    with pytest.raises(ValueError, match=r"symlink|escape|corpus|outside"):
        resolve_corpus_path(root, "link.wav")


# --- append_sample_atomic ------------------------------------------


def test_append_adds_a_row_and_round_trips(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, [_sample_row(tmp_path, sample_id="s1")])
    extra_wav = _write_sample_wav(tmp_path, "s2.wav")

    append_sample_atomic(
        manifest_path,
        tmp_path,
        SpeakerSample(
            sample_id="s2",
            subject_id="owner",
            sample_class="genuine",
            session_id="probe-01",
            phrase_id="phrase-01",
            condition="quiet-near",
            wav_path=extra_wav,
            sha256=sha256_of_file(extra_wav),
        ),
    )

    manifest = load_manifest(manifest_path, tmp_path)
    assert [s.sample_id for s in manifest.samples] == ["s1", "s2"]


def test_append_leaves_the_manifest_intact_when_the_swap_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed atomic replace must not expose a partial manifest."""
    manifest_path = _write_manifest(tmp_path, [_sample_row(tmp_path, sample_id="s1")])
    extra_wav = _write_sample_wav(tmp_path, "s2.wav")

    def _boom(self: object, target: object) -> None:
        raise OSError("simulated crash mid-swap")

    monkeypatch.setattr("pathlib.Path.replace", _boom)

    with pytest.raises(OSError, match="simulated"):
        append_sample_atomic(
            manifest_path,
            tmp_path,
            SpeakerSample(
                sample_id="s2",
                subject_id="owner",
                sample_class="genuine",
                session_id="probe-01",
                phrase_id="phrase-01",
                condition="quiet-near",
                wav_path=extra_wav,
                sha256=sha256_of_file(extra_wav),
            ),
        )

    monkeypatch.undo()
    assert [s.sample_id for s in load_manifest(manifest_path, tmp_path).samples] == ["s1"]


# --- validate_corpus ------------------------------------------------


def test_corpus_accepts_the_minimum_matrix(tmp_path: Path) -> None:
    validate_corpus(_load_minimum_manifest(tmp_path))


def test_corpus_rejects_an_unknown_condition_label(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    rows[0]["condition"] = "quiet-medium"
    with pytest.raises(ValueError, match="condition"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_rejects_an_unknown_phrase_id(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    rows[0]["phrase_id"] = "phrase-99"
    with pytest.raises(ValueError, match="phrase"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_requires_owner_subject_for_genuine(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    genuine = next(r for r in rows if r["sample_class"] == "genuine")
    genuine["subject_id"] = "impostor_a"
    with pytest.raises(ValueError, match=r"owner|subject"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_requires_an_impostor_pseudonym_for_impostors(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    impostor = next(r for r in rows if r["sample_class"] == "impostor")
    impostor["subject_id"] = "owner"
    with pytest.raises(ValueError, match=r"impostor|subject"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_requires_reference_samples_to_be_quiet_near(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    reference = next(r for r in rows if r["sample_class"] == "reference")
    reference["condition"] = "quiet-far"
    with pytest.raises(ValueError, match="reference"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_requires_one_dedicated_reference_session(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    references = [r for r in rows if r["sample_class"] == "reference"]
    references[0]["session_id"] = "reference-02"
    with pytest.raises(ValueError, match=r"reference|session"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_rejects_reference_and_probe_session_leakage(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    for row in rows:
        if row["sample_class"] == "reference":
            row["session_id"] = "probe-01"
    with pytest.raises(ValueError, match="session"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_rejects_a_class_below_its_minimum(tmp_path: Path) -> None:
    rows = [r for r in _minimum_corpus_rows(tmp_path) if r["sample_class"] != "replay"]
    rows.append(
        _sample_row(tmp_path, sample_id="rep-1", sample_class="replay", session_id="replay-01")
    )
    with pytest.raises(ValueError, match=r"replay|minimum|at least"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_rejects_a_reused_wav_path(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    rows[1]["wav_path"] = rows[0]["wav_path"]
    rows[1]["sha256"] = rows[0]["sha256"]
    with pytest.raises(ValueError, match=r"wav|reuse|distinct|duplicate"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_requires_genuine_to_span_all_four_conditions(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    for row in rows:
        if row["sample_class"] == "genuine" and row["condition"] == "background-far":
            row["condition"] = "quiet-near"
    with pytest.raises(ValueError, match=r"condition|genuine"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


def test_corpus_requires_at_least_three_impostor_subjects(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    for row in rows:
        if row["sample_class"] == "impostor" and row["subject_id"] == "impostor_c":
            row["subject_id"] = "impostor_a"
    with pytest.raises(ValueError, match=r"impostor|adult|three"):
        validate_corpus(load_manifest(_write_manifest(tmp_path, rows), tmp_path))


# --- AggregateSpeakerReport invariants -----------------------------


def _condition_summary() -> ConditionSummary:
    return ConditionSummary(
        sample_class="genuine",
        condition="quiet-near",
        total=6,
        accepted=6,
        rejected=0,
        distance_min=0.05,
        distance_max=0.20,
        distance_mean=0.12,
    )


def _full_counts() -> dict[str, int]:
    return {"reference": 6, "genuine": 24, "impostor": 18, "replay": 6}


def test_report_backend_latency_permits_no_corpus_or_rates() -> None:
    report = AggregateSpeakerReport(
        model_id="ecapa@0f99f2d0",
        package_version="speechbrain==1.1.1",
        sample_counts={},
        selected_threshold=None,
        live_false_accepts=None,
        live_far=None,
        genuine_false_rejects=None,
        genuine_frr=None,
        replay_accepts=None,
        replay_accept_rate=None,
        latency_p50_ms=410.0,
        latency_p95_ms=620.0,
        by_condition={},
        outcome="fail_backend_latency",
        limitations=("measured p95 620 ms exceeds the 500 ms budget",),
    )
    assert "fail_backend_latency" in render_aggregate_report(report)


def test_report_backend_latency_rejects_a_populated_rate() -> None:
    with pytest.raises(ValueError, match="fail_backend_latency"):
        AggregateSpeakerReport(
            model_id="m",
            package_version="v",
            sample_counts={},
            selected_threshold=None,
            live_false_accepts=0,
            live_far=0.0,
            genuine_false_rejects=None,
            genuine_frr=None,
            replay_accepts=None,
            replay_accept_rate=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            by_condition={},
            outcome="fail_backend_latency",
            limitations=("x",),
        )


def _measurement_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "model_id": "ecapa@0f99f2d0",
        "package_version": "speechbrain==1.1.1",
        "sample_counts": _full_counts(),
        "selected_threshold": 0.32,
        "live_false_accepts": 0,
        "live_far": 0.0,
        "genuine_false_rejects": 1,
        "genuine_frr": 0.04,
        "replay_accepts": 2,
        "replay_accept_rate": 0.33,
        "latency_p50_ms": 300.0,
        "latency_p95_ms": 420.0,
        "by_condition": {"genuine/quiet-near": _condition_summary()},
        "outcome": "provisional_pass",
        "limitations": ("zero-FAR on 18 impostor samples is provisional, not population proof",),
    }
    base.update(overrides)
    return base


def test_report_provisional_pass_is_valid_with_zero_false_accepts_and_a_threshold() -> None:
    rendered = render_aggregate_report(AggregateSpeakerReport(**_measurement_kwargs()))  # type: ignore[arg-type]

    assert "provisional_pass" in rendered
    assert "quiet-near" in rendered
    assert "owner" not in rendered
    assert ".wav" not in rendered
    assert "sha256" not in rendered


def test_report_provisional_pass_requires_a_selected_threshold() -> None:
    with pytest.raises(ValueError, match="threshold"):
        AggregateSpeakerReport(**_measurement_kwargs(selected_threshold=None))  # type: ignore[arg-type]


def test_report_provisional_pass_requires_zero_live_false_accepts() -> None:
    with pytest.raises(ValueError, match="false accept"):
        AggregateSpeakerReport(**_measurement_kwargs(live_false_accepts=1, live_far=0.05))  # type: ignore[arg-type]


def test_report_distance_overlap_forbids_a_selected_threshold() -> None:
    with pytest.raises(ValueError, match="threshold"):
        AggregateSpeakerReport(
            **_measurement_kwargs(outcome="fail_distance_overlap", selected_threshold=0.3)  # type: ignore[arg-type]
        )


def test_report_always_requires_model_identity_and_limitations() -> None:
    with pytest.raises(ValueError, match="limitation"):
        AggregateSpeakerReport(**_measurement_kwargs(limitations=()))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=r"model_id|package_version|mandatory"):
        AggregateSpeakerReport(**_measurement_kwargs(model_id=""))  # type: ignore[arg-type]


# --- parse_cli_args ------------------------------------------------


def test_cli_capture_requires_every_metadata_flag() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["capture", "--class", "reference", "--subject", "owner"])


def test_cli_capture_parses_a_complete_invocation() -> None:
    options = parse_cli_args(
        [
            "capture",
            "--class",
            "reference",
            "--subject",
            "owner",
            "--session",
            "reference-01",
            "--phrase",
            "phrase-01",
            "--condition",
            "quiet-near",
        ]
    )

    assert options.action == "capture"
    assert options.sample_class == "reference"
    assert options.phrase_id == "phrase-01"


def test_cli_non_capture_actions_reject_capture_flags() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["validate", "--class", "genuine"])


def test_cli_validate_needs_no_flags() -> None:
    assert parse_cli_args(["validate"]).action == "validate"


# --- run_cli ------------------------------------------------------


def _capture_opts(tmp_path: Path) -> SpeakerCliOptions:
    return parse_cli_args(
        [
            "capture",
            "--corpus-root",
            str(tmp_path),
            "--class",
            "genuine",
            "--subject",
            "owner",
            "--session",
            "probe-09",
            "--phrase",
            "phrase-01",
            "--condition",
            "quiet-near",
        ]
    )


def test_run_cli_validate_fails_cleanly_on_a_missing_manifest(tmp_path: Path) -> None:
    exit_code = run_cli(parse_cli_args(["validate", "--corpus-root", str(tmp_path)]))

    assert exit_code != 0


def test_run_cli_validate_passes_on_a_minimum_corpus(tmp_path: Path) -> None:
    _write_manifest(tmp_path, _minimum_corpus_rows(tmp_path))

    assert run_cli(parse_cli_args(["validate", "--corpus-root", str(tmp_path)])) == 0


def test_run_cli_capture_writes_only_under_the_corpus_root(tmp_path: Path) -> None:
    exit_code = run_cli(_capture_opts(tmp_path), capture_audio=_wav_bytes)

    assert exit_code == 0
    written = list(tmp_path.rglob("*.wav"))
    assert written
    assert all(p.resolve().is_relative_to(tmp_path.resolve()) for p in written)
    assert (tmp_path / "manifest.json").exists()


def test_run_cli_capture_failure_adds_no_manifest_row(tmp_path: Path) -> None:
    def _explode() -> bytes:
        raise RuntimeError("microphone unavailable")

    exit_code = run_cli(_capture_opts(tmp_path), capture_audio=_explode)

    assert exit_code != 0
    assert not (tmp_path / "manifest.json").exists()


def test_phrase_text_holds_the_three_frozen_phrases() -> None:
    assert set(PHRASE_TEXT) == set(PHRASE_IDS)
    assert PHRASE_TEXT["phrase-01"] == "La lluvia cae despacio sobre el tejado de la casa"


def test_reject_if_too_short_blocks_a_clipped_capture() -> None:
    with pytest.raises(ValueError, match="steady pace"):
        _reject_if_too_short(_wav_bytes(frames=16_000))  # 1.0 s


def test_reject_if_too_short_allows_a_full_phrase_length() -> None:
    _reject_if_too_short(_wav_bytes(frames=16_000 * 4))  # 4.0 s — no raise


def test_run_cli_capture_with_injected_recorder_skips_the_human_announce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_phrase_id: str) -> None:
        raise AssertionError("announce/countdown must not run when a recorder is injected")

    monkeypatch.setattr("scripts.speaker_calibration._announce_capture", _boom)

    assert run_cli(_capture_opts(tmp_path), capture_audio=_wav_bytes) == 0


def test_run_cli_analyze_never_invokes_the_capture_boundary(tmp_path: Path) -> None:
    def _forbidden() -> bytes:
        raise AssertionError("analyze must never open the microphone")

    run_cli(parse_cli_args(["analyze", "--corpus-root", str(tmp_path)]), capture_audio=_forbidden)


def test_run_cli_embed_without_a_backend_fails(tmp_path: Path) -> None:
    _write_manifest(tmp_path, _minimum_corpus_rows(tmp_path))

    assert run_cli(parse_cli_args(["embed", "--corpus-root", str(tmp_path)]), backend=None) != 0


class _FakeBackend:
    """Typed test double for ``SpeakerEmbeddingBackend`` — no model, no audio."""

    model_id = "fake-ecapa@test"

    def embed_wav(self, wav_bytes: bytes) -> np.ndarray:
        seed = len(wav_bytes) % 7 + 1
        return np.full(192, float(seed), dtype=np.float32)


def test_run_cli_embed_writes_one_vector_per_sample_via_the_protocol(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    _write_manifest(tmp_path, rows)

    exit_code = run_cli(
        parse_cli_args(["embed", "--corpus-root", str(tmp_path)]), backend=_FakeBackend()
    )

    assert exit_code == 0
    with np.load(tmp_path / "embeddings.npz") as stored:
        assert sorted(stored.files) == sorted(r["sample_id"] for r in rows)
        assert all(stored[name].shape == (192,) for name in stored.files)


def test_run_cli_embed_rejects_a_wrong_dimension_embedding(tmp_path: Path) -> None:
    _write_manifest(tmp_path, _minimum_corpus_rows(tmp_path))

    class _BadBackend:
        model_id = "bad@test"

        def embed_wav(self, wav_bytes: bytes) -> np.ndarray:  # noqa: ARG002
            return np.ones(64, dtype=np.float32)

    exit_code = run_cli(
        parse_cli_args(["embed", "--corpus-root", str(tmp_path)]), backend=_BadBackend()
    )

    assert exit_code != 0
    assert not (tmp_path / "embeddings.npz").exists()


def test_run_cli_analyze_refuses_to_overwrite_its_output(tmp_path: Path) -> None:
    output = tmp_path / "aggregate-report.md"
    output.write_text("previous run", encoding="utf-8")
    _write_manifest(tmp_path, _minimum_corpus_rows(tmp_path))

    exit_code = run_cli(
        parse_cli_args(["analyze", "--corpus-root", str(tmp_path), "--output", str(output)])
    )

    assert exit_code != 0
    assert output.read_text(encoding="utf-8") == "previous run"


def test_run_cli_cleanup_requires_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(tmp_path, [_sample_row(tmp_path, sample_id="s1")])
    monkeypatch.setattr("builtins.input", lambda *_: "no")

    exit_code = run_cli(parse_cli_args(["cleanup", "--corpus-root", str(tmp_path)]))

    assert exit_code != 0
    assert (tmp_path / "manifest.json").exists()


# =====================================================================
# Task 3 — frozen SpeechBrain ECAPA backend (fake-encoder driven)
# =====================================================================


def _tone_wav_bytes(*, rate: int = 16_000, seconds: float = 1.0, amplitude: int = 12_000) -> bytes:
    """Return a non-biometric sine-tone WAV — 16 kHz, mono, int16."""
    step = np.arange(int(rate * seconds), dtype=np.float32) / rate
    samples = (np.sin(2.0 * np.pi * 220.0 * step) * amplitude).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return buf.getvalue()


class _FakeEncoder:
    """Stand-in for ``EncoderClassifier`` — returns a fixed ``(1, 1, 192)`` tensor."""

    def __init__(self, vector: np.ndarray | None = None) -> None:
        self._vector = vector if vector is not None else np.arange(1, 193, dtype=np.float32)

    def encode_batch(
        self,
        wavs: object,  # noqa: ARG002 -- fake ignores the tensor
        wav_lens: object = None,  # noqa: ARG002
        normalize: bool = False,  # noqa: ARG002
    ) -> object:
        import torch  # noqa: PLC0415 -- lazy: keeps torch out of unrelated unit-test collection

        return torch.from_numpy(self._vector).reshape(1, 1, -1)


def test_backend_model_id_pins_frozen_source_and_revision() -> None:
    backend = SpeechBrainEcapaBackend(_FakeEncoder())

    assert _MODEL_SOURCE in backend.model_id
    assert _MODEL_REVISION in backend.model_id
    assert len(_MODEL_REVISION) == 40


def test_backend_pcm16_to_float32_scales_by_full_scale() -> None:
    wav = _tone_wav_bytes(seconds=0.5)

    wave_f32 = _pcm16_wav_to_float32(wav)

    assert wave_f32.dtype == np.float32
    assert wave_f32.max() <= 1.0
    assert wave_f32.min() >= -1.0
    assert wave_f32.shape == (8_000,)


def test_backend_embed_wav_returns_finite_192d_vector() -> None:
    backend = SpeechBrainEcapaBackend(_FakeEncoder())

    vector = backend.embed_wav(_tone_wav_bytes(seconds=1.0))

    assert vector.shape == (192,)
    assert np.all(np.isfinite(vector))


def test_backend_embed_wav_rejects_non_contract_wav() -> None:
    off_contract = _wav_bytes(rate=8_000)

    with pytest.raises(ValueError, match="audio contract"):
        SpeechBrainEcapaBackend(_FakeEncoder()).embed_wav(off_contract)


def test_backend_embed_wav_rejects_wrong_dimension() -> None:
    backend = SpeechBrainEcapaBackend(_FakeEncoder(np.ones(64, dtype=np.float32)))

    with pytest.raises(ValueError, match="192"):
        backend.embed_wav(_tone_wav_bytes())


def test_backend_embed_wav_rejects_all_zero_vector() -> None:
    backend = SpeechBrainEcapaBackend(_FakeEncoder(np.zeros(192, dtype=np.float32)))

    with pytest.raises(ValueError, match="zero"):
        backend.embed_wav(_tone_wav_bytes())


def test_backend_embed_wav_rejects_non_finite_vector() -> None:
    bad = np.arange(1, 193, dtype=np.float32)
    bad[7] = np.nan
    backend = SpeechBrainEcapaBackend(_FakeEncoder(bad))

    with pytest.raises(ValueError, match="finite"):
        backend.embed_wav(_tone_wav_bytes())


def test_backend_satisfies_the_frozen_protocol() -> None:
    backend: SpeakerEmbeddingBackend = SpeechBrainEcapaBackend(_FakeEncoder())

    assert isinstance(backend.model_id, str)


def test_run_cli_embed_accepts_the_concrete_backend(tmp_path: Path) -> None:
    rows = _minimum_corpus_rows(tmp_path)
    _write_manifest(tmp_path, rows)

    exit_code = run_cli(
        parse_cli_args(["embed", "--corpus-root", str(tmp_path)]),
        backend=SpeechBrainEcapaBackend(_FakeEncoder()),
    )

    assert exit_code == 0
    with np.load(tmp_path / "embeddings.npz") as stored:
        assert all(stored[name].shape == (192,) for name in stored.files)


def test_run_cli_model_contract_dispatches_to_the_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "scripts.speaker_calibration_backend.run_model_contract",
        lambda: calls.append("ran") or 0,
    )

    exit_code = run_cli(parse_cli_args(["model-contract"]))

    assert exit_code == 0
    assert calls == ["ran"]


def test_run_cli_model_contract_propagates_backend_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.speaker_calibration_backend.run_model_contract",
        lambda: 1,
    )

    assert run_cli(parse_cli_args(["model-contract"])) != 0
