from collections.abc import Generator
from datetime import UTC, datetime
import inspect
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.exceptions import BrainMemoryError, LLMError
from server.memory import working
from server.schemas import MemoryContext
from server.settings import settings

from server import text_turn

_DEFAULT_SESSION_ID = UUID("11111111-1111-1111-1111-111111111111")


def _manual_evidence(
    *,
    person_id: int = 7,
    session_id: UUID = _DEFAULT_SESSION_ID,
    observed_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> IdentityEvidence:
    """Create explicit manual evidence for a trusted internal test adapter."""
    observed_at = observed_at or datetime(2026, 8, 10, tzinfo=UTC)
    return IdentityEvidence(
        evidence_id=session_id,
        source=IdentityEvidenceSource.MANUAL,
        candidate_person_id=person_id,
        confidence=Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=True,
            reason="Explicit local selection",
        ),
        observed_at=observed_at,
        expires_at=expires_at,
        reference="trusted-local-adapter",
    )


def _identified_person(
    *,
    person_id: int = 7,
    display_name: str = "Sofía",
    session_id: UUID = _DEFAULT_SESSION_ID,
) -> ActivePersonContext:
    """Create an identified manual context for a trusted internal test adapter."""
    observed_at = datetime(2026, 8, 10, tzinfo=UTC)
    return ActivePersonContext(
        person_id=person_id,
        display_name=display_name,
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=True,
            reason="Explicit local selection",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(_manual_evidence(person_id=person_id, session_id=session_id),),
        resolved_at=observed_at,
    )


def _unidentified_person(
    status: ActivePersonStatus,
    evidence: tuple[IdentityEvidence, ...] = (),
) -> ActivePersonContext:
    """Create an explicit non-identified active-person result for one turn."""
    resolved_at = datetime(2026, 8, 10, tzinfo=UTC)
    return ActivePersonContext(
        person_id=None,
        display_name=None,
        status=status,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason="No verified person",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=evidence,
        resolved_at=resolved_at,
    )


@pytest.fixture(autouse=True)
def _reset_turn_state() -> Generator[None, None, None]:
    """Reset process-local conversation state."""
    working._buffers.clear()
    working._emotion_buffers.clear()
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
        text_turn, "_memory_prompt_state", AsyncMock(return_value=(context, False, None))
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    first_person = _identified_person()
    second_person = _identified_person(
        person_id=8,
        display_name="Mateo",
        session_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    await text_turn.process_text_turn("question-a", "web-a", active_person=first_person)
    await text_turn.process_text_turn("question-b", "web-b", active_person=second_person)
    await text_turn.process_text_turn("follow-up-a", "web-a", active_person=first_person)

    third_call = generate.await_args_list[2]
    assert [turn.content for turn in third_call.kwargs["history"]] == ["question-a", "A1"]
    assert third_call.kwargs["user_emotion"] == "joy"
    assert "web-a" not in working._buffers
    assert "web-b" not in working._buffers


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manual_history_scope_uses_opaque_session_and_person_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Display names and public conversation IDs must not scope manual history."""
    generate = AsyncMock(
        side_effect=[("Primera", "neutral"), ("Segunda", "neutral"), ("Tercera", "neutral")]
    )
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn,
        "_memory_prompt_state",
        AsyncMock(return_value=(MemoryContext(), False, None)),
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)
    first = _identified_person(display_name="Sofía")
    renamed = _identified_person(display_name="Sofía Ramírez")
    other_session = _identified_person(session_id=UUID("33333333-3333-3333-3333-333333333333"))

    await text_turn.process_text_turn("primera", "public-a", active_person=first)
    await text_turn.process_text_turn("segunda", "public-b", active_person=renamed)
    await text_turn.process_text_turn("tercera", "public-a", active_person=other_session)

    assert [turn.content for turn in generate.await_args_list[1].kwargs["history"]] == [
        "primera",
        "Primera",
    ]
    assert generate.await_args_list[2].kwargs["history"] == []
    history_keys = set(working._buffers)
    assert all("public" not in key and "Sofía" not in key for key in history_keys)
    assert "session:11111111111111111111111111111111:person:7" in history_keys
    assert "session:33333333333333333333333333333333:person:7" in history_keys


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manual_identified_turn_schedules_legacy_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only manual identity may reach consolidation and must remain attached."""
    generate = AsyncMock(return_value=("Veo una taza", "neutral"))
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn,
        "_memory_prompt_state",
        AsyncMock(return_value=(MemoryContext(), False, None)),
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    person = _identified_person()
    await text_turn.process_text_turn(
        "¿Qué ves?",
        "vision-a",
        perception="A blue mug",
        schedule_consolidation=scheduler,
        active_person=person,
    )

    assert generate.await_args_list[-1].kwargs["perception"] == "A blue mug"
    history_key = next(iter(working._buffers))
    assert [turn.content for turn in working.get_history(history_key)] == [
        "¿Qué ves?",
        "Veo una taza",
    ]
    scheduler.assert_called_once_with("¿Qué ves?", "Veo una taza", person)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_turn_leaves_no_reusable_working_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public chat turn is unknown and clears its one-turn working scope."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn.llm, "generate_response", AsyncMock(return_value=("Reply", "neutral"))
    )

    await text_turn.process_text_turn("Question", "web-a")

    assert working._buffers == {}
    assert working._emotion_buffers == {}


def _seed_identified_scope(active_person: ActivePersonContext) -> str:
    """Seed reusable history and emotion state for one identified manual scope."""
    scope = f"session:{active_person.evidence[0].evidence_id.hex}:person:{active_person.person_id}"
    working.add_turn(scope, "user", "private history")
    working.add_emotion(scope, "joy")
    return scope


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expired_evidence_clears_identified_scope_before_memory_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expired manual evidence must clear reusable state even when memory is disabled."""
    identified = _identified_person()
    scope = _seed_identified_scope(identified)
    expired = _manual_evidence(
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
        expires_at=identified.resolved_at,
    )
    monkeypatch.setattr(settings, "memory_enabled", False)

    await text_turn.prepare_text_turn(
        "Question",
        "public-conversation",
        active_person=_unidentified_person(ActivePersonStatus.UNKNOWN, (expired,)),
    )

    assert scope not in working._buffers
    assert scope not in working._emotion_buffers


@pytest.mark.unit
@pytest.mark.asyncio
async def test_explicit_clear_evidence_removes_identified_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cleared manual selection must discard its prior reusable scope."""
    identified = _identified_person()
    scope = _seed_identified_scope(identified)
    monkeypatch.setattr(settings, "memory_enabled", False)

    await text_turn.prepare_text_turn(
        "Question",
        "public-conversation",
        active_person=_unidentified_person(ActivePersonStatus.UNKNOWN, identified.evidence),
    )

    assert scope not in working._buffers
    assert scope not in working._emotion_buffers


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ambiguous_evidence_clears_all_identified_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ambiguity must remove every candidate's reusable history and emotion."""
    first = _identified_person()
    second = _identified_person(
        person_id=8,
        display_name="Mateo",
        session_id=UUID("44444444-4444-4444-4444-444444444444"),
    )
    first_scope = _seed_identified_scope(first)
    second_scope = _seed_identified_scope(second)
    monkeypatch.setattr(settings, "memory_enabled", False)

    await text_turn.prepare_text_turn(
        "Question",
        "public-conversation",
        active_person=_unidentified_person(
            ActivePersonStatus.AMBIGUOUS,
            first.evidence + second.evidence,
        ),
    )

    assert first_scope not in working._buffers
    assert first_scope not in working._emotion_buffers
    assert second_scope not in working._buffers
    assert second_scope not in working._emotion_buffers


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_fallback_does_not_contaminate_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expected provider failures should return a local fallback without recording."""
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn, "_memory_prompt_state", AsyncMock(return_value=(None, False, None))
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

    result = await text_turn.process_text_turn(
        "Question", "web-a", active_person=_identified_person()
    )

    assert result.response == "Reply"
    assert generate.await_args_list[-1].kwargs["context"] is None
    assert generate.await_args_list[-1].kwargs["onboarding"] is False


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        ActivePersonStatus.UNKNOWN,
        ActivePersonStatus.PROBABLE,
        ActivePersonStatus.AMBIGUOUS,
    ],
)
async def test_nonidentified_turn_skips_persistent_and_working_memory(
    monkeypatch: pytest.MonkeyPatch,
    status: ActivePersonStatus,
) -> None:
    """An uncertain person must get one stateless response without consolidation."""
    build_context = AsyncMock()
    persistent_inputs = AsyncMock()
    get_history = Mock()
    get_emotion = Mock()
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(text_turn, "build_context", build_context)
    monkeypatch.setattr(text_turn, "_memory_prompt_state", persistent_inputs)
    monkeypatch.setattr(text_turn.working, "get_history", get_history)
    monkeypatch.setattr(text_turn.working, "get_recent_emotion", get_emotion)
    monkeypatch.setattr(
        text_turn.llm, "generate_response", AsyncMock(return_value=("Reply", "neutral"))
    )

    await text_turn.process_text_turn(
        "Question",
        "public-conversation",
        active_person=_unidentified_person(status),
        schedule_consolidation=scheduler,
    )

    build_context.assert_not_awaited()
    persistent_inputs.assert_not_awaited()
    get_history.assert_not_called()
    get_emotion.assert_not_called()
    scheduler.assert_not_called()
    assert working._buffers == {}
    assert working._emotion_buffers == {}


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
