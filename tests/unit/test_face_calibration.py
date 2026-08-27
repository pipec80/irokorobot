"""Tests for the Plan 0030 face-calibration math — pure, no I/O, no model."""

import numpy as np
import pytest

from scripts.face_calibration import (
    ThresholdResult,
    closest_profile_distance,
    cosine_distance,
    sweep_thresholds,
    zero_far_threshold,
)


def _unit_vector(axis: int) -> np.ndarray:
    """Return a 512-d unit vector along *axis* — a synthetic 'face'."""
    vec = np.zeros(512, dtype=np.float32)
    vec[axis] = 1.0
    return vec


def test_cosine_distance_matches_the_production_formula() -> None:
    """1 - dot(a, b) must equal faces.py's L2² / 2 formula on the same inputs."""
    a = _unit_vector(0)
    near = np.zeros(512, dtype=np.float32)
    near[0], near[1] = 0.8, 0.6

    distance = cosine_distance(a, near)

    l2_squared_over_2 = float(np.linalg.norm(a - near) ** 2) / 2
    assert distance == pytest.approx(l2_squared_over_2, abs=1e-6)
    assert distance == pytest.approx(0.2, abs=1e-6)


def test_cosine_distance_is_zero_for_identical_vectors() -> None:
    """The same embedding compared to itself has zero distance."""
    a = _unit_vector(0)

    assert cosine_distance(a, a) == pytest.approx(0.0, abs=1e-6)


def test_cosine_distance_is_one_for_orthogonal_vectors() -> None:
    """Orthogonal unit vectors (cos similarity 0) are distance 1.0 apart."""
    assert cosine_distance(_unit_vector(0), _unit_vector(1)) == pytest.approx(1.0, abs=1e-6)


def test_closest_profile_distance_is_the_minimum_over_profiles() -> None:
    """Multi-profile matching takes the minimum distance, mirroring k=1 KNN."""
    probe = _unit_vector(0)
    near = np.zeros(512, dtype=np.float32)
    near[0], near[1] = 0.8, 0.6
    far = _unit_vector(1)
    profiles = [far, near, _unit_vector(2)]

    distance = closest_profile_distance(probe, profiles)

    assert distance == pytest.approx(cosine_distance(probe, near), abs=1e-6)


def test_closest_profile_distance_with_a_single_profile() -> None:
    """A one-profile policy still uses the same minimum-over-set logic."""
    probe = _unit_vector(0)

    assert closest_profile_distance(probe, [probe]) == pytest.approx(0.0, abs=1e-6)


def test_sweep_thresholds_counts_false_accepts_and_false_rejects() -> None:
    """A threshold accepts distance <= threshold — mirroring faces.py's `> threshold` reject."""
    genuine = [0.1, 0.2, 0.35]
    impostor = [0.3, 0.5, 0.6]

    results = sweep_thresholds(genuine, impostor, candidates=[0.25, 0.4])

    by_threshold = {r.threshold: r for r in results}
    # threshold 0.25: genuine 0.35 rejected (FR=1); impostor none <= 0.25 (FA=0)
    assert by_threshold[0.25] == ThresholdResult(
        threshold=0.25, false_accepts=0, false_rejects=1, total_genuine=3, total_impostor=3
    )
    # threshold 0.4: all genuine accepted (FR=0); impostor 0.3 <= 0.4 accepted (FA=1)
    assert by_threshold[0.4] == ThresholdResult(
        threshold=0.4, false_accepts=1, false_rejects=0, total_genuine=3, total_impostor=3
    )


def test_sweep_thresholds_handles_empty_impostor_set() -> None:
    """No impostor samples yet must not crash the sweep — FAR is simply zero."""
    results = sweep_thresholds([0.1, 0.2], [], candidates=[0.3])

    assert results == [
        ThresholdResult(
            threshold=0.3, false_accepts=0, false_rejects=0, total_genuine=2, total_impostor=0
        )
    ]


def test_zero_far_threshold_returns_none_when_distances_overlap() -> None:
    """A genuine sample farther than an impostor sample means no threshold separates them."""
    genuine = [0.1, 0.5]  # 0.5 overlaps with the impostor below
    impostor = [0.3, 0.6]

    assert zero_far_threshold(genuine, impostor) is None


def test_zero_far_threshold_returns_the_midpoint_and_margin_when_separable() -> None:
    """A clean separation reports the midpoint threshold and the full gap as margin."""
    genuine = [0.1, 0.2, 0.25]
    impostor = [0.45, 0.5, 0.6]

    result = zero_far_threshold(genuine, impostor)

    assert result is not None
    threshold, margin = result
    assert threshold == pytest.approx(0.35, abs=1e-6)  # midpoint of 0.25 and 0.45
    assert margin == pytest.approx(0.2, abs=1e-6)  # 0.45 - 0.25


def test_zero_far_threshold_treats_equal_boundary_as_overlap() -> None:
    """A genuine and impostor distance tied exactly is not a safe separation."""
    assert zero_far_threshold([0.1, 0.3], [0.3, 0.5]) is None
