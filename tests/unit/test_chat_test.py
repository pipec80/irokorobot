"""Tests for the independent M3 chat QA script."""

import pytest

from scripts.chat_test import ChatReply, assess_smoke, parse_chat_reply


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
