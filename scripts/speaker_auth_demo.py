"""speaker_auth_demo.py — enroll or revoke the owner's voice for speaker evidence.

Administrative demo for the Plan 0053 endpoints:
`POST /auth/owner/voice/enroll` and `POST /auth/owner/voice/revoke`. Both
require a fresh local owner PIN unlock first — this script prompts for the
PIN via getpass (never echoed, never logged) and consumes it once.

Requires the server running (just run-server) on loopback, with an owner
and PIN already configured (just setup-personal), and
`SPEAKER_AUTHENTICATION_ENABLED=true` in `.env` — enrolment returns 503
otherwise (Plan 0053's flag matrix).

Usage:
    just speaker-auth-demo --enroll
    just speaker-auth-demo --enroll --wav clip.wav
    just speaker-auth-demo --revoke

It never writes audio to the repository: a microphone capture lives only in
memory (or wherever `--wav` already pointed) for the duration of one HTTP
request, then is discarded.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
from pathlib import Path

import httpx
from server.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_SECONDS = 5


def _get_wav(wav_path: str | None, seconds: int, device: int | None) -> bytes:
    """Return contract WAV bytes from a file path or the microphone."""
    if wav_path is not None:
        resolved = Path(wav_path)
        print(f"  WAV: {resolved}")  # noqa: T201
        return resolved.read_bytes()
    from scripts.mic_test import record  # noqa: PLC0415 -- deferred, demo-only dependency

    print(f"  Grabando {seconds}s desde el microfono...")  # noqa: T201
    return record(seconds, device)


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


async def _enroll(url: str, wav_path: str | None, seconds: int, device: int | None) -> None:
    """Unlock once, then enroll one voiceprint reference for the owner."""
    wav_bytes = _get_wav(wav_path, seconds, device)
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _unlock(client, url)
        resp = await client.post(
            f"{url}/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": token},
            files={"audio": ("clip.wav", wav_bytes, "audio/wav")},
        )
    if resp.is_error:
        logger.error("Enroll failed: %s %s", resp.status_code, resp.text[:300])
        raise SystemExit(1)
    data = resp.json()
    print(  # noqa: T201
        f"  Enrolado: profile_id={data['profile_id']} "
        f"enrolled_at={data['enrolled_at']} reference_count={data['reference_count']}"
    )


async def _revoke(url: str) -> None:
    """Unlock once, then revoke the owner's voice consent and stored voiceprints."""
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _unlock(client, url)
        resp = await client.post(
            f"{url}/auth/owner/voice/revoke",
            headers={"X-Iroko-Identity-Token": token},
        )
    if resp.is_error:
        logger.error("Revoke failed: %s %s", resp.status_code, resp.text[:300])
        raise SystemExit(1)
    print("  Revocado: consentimiento y voiceprints borrados.")  # noqa: T201


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Enroll/revoke owner speaker authentication")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--enroll", action="store_true", help="Enroll one voiceprint reference")
    action.add_argument(
        "--revoke", action="store_true", help="Revoke consent and purge voiceprints"
    )
    parser.add_argument(
        "--wav",
        nargs="+",
        metavar="PATH",
        default=None,
        help="Usa un WAV en vez del microfono (ruta al archivo, solo con --enroll)",
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=_DEFAULT_SECONDS,
        help=f"Duracion de la grabacion del microfono (default: {_DEFAULT_SECONDS})",
    )
    parser.add_argument(
        "--device", type=int, default=None, help="Input device index (default: system default)"
    )
    args = parser.parse_args()

    wav_path = " ".join(args.wav) if args.wav else None
    host = "localhost" if settings.server_host == "0.0.0.0" else settings.server_host  # noqa: S104
    url = f"http://{host}:{settings.server_port}"
    if args.enroll:
        asyncio.run(_enroll(url, wav_path, args.seconds, args.device))
    else:
        asyncio.run(_revoke(url))


if __name__ == "__main__":
    main()
