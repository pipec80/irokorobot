"""Debug script: mic → STT → LLM → TTS → speaker — full pipeline validation.

Imports the actual server modules so this exercises the real production code path.
Requires .env in repo root with LLM_PROVIDER, OLLAMA_URL / ANTHROPIC_API_KEY, etc.

Audio contract: WAV · 16000 Hz · mono · int16.

Usage:
    just test-pipeline
    just test-pipeline --seconds 8
    just test-pipeline --text hola robot
    just test-pipeline --no-play
    just test-pipeline --save out.wav
    just test-pipeline --list-devices
"""

import argparse
import asyncio
import base64
import io
import logging
from pathlib import Path
import time
import wave

import numpy as np
import sounddevice as sd

from server import llm, stt, tts

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000
_CHANNELS = 1
_DTYPE = "int16"
_RMS_SPEECH_THRESHOLD = 200
_SEP = "─" * 52


def _header(step: str) -> None:
    print(f"\n{_SEP}")  # noqa: T201
    print(f"  {step}")  # noqa: T201
    print(_SEP)  # noqa: T201


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
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(frames.tobytes())
    rms = float(np.sqrt(np.mean(frames.astype(np.float32) ** 2)))
    logger.info(
        "RMS energy: %.0f  [%s]",
        rms,
        "OK" if rms > _RMS_SPEECH_THRESHOLD else "LOW — check mic",
    )
    return buf.getvalue()


def play_wav(wav_bytes: bytes) -> None:
    """Play WAV bytes through the default audio output device.

    Args:
        wav_bytes: WAV at 16kHz mono int16.
    """
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16)
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


async def run_pipeline(
    wav_bytes: bytes | None,
    input_text: str | None,
    play: bool,
    save: str | None,
) -> None:
    """Execute the full STT → LLM → TTS pipeline, printing each step result.

    Args:
        wav_bytes: WAV input for STT, or None when input_text is provided.
        input_text: Skip STT and feed this text directly to LLM.
        play: Whether to play TTS output through speakers.
        save: Optional file path to save the output WAV.
    """
    # ── Step 1: STT ──────────────────────────────────────────────────────
    if input_text is not None:
        text_heard = input_text
        _header("1/3  STT  [skipped — using --text]")
        print(f"  text : {text_heard}")  # noqa: T201
    else:
        _header("1/3  STT  (Whisper)")
        assert wav_bytes is not None  # noqa: S101
        t0 = time.perf_counter()
        text_heard = await stt.transcribe(wav_bytes)
        elapsed = time.perf_counter() - t0
        print(f"  text : {text_heard or '(silence / no speech detected)'}")  # noqa: T201
        print(f"  time : {elapsed:.2f}s")  # noqa: T201
        if not text_heard:
            logger.warning("STT returned empty — stopping pipeline")
            return

    # ── Step 2: LLM ──────────────────────────────────────────────────────
    _header("2/3  LLM  (Ollama / Anthropic)")
    t0 = time.perf_counter()
    llm_response, emotion = await llm.generate_response(text_heard)
    elapsed = time.perf_counter() - t0
    print(f"  response : {llm_response}")  # noqa: T201
    print(f"  emotion  : {emotion}")  # noqa: T201
    print(f"  time     : {elapsed:.2f}s")  # noqa: T201

    # ── Step 3: TTS ──────────────────────────────────────────────────────
    _header("3/3  TTS  (Piper)")
    t0 = time.perf_counter()
    audio_b64, duration_ms = await tts.synthesize(llm_response)
    elapsed = time.perf_counter() - t0
    wav_out = base64.b64decode(audio_b64)
    print(f"  size     : {len(wav_out):,} bytes")  # noqa: T201
    print(f"  duration : {duration_ms} ms  (synthesis {elapsed:.2f}s)")  # noqa: T201

    if save:
        Path(save).write_bytes(wav_out)
        logger.info("WAV saved → %s", save)

    if play:
        logger.info("Playing response...")
        play_wav(wav_out)

    # ── Summary ──────────────────────────────────────────────────────────
    _header("Pipeline complete")
    print(f"  heard    : {text_heard}")  # noqa: T201
    print(f"  response : {llm_response}")  # noqa: T201
    print(f"  emotion  : {emotion}")  # noqa: T201
    print()  # noqa: T201


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Full pipeline: mic → STT → LLM → TTS → speaker")
    parser.add_argument("--seconds", type=int, default=5, help="Recording duration (default: 5)")
    parser.add_argument("--device", type=int, default=None, help="Input device index")
    parser.add_argument(
        "--text",
        nargs="+",
        default=None,
        help="Skip mic+STT, feed this text directly to LLM (quotes optional)",
    )
    parser.add_argument("--no-play", action="store_true", help="Skip audio playback")
    parser.add_argument("--save", type=str, default=None, help="Save TTS output WAV to this path")
    parser.add_argument(
        "--list-devices", action="store_true", help="List audio input devices and exit"
    )
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    input_text: str | None = " ".join(args.text) if args.text else None
    wav_bytes: bytes | None = None
    if input_text is None:
        wav_bytes = record(args.seconds, args.device)

    asyncio.run(
        run_pipeline(
            wav_bytes=wav_bytes,
            input_text=input_text,
            play=not args.no_play,
            save=args.save,
        )
    )


if __name__ == "__main__":
    main()
