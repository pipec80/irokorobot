"""Mini-QA for M3: ``just chat-test`` or ``just chat-test --interactive``.

Short-term continuity belongs to the identified person (ADR 0020), and ``/chat`` identifies
through a one-use owner token that it only observes. The script asks for the owner PIN with
a hidden prompt (never echoed, never logged), unlocks once with the default scope and
presents the token to conversation A; conversation B presents nothing. Without a PIN the
continuity check is reported as not checked instead of failing.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import getpass
import logging
from typing import TYPE_CHECKING, NoReturn
from uuid import uuid4

import httpx

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_DEFAULT_URL = "http://localhost:8000"
_DEFAULT_TIMEOUT_S = 60.0
_EXIT_COMMANDS = {"/exit", "/quit", "q"}
_IDENTITY_HEADER = "X-Iroko-Identity-Token"
_UNLOCK_PATH = "/auth/owner/unlock"
_INTRO_PROMPT = "Recuerda temporalmente esta clave exacta: {secret}. Responde brevemente."
_ISOLATION_PROMPT = "¿Te di una clave temporal en esta conversación? Si no, di DESCONOCIDA."
_RECALL_PROMPT = "¿Cuál es la clave temporal exacta que te di? Inclúyela literalmente."


@dataclass(frozen=True)
class ChatReply:
    """Validated response from POST /chat."""

    response: str
    emotion: str
    duration_ms: int
    conversation_id: str


@dataclass(frozen=True)
class CheckResult:
    """One self-validating smoke-test result."""

    name: str
    passed: bool
    detail: str
    skipped: bool = False


def _require_text(payload: dict[object, object], field: str) -> str:
    """Read a required, non-empty text field from a response payload."""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"/chat response field {field!r} must be non-empty text")
    return value


def parse_chat_reply(payload: object, expected_conversation_id: str) -> ChatReply:
    """Validate and convert the public POST /chat response contract."""
    if not isinstance(payload, dict):
        raise ValueError("/chat response must be a JSON object")
    response = _require_text(payload, "response")
    emotion = _require_text(payload, "emotion")
    conversation_id = _require_text(payload, "conversation_id")
    duration_ms = payload.get("duration_ms")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
        raise ValueError("/chat response field 'duration_ms' must be a non-negative integer")
    if conversation_id != expected_conversation_id:
        raise ValueError("/chat response conversation_id does not match the requested conversation")
    return ChatReply(response, emotion, duration_ms, conversation_id)


async def _read_pin() -> str:
    """Read the owner PIN via getpass, off the event loop. Never logged.

    Returns:
        The PIN, or an empty string when stdin is closed (continuity is then skipped).
    """
    try:
        return await asyncio.to_thread(getpass.getpass, "PIN del dueño (Enter para omitir): ")
    except EOFError:
        return ""


async def obtain_owner_token(
    client: httpx.AsyncClient,
    base_url: str,
    *,
    read_pin: Callable[[], Awaitable[str]] = _read_pin,
) -> str | None:
    """Unlock once with the default scope and return the one-use token, or ``None``.

    Args:
        client: HTTP client bound to the server.
        base_url: Server base URL.
        read_pin: Source of the PIN; the default prompts without echo.

    Returns:
        The opaque token, or ``None`` when the PIN was left empty or was rejected (the
        run then reports continuity as not checked).
    """
    pin = await read_pin()
    if not pin:
        logger.info("Sin PIN: la continuidad no se comprobará.")
        return None
    response = await client.post(f"{base_url.rstrip('/')}{_UNLOCK_PATH}", json={"pin": pin})
    if response.is_error:
        logger.warning("PIN rechazado (%s): la continuidad no se comprobará.", response.status_code)
        return None
    return str(response.json()["token"])


async def post_chat(
    client: httpx.AsyncClient,
    base_url: str,
    message: str,
    conversation_id: str,
    token: str | None = None,
) -> ChatReply:
    """Send one text turn to the running server and validate its response.

    Args:
        client: HTTP client bound to the server.
        base_url: Server base URL.
        message: The user text.
        conversation_id: Public conversation label (never identity).
        token: Optional owner token, presented in the identity header.

    Returns:
        The validated reply.
    """
    headers = {_IDENTITY_HEADER: token} if token else {}
    response = await client.post(
        f"{base_url.rstrip('/')}/chat",
        json={"message": message, "conversation_id": conversation_id},
        headers=headers,
    )
    response.raise_for_status()
    return parse_chat_reply(response.json(), conversation_id)


def assess_smoke(
    intro: ChatReply,
    isolated: ChatReply,
    recalled: ChatReply,
    marker: str,
    *,
    with_token: bool = True,
) -> tuple[CheckResult, ...]:
    """Assess contract, cross-conversation isolation, and the owner's continuity.

    Args:
        intro: Reply to the introduction of the marker (conversation A).
        isolated: Reply of conversation B, which presents no token.
        recalled: Reply of conversation A asked to recall the marker.
        marker: The temporary key that A introduced.
        with_token: Whether A presented an owner token. Without one the server cannot
            give continuity, so that check is skipped rather than failed (ADR 0020 §9).

    Returns:
        The three checks.
    """
    normalized_marker = marker.casefold()
    ids_are_consistent = (
        intro.conversation_id == recalled.conversation_id
        and intro.conversation_id != isolated.conversation_id
    )
    return (
        CheckResult(
            "Contrato JSON",
            ids_are_consistent,
            "3 respuestas válidas, IDs exactos y latencias no negativas",
        ),
        CheckResult(
            "Aislamiento A/B",
            normalized_marker not in isolated.response.casefold(),
            "la conversación B no recibió la clave de A",
        ),
        _continuity_check(recalled, normalized_marker, with_token=with_token),
    )


def _continuity_check(
    recalled: ChatReply, normalized_marker: str, *, with_token: bool
) -> CheckResult:
    """Build the continuity check, or its skipped form when no token was presented."""
    if not with_token:
        return CheckResult(
            "Continuidad de A",
            True,
            "no comprobada: sin PIN no hay token del dueño ni continuidad que medir",
            skipped=True,
        )
    return CheckResult(
        "Continuidad de A",
        normalized_marker in recalled.response.casefold(),
        "la conversación A recordó su clave temporal",
    )


def _log_reply(label: str, reply: ChatReply) -> None:
    """Render one reply without exposing internal prompts or provider data."""
    logger.info("%s [%s, %d ms]\n  %s", label, reply.emotion, reply.duration_ms, reply.response)


async def _run_probes(
    client: httpx.AsyncClient,
    base_url: str,
    marker: str,
    conversation_a: str,
    conversation_b: str,
    token: str | None,
) -> tuple[ChatReply, ChatReply, ChatReply]:
    """Send the three ordered requests that exercise M3 context boundaries.

    A presents the owner token (when there is one); B presents nothing, so it is the
    public unknown and cannot see A's session.
    """
    intro = await post_chat(
        client, base_url, _INTRO_PROMPT.format(secret=marker), conversation_a, token
    )
    isolated = await post_chat(client, base_url, _ISOLATION_PROMPT, conversation_b)
    recalled = await post_chat(client, base_url, _RECALL_PROMPT, conversation_a, token)
    return intro, isolated, recalled


async def run_smoke(
    base_url: str,
    timeout_s: float,
    *,
    read_pin: Callable[[], Awaitable[str]] = _read_pin,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Run the deterministic-shape M3 smoke and return its process status.

    Args:
        base_url: Server base URL.
        timeout_s: Per-request timeout in seconds.
        read_pin: Source of the owner PIN; the default prompts without echo.
        transport: Optional transport, so tests need no network.

    Returns:
        ``0`` when every check passed or was skipped, else ``1``.
    """
    run_token = uuid4().hex
    marker = f"COBALTO-{run_token[:6].upper()}"
    conversation_a = f"m3qa-a-{run_token[:10]}"
    conversation_b = f"m3qa-b-{run_token[:10]}"
    async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as client:
        token = await obtain_owner_token(client, base_url, read_pin=read_pin)
        intro, isolated, recalled = await _run_probes(
            client, base_url, marker, conversation_a, conversation_b, token
        )

    _log_reply("A presenta clave", intro)
    _log_reply("B consulta sin contexto", isolated)
    _log_reply("A recuerda clave", recalled)
    checks = assess_smoke(intro, isolated, recalled, marker, with_token=token is not None)
    for check in checks:
        verdict = "SKIP" if check.skipped else ("PASS" if check.passed else "FAIL")
        logger.info("%s  %s — %s", verdict, check.name, check.detail)
    return 0 if all(check.passed for check in checks) else 1


async def run_interactive(
    base_url: str,
    timeout_s: float,
    conversation_id: str,
    *,
    read_pin: Callable[[], Awaitable[str]] = _read_pin,
) -> int:
    """Run a manual multi-turn text conversation until the user exits.

    The owner token lasts ``OWNER_UNLOCK_TTL_SECONDS``; after that the turns are the public
    unknown again and the session is suspended, not lost.
    """
    logger.info("Conversación %s. Escribe /exit para salir.", conversation_id)
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        token = await obtain_owner_token(client, base_url, read_pin=read_pin)
        while True:
            message = input("Tú> ").strip()
            if message.casefold() in _EXIT_COMMANDS:
                return 0
            if not message:
                continue
            reply = await post_chat(client, base_url, message, conversation_id, token)
            _log_reply("Bot", reply)


def _parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Mini-QA independiente para POST /chat")
    parser.add_argument("--url", default=_DEFAULT_URL, help="URL base del server")
    parser.add_argument("--timeout", type=float, default=_DEFAULT_TIMEOUT_S)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--conversation-id", default=f"manual-{uuid4().hex[:10]}")
    return parser.parse_args()


def main() -> NoReturn:
    """Run the selected QA mode and exit with a useful status code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    args = _parse_args()
    try:
        if args.interactive:
            exit_code = asyncio.run(run_interactive(args.url, args.timeout, args.conversation_id))
        else:
            exit_code = asyncio.run(run_smoke(args.url, args.timeout))
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Chat QA failed: %s", exc)
        exit_code = 1
    except (EOFError, KeyboardInterrupt):
        logger.info("Chat QA interrupted.")
        exit_code = 130
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
