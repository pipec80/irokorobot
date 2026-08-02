"""Debug script: microphone capture → Whisper STT.

Standalone — no .env, no server, no Piper required.
Tests only the audio capture + transcription pipeline.

Audio contract: WAV · 16000 Hz · mono · int16.

Usage:
    uv run python scripts/mic_test.py
    uv run python scripts/mic_test.py --seconds 8
    uv run python scripts/mic_test.py --model small --language es
    uv run python scripts/mic_test.py --save debug.wav
    uv run python scripts/mic_test.py --list-devices
    uv run python scripts/mic_test.py --prompt "Conversación con un robot llamado Omnibot."
"""

import argparse
import io
import logging
from pathlib import Path
import wave

from faster_whisper import WhisperModel
from faster_whisper.transcribe import VadOptions
import numpy as np
import sounddevice as sd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000
_CHANNELS = 1
_DTYPE = "int16"
_RMS_SPEECH_THRESHOLD = 200

_DEFAULT_PROMPT = "Conversación con un robot doméstico llamado Omnibot."
_NO_SPEECH_THRESHOLD = 0.6
_LOGPROB_LOW = -1.0
_LOGPROB_MED = -0.5


def list_devices() -> None:
    """Print available audio input devices."""
    print("\n=== Audio Input Devices ===")  # noqa: T201
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:  # type: ignore[index]
            marker = "→" if i == sd.default.device[0] else " "
            print(f"  {marker} [{i}] {dev['name']}")  # type: ignore[index]  # noqa: T201
    print()  # noqa: T201


def record(seconds: int, device: int | None) -> bytes:
    """Record audio from microphone for N seconds.

    Args:
        seconds: Duration to record.
        device: Input device index, or None for system default.

    Returns:
        WAV bytes at 16kHz mono int16.
    """
    logger.info("Recording %d seconds on device %s... speak now!", seconds, device or "default")
    frames = sd.rec(
        int(seconds * _SAMPLE_RATE),
        samplerate=_SAMPLE_RATE,
        channels=_CHANNELS,
        dtype=_DTYPE,
        device=device,
    )
    sd.wait()
    logger.info("Recording complete — encoding WAV")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(frames.tobytes())
    return buf.getvalue()


def check_rms(frames: np.ndarray) -> None:
    """Log RMS energy so you can verify the mic is actually picking up sound."""
    rms = float(np.sqrt(np.mean(frames.astype(np.float32) ** 2)))
    level = "OK" if rms > _RMS_SPEECH_THRESHOLD else "LOW — check mic volume or threshold"
    logger.info("Audio RMS energy: %.0f  [%s]", rms, level)


def transcribe(
    wav_bytes: bytes,
    model_size: str,
    language: str,
    prompt: str | None,
    hotwords: str | None,
    beam_size: int,
) -> str:
    """Transcribe WAV bytes using Whisper, printing per-segment quality metrics.

    Args:
        wav_bytes: WAV bytes at 16kHz mono int16.
        model_size: Whisper model name (tiny/base/small/medium).
        language: ISO 639-1 language code.
        prompt: Initial prompt to anchor the model to the domain vocabulary.
        hotwords: Comma-separated priority words for the model.
        beam_size: Beam search width — higher = more accurate but slower.

    Returns:
        Transcribed text string.
    """
    logger.info(
        "Loading Whisper '%s' (first run downloads ~%s)...", model_size, _model_size_mb(model_size)
    )
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    vad_params = VadOptions(min_silence_duration_ms=500)
    logger.info("Transcribing...")
    segments, info = model.transcribe(
        io.BytesIO(wav_bytes),
        language=language,
        beam_size=beam_size,
        initial_prompt=prompt,
        hotwords=hotwords,
        condition_on_previous_text=False,
        hallucination_silence_threshold=2.0,
        vad_filter=True,
        vad_parameters=vad_params,
    )
    logger.info(
        "Language: %s (%.0f%%) — duration: %.1fs → %.1fs after VAD",
        info.language,
        info.language_probability * 100,
        info.duration,
        info.duration_after_vad,
    )

    parts: list[str] = []
    print("\n=== Segments ===")  # noqa: T201
    for seg in segments:
        confidence = _confidence_label(seg.avg_logprob, seg.no_speech_prob)
        print(  # noqa: T201
            f"  [{seg.start:5.1f}s→{seg.end:5.1f}s]"
            f"  logprob={seg.avg_logprob:+.2f}"
            f"  no_speech={seg.no_speech_prob:.2f}"
            f"  temp={seg.temperature or 0.0:.1f}"
            f"  [{confidence}]"
            f"  {seg.text.strip()}"
        )
        parts.append(seg.text.strip())
    print()  # noqa: T201

    return " ".join(parts)


def _confidence_label(avg_logprob: float, no_speech_prob: float) -> str:
    """Map Whisper segment metrics to a human-readable confidence label."""
    if no_speech_prob > _NO_SPEECH_THRESHOLD:
        return "NOISE/SILENCE"
    if avg_logprob < _LOGPROB_LOW:
        return "LOW"
    if avg_logprob < _LOGPROB_MED:
        return "MED"
    return "HIGH"


def _model_size_mb(model: str) -> str:
    sizes = {
        "tiny": "70 MB",
        "base": "140 MB",
        "small": "240 MB",
        "medium": "760 MB",
        "large": "1.5 GB",
    }
    return sizes.get(model, "?")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Mic → Whisper STT debug script")
    parser.add_argument("--seconds", type=int, default=5, help="Recording duration (default: 5)")
    parser.add_argument(
        "--model", default="tiny", help="Whisper model: tiny/base/small/medium (default: tiny)"
    )
    parser.add_argument("--language", default="es", help="Language code (default: es)")
    parser.add_argument(
        "--device", type=int, default=None, help="Input device index (default: system default)"
    )
    parser.add_argument("--save", type=str, default=None, help="Save WAV to file path (optional)")
    parser.add_argument(
        "--list-devices", action="store_true", help="List audio input devices and exit"
    )
    parser.add_argument(
        "--prompt",
        default=_DEFAULT_PROMPT,
        help="Initial prompt to anchor model vocabulary (default: robot context)",
    )
    parser.add_argument(
        "--hotwords", default=None, help="Comma-separated priority words (e.g. 'Omnibot,apagar')"
    )
    parser.add_argument("--beam-size", type=int, default=5, help="Beam size (default: 5)")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    wav_bytes = record(args.seconds, args.device)

    raw_frames = np.frombuffer(wav_bytes[44:], dtype=np.int16)  # skip 44-byte WAV header
    check_rms(raw_frames)

    if args.save:
        Path(args.save).write_bytes(wav_bytes)
        logger.info("WAV saved → %s", args.save)

    text = transcribe(
        wav_bytes,
        args.model,
        args.language,
        prompt=args.prompt,
        hotwords=args.hotwords,
        beam_size=args.beam_size,
    )

    print(f"{'=' * 40}")  # noqa: T201
    print(f"  {text or '(silence / no speech detected)'}")  # noqa: T201
    print(f"{'=' * 40}\n")  # noqa: T201


if __name__ == "__main__":
    main()
