"""just commission — the guided alta of the robot; wires the camera and the microphone.

The state machine, the face and voice sessions and the acta live in ``server.commission_cli``, which
is server-only and never imports the robot (CLAUDE.md hard boundary). This thin entry point, like
``scripts/onboard.py``, supplies the camera (robot) and the microphone (sounddevice) adapters and
drives the flow. It runs in the full workspace environment.

Usage:
    just commission
"""

from __future__ import annotations

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


def _record_clip() -> bytes:
    """Record a few seconds from the microphone as contract WAV bytes (16 kHz mono int16)."""
    import sounddevice as sd  # noqa: PLC0415 — optional, demo-only dependency

    frames = sd.rec(_SECONDS * _SAMPLE_RATE, samplerate=_SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_SAMPLE_RATE)
        handle.writeframes(frames.tobytes())
    return buffer.getvalue()


async def _main() -> int:
    """Wire the camera and microphone adapters and drive the alta."""
    async with httpx.AsyncClient(timeout=30) as client:
        face = build_face_session(client, getpass.getpass, lambda: capture_frame(0))
        voice = build_voice_session(client, getpass.getpass, _record_clip)
        return await drive(
            read_text=input,
            write_text=print,
            face_session=face,
            voice_session=voice,
            now=iso_utc(datetime.now(UTC)),
        )


def main() -> None:
    """CLI entrypoint for the guided alta."""
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
