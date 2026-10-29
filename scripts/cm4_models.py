"""Dataclasses shared by the Plan 0075 CM-4 pre-measurement instruments.

No I/O, no audio, no model: only the small frozen records the voice-rate
harness and its report pass around. Every tracked output built from these
carries counts and rates only — never a transcript, a phrase or a per-clip
distance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

type DurationBucket = Literal["lt_1_5", "1_5_to_3", "gt_3"]


@dataclass(frozen=True)
class ClipVerdict:
    """The production voice verdict for one corpus clip.

    Attributes:
        duration_s: Decoded clip length in seconds.
        bucket: Which duration bucket the clip falls in.
        gate: The first failed gate name (``references``, ``energy``,
            ``duration``, ``distance``) or ``ok`` when every gate passed.
        verdict: The ``SpeakerVerdict`` value (``verified``/``unknown``/
            ``unavailable``).
        phrase_type: Pipec's coarse annotation (one of the five classes).
        no_floor_distance: For a sub-1.5 s clip only, the owner distance if the
            duration floor did not exist; ``None`` otherwise (a diagnostic, not
            a proposal).
        no_floor_would_match: Whether that diagnostic distance is within the
            fixed threshold; ``None`` when no diagnostic distance was computed.
    """

    duration_s: float
    bucket: DurationBucket
    gate: str
    verdict: str
    phrase_type: str
    no_floor_distance: float | None
    no_floor_would_match: bool | None


@dataclass(frozen=True)
class CountTable:
    """Pure counts aggregated from a sequence of :class:`ClipVerdict`.

    Attributes:
        by_bucket: ``bucket -> verdict -> count``.
        by_phrase_type: ``phrase_type -> verdict -> count``.
        no_floor_assessed: Sub-1.5 s clips for which a no-floor distance was
            computed.
        no_floor_would_match: Of those, how many would have matched the owner.
        total: Total clips counted.
    """

    by_bucket: dict[str, dict[str, int]]
    by_phrase_type: dict[str, dict[str, int]]
    no_floor_assessed: int
    no_floor_would_match: int
    total: int
