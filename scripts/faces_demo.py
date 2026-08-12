"""faces_demo.py — scene-only visual dialogue demo without the microphone.

This demo sends one frame and a scene question through `/vision/respond` —
the same conversational path the robot uses. It does not enroll biometrics or
claim to identify the person in the frame. Frames and photos are processed in
memory, never written by the server.

Requires the server running (just run-server) with VISION_ENABLED=true.
Usage:
    just faces-demo --see
    just faces-demo --see --image foto.jpg
    just faces-demo --see --speak

Photos live in the drop-folder (IMAGES_DIR, default
server/src/server/images — gitignored): drop foto.jpg there and pass just
the file name. A full path works too.

The public face-enrollment path is quarantined pending local administration,
consent, and authorization policy (P0-S1/P0.5).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
from pathlib import Path
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


def _resolve_photo(path: str) -> Path:
    """Resolve a photo argument against the drop-folder (IMAGES_DIR).

    ``--image foto.jpg`` finds ``settings.images_dir/foto.jpg``; a full
    path is used as-is when it exists.

    Args:
        path: File name inside the drop-folder, or a full path.

    Returns:
        The existing photo path.

    Raises:
        CameraError: If the file exists in neither location.
    """
    direct = Path(path)
    if direct.exists():
        return direct
    dropped = settings.images_dir / path
    if dropped.exists():
        return dropped
    raise CameraError(
        f"Photo not found: {path} (looked in {settings.images_dir} too — "
        "deja la foto en esa carpeta y usa solo el nombre del archivo)"
    )


def _load_photo(path: str) -> bytes:
    """Load a photo (drop-folder or full path) and fit it to the contract.

    Args:
        path: File name inside IMAGES_DIR, or a full path, of any image
            OpenCV can read (jpg/png/etc).

    Returns:
        JPEG bytes — contract: max 1280x720 · quality 85.

    Raises:
        CameraError: If the file is missing or cannot be read as an image.
    """
    import cv2  # noqa: PLC0415 — heavy, demo-only path
    from robot.camera_capture import encode_jpeg, fit_to_contract  # noqa: PLC0415

    resolved = _resolve_photo(path)
    print(f"  Foto: {resolved}")  # noqa: T201
    frame = cv2.imread(str(resolved), cv2.IMREAD_COLOR)
    if frame is None:
        raise CameraError(f"Could not read image file: {resolved}")
    return encode_jpeg(fit_to_contract(frame))


def _get_frame(image_path: str | None, device: int) -> bytes:
    """Return contract JPEG bytes from a photo file or the webcam."""
    if image_path is not None:
        return _load_photo(image_path)
    print("  Capturando frame de la webcam...")  # noqa: T201
    return capture_frame(device)


async def _ask(url: str, phrase: str, jpeg: bytes, speak: bool) -> None:
    """Send a scene question with the frame to /vision/respond.

    Args:
        url: Server base URL.
        phrase: The scripted user phrase.
        jpeg: Contract JPEG bytes.
        speak: Whether to speak the response with Piper.
    """
    print(f"  > {phrase}")  # noqa: T201
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=settings.ollama_timeout_s + 60) as client:
        resp = await client.post(
            f"{url}/vision/respond",
            files={"image": ("frame.jpg", jpeg, "image/jpeg")},
            data={"text": phrase},
        )
    if resp.is_error:
        logger.error("Server %s: %s", resp.status_code, resp.text[:300])
        return
    data = resp.json()
    elapsed = time.perf_counter() - t0
    print(f"\n  IROKO: {data['llm_response']}")  # noqa: T201
    print(f"  (total {elapsed:.1f}s)")  # noqa: T201
    if speak:
        _speak(data["llm_response"])


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Scene-only visual demo via /vision/respond")
    parser.add_argument("--see", action="store_true", required=True, help="Pregunta: que ves")
    parser.add_argument(
        "--image",
        nargs="+",
        metavar="PATH",
        default=None,
        help="Usa una FOTO en vez de la webcam (ruta al archivo)",
    )
    parser.add_argument("--device", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--speak", action="store_true", help="Speak the response with Piper")
    args = parser.parse_args()

    image_path = " ".join(args.image) if args.image else None
    host = "localhost" if settings.server_host == "0.0.0.0" else settings.server_host  # noqa: S104
    url = f"http://{host}:{settings.server_port}"
    try:
        jpeg = _get_frame(image_path, args.device)
        asyncio.run(_ask(url, "¿Qué ves?", jpeg, args.speak))
    except CameraError as exc:
        logger.error("Camera/photo failed: %s", exc)


if __name__ == "__main__":
    main()
