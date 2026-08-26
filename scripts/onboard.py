"""onboard.py — one flow to become the robot's owner: identity, PIN, then face.

Orchestrates the existing personal-setup wizard (owner name, children, PIN —
requires the server and robot stopped, since it takes the DB directly) and
the Plan 0029 face-enrollment endpoints (require the server running, since
they go over loopback HTTP). Those two phases need opposite server states,
so this script does whichever phase the current state allows and tells you
the exact next step — safe to re-run after starting or stopping the server
yourself.

Usage:
    just onboard
    just onboard --skip-face
    just onboard --device 1
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

import httpx
from robot.camera_capture import capture_frame
from robot.exceptions import CameraError
from server.exceptions import BrainMemoryError
from server.personal_setup import (
    check_db_available,
    read_personal_setup_status,
    run_personal_setup_wizard,
)
from server.settings import settings

from server import db


def _server_url() -> str:
    """Resolve the server's loopback base URL from settings."""
    host = "localhost" if settings.server_host == "0.0.0.0" else settings.server_host  # noqa: S104
    return f"http://{host}:{settings.server_port}"


async def _server_reachable(url: str) -> bool:
    """Return whether the server answers `GET /health` right now."""
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{url}/health")
    except httpx.HTTPError:
        return False
    return resp.is_success


async def _run_identity_phase() -> None:
    """Run the owner/children/PIN wizard, then point at the next step."""
    print("== Paso 1/2: identidad, hijos y PIN ==")  # noqa: T201
    await check_db_available()
    result = await run_personal_setup_wizard(
        read_text=input, read_secret=getpass.getpass, write_text=print
    )
    if result is None:
        return
    print()  # noqa: T201
    print("Inicia el servidor en otra terminal (just run-server) y vuelve a")  # noqa: T201
    print("correr `just onboard` para enrolar tu cara.")  # noqa: T201


async def _run_face_phase(url: str, device: int) -> None:
    """Unlock with the owner PIN, capture one webcam frame, and enroll it."""
    print("== Paso 2/2: enrolar tu cara ==")  # noqa: T201
    pin = await asyncio.to_thread(getpass.getpass, "Owner PIN: ")
    async with httpx.AsyncClient(timeout=30) as client:
        unlock_resp = await client.post(f"{url}/auth/owner/unlock", json={"pin": pin})
        if unlock_resp.is_error:
            print(f"PIN rechazado: {unlock_resp.status_code}")  # noqa: T201
            raise SystemExit(1)
        token = str(unlock_resp.json()["token"])

        try:
            frame = capture_frame(device)
        except CameraError as exc:
            print(f"Camara no disponible: {exc}")  # noqa: T201
            raise SystemExit(1) from exc

        enroll_resp = await client.post(
            f"{url}/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": token},
            files={"image": ("frame.jpg", frame, "image/jpeg")},
        )
    if enroll_resp.is_error:
        print(f"Enrolamiento fallido: {enroll_resp.status_code} {enroll_resp.text[:200]}")  # noqa: T201
        raise SystemExit(1)

    data = enroll_resp.json()
    print(f"Cara enrolada: profile_id={data['profile_id']}")  # noqa: T201
    if not settings.face_authentication_enabled:
        print("Aviso: FACE_AUTHENTICATION_ENABLED=false — la cara no se usara todavia.")  # noqa: T201
    print()  # noqa: T201
    print("Onboarding completo: identidad, PIN y cara listos.")  # noqa: T201


async def _run(*, skip_face: bool, device: int) -> None:
    """Run the status-driven onboarding state machine against the real DB."""
    await db.open_db()
    try:
        await db.run_migrations()
        status = await read_personal_setup_status()
        if not status.personal_security_ready:
            await _run_identity_phase()
            return

        print("Identidad y PIN ya configurados.")  # noqa: T201
        if skip_face:
            return

        url = _server_url()
        if not await _server_reachable(url):
            print(f"El servidor no responde en {url}.")  # noqa: T201
            print("Inicia `just run-server` en otra terminal y vuelve a correr `just onboard`.")  # noqa: T201
            return

        await _run_face_phase(url, device)
    finally:
        await db.close_db()


def main() -> None:
    """CLI entrypoint for the unified onboarding flow."""
    parser = argparse.ArgumentParser(description="Onboarding unificado: identidad, PIN y cara.")
    parser.add_argument(
        "--skip-face", action="store_true", help="Solo corre identidad y PIN, sin la cara"
    )
    parser.add_argument("--device", type=int, default=0, help="Indice de camara (default: 0)")
    args = parser.parse_args()
    try:
        asyncio.run(_run(skip_face=args.skip_face, device=args.device))
    except BrainMemoryError as exc:
        print(str(exc))  # noqa: T201
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
