"""Tests for the independent M3 chat QA script."""

import json

import httpx
import pytest

from scripts.chat_test import (
    ChatReply,
    assess_smoke,
    obtain_owner_token,
    parse_chat_reply,
    run_smoke,
)

_GRANT = "token-canary-1"


def test_parse_chat_reply_accepts_the_public_contract() -> None:
    """A complete valid response is converted to a typed reply."""
    payload = {
        "response": "Hola",
        "emotion": "neutral",
        "duration_ms": 42,
        "conversation_id": "qa-a",
    }

    reply = parse_chat_reply(payload, expected_conversation_id="qa-a")

    assert reply == ChatReply(
        response="Hola",
        emotion="neutral",
        duration_ms=42,
        conversation_id="qa-a",
    )


def test_parse_chat_reply_rejects_a_mismatched_conversation() -> None:
    """A response cannot silently cross the requested conversation boundary."""
    payload = {
        "response": "Hola",
        "emotion": "neutral",
        "duration_ms": 42,
        "conversation_id": "qa-b",
    }

    with pytest.raises(ValueError, match="conversation_id"):
        parse_chat_reply(payload, expected_conversation_id="qa-a")


def test_assess_smoke_passes_when_context_is_isolated_and_recalled() -> None:
    """The probe passes when B lacks A's token and A recalls it."""
    intro = ChatReply("Entendido", "neutral", 10, "qa-a")
    isolated = ChatReply("DESCONOCIDA", "neutral", 11, "qa-b")
    recalled = ChatReply("La clave es COBALTO-731", "neutral", 12, "qa-a")

    checks = assess_smoke(intro, isolated, recalled, marker="COBALTO-731")

    assert [check.passed for check in checks] == [True, True, True]


def test_assess_smoke_fails_when_context_leaks_to_another_conversation() -> None:
    """The isolation probe fails if conversation B receives A's token."""
    intro = ChatReply("Entendido", "neutral", 10, "qa-a")
    leaked = ChatReply("La clave es COBALTO-731", "neutral", 11, "qa-b")
    recalled = ChatReply("La clave es COBALTO-731", "neutral", 12, "qa-a")

    checks = assess_smoke(intro, leaked, recalled, marker="COBALTO-731")

    assert checks[1].passed is False


def test_assess_smoke_without_a_token_reports_continuity_as_not_checked() -> None:
    """ADR 0020 §9: with no owner token the server cannot give continuity, so it is skipped."""
    intro = ChatReply("Entendido", "neutral", 10, "qa-a")
    isolated = ChatReply("DESCONOCIDA", "neutral", 11, "qa-b")
    recalled = ChatReply("No tengo esa clave", "neutral", 12, "qa-a")

    checks = assess_smoke(intro, isolated, recalled, marker="COBALTO-731", with_token=False)

    assert [check.passed for check in checks] == [True, True, True]
    assert [check.skipped for check in checks] == [False, False, True]
    assert "no comprobada" in checks[2].detail


def test_assess_smoke_with_a_token_still_requires_the_recall() -> None:
    intro = ChatReply("Entendido", "neutral", 10, "qa-a")
    isolated = ChatReply("DESCONOCIDA", "neutral", 11, "qa-b")
    forgotten = ChatReply("No tengo esa clave", "neutral", 12, "qa-a")

    checks = assess_smoke(intro, isolated, forgotten, marker="COBALTO-731", with_token=True)

    assert checks[2].passed is False
    assert checks[2].skipped is False


def _server(seen: list[tuple[str, str | None]], *, unlock_status: int = 200) -> httpx.MockTransport:
    """A fake server: records (path, token header); only a request with the token recalls."""
    remembered: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("X-Iroko-Identity-Token")
        seen.append((request.url.path, token))
        if request.url.path == "/auth/owner/unlock":
            body = json.loads(request.content)
            assert "scope" not in body  # the default scope: the token is only observed
            if unlock_status != 200:
                return httpx.Response(unlock_status, json={"detail": "no"})
            return httpx.Response(200, json={"token": _GRANT, "expires_at": "x", "scope": "x"})
        payload = json.loads(request.content)
        message: str = payload["message"]
        if "exacta: " in message:  # the introduction: remember what was said
            remembered["marker"] = message.split("exacta: ")[1].split(".", maxsplit=1)[0]
            reply = "Entendido."
        elif "clave temporal exacta que te di" in message:  # the recall
            marker = remembered.get("marker")
            reply = f"La clave es {marker}" if token and marker else "No tengo esa clave."
        else:  # the isolation probe
            reply = "DESCONOCIDA"
        return httpx.Response(
            200,
            json={
                "response": reply,
                "emotion": "neutral",
                "duration_ms": 1,
                "conversation_id": payload["conversation_id"],
                "authentication_consumed": False,
            },
        )

    return httpx.MockTransport(handle)


async def _pin_is(value: str) -> str:
    return value


async def test_obtain_owner_token_unlocks_with_the_default_scope() -> None:
    seen: list[tuple[str, str | None]] = []
    async with httpx.AsyncClient(transport=_server(seen), base_url="http://test") as client:
        token = await obtain_owner_token(client, "http://test", read_pin=lambda: _pin_is("0000"))

    assert token == _GRANT
    assert seen == [("/auth/owner/unlock", None)]


async def test_an_empty_pin_means_no_token_and_no_request() -> None:
    seen: list[tuple[str, str | None]] = []
    async with httpx.AsyncClient(transport=_server(seen), base_url="http://test") as client:
        token = await obtain_owner_token(client, "http://test", read_pin=lambda: _pin_is(""))

    assert token is None
    assert seen == []


async def test_a_rejected_pin_means_no_token_and_the_run_goes_on() -> None:
    seen: list[tuple[str, str | None]] = []
    transport = _server(seen, unlock_status=401)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        token = await obtain_owner_token(client, "http://test", read_pin=lambda: _pin_is("bad"))

    assert token is None


async def test_the_smoke_sends_the_token_to_a_and_nothing_to_b() -> None:
    seen: list[tuple[str, str | None]] = []

    code = await run_smoke(
        "http://test", 5.0, read_pin=lambda: _pin_is("0000"), transport=_server(seen)
    )

    chat = [token for path, token in seen if path == "/chat"]
    assert chat == [_GRANT, None, _GRANT]  # A introduces, B asks, A recalls
    assert code == 0


async def test_the_smoke_without_a_token_does_not_fail_for_missing_continuity() -> None:
    seen: list[tuple[str, str | None]] = []

    code = await run_smoke(
        "http://test", 5.0, read_pin=lambda: _pin_is(""), transport=_server(seen)
    )

    assert [token for path, token in seen if path == "/chat"] == [None, None, None]
    assert code == 0


async def test_a_closed_stdin_means_no_pin_and_the_smoke_still_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`just chat-test < NUL` must skip the continuity check, not abort the run."""
    seen: list[tuple[str, str | None]] = []

    def closed(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("scripts.chat_test.getpass.getpass", closed)

    code = await run_smoke("http://test", 5.0, transport=_server(seen))

    assert code == 0
    assert [path for path, _ in seen].count("/auth/owner/unlock") == 0
