"""Mini-QA for M3: ``just chat-test`` or ``just chat-test --interactive``."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import logging
from typing import NoReturn
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_URL = "http://localhost:8000"
_DEFAULT_TIMEOUT_S = 60.0
_EXIT_COMMANDS = {"/exit", "/quit", "q"}
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


async def post_chat(
    client: httpx.AsyncClient,
    base_url: str,
    message: str,
    conversation_id: str,
) -> ChatReply:
    """Send one text turn to the running server and validate its response."""
    response = await client.post(
        f"{base_url.rstrip('/')}/chat",
        json={"message": message, "conversation_id": conversation_id},
    )
    response.raise_for_status()
    return parse_chat_reply(response.json(), conversation_id)


def assess_smoke(
    intro: ChatReply,
    isolated: ChatReply,
    recalled: ChatReply,
    marker: str,
) -> tuple[CheckResult, ...]:
    """Assess contract, cross-conversation isolation, and same-ID continuity."""
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
        CheckResult(
            "Continuidad de A",
            normalized_marker in recalled.response.casefold(),
            "la conversación A recordó su clave temporal",
        ),
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
) -> tuple[ChatReply, ChatReply, ChatReply]:
    """Send the three ordered requests that exercise M3 context boundaries."""
    intro = await post_chat(client, base_url, _INTRO_PROMPT.format(secret=marker), conversation_a)
    isolated = await post_chat(client, base_url, _ISOLATION_PROMPT, conversation_b)
    recalled = await post_chat(client, base_url, _RECALL_PROMPT, conversation_a)
    return intro, isolated, recalled


async def run_smoke(base_url: str, timeout_s: float) -> int:
    """Run the deterministic-shape M3 smoke and return its process status."""
    run_token = uuid4().hex
    marker = f"COBALTO-{run_token[:6].upper()}"
    conversation_a = f"m3qa-a-{run_token[:10]}"
    conversation_b = f"m3qa-b-{run_token[:10]}"
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        intro, isolated, recalled = await _run_probes(
            client, base_url, marker, conversation_a, conversation_b
        )

    _log_reply("A presenta clave", intro)
    _log_reply("B consulta sin contexto", isolated)
    _log_reply("A recuerda clave", recalled)
    checks = assess_smoke(intro, isolated, recalled, marker)
    for check in checks:
        logger.info("%s  %s — %s", "PASS" if check.passed else "FAIL", check.name, check.detail)
    return 0 if all(check.passed for check in checks) else 1


async def run_interactive(base_url: str, timeout_s: float, conversation_id: str) -> int:
    """Run a manual multi-turn text conversation until the user exits."""
    logger.info("Conversación %s. Escribe /exit para salir.", conversation_id)
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        while True:
            message = input("Tú> ").strip()
            if message.casefold() in _EXIT_COMMANDS:
                return 0
            if not message:
                continue
            reply = await post_chat(client, base_url, message, conversation_id)
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
