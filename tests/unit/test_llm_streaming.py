"""Unit tests for server.llm_streaming: streaming output contract ownership.

llm_streaming.py is the sole owner of the streaming output contract, appended exactly once to a
format-neutral base prompt from build_system_prompt. Since Plan 0059 (ADR 0018) the contract asks
for plain text only: no JSON, no label, no tag, and no mention of the protocol tag at all — the
emotion of the turn is decided apart from the reply.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.characters.base import CharacterProfile, PersonalityProfile
from server.schemas import MemoryContext, MemoryHit
from server.settings import settings

from server import llm_streaming

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx


def _capturing_stream_factory(captured: dict[str, object]) -> object:
    """Return a fake ollama_chat_stream that records the messages it receives."""

    async def _fake(
        _client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        *,
        model: str,
        **_kwargs: object,
    ) -> AsyncIterator[str]:
        captured["messages"] = messages
        captured["model"] = model
        yield "hola"

    return _fake


@pytest.mark.unit
async def test_generate_response_stream_empty_text_raises_value_error(
    http_client: httpx.AsyncClient,
) -> None:
    with pytest.raises(ValueError, match="empty"):
        async for _ in llm_streaming.generate_response_stream(http_client, ""):
            pass


@pytest.mark.unit
async def test_generate_response_stream_uses_single_plain_text_contract(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The system prompt carries one plain-text contract: no tag, no JSON markers."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", _capturing_stream_factory(captured))

    deltas = [d async for d in llm_streaming.generate_response_stream(http_client, "hola")]

    messages = captured["messages"]
    assert isinstance(messages, list)
    system_prompt = messages[0]["content"]
    assert "EMOTION" not in system_prompt
    assert system_prompt.count(llm_streaming._STREAMING_OUTPUT_CONTRACT) == 1
    assert '"response"' not in system_prompt
    assert '"emotion"' not in system_prompt
    assert "".join(deltas) == "hola"


@pytest.mark.unit
async def test_generate_response_stream_dynamic_profile_has_single_contract(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dynamic (markdown-loaded) profile must also get exactly one contract."""
    dynamic = CharacterProfile(
        name="vendedor",
        base_prompt="Sos un vendedor carismático.",
        onboarding_prompt="",
        personality=PersonalityProfile(),
    )
    monkeypatch.setattr(llm_streaming, "get_character", lambda _name: dynamic)
    captured: dict[str, object] = {}
    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", _capturing_stream_factory(captured))

    async for _ in llm_streaming.generate_response_stream(http_client, "hola"):
        pass

    messages = captured["messages"]
    assert isinstance(messages, list)
    system_prompt = messages[0]["content"]
    assert "EMOTION" not in system_prompt
    assert system_prompt.count(llm_streaming._STREAMING_OUTPUT_CONTRACT) == 1
    assert '"response"' not in system_prompt
    assert '"emotion"' not in system_prompt
    assert "vendedor carismático" in system_prompt


@pytest.mark.unit
async def test_generate_response_stream_puts_the_profile_card_in_the_system_prompt(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 0074: the streaming route forwards the authorized card, in the configured position."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", _capturing_stream_factory(captured))

    async for _ in llm_streaming.generate_response_stream(
        http_client, "hola", profile_card="CARD-CANARY"
    ):
        pass
    messages = captured["messages"]
    assert isinstance(messages, list)
    with_card = messages[0]["content"]
    async for _ in llm_streaming.generate_response_stream(http_client, "hola"):
        pass
    messages = captured["messages"]
    assert isinstance(messages, list)
    without_card = messages[0]["content"]

    assert "CARD-CANARY" in with_card
    assert "CARD-CANARY" not in without_card
    assert with_card.index("CARD-CANARY") < with_card.index("IDIOMA")


@pytest.mark.unit
async def test_generate_response_stream_honours_the_profile_card_position(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", _capturing_stream_factory(captured))
    memory = MemoryContext(
        memories=[
            MemoryHit(
                id=1,
                kind="semantic",
                content="Un dato.",
                summary=None,
                importance=0.5,
                distance=0.1,
            )
        ]
    )
    prompts = []
    for position in ("with_memory", "before_language"):
        monkeypatch.setattr(settings, "profile_card_position", position)
        async for _ in llm_streaming.generate_response_stream(
            http_client, "hola", context=memory, profile_card="CARD-CANARY"
        ):
            pass
        messages = captured["messages"]
        assert isinstance(messages, list)
        prompts.append(messages[0]["content"])

    with_memory, before_language = prompts
    assert with_memory.index("CARD-CANARY") < with_memory.index("--- Memoria activa")
    assert before_language.index("--- Memoria activa") < before_language.index("CARD-CANARY")
    assert before_language.index("CARD-CANARY") < before_language.index("IDIOMA")


@pytest.mark.unit
async def test_generate_response_stream_no_structured_format_argument(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming must never pass a structured `format` schema: the reply is plain text."""
    received_kwargs: dict[str, object] = {}

    async def _fake(
        _client: httpx.AsyncClient, messages: list[dict[str, str]], **kwargs: object
    ) -> AsyncIterator[str]:
        received_kwargs.update(kwargs)
        yield "hola"

    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", _fake)

    async for _ in llm_streaming.generate_response_stream(http_client, "hola"):
        pass

    assert "format_schema" not in received_kwargs
    assert "format" not in received_kwargs


@pytest.mark.unit
def test_streaming_system_prompt_appends_exactly_one_plain_text_contract() -> None:
    prompt = llm_streaming._streaming_system_prompt("base prompt")

    assert prompt.startswith("base prompt")
    assert prompt.endswith(llm_streaming._STREAMING_OUTPUT_CONTRACT)
    assert prompt.count(llm_streaming._STREAMING_OUTPUT_CONTRACT) == 1
    assert "EMOTION" not in prompt
    assert '"response"' not in prompt
    assert '"emotion"' not in prompt


@pytest.mark.unit
def test_the_contract_asks_for_plain_text_and_names_no_tag() -> None:
    contract = llm_streaming._STREAMING_OUTPUT_CONTRACT

    assert "texto plano" in contract
    assert "EMOTION" not in contract.upper()
    assert "emoci" not in contract.lower()


@pytest.mark.unit
@pytest.mark.parametrize("name", ["parse_streaming_emotion", "validate_streaming_body_start"])
def test_the_protocol_functions_are_no_longer_re_exported(name: str) -> None:
    """The temporary re-export is gone: callers import from streaming_protocol."""
    assert not hasattr(llm_streaming, name)
