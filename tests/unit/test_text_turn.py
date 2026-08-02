from collections.abc import Generator
import inspect
from unittest.mock import AsyncMock, Mock, call

import pytest
from server.exceptions import BrainMemoryError, LLMError
from server.memory import working
from server.schemas import MemoryContext
from server.settings import settings

from server import text_turn


@pytest.fixture(autouse=True)
def _reset_turn_state() -> Generator[None, None, None]:
    """Reset process-local conversation and onboarding state."""
    working._buffers.clear()
    working._emotion_buffers.clear()
    text_turn._onboarding_done = False
    yield
    working._buffers.clear()
    working._emotion_buffers.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stateless_turn_calls_llm_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disabled memory should still produce one typed text result."""
    generate = AsyncMock(return_value=("Hola", "joy"))
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    result = await text_turn.process_text_turn("Hola", "web-a")

    assert result.response == "Hola"
    assert result.emotion == "joy"
    assert result.duration_ms >= 0
    assert result.llm_failed is False
    generate.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversations_isolate_history_and_emotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alternating conversation IDs must never share working memory."""
    context = MemoryContext()
    generate = AsyncMock(side_effect=[("A1", "joy"), ("B1", "sadness"), ("A2", "neutral")])
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn, "_memory_prompt_state", AsyncMock(return_value=(context, False, None, "Owner"))
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    await text_turn.process_text_turn("question-a", "web-a")
    await text_turn.process_text_turn("question-b", "web-b")
    await text_turn.process_text_turn("follow-up-a", "web-a")

    third_call = generate.await_args_list[2]
    assert [turn.content for turn in third_call.kwargs["history"]] == ["question-a", "A1"]
    assert third_call.kwargs["user_emotion"] == "joy"
    assert [turn.content for turn in working.get_history("web-b")] == ["question-b", "B1"]
    assert working.get_recent_emotion("web-b") == "sadness"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preparation_resolves_shared_persistent_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preparation should resolve persistent context independently of channel ID."""
    context = MemoryContext()
    build_context = AsyncMock(return_value=context)
    get_flag = AsyncMock(side_effect=["true", "Owner", "Owner"])
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(text_turn, "build_context", build_context)
    monkeypatch.setattr(text_turn.meta, "get_flag", get_flag)

    first = await text_turn.prepare_text_turn("same question", "web-a")
    second = await text_turn.prepare_text_turn("same question", "web-b")

    assert first.context is context
    assert second.context is context
    assert first.history == []
    assert second.history == []
    assert build_context.await_args_list == [call("same question"), call("same question")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_perception_and_scheduler_reach_expected_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Perception should reach the LLM and successful turns should be recorded."""
    generate = AsyncMock(return_value=("Veo una taza", "neutral"))
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn,
        "_memory_prompt_state",
        AsyncMock(return_value=(MemoryContext(), False, None, None)),
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    await text_turn.process_text_turn(
        "¿Qué ves?",
        "vision-a",
        perception="A blue mug",
        schedule_consolidation=scheduler,
    )

    assert generate.await_args_list[-1].kwargs["perception"] == "A blue mug"
    assert [turn.content for turn in working.get_history("vision-a")] == [
        "¿Qué ves?",
        "Veo una taza",
    ]
    scheduler.assert_called_once_with("¿Qué ves?", "Veo una taza")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_success_without_scheduler_only_updates_working_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful web turn should not consolidate without an injected scheduler."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn, "_memory_prompt_state", AsyncMock(return_value=(None, False, None, None))
    )
    monkeypatch.setattr(
        text_turn.llm, "generate_response", AsyncMock(return_value=("Reply", "neutral"))
    )

    await text_turn.process_text_turn("Question", "web-a")

    assert [turn.content for turn in working.get_history("web-a")] == ["Question", "Reply"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_fallback_does_not_contaminate_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expected provider failures should return a local fallback without recording."""
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn, "_memory_prompt_state", AsyncMock(return_value=(None, False, None, None))
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", AsyncMock(side_effect=LLMError("down")))

    result = await text_turn.process_text_turn(
        "Question",
        "web-a",
        schedule_consolidation=scheduler,
    )

    assert result.response == settings.llm_fallback_phrase
    assert result.emotion == "neutral"
    assert result.llm_failed is True
    assert working.get_history("web-a") == []
    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memory_failure_degrades_to_generation_without_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent memory failure should not prevent a text response."""
    generate = AsyncMock(return_value=("Reply", "neutral"))
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn, "build_context", AsyncMock(side_effect=BrainMemoryError("db down"))
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    result = await text_turn.process_text_turn("Question", "web-a")

    assert result.response == "Reply"
    assert generate.await_args_list[-1].kwargs["context"] is None
    assert generate.await_args_list[-1].kwargs["onboarding"] is False


@pytest.mark.unit
def test_public_apis_are_typed_and_documented() -> None:
    """Public service APIs should expose typed signatures and docstrings."""
    for api in (
        text_turn.prepare_text_turn,
        text_turn.record_text_turn,
        text_turn.process_text_turn,
    ):
        signature = inspect.signature(api)
        assert api.__doc__
        assert signature.return_annotation is not inspect.Signature.empty
        assert all(
            parameter.annotation is not inspect.Parameter.empty
            for parameter in signature.parameters.values()
        )
