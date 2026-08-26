"""face_auth_demo.py — enroll or revoke the owner's face for authentication.

Administrative demo for the Plan 0029 endpoints: `POST /auth/owner/face/enroll`
and `POST /auth/owner/face/revoke`. Both require a fresh local owner PIN
unlock first — this script prompts for the PIN via getpass (never echoed,
never logged) and consumes it once. The public scene-only path
(`/vision/respond`, no biometrics) stays covered by faces_demo.py.

Requires the server running (just run-server) on loopback, with an owner
and PIN already configured (just setup-personal).

Usage:
    just face-auth-demo --enroll
    just face-auth-demo --enroll --image foto.jpg
    just face-auth-demo --revoke

Photos live in the drop-folder (IMAGES_DIR, default
server/src/server/images — gitignored): drop foto.jpg there and pass just
the file name. A full path works too. Omit --image to capture one frame
from the webcam.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
from pathlib import Path

import httpx
from robot.camera_capture import capture_frame
from robot.exceptions import CameraError
from server.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _resolve_photo(path: str) -> Path:
    """Resolve a photo argument against the drop-folder (IMAGES_DIR).

    Args:
        path: File name inside IMAGES_DIR, or a full path.

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


def _get_frame(image_path: str | None, device: int) -> bytes:
    """Return contract JPEG bytes from a photo file or the webcam."""
    if image_path is not None:
        resolved = _resolve_photo(image_path)
        print(f"  Foto: {resolved}")  # noqa: T201
        return resolved.read_bytes()
    print("  Capturando frame de la webcam...")  # noqa: T201
    return capture_frame(device)


async def _read_pin() -> str:
    """Read the owner PIN via getpass, off the event loop. Never logged."""
    return await asyncio.to_thread(getpass.getpass, "Owner PIN: ")


async def _unlock(client: httpx.AsyncClient, url: str) -> str:
    """Verify the local PIN and return one fresh one-use token.

    Args:
        client: Shared HTTP client bound to the server's loopback URL.
        url: Server base URL.

    Returns:
        The opaque one-use token.

    Raises:
        SystemExit: If the PIN is rejected or the server is unreachable.
    """
    pin = await _read_pin()
    resp = await client.post(f"{url}/auth/owner/unlock", json={"pin": pin})
    if resp.is_error:
        logger.error("Unlock rejected: %s %s", resp.status_code, resp.text[:200])
        raise SystemExit(1)
    return str(resp.json()["token"])


async def _enroll(url: str, image_path: str | None, device: int) -> None:
    """Unlock once, then enroll one face profile for the owner."""
    jpeg = _get_frame(image_path, device)
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _unlock(client, url)
        resp = await client.post(
            f"{url}/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": token},
            files={"image": ("frame.jpg", jpeg, "image/jpeg")},
        )
    if resp.is_error:
        logger.error("Enroll failed: %s %s", resp.status_code, resp.text[:300])
        raise SystemExit(1)
    data = resp.json()
    print(f"  Enrolado: profile_id={data['profile_id']} enrolled_at={data['enrolled_at']}")  # noqa: T201


async def _revoke(url: str) -> None:
    """Unlock once, then revoke the owner's face consent and stored profiles."""
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _unlock(client, url)
        resp = await client.post(
            f"{url}/auth/owner/face/revoke",
            headers={"X-Iroko-Identity-Token": token},
        )
    if resp.is_error:
        logger.error("Revoke failed: %s %s", resp.status_code, resp.text[:300])
        raise SystemExit(1)
    print("  Revocado: consentimiento y perfiles faciales borrados.")  # noqa: T201


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Enroll/revoke owner face authentication")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--enroll", action="store_true", help="Enroll one face profile")
    action.add_argument("--revoke", action="store_true", help="Revoke consent and purge profiles")
    parser.add_argument(
        "--image",
        nargs="+",
        metavar="PATH",
        default=None,
        help="Usa una FOTO en vez de la webcam (ruta al archivo, solo con --enroll)",
    )
    parser.add_argument("--device", type=int, default=0, help="Camera index (default: 0)")
    args = parser.parse_args()

    image_path = " ".join(args.image) if args.image else None
    host = "localhost" if settings.server_host == "0.0.0.0" else settings.server_host  # noqa: S104
    url = f"http://{host}:{settings.server_port}"
    try:
        if args.enroll:
            asyncio.run(_enroll(url, image_path, args.device))
        else:
            asyncio.run(_revoke(url))
    except CameraError as exc:
        logger.error("Camera/photo failed: %s", exc)


if __name__ == "__main__":
    main()
