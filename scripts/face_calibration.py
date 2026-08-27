"""face_calibration.py — Plan 0030: measure the real-camera face threshold.

Two layers: pure FAR/FRR math (this module, no I/O) and a capture/corpus CLI
(added in Task 2) that reads Pipec's already-enrolled reference profiles
read-only from `omnibot.db` and appends probe embeddings to an untracked
corpus under `project-history/calibration/`. No frame is ever persisted; no
impostor is ever enrolled.

The distance formula below is deliberately identical to
`server.vision.faces.match_face`'s `L2² / 2` on L2-normalized embeddings,
which is algebraically `1 - dot(a, b)` — this module reproduces the exact
number sqlite-vec's KNN would produce in production, not an approximation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Return the cosine distance between two L2-normalized embeddings.

    Args:
        a: A 512-d L2-normalized face embedding.
        b: A 512-d L2-normalized face embedding.

    Returns:
        `1 - dot(a, b)`, identical to `server.vision.faces.match_face`'s
        `L2² / 2` formula on L2-normalized inputs. `0.0` for identical
        vectors, `1.0` for orthogonal ones.
    """
    return float(1.0 - np.dot(a, b))


def closest_profile_distance(probe: np.ndarray, profiles: list[np.ndarray]) -> float:
    """Return the minimum distance from *probe* to any enrolled profile.

    Mirrors `k = 1` in the real sqlite-vec KNN query — a multi-profile match
    is the closest of the enrolled profiles, never an average.

    Args:
        probe: The embedding being evaluated.
        profiles: One or more enrolled reference embeddings for one person.

    Returns:
        The smallest `cosine_distance` between *probe* and any profile.

    Raises:
        ValueError: If `profiles` is empty.
    """
    if not profiles:
        raise ValueError("profiles must contain at least one enrolled embedding")
    return min(cosine_distance(probe, profile) for profile in profiles)


@dataclass(frozen=True)
class ThresholdResult:
    """False-accept/false-reject counts for one candidate threshold.

    Attributes:
        threshold: The candidate cosine-distance threshold evaluated.
        false_accepts: Impostor samples with distance <= threshold.
        false_rejects: Genuine samples with distance > threshold.
        total_genuine: Total genuine samples evaluated.
        total_impostor: Total impostor samples evaluated.
    """

    threshold: float
    false_accepts: int
    false_rejects: int
    total_genuine: int
    total_impostor: int


def sweep_thresholds(
    genuine_distances: list[float],
    impostor_distances: list[float],
    candidates: list[float],
) -> list[ThresholdResult]:
    """Count false accepts/rejects for each candidate threshold.

    A sample is accepted when its distance is `<= threshold` — the same
    accept/reject boundary `server.vision.faces.match_face` applies (it
    rejects only when `cosine_distance > threshold`).

    Args:
        genuine_distances: Measured distances for Pipec's own probe samples.
        impostor_distances: Measured distances for impostor probe samples.
        candidates: Threshold values to evaluate.

    Returns:
        One `ThresholdResult` per candidate, in the given order.
    """
    return [
        ThresholdResult(
            threshold=candidate,
            false_accepts=sum(1 for d in impostor_distances if d <= candidate),
            false_rejects=sum(1 for d in genuine_distances if d > candidate),
            total_genuine=len(genuine_distances),
            total_impostor=len(impostor_distances),
        )
        for candidate in candidates
    ]


def zero_far_threshold(
    genuine_distances: list[float], impostor_distances: list[float]
) -> tuple[float, float] | None:
    """Return the midpoint threshold and margin at zero false accepts.

    A threshold that admits every genuine sample and rejects every impostor
    sample exists only when the largest genuine distance is strictly smaller
    than the smallest impostor distance. When it exists, this returns the
    midpoint of that gap — not the boundary itself — so the chosen threshold
    keeps a symmetric safety margin against future measurement noise on
    either side, rather than sitting exactly against one edge.

    Args:
        genuine_distances: Measured distances for Pipec's own probe samples.
        impostor_distances: Measured distances for impostor probe samples.

    Returns:
        `(threshold, margin)` where `margin` is the full gap between the
        largest genuine and smallest impostor distance, or `None` when no
        such threshold exists (the two distributions overlap or touch).
    """
    if not genuine_distances or not impostor_distances:
        return None
    largest_genuine = max(genuine_distances)
    smallest_impostor = min(impostor_distances)
    if largest_genuine >= smallest_impostor:
        return None
    margin = smallest_impostor - largest_genuine
    threshold = (largest_genuine + smallest_impostor) / 2
    return threshold, margin
