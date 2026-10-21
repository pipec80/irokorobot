"""A tiny synthetic STT corpus and a fake Whisper for the bench tests (Plan 0069 Task 7).

Every clip is digital silence of a distinct length, so a fake transcriber can answer per
clip. Audio contract: WAV · 16000 Hz · mono · int16.
"""

import io
from pathlib import Path
import wave

import numpy as np

from scripts.speaker_calibration_corpus import sha256_of_file
from scripts.stt_corpus_models import Clip, Take, append_take
from server import stt

FREE_SENTINEL = "frasecentinelaprivada"


def wav(samples: int) -> bytes:
    """Silent WAV bytes — 16 kHz, mono, int16 — of *samples* samples."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(np.zeros(samples, dtype=np.int16).tobytes())
    return buffer.getvalue()


def _write(root: Path, relative: str, samples: int) -> Clip:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav(samples))
    return Clip(path=relative, sha256=sha256_of_file(path))


def build_corpus(root: Path) -> dict[int, str]:
    """Write four read takes and one annotated free take; return clip length → heard text."""
    heard: dict[int, str] = {}
    spec = [
        ("A01", "Me gusta el helado de chocolate.", [(16_000, "me gusta el helado de chocolate")]),
        (
            "A02",
            "¿Me gusta el helado de chocolate?",
            [(16_160, "¿Me gusta el"), (16_320, "helado de chocolate?")],
        ),
        ("D01", "Dijo helado.", [(16_480, "dijo de lado")]),
        ("B05", "Sí, autorizo.", [(16_640, "Sí, autorizo.")]),
    ]
    for number, (item_id, reference, clips) in enumerate(spec, 1):
        take_id = f"s1-c60-careful-{item_id}-{number}"
        raw = _write(root, f"takes/{take_id}.wav", 48_000 + number)
        written = []
        for index, (samples, text) in enumerate(clips, 1):
            written.append(_write(root, f"clips/{take_id}-{index}.wav", samples))
            heard[samples] = text
        append_take(
            root / "manifest.jsonl",
            root,
            Take(
                take_id=take_id,
                session="s1",
                condition="c60",
                style="careful",
                mode="read",
                item_id=item_id,
                raw_path=raw.path,
                raw_sha256=raw.sha256,
                clips=tuple(written),
                reference=reference,
            ),
        )
    free_raw = _write(root, "takes/s4-free.wav", 96_000)
    free_clip = _write(root, "clips/s4-free-1.wav", 16_800)
    heard[16_800] = f"me dijiste {FREE_SENTINEL}"
    append_take(
        root / "manifest.jsonl",
        root,
        Take(
            take_id="s4-free",
            session="s4",
            condition="c60",
            style="natural",
            mode="free",
            item_id=None,
            raw_path=free_raw.path,
            raw_sha256=free_raw.sha256,
            clips=(
                Clip(
                    path=free_clip.path, sha256=free_clip.sha256, reference=f"dije {FREE_SENTINEL}"
                ),
            ),
            reference=None,
        ),
    )
    return heard


class FakeTranscriber:
    """Answers each clip by its length; counts calls."""

    def __init__(self, heard: dict[int, str], logprob: float = -0.3) -> None:
        self.heard = heard
        self.logprob = logprob
        self.calls = 0

    def __call__(
        self, _model: object, audio: bytes, _options: object, _hotwords: str | None
    ) -> stt.Transcript:
        self.calls += 1
        samples = (len(audio) - 44) // 2
        text = self.heard.get(samples, "")
        return stt.Transcript(
            text=text,
            confidence=stt.TranscriptConfidence(
                avg_logprob=self.logprob,
                no_speech_prob=0.1,
                compression_ratio=1.2,
                temperature=0.0,
                segments=1,
            ),
            clip_s=samples / 16_000,
            after_vad_s=samples / 16_000,
        )
