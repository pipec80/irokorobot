"""HTTP client test: send audio to the running server and play the response.

Requires the server running: just run-server

Modes:
  default  — record from microphone, send to server
  --text   — synthesize text locally with piper, send to server (no mic needed)
  --file   — send an existing WAV file to the server

Audio contract: WAV 16000 Hz mono int16.

Usage:
    just test-client
    just test-client --text hola robot como estas
    just test-client --file debug.wav
    just test-client --seconds 8
    just test-client --no-play
    just test-client --save out.wav
    just test-client --url http://homelab-server:8000
"""

import argparse
import asyncio
import base64
from dataclasses import dataclass
import io
import json
import logging
from pathlib import Path
import time
from time import sleep
import wave

import httpx
import numpy as np
from piper import PiperVoice, SynthesisConfig
import sounddevice as sd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000
_CHANNELS = 1
_DTYPE = "int16"
_RMS_SPEECH_THRESHOLD = 200
_DEFAULT_URL = "http://localhost:8000"
_DEFAULT_VOICE = "models/piper/es_MX-ald-medium.onnx"
_SEP = "-" * 52


@dataclass(frozen=True)
class ServerResponse:
    """Parsed response from POST /transcribe."""

    text_heard: str
    llm_response: str
    audio_bytes: bytes
    duration_ms: int
    emotion: str


def _header(label: str) -> None:
    print(f"\n{_SEP}")  # noqa: T201
    print(f"  {label}")  # noqa: T201
    print(_SEP)  # noqa: T201


def record(seconds: int, device: int | None) -> bytes:
    """Record audio from microphone.

    Args:
        seconds: Duration to record.
        device: Input device index, or None for system default.

    Returns:
        WAV bytes at 16kHz mono int16.
    """
    logger.info("Recording %d seconds... speak now!", seconds)
    frames = sd.rec(
        int(seconds * _SAMPLE_RATE),
        samplerate=_SAMPLE_RATE,
        channels=_CHANNELS,
        dtype=_DTYPE,
        device=device,
    )
    sd.wait()
    rms = float(np.sqrt(np.mean(frames.astype(np.float32) ** 2)))
    logger.info(
        "RMS energy: %.0f  [%s]",
        rms,
        "OK" if rms > _RMS_SPEECH_THRESHOLD else "LOW — check mic",
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(frames.tobytes())
    return buf.getvalue()


def synthesize_locally(text: str, voice_path: str) -> bytes:
    """Synthesize text to WAV using local piper model (no mic needed).

    Args:
        text: Text to synthesize as input audio.
        voice_path: Path to the .onnx piper voice model.

    Returns:
        WAV bytes at 16kHz mono int16.
    """
    model_path = Path(voice_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Voice model not found: {model_path}")
    logger.info("Synthesizing input locally: %r", text)
    voice = PiperVoice.load(str(model_path))
    config = SynthesisConfig()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=config)
    logger.info("Local synthesis done — %d bytes", buf.tell())
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
    sleep(0.1)  # Windows audio driver buffer drain


async def call_server(wav_bytes: bytes, url: str) -> ServerResponse:
    """POST WAV audio to the server and return the parsed response.

    Args:
        wav_bytes: WAV bytes at 16kHz mono int16.
        url: Base URL of the OMNiBot server.

    Returns:
        Parsed ServerResponse with text, LLM reply, and audio.

    Raises:
        httpx.HTTPStatusError: If the server returns a non-2xx response.
        httpx.RequestError: If the server is unreachable.
    """
    endpoint = f"{url}/transcribe"
    logger.info("POST %s  (%d bytes)", endpoint, len(wav_bytes))
    async with httpx.AsyncClient(timeout=60.0) as client:
        t0 = time.perf_counter()
        response = await client.post(
            endpoint,
            files={"audio": ("audio.wav", wav_bytes, "audio/wav")},
        )
        elapsed = time.perf_counter() - t0
        response.raise_for_status()
    logger.info("Server responded in %.2fs", elapsed)
    data = response.json()
    return ServerResponse(
        text_heard=data["text_heard"],
        llm_response=data["llm_response"],
        audio_bytes=base64.b64decode(data["audio_base64"]),
        duration_ms=data["duration_ms"],
        emotion=data["emotion"],
    )


async def call_server_stream(wav_bytes: bytes, url: str) -> None:
    """POST WAV audio to POST /transcribe/stream and print R3 latency (NDJSON).

    Measures the metric R3 optimizes for: end-of-speech to first audio chunk
    (perceived latency), separately from total_ms (full turn, from the
    server's own ``done`` event) — the same qualitative comparison as R2's
    stt/llm/tts/total breakdown, but with a first-chunk number added.

    Args:
        wav_bytes: WAV bytes at 16kHz mono int16.
        url: Base URL of the OMNiBot server.

    Raises:
        httpx.HTTPStatusError: If the server returns a non-2xx response.
        httpx.RequestError: If the server is unreachable.
    """
    endpoint = f"{url}/transcribe/stream"
    logger.info("POST %s  (%d bytes)", endpoint, len(wav_bytes))
    _header("Streaming response (R3)")
    t0 = time.perf_counter()
    first_audio_s: float | None = None
    sentence_count = 0
    async with (
        httpx.AsyncClient(timeout=60.0) as client,
        client.stream(
            "POST", endpoint, files={"audio": ("audio.wav", wav_bytes, "audio/wav")}
        ) as response,
    ):
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            event = json.loads(line)
            elapsed = time.perf_counter() - t0
            match event["type"]:
                case "text_heard":
                    print(f"  [{elapsed:6.2f}s] text_heard : {event['value']}")  # noqa: T201
                case "emotion":
                    print(f"  [{elapsed:6.2f}s] emotion    : {event['value']}")  # noqa: T201
                case "audio":
                    sentence_count += 1
                    if first_audio_s is None:
                        first_audio_s = elapsed
                    print(f"  [{elapsed:6.2f}s] audio #{sentence_count}    : {event['text']!r}")  # noqa: T201
                case "done":
                    print(f"  [{elapsed:6.2f}s] done       : {event}")  # noqa: T201

    _header("R3 latency summary")
    summary = (
        f"  time to first audio chunk : {first_audio_s:.2f}s"
        if first_audio_s
        else "  no audio chunk received"
    )
    print(summary)  # noqa: T201
    print(f"  sentences synthesized     : {sentence_count}")  # noqa: T201
    print()  # noqa: T201


async def run(
    wav_bytes: bytes,
    url: str,
    play: bool,
    save: str | None,
    *,
    stream: bool,
) -> None:
    """Send audio to server, print results, optionally play and save response.

    Args:
        wav_bytes: Input WAV bytes at 16kHz mono int16.
        url: Base URL of the OMNiBot server.
        play: Whether to play TTS response through speakers.
        save: Optional path to save response WAV.
        stream: If True, use POST /transcribe/stream (R3) instead of the
            classic single-shot POST /transcribe.
    """
    if stream:
        try:
            await call_server_stream(wav_bytes, url)
        except httpx.HTTPStatusError as exc:
            logger.error("Server error %d: %s", exc.response.status_code, exc.response.text)
        except httpx.RequestError as exc:
            logger.error("Could not reach server: %s", exc)
        return

    _header("Sending to server")
    try:
        result = await call_server(wav_bytes, url)
    except httpx.HTTPStatusError as exc:
        logger.error("Server error %d: %s", exc.response.status_code, exc.response.text)
        return
    except httpx.RequestError as exc:
        logger.error("Could not reach server: %s", exc)
        return

    _header("Response")
    print(f"  heard    : {result.text_heard}")  # noqa: T201
    print(f"  response : {result.llm_response}")  # noqa: T201
    print(f"  emotion  : {result.emotion}")  # noqa: T201
    print(f"  tts      : {result.duration_ms} ms  ({len(result.audio_bytes):,} bytes)")  # noqa: T201

    if save:
        Path(save).write_bytes(result.audio_bytes)
        logger.info("Response WAV saved to %s", save)

    if play:
        logger.info("Playing response...")
        play_wav(result.audio_bytes)

    print()  # noqa: T201


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Client test: send audio to server, play response")
    parser.add_argument(
        "--text",
        nargs="+",
        default=None,
        help="Synthesize this text locally and send to server instead of recording",
    )
    parser.add_argument("--file", type=str, default=None, help="Send this WAV file to the server")
    parser.add_argument(
        "--seconds", type=int, default=5, help="Mic recording duration (default: 5)"
    )
    parser.add_argument("--device", type=int, default=None, help="Mic input device index")
    parser.add_argument(
        "--url", type=str, default=_DEFAULT_URL, help=f"Server URL (default: {_DEFAULT_URL})"
    )
    parser.add_argument(
        "--voice", type=str, default=_DEFAULT_VOICE, help="Piper model path for --text mode"
    )
    parser.add_argument("--no-play", action="store_true", help="Skip audio playback")
    parser.add_argument("--save", type=str, default=None, help="Save response WAV to this path")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use POST /transcribe/stream (R3) instead of the classic /transcribe",
    )
    args = parser.parse_args()

    if args.list_devices:
        print("\n=== Audio Input Devices ===")  # noqa: T201
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:  # type: ignore[index]
                marker = "->" if i == sd.default.device[0] else "  "
                print(f"  {marker} [{i}] {dev['name']}")  # type: ignore[index]  # noqa: T201
        return

    if args.text:
        input_text = " ".join(args.text)
        _header(f"Mode: text  ({input_text!r})")
        wav_bytes = synthesize_locally(input_text, args.voice)
    elif args.file:
        _header(f"Mode: file  ({args.file})")
        wav_bytes = Path(args.file).read_bytes()
        logger.info("Loaded %d bytes from %s", len(wav_bytes), args.file)
    else:
        _header("Mode: mic")
        wav_bytes = record(args.seconds, args.device)

    asyncio.run(run(wav_bytes, args.url, play=not args.no_play, save=args.save, stream=args.stream))


if __name__ == "__main__":
    main()
