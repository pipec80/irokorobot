"""Task 2 (Plan 0075): the private CM-4 conversation corpus tool.

Synthetic signals, a fake VAD and a fake recorder: no microphone, no private
audio. Audio contract of every WAV: WAV, 16 000 Hz, mono, int16.
"""

from pathlib import Path
import wave

import numpy as np
import pytest
from robot.audio_capture import SegmentationPolicy

from scripts import cm4_corpus
from scripts.cm4_corpus import ClipRecord

_RATE = 16_000
_POLICY = SegmentationPolicy(preroll_ms=400, close_silence_ms=1200, upload_tail_ms=300)


class _LoudVad:
    def detect(self, chunk: np.ndarray) -> bool:
        return bool(np.abs(chunk).max() > 0)


def _segment(seconds: float, *, loud: bool) -> np.ndarray:
    n = int(seconds * _RATE)
    if loud:
        t = np.arange(n) / _RATE
        return (10_000 * np.sin(2 * np.pi * 200 * t)).astype(np.int16)
    return np.zeros(n, dtype=np.int16)


def _raw(*parts: tuple[float, bool]) -> np.ndarray:
    return np.concatenate([_segment(seconds, loud=loud) for seconds, loud in parts])


def test_capture_guidance_lists_the_types_and_examples() -> None:
    text = cm4_corpus.capture_guidance()
    for phrase_type in cm4_corpus.PHRASE_TYPES:
        assert phrase_type in text
    assert "Apaga la luz" in text
    assert "¿Qué hora es?" in text
    assert "Me gusta" in text


def test_validate_phrase_type_accepts_the_five_and_rejects_others() -> None:
    for phrase_type in cm4_corpus.PHRASE_TYPES:
        assert cm4_corpus.validate_phrase_type(phrase_type) == phrase_type
    with pytest.raises(ValueError, match="phrase type"):
        cm4_corpus.validate_phrase_type("gossip")


def test_segment_splits_on_a_long_gap() -> None:
    raw = _raw((0.3, False), (0.5, True), (2.0, False), (0.5, True), (0.4, False))
    clips = cm4_corpus.segment_session_take(raw, policy=_POLICY, vad_factory=_LoudVad)
    assert len(clips) == 2


def test_segment_keeps_a_short_gap_as_one_clip() -> None:
    raw = _raw((0.3, False), (0.5, True), (0.5, False), (0.5, True), (0.4, False))
    clips = cm4_corpus.segment_session_take(raw, policy=_POLICY, vad_factory=_LoudVad)
    assert len(clips) == 1


def test_segment_of_silence_is_empty() -> None:
    clips = cm4_corpus.segment_session_take(
        _segment(1.0, loud=False), policy=_POLICY, vad_factory=_LoudVad
    )
    assert clips == []


def test_manifest_round_trip(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    record = ClipRecord(
        clip_id="s1-000", session="s1", duration_s=2.1, phrase_type="question", sha256="abc123"
    )
    cm4_corpus.append_clip(manifest, tmp_path, record)
    assert cm4_corpus.load_clips(manifest, tmp_path) == [record]


def test_append_clip_refuses_a_manifest_outside_the_root(tmp_path: Path) -> None:
    inside = tmp_path / "corpus"
    inside.mkdir()
    outside = tmp_path / "evil.jsonl"
    record = ClipRecord("s1-000", "s1", 1.0, "other", "abc")
    with pytest.raises(ValueError, match="escapes"):
        cm4_corpus.append_clip(outside, inside, record)


def test_cleanup_requires_the_typed_delete(tmp_path: Path) -> None:
    takes = tmp_path / "takes"
    takes.mkdir()
    (takes / "x.wav").write_bytes(b"not audio")
    assert cm4_corpus.cleanup(tmp_path, "no") is False
    assert (takes / "x.wav").exists()
    assert cm4_corpus.cleanup(tmp_path, "delete") is True
    assert not takes.exists()


def test_capture_conversation_saves_a_raw_take_without_text(tmp_path: Path) -> None:
    samples = _segment(1.0, loud=True)

    def recorder(_seconds: float) -> np.ndarray:
        return samples

    path = cm4_corpus.capture_conversation("s1", minutes=0.01, recorder=recorder, root=tmp_path)
    assert path.exists()
    assert path.parent == tmp_path / "takes"
    with wave.open(str(path), "rb") as handle:
        assert handle.getframerate() == _RATE
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
    assert not (tmp_path / "manifest.jsonl").exists()
