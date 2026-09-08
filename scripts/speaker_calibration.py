"""speaker_calibration.py - Plan 0047 (PC-3A) speaker-evidence calibration study.

Three isolated layers, built one task at a time:

1. **Pure numeric harness** (this task): L2 normalization, reference centroid,
   cosine distance, deterministic threshold sweep, zero-observed-FAR selection
   and nearest-rank latency percentiles. No audio, model, network or disk.
2. Replaceable evaluation backend and private-corpus CLI - added by Tasks 2-3.

This study measures whether a local CPU speaker embedding can separate the
owner's live voice from consenting live impostors. It never enrolls a
production voiceprint and never makes ``VOICE`` trusted identity evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeakerThresholdResult:
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


def _as_finite_1d(vector: np.ndarray) -> np.ndarray:
    """Return *vector* as a 1-D float64 array, rejecting non-finite values.

    Raises:
        ValueError: If any component is NaN or infinite.
    """
    array = np.asarray(vector, dtype=np.float64).ravel()
    if not np.all(np.isfinite(array)):
        raise ValueError("embedding must contain only finite values")
    return array


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    """Return a finite unit vector pointing the same direction as *vector*.

    Args:
        vector: A finite, non-zero embedding of any dimension.

    Returns:
        The vector scaled to euclidean norm 1.0, as float64.

    Raises:
        ValueError: If *vector* is non-finite or the zero vector.
    """
    array = _as_finite_1d(vector)
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        raise ValueError("cannot normalize the zero vector")
    return array / norm


def reference_centroid(references: Sequence[np.ndarray]) -> np.ndarray:
    """Return the normalized mean of individually normalized reference embeddings.

    Each reference is L2-normalized, the results are averaged, and the mean is
    L2-normalized again so magnitude differences between enrolment samples
    cannot skew the centroid.

    Args:
        references: One or more finite, non-zero reference embeddings, all of
            the same dimension.

    Returns:
        The unit-length centroid embedding, as float64.

    Raises:
        ValueError: If *references* is empty, dimensions differ, or any
            reference is non-finite or zero.
    """
    if len(references) == 0:
        raise ValueError("references must not be empty")
    normalized = [l2_normalize(ref) for ref in references]
    if len({vec.shape for vec in normalized}) != 1:
        raise ValueError("all references must share one embedding dimension")
    return l2_normalize(np.mean(np.vstack(normalized), axis=0))


def cosine_distance(probe: np.ndarray, reference: np.ndarray) -> float:
    """Return one-minus-cosine-similarity between two embeddings.

    Both inputs are L2-normalized internally, so the result is 0.0 for vectors
    of identical direction, 1.0 for orthogonal ones and 2.0 for opposite ones.

    Args:
        probe: A finite, non-zero embedding.
        reference: A finite, non-zero embedding of the same dimension.

    Returns:
        ``1 - dot(unit(probe), unit(reference))``.

    Raises:
        ValueError: If the dimensions differ, or either vector is non-finite
            or zero.
    """
    if _as_finite_1d(probe).shape != _as_finite_1d(reference).shape:
        raise ValueError("probe and reference must share one embedding dimension")
    return float(1.0 - np.dot(l2_normalize(probe), l2_normalize(reference)))


def sweep_speaker_thresholds(
    genuine_distances: Sequence[float],
    impostor_distances: Sequence[float],
    candidates: Sequence[float],
) -> list[SpeakerThresholdResult]:
    """Evaluate FAR and FRR at each candidate threshold.

    A sample is accepted when its distance is ``<= threshold``: an impostor at
    or below the threshold is a false accept; a genuine sample above it is a
    false reject.

    Args:
        genuine_distances: Distances for the owner's own probe samples.
        impostor_distances: Distances for live-impostor probe samples.
        candidates: Threshold values to evaluate, kept in the given order.

    Returns:
        One :class:`SpeakerThresholdResult` per candidate, in input order.

    Raises:
        ValueError: If either distance set is empty.
    """
    if len(genuine_distances) == 0 or len(impostor_distances) == 0:
        raise ValueError("genuine and impostor distance sets must not be empty")
    return [
        SpeakerThresholdResult(
            threshold=candidate,
            false_accepts=sum(1 for d in impostor_distances if d <= candidate),
            false_rejects=sum(1 for d in genuine_distances if d > candidate),
            total_genuine=len(genuine_distances),
            total_impostor=len(impostor_distances),
        )
        for candidate in candidates
    ]


def zero_far_speaker_threshold(
    genuine_distances: Sequence[float],
    impostor_distances: Sequence[float],
) -> tuple[float, float] | None:
    """Return the best zero-observed-FAR threshold and its FRR, or ``None``.

    The safe thresholds are the genuine distances strictly below the closest
    impostor distance. The largest of those minimizes false rejects; when
    several thresholds all reach the same FRR, the lowest is returned so the
    choice sits against the genuine cluster, not against the impostor edge.

    Args:
        genuine_distances: Distances for the owner's own probe samples.
        impostor_distances: Distances for live-impostor probe samples.

    Returns:
        ``(threshold, frr)`` where ``frr`` is false rejects over all genuine
        samples, or ``None`` when either set is empty or the closest sample of
        all is an impostor (the distributions overlap).
    """
    if len(genuine_distances) == 0 or len(impostor_distances) == 0:
        return None
    closest_impostor = min(impostor_distances)
    safe = [d for d in genuine_distances if d < closest_impostor]
    if not safe:
        return None
    threshold = max(safe)
    false_rejects = sum(1 for d in genuine_distances if d > threshold)
    return threshold, false_rejects / len(genuine_distances)


def percentile(values: Sequence[float], quantile: float) -> float:
    """Return the nearest-rank percentile of *values*.

    Nearest-rank: the p-quantile of ``n`` sorted values is the value at
    1-indexed rank ``ceil(p * n)``. Deterministic, no interpolation - the
    frozen latency protocol (Plan 0047 block 5) reports p50 and p95 this way.

    Args:
        values: One or more measurements.
        quantile: A fraction in ``(0, 1]`` (the study uses 0.5 and 0.95).

    Returns:
        The measurement at the nearest rank.

    Raises:
        ValueError: If *values* is empty.
    """
    if len(values) == 0:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return float(ordered[rank - 1])
