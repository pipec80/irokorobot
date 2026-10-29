"""Task 3 (Plan 0075): the voice-rate report over synthetic verdicts.

No audio and no database: the report's pure aggregation and statistics are
tested here; the DB-and-model scoring is Pipec's hardware run.
"""

import json

from scripts import cm4_voice_rate
from scripts.cm4_models import ClipVerdict


def _verdict(
    bucket: str,
    verdict: str,
    phrase_type: str,
    *,
    no_floor_distance: float | None = None,
    no_floor_would_match: bool | None = None,
    duration_s: float = 2.0,
) -> ClipVerdict:
    gate = "ok" if verdict == "verified" else "distance"
    return ClipVerdict(
        duration_s, bucket, gate, verdict, phrase_type, no_floor_distance, no_floor_would_match
    )


def test_build_report_counts_rates_and_hides_distances() -> None:
    scored = [
        ("s1", _verdict("1_5_to_3", "verified", "taste_statement")),
        ("s1", _verdict("1_5_to_3", "unknown", "question")),
        (
            "s2",
            _verdict(
                "lt_1_5",
                "unknown",
                "short_answer",
                no_floor_distance=0.4242,
                no_floor_would_match=True,
                duration_s=0.8,
            ),
        ),
        (
            "s2",
            _verdict(
                "lt_1_5",
                "unknown",
                "short_answer",
                no_floor_distance=0.4242,
                no_floor_would_match=False,
                duration_s=0.8,
            ),
        ),
    ]
    report = cm4_voice_rate.build_report(scored, centroid_source="real_voiceprint")

    assert report["total_clips"] == 4
    assert report["centroid_source"] == "real_voiceprint"
    assert report["by_bucket"]["1_5_to_3"]["verified"] == 1
    assert report["by_bucket"]["lt_1_5"]["unknown"] == 2
    assert report["by_phrase_type"]["short_answer"]["unknown"] == 2
    assert report["per_turn"]["verified"] == 1
    assert report["per_turn"]["n"] == 4
    assert report["per_turn"]["rate"] == 0.25
    assert report["per_conversation"]["conversations"] == 2
    assert report["per_conversation"]["with_at_least_one_verified"] == 1
    assert report["no_floor_diagnostic"]["assessed"] == 2
    assert report["no_floor_diagnostic"]["would_match"] == 1

    text = json.dumps(report)
    assert "0.4242" not in text  # no raw per-clip distance may leak
    assert "s1" not in text  # aggregates only: no session ids
    assert "s2" not in text
