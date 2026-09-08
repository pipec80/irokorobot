"""Tests for the Plan 0047 speaker-calibration harness.

Task 1 scope: the pure numeric layer only — L2 normalization, reference
centroid, cosine distance, deterministic threshold sweep, zero-observed-FAR
selection and nearest-rank latency percentiles. Every test uses synthetic
vectors and never loads a model or touches audio, the network or disk.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.speaker_calibration import (
    SpeakerThresholdResult,
    cosine_distance,
    l2_normalize,
    percentile,
    reference_centroid,
    sweep_speaker_thresholds,
    zero_far_speaker_threshold,
)

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
