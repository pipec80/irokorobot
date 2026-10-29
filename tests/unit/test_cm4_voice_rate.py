"""Task 1 (Plan 0075): the verified-voice verdict harness.

Pure replay of the production voice pipeline over synthetic WAVs and fake
embed/match/count seams — no microphone, no model, no network.

Audio contract of every WAV built here: WAV, 16 000 Hz, mono, int16.
"""

import asyncio
import io
import wave

import numpy as np
from server.exceptions import AudioContractError
from server.voice.voiceprints import CentroidMatch

from scripts import cm4_voice_rate
from scripts.cm4_models import ClipVerdict, CountTable

_RATE = 16_000


def _wav(duration_s: float, *, loud: bool) -> bytes:
    """Build a contract WAV of *duration_s*; a 200 Hz tone when *loud*, else silence."""
    n = max(1, int(duration_s * _RATE))
    if loud:
        t = np.arange(n) / _RATE
        samples = (10_000 * np.sin(2 * np.pi * 200 * t)).astype(np.int16)
    else:
        samples = np.zeros(n, dtype=np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_RATE)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def _fake_count(value: int):
    async def count(_person_id: int, _model_id: str) -> int:
        return value

    return count


def _fake_embed():
    async def embed(_wav_bytes: bytes) -> np.ndarray:
        return np.ones(192, dtype=np.float32)

    return embed


def _fake_match(distance: float | None, references: int = 3):
    async def match(
        _person_id: int, _embedding: np.ndarray, _model_id: str
    ) -> CentroidMatch | None:
        if distance is None:
            return None
        return CentroidMatch(distance=distance, reference_count=references)

    return match


def _score(wav_bytes: bytes, phrase_type: str, *, refs: int, distance: float | None) -> ClipVerdict:
    return asyncio.run(
        cm4_voice_rate.score_clip(
            wav_bytes,
            phrase_type,
            owner_person_id=1,
            model_id="m@rev",
            embed=_fake_embed(),
            match=_fake_match(distance),
            count_refs=_fake_count(refs),
        )
    )


def test_duration_bucket_boundaries() -> None:
    assert cm4_voice_rate.duration_bucket(1.49) == "lt_1_5"
    assert cm4_voice_rate.duration_bucket(1.5) == "1_5_to_3"
    assert cm4_voice_rate.duration_bucket(3.0) == "1_5_to_3"
    assert cm4_voice_rate.duration_bucket(3.01) == "gt_3"


def test_sub_1_5_loud_clip_is_duration_gated_with_no_floor_diagnostic() -> None:
    verdict = _score(_wav(0.8, loud=True), "short_answer", refs=3, distance=0.30)
    assert verdict.bucket == "lt_1_5"
    assert verdict.gate == "duration"
    assert verdict.verdict == "unknown"
    assert verdict.no_floor_distance == 0.30
    assert verdict.no_floor_would_match is True


def test_silent_sub_1_5_clip_is_energy_gated_without_no_floor() -> None:
    verdict = _score(_wav(0.8, loud=False), "other", refs=3, distance=0.30)
    assert verdict.bucket == "lt_1_5"
    assert verdict.gate == "energy"
    assert verdict.verdict == "unknown"
    assert verdict.no_floor_distance is None
    assert verdict.no_floor_would_match is None


def test_clip_with_distance_under_threshold_verifies() -> None:
    verdict = _score(_wav(2.0, loud=True), "taste_statement", refs=3, distance=0.30)
    assert verdict.bucket == "1_5_to_3"
    assert verdict.gate == "ok"
    assert verdict.verdict == "verified"
    assert verdict.no_floor_distance is None


def test_clip_with_distance_over_threshold_is_distance_gated() -> None:
    verdict = _score(_wav(2.0, loud=True), "question", refs=3, distance=0.60)
    assert verdict.gate == "distance"
    assert verdict.verdict == "unknown"


def test_too_few_references_is_reference_gated() -> None:
    verdict = _score(_wav(2.0, loud=True), "command", refs=2, distance=0.30)
    assert verdict.gate == "references"
    assert verdict.verdict == "unknown"


def test_clip_the_backend_rejects_is_unavailable_not_a_crash() -> None:
    async def rejecting_embed(_wav_bytes: bytes) -> np.ndarray:
        raise AudioContractError("Audio is 30.5s - max 30.0s")

    verdict = asyncio.run(
        cm4_voice_rate.score_clip(
            _wav(2.0, loud=True),
            "other",
            owner_person_id=1,
            model_id="m@rev",
            embed=rejecting_embed,
            match=_fake_match(0.30),
            count_refs=_fake_count(3),
        )
    )
    assert verdict.verdict == "unavailable"
    assert verdict.gate == "unavailable"


def test_aggregate_counts_by_bucket_and_type_without_distances() -> None:
    verdicts = [
        ClipVerdict(2.0, "1_5_to_3", "ok", "verified", "taste_statement", None, None),
        ClipVerdict(2.0, "1_5_to_3", "distance", "unknown", "question", None, None),
        ClipVerdict(0.8, "lt_1_5", "duration", "unknown", "short_answer", 0.30, True),
        ClipVerdict(0.8, "lt_1_5", "duration", "unknown", "short_answer", 0.60, False),
    ]
    table = cm4_voice_rate.aggregate(verdicts)
    assert isinstance(table, CountTable)
    assert table.total == 4
    assert table.by_bucket["1_5_to_3"]["verified"] == 1
    assert table.by_bucket["1_5_to_3"]["unknown"] == 1
    assert table.by_bucket["lt_1_5"]["unknown"] == 2
    assert table.by_phrase_type["short_answer"]["unknown"] == 2
    assert table.no_floor_assessed == 2
    assert table.no_floor_would_match == 1
