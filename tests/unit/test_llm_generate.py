from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import UUID

import pytest
from server.characters import _format_memory_block, build_system_prompt
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
from server.onboarding import OnboardingSlot
from server.schemas import (
    ConversationTurn,
    EntityWithFacts,
    FactRecord,
    MemoryContext,
    MemoryHit,
)

from server import llm


def _manual_active_person() -> ActivePersonContext:
    """Create explicit manual identity evidence for prompt-boundary tests."""
    resolved_at = datetime(2026, 8, 10, tzinfo=UTC)
    return ActivePersonContext(
        person_id=7,
        display_name="Sofía",
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
async def test_generate_response_empty_text_raises_value_error() -> None:
    with pytest.raises(ValueError, match="empty"):
        await llm.generate_response("")


@pytest.mark.unit
async def test_generate_response_routes_to_anthropic_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default provider is 'anthropic' — dispatcher must call _generate_anthropic."""
    mock_anthropic = AsyncMock(return_value=("hola", "joy"))
    mock_ollama = AsyncMock(return_value=("no debería llamarme", "neutral"))
    monkeypatch.setattr(llm, "_generate_anthropic", mock_anthropic)
    monkeypatch.setattr(llm, "_generate_ollama", mock_ollama)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    response, emotion = await llm.generate_response("hello")

    assert response == "hola"
    assert emotion == "joy"
    mock_anthropic.assert_awaited_once_with(
        ANY,  # system prompt built dynamically by build_system_prompt
        [{"role": "user", "content": "hello"}],
    )
    mock_ollama.assert_not_awaited()


@pytest.mark.unit
async def test_generate_response_routes_to_ollama_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_anthropic = AsyncMock(return_value=("no debería llamarme", "neutral"))
    mock_ollama = AsyncMock(return_value=("ollama says hi", "surprise"))
    monkeypatch.setattr(llm, "_generate_anthropic", mock_anthropic)
    monkeypatch.setattr(llm, "_generate_ollama", mock_ollama)
    monkeypatch.setattr(llm.settings, "llm_provider", "ollama")

    response, emotion = await llm.generate_response("hi")

    assert response == "ollama says hi"
    assert emotion == "surprise"
    mock_ollama.assert_awaited_once_with(
        ANY,  # system prompt built dynamically by build_system_prompt
        [{"role": "user", "content": "hi"}],
    )
    mock_anthropic.assert_not_awaited()


@pytest.mark.unit
async def test_generate_response_wraps_unexpected_exceptions_as_llmerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anything not LLMError/ValueError must be wrapped as LLMError."""

    async def _broken(
        _prompt: str,
        _msgs: list[dict[str, str]],
    ) -> tuple[str, str]:
        raise RuntimeError("network down")

    monkeypatch.setattr(llm, "_generate_anthropic", _broken)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    with pytest.raises(LLMError):
        await llm.generate_response("hola")


@pytest.mark.unit
async def test_generate_response_propagates_llmerror_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMError raised by a backend must bubble up unchanged (no double-wrapping)."""

    async def _raises_llm_error(
        _prompt: str,
        _msgs: list[dict[str, str]],
    ) -> tuple[str, str]:
        raise LLMError("specific error")

    monkeypatch.setattr(llm, "_generate_anthropic", _raises_llm_error)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    with pytest.raises(LLMError, match="specific error"):
        await llm.generate_response("hola")


@pytest.mark.unit
async def test_generate_anthropic_raises_when_no_text_block_in_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive path added by audit: non-text content blocks must raise LLMError."""
    fake_tool_block = MagicMock()
    fake_tool_block.type = "tool_use"  # not "text"

    fake_message = MagicMock()
    fake_message.content = [fake_tool_block]

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_message)

    monkeypatch.setattr(llm, "_get_anthropic_client", lambda: fake_client)

    with pytest.raises(LLMError, match="no text block"):
        await llm._generate_anthropic(
            "test prompt",
            [{"role": "user", "content": "hola"}],
        )


@pytest.mark.unit
async def test_generate_anthropic_extracts_first_text_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both tool_use and text blocks exist, the text one must be selected."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '{"response": "hola mundo", "emotion": "joy"}'

    fake_message = MagicMock()
    fake_message.content = [tool_block, text_block]

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_message)

    monkeypatch.setattr(llm, "_get_anthropic_client", lambda: fake_client)

    response, emotion = await llm._generate_anthropic(
        "test prompt",
        [{"role": "user", "content": "hola"}],
    )
    assert response == "hola mundo"
    assert emotion == "joy"


# ---------------------------------------------------------------------------
# Context + history support
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_generate_response_without_context_backward_compat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling without context/history must still route correctly."""
    mock = AsyncMock(return_value=("ok", "neutral"))
    monkeypatch.setattr(llm, "_generate_anthropic", mock)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    await llm.generate_response("test")

    mock.assert_awaited_once_with(
        ANY,
        [{"role": "user", "content": "test"}],
    )


@pytest.mark.unit
async def test_generate_response_with_context_and_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Context block appended to system prompt; history prepended to messages."""
    mock = AsyncMock(return_value=("remembered", "joy"))
    monkeypatch.setattr(llm, "_generate_anthropic", mock)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    ctx = MemoryContext(
        entities=[
            EntityWithFacts(
                id=1,
                name="María",
                type="person",
                facts=[FactRecord(predicate="vive_en", object_value="CDMX")],
            ),
        ],
        memories=[
            MemoryHit(
                id=1,
                kind="episodic",
                content="Le gusta el café",
                summary="Café preference",
                importance=0.8,
                distance=0.1,
            ),
        ],
    )
    history = [
        ConversationTurn(role="user", content="hola"),
        ConversationTurn(role="assistant", content="hola, soy OMNiBot"),
    ]

    await llm.generate_response("qué sabes de María", context=ctx, history=history)

    call_args = mock.call_args
    system_prompt = call_args[0][0]
    messages = call_args[0][1]

    assert "Memoria activa" in system_prompt
    assert "María" in system_prompt
    assert "Café preference" in system_prompt
    assert len(messages) == 3  # 2 history + 1 current
    assert messages[-1] == {"role": "user", "content": "qué sabes de María"}


@pytest.mark.unit
async def test_generate_response_uses_manual_context_for_neutral_display_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual context may guide presentation but cannot assert identity or access."""
    mock = AsyncMock(return_value=("hola Sofía", "joy"))
    monkeypatch.setattr(llm, "_generate_anthropic", mock)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    await llm.generate_response(
        "¿cómo se llaman mis hijos?",
        active_person=_manual_active_person(),
    )

    system_prompt = mock.call_args[0][0]
    assert "PRESENTATION GUIDANCE" in system_prompt
    assert "Sofía" in system_prompt
    assert "OWNER IDENTITY" not in system_prompt
    assert "your owner" not in system_prompt.lower()
    assert "Do not infer relationships, personal facts, or authorization" in system_prompt


# ---------------------------------------------------------------------------
# build_system_prompt / _format_memory_block (moved to server.characters)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_system_prompt_empty_context_excludes_memory_block() -> None:
    """Empty context must not add any memory block to the prompt."""
    ctx = MemoryContext(entities=[], memories=[])
    prompt = build_system_prompt(IROKO, ctx)
    assert "Memoria activa" not in prompt


@pytest.mark.unit
def test_build_system_prompt_without_active_person_has_no_display_guidance() -> None:
    """No active person must leave the prompt without display guidance."""
    prompt = build_system_prompt(IROKO, None)
    assert "PRESENTATION GUIDANCE" not in prompt


@pytest.mark.unit
def test_build_system_prompt_with_slot_names_the_goal() -> None:
    """During onboarding the checklist injects the ONE datum to ask for."""
    slot = OnboardingSlot(key="vive_en", question_hint="dónde vive")

    prompt = build_system_prompt(IROKO, None, onboarding=True, onboarding_slot=slot)

    assert "PRÓXIMO OBJETIVO de la entrevista" in prompt
    assert "dónde vive" in prompt


@pytest.mark.unit
def test_build_system_prompt_onboarding_without_slot_has_no_goal() -> None:
    """Degraded memory can leave onboarding on with no slot — no goal block.

    The character prompt REFERENCES "PRÓXIMO OBJETIVO", so the assertion
    targets the goal template's unique opening phrase.
    """
    prompt = build_system_prompt(IROKO, None, onboarding=True)

    assert "PRIMER ENCUENTRO" in prompt
    assert "PRÓXIMO OBJETIVO de la entrevista" not in prompt


@pytest.mark.unit
def test_build_system_prompt_slot_ignored_outside_onboarding() -> None:
    """After onboarding the interview goal must never reappear."""
    slot = OnboardingSlot(key="le_gusta", question_hint="qué le gusta hacer")

    prompt = build_system_prompt(IROKO, None, onboarding=False, onboarding_slot=slot)

    assert "PRÓXIMO OBJETIVO de la entrevista" not in prompt


@pytest.mark.unit
async def test_generate_response_forwards_onboarding_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The slot's hint must reach the system prompt sent to the backend."""
    mock = AsyncMock(return_value=("¿cuándo naciste?", "neutral"))
    monkeypatch.setattr(llm, "_generate_anthropic", mock)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")
    slot = OnboardingSlot(key="fecha_nacimiento", question_hint="cuándo nació")

    await llm.generate_response("me llamo Felipe", onboarding=True, onboarding_slot=slot)

    system_prompt = mock.call_args[0][0]
    assert "PRÓXIMO OBJETIVO de la entrevista" in system_prompt
    assert "cuándo nació" in system_prompt


@pytest.mark.unit
def test_format_memory_block_with_data_includes_entity_and_memory() -> None:
    """Non-empty context must include entity names and memory summaries."""
    ctx = MemoryContext(
        entities=[
            EntityWithFacts(
                id=1,
                name="Carlos",
                type="person",
                facts=[FactRecord(predicate="trabajo", object_value="ingeniero")],
            ),
        ],
        memories=[
            MemoryHit(
                id=1,
                kind="semantic",
                content="Carlos prefiere té verde",
                summary="Té verde preference",
                importance=0.6,
                distance=0.2,
            ),
        ],
    )
    block = _format_memory_block(ctx)
    assert "Carlos" in block
    assert "ingeniero" in block
    assert "Té verde preference" in block
    assert "Memoria activa" in block
