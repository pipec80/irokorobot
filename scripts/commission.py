"""just commission — the guided alta of the robot; wires the camera and the microphone.

The state machine, the face and voice sessions and the acta live in ``server.commission_cli``, which
is server-only and never imports the robot (CLAUDE.md hard boundary). This thin entry point, like
``scripts/onboard.py``, supplies the camera (robot) and the microphone (sounddevice) adapters and
drives the flow. It runs in the full workspace environment.

Usage:
    just commission
    just commission --device 1
    just commission --mic 2
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import getpass
import io
import wave

import httpx
from robot.camera_capture import capture_frame
from server.commission_cli import build_face_session, build_voice_session, drive
from server.memory.candidates import iso_utc

_SAMPLE_RATE = 16_000
_SECONDS = 5
_BEEP_START_HZ = 1000
_BEEP_END_HZ = 500
_BEEP_MS = 150


def _beep(frequency_hz: int) -> None:
    """Play a short beep so the owner hears when recording starts and ends (Windows only)."""
    try:
        import winsound  # noqa: PLC0415 — Windows-only; elsewhere the printed notice is enough
    except ImportError:
        return
    winsound.Beep(frequency_hz, _BEEP_MS)


def _record_clip(device: int | None) -> bytes:
    """Record a few seconds from the microphone as contract WAV bytes (16 kHz mono int16).

    A high beep marks the start and a low one the end; each plays outside the recording, so the
    microphone never hears it.
    """
    import sounddevice as sd  # noqa: PLC0415 — optional, demo-only dependency

    _beep(_BEEP_START_HZ)
    frames = sd.rec(
        _SECONDS * _SAMPLE_RATE,
        samplerate=_SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=device,
    )
    sd.wait()
    _beep(_BEEP_END_HZ)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_SAMPLE_RATE)
        handle.writeframes(frames.tobytes())
    return buffer.getvalue()


async def _main(camera: int, microphone: int | None) -> int:
    """Wire the camera and microphone adapters and drive the alta."""
    async with httpx.AsyncClient(timeout=30) as client:
        face = build_face_session(client, getpass.getpass, lambda: capture_frame(camera))
        voice = build_voice_session(client, getpass.getpass, lambda: _record_clip(microphone))
        return await drive(
            read_text=input,
            write_text=print,
            face_session=face,
            voice_session=voice,
            now=iso_utc(datetime.now(UTC)),
        )


def main() -> None:
    """CLI entrypoint for the guided alta."""
    parser = argparse.ArgumentParser(description="Alta guiada del robot (Plan 0072).")
    parser.add_argument("--device", type=int, default=0, help="Indice de camara (default: 0)")
    parser.add_argument(
        "--mic", type=int, default=None, help="Indice del microfono (default: el del sistema)"
    )
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(_main(args.device, args.mic)))
    except KeyboardInterrupt:
        print("Cancelado. Puedes volver a correr just commission: retoma donde quedo.")  # noqa: T201
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
