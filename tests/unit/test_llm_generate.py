from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock
from uuid import UUID

import httpx
import pytest
from server.characters import build_system_prompt
from server.characters.iroko import IROKO
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.exceptions import LLMError
from server.settings import settings

from server import llm


def _manual_active_person() -> ActivePersonContext:
    """Create explicit manual identity evidence for prompt-boundary tests."""
    resolved_at = datetime(2026, 8, 10, tzinfo=UTC)
    return ActivePersonContext(
        person_id=7,
        display_name="Paula",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=True,
            reason="Explicit local selection",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(
            IdentityEvidence(
                evidence_id=UUID("11111111-1111-1111-1111-111111111111"),
                source=IdentityEvidenceSource.MANUAL,
                candidate_person_id=7,
                confidence=Confidence(
                    score=1.0,
                    basis=ConfidenceBasis.ASSERTED,
                    calibrated=True,
                    reason="Explicit local selection",
                ),
                observed_at=resolved_at,
                reference="trusted-local-adapter",
            ),
        ),
        resolved_at=resolved_at,
    )


@pytest.mark.unit
async def test_generate_response_empty_text_raises_value_error(
    http_client: httpx.AsyncClient,
) -> None:
    with pytest.raises(ValueError, match="empty"):
        await llm.generate_response(http_client, "")


@pytest.mark.unit
async def test_generate_response_uses_ollama_by_default(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default generation backend must be the local Ollama adapter."""
    local_backend = AsyncMock(return_value=("hola", "joy"))
    monkeypatch.setattr(llm, "_generate_ollama", local_backend)

    response, emotion = await llm.generate_response(http_client, "hello")

    assert response == "hola"
    assert emotion == "joy"
    local_backend.assert_awaited_once_with(
        http_client,
        ANY,  # system prompt built dynamically by build_system_prompt
        [{"role": "user", "content": "hello"}],
    )


@pytest.mark.unit
async def test_generate_response_uses_local_backend_after_invalid_runtime_mutation(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generation must stay local even if a caller corrupts the provider field."""
    local_backend = AsyncMock(return_value=("respuesta local", "joy"))
    monkeypatch.setattr(llm, "_generate_ollama", local_backend)
    monkeypatch.delattr(llm, "_generate_anthropic", raising=False)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    response, emotion = await llm.generate_response(http_client, "hola")

    assert (response, emotion) == ("respuesta local", "joy")
    local_backend.assert_awaited_once_with(
        http_client,
        ANY,
        [{"role": "user", "content": "hola"}],
    )


@pytest.mark.unit
async def test_generate_response_wraps_unexpected_exceptions_as_llmerror(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anything not LLMError/ValueError must be wrapped as LLMError."""

    async def _broken(
        _client: httpx.AsyncClient,
        _prompt: str,
        _msgs: list[dict[str, str]],
    ) -> tuple[str, str]:
        raise RuntimeError("network down")

    monkeypatch.setattr(llm, "_generate_ollama", _broken)

    with pytest.raises(LLMError):
        await llm.generate_response(http_client, "hola")


@pytest.mark.unit
async def test_generate_response_propagates_llmerror_directly(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMError raised by a backend must bubble up unchanged (no double-wrapping)."""

    async def _raises_llm_error(
        _client: httpx.AsyncClient,
        _prompt: str,
        _msgs: list[dict[str, str]],
    ) -> tuple[str, str]:
        raise LLMError("specific error")

    monkeypatch.setattr(llm, "_generate_ollama", _raises_llm_error)

    with pytest.raises(LLMError, match="specific error"):
        await llm.generate_response(http_client, "hola")


# ---------------------------------------------------------------------------
# Context + history support
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_generate_response_without_context_backward_compat(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling without context/history must still route correctly."""
    mock = AsyncMock(return_value=("ok", "neutral"))
    monkeypatch.setattr(llm, "_generate_ollama", mock)

    await llm.generate_response(http_client, "test")

    mock.assert_awaited_once_with(
        http_client,
        ANY,
        [{"role": "user", "content": "test"}],
    )


@pytest.mark.unit
async def test_generate_response_uses_manual_context_for_neutral_display_guidance(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual context adds static guidance without exposing identity or access."""
    mock = AsyncMock(return_value=("hola Paula", "joy"))
    monkeypatch.setattr(llm, "_generate_ollama", mock)

    await llm.generate_response(
        http_client,
        "¿cómo se llaman mis hijos?",
        active_person=_manual_active_person(),
    )

    system_prompt = mock.call_args[0][1]
    assert "PRESENTATION GUIDANCE" in system_prompt
    assert "An explicitly identified manual context is available for this turn." in system_prompt
    assert "Paula" not in system_prompt
    assert "OWNER IDENTITY" not in system_prompt
    assert "your owner" not in system_prompt.lower()
    assert "Do not infer relationships, personal facts, or authorization" in system_prompt


@pytest.mark.unit
async def test_generate_response_puts_the_profile_card_in_the_system_prompt(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 0074: the classic route forwards the authorized card to the prompt."""
    mock = AsyncMock(return_value=("hola", "neutral"))
    monkeypatch.setattr(llm, "_generate_ollama", mock)

    await llm.generate_response(http_client, "hola", profile_card="CARD-CANARY")
    await llm.generate_response(http_client, "hola")

    assert "CARD-CANARY" in mock.call_args_list[0][0][1]
    assert "CARD-CANARY" not in mock.call_args_list[1][0][1]


@pytest.mark.unit
async def test_generate_response_honours_the_profile_card_position(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock = AsyncMock(return_value=("hola", "neutral"))
    monkeypatch.setattr(llm, "_generate_ollama", mock)

    for position in ("with_memory", "before_language"):
        monkeypatch.setattr(settings, "profile_card_position", position)
        await llm.generate_response(
            http_client, "hola", perception="Una mesa.", profile_card="CARD-CANARY"
        )

    with_memory, before_language = (call[0][1] for call in mock.call_args_list)
    assert with_memory.index("CARD-CANARY") < with_memory.index("Percepción visual")
    assert before_language.index("Percepción visual") < before_language.index("CARD-CANARY")


# ---------------------------------------------------------------------------
# build_system_prompt / _format_memory_block (moved to server.characters)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_system_prompt_without_active_person_has_no_display_guidance() -> None:
    """No active person must leave the prompt without display guidance."""
    prompt = build_system_prompt(IROKO)
    assert "PRESENTATION GUIDANCE" not in prompt


# ---------------------------------------------------------------------------
# Classic output contract ownership (P0-C6 Task 1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_generate_response_system_prompt_has_single_classic_contract(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly one classic JSON contract must be appended, never the streaming tag."""
    mock = AsyncMock(return_value=("ok", "neutral"))
    monkeypatch.setattr(llm, "_generate_ollama", mock)

    await llm.generate_response(http_client, "hola")

    system_prompt = mock.call_args[0][1]
    assert system_prompt.count('"response"') == 1
    assert system_prompt.count('"emotion"') == 1
    assert "EMOTION:" not in system_prompt


@pytest.mark.unit
def test_classic_system_prompt_appends_exactly_once() -> None:
    """_classic_system_prompt must append the contract exactly once."""
    prompt = llm._classic_system_prompt("base prompt")

    assert prompt.startswith("base prompt")
    assert prompt.count('"response"') == 1
    assert prompt.count('"emotion"') == 1


@pytest.mark.unit
async def test_generate_ollama_uses_unchanged_response_schema(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_generate_ollama must still force the existing structured JSON schema."""
    mock_chat = AsyncMock(return_value='{"response": "hola", "emotion": "neutral"}')
    monkeypatch.setattr(llm, "ollama_chat", mock_chat)

    await llm._generate_ollama(http_client, "system prompt", [{"role": "user", "content": "hi"}])

    assert mock_chat.call_args.kwargs["format_schema"] == llm._OLLAMA_RESPONSE_SCHEMA


@pytest.mark.unit
async def test_generate_response_raises_llm_error_for_a_non_text_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that answers `{"response": []}` becomes the audible fallback, not TTS input."""
    monkeypatch.setattr(
        llm, "ollama_chat", AsyncMock(return_value='{"response": [], "emotion": "joy"}')
    )
    async with httpx.AsyncClient() as client:  # no request is sent: ollama_chat is stubbed
        with pytest.raises(LLMError):
            await llm.generate_response(client, "hola")
