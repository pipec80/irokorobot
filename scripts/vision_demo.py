"""vision_demo.py — V0 demo: webcam frame → POST /vision/describe → print/speak.

Captures ONE frame from the webcam (image contract: JPEG · max 1280x720 ·
quality 85), sends it to the server, and prints the Spanish description.
With --speak the description is also synthesized locally with Piper and
played through the speakers.

Requires the server running (just run-server) with VISION_ENABLED=true and
the VLM pulled (ollama pull qwen3-vl:2b-instruct). The frame is never
written to disk.

Usage:
    just vision-demo
    just vision-demo --speak
    just vision-demo --device 1
    just vision-demo --loop
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import time
import wave

import httpx
import numpy as np
from piper import PiperVoice, SynthesisConfig
from robot.camera_capture import capture_frame
from robot.exceptions import CameraError
from server.settings import settings
import sounddevice as sd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _speak(text: str) -> None:
    """Synthesize *text* with the local Piper voice and play it.

    Args:
        text: Spanish text to speak.

    Raises:
        FileNotFoundError: If the Piper voice model is missing.
    """
    model_path = settings.models_dir / "piper" / f"{settings.piper_voice}.onnx"
    if not model_path.exists():
        raise FileNotFoundError(f"Piper model not found: {model_path}")
    voice = PiperVoice.load(str(model_path))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=SynthesisConfig())
    buf.seek(0)
    with wave.open(buf) as wf:
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    sd.play(np.frombuffer(raw, dtype=np.int16), samplerate=sample_rate)
    sd.wait()


async def _describe_once(url: str, device: int, speak: bool) -> None:
    """Capture one frame, POST it, and print (optionally speak) the result.

    Args:
        url: Server base URL.
        device: OpenCV camera index.
        speak: Whether to speak the description with Piper.
    """
    print("  Capturando frame de la webcam...")  # noqa: T201
    t0 = time.perf_counter()
    jpeg = capture_frame(device)
    print(f"  Frame: {len(jpeg) / 1024:.0f} KB — enviando al server...")  # noqa: T201
    async with httpx.AsyncClient(timeout=settings.ollama_timeout_s + 10) as client:
        resp = await client.post(
            f"{url}/vision/describe",
            files={"image": ("frame.jpg", jpeg, "image/jpeg")},
        )
    if resp.is_error:
        logger.error("Server %s: %s", resp.status_code, resp.text[:300])
        return
    data = resp.json()
    elapsed = time.perf_counter() - t0
    print(f"\n  IROKO VE: {data['description']}")  # noqa: T201
    print(f"  (VLM {data['duration_ms']} ms · total {elapsed:.1f}s)")  # noqa: T201
    if speak:
        _speak(data["description"])


async def _run(url: str, device: int, speak: bool, loop: bool) -> None:
    """Run the demo once, or repeatedly until 'q' when *loop* is set."""
    while True:
        try:
            await _describe_once(url, device, speak)
        except CameraError as exc:
            logger.error("Camera failed: %s", exc)
        if not loop:
            return
        answer = input("\n  Enter = otra captura, q = salir: ")
        if answer.strip().lower() == "q":
            return


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="V0 demo: webcam -> /vision/describe")
    parser.add_argument("--device", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--speak", action="store_true", help="Speak the description with Piper")
    parser.add_argument("--loop", action="store_true", help="Capture repeatedly until q")
    args = parser.parse_args()

    host = "localhost" if settings.server_host == "0.0.0.0" else settings.server_host  # noqa: S104
    url = f"http://{host}:{settings.server_port}"
    asyncio.run(_run(url, args.device, args.speak, args.loop))


if __name__ == "__main__":
    main()
