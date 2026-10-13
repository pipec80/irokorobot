from datetime import UTC, datetime
import inspect
import logging
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.exceptions import BrainMemoryError, LLMError
from server.memory import continuity
from server.memory.continuity import SuspendCause, Transition
from server.schemas import MemoryContext
from server.settings import settings

from server import text_turn

_DEFAULT_SESSION_ID = UUID("11111111-1111-1111-1111-111111111111")
_OWNER = 7
_VISITOR = 8


def _evidence(
    source: IdentityEvidenceSource,
    *,
    person_id: int = _OWNER,
    session_id: UUID = _DEFAULT_SESSION_ID,
) -> IdentityEvidence:
    """Create one piece of trusted evidence for an internal test adapter."""
    return IdentityEvidence(
        evidence_id=session_id,
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=True,
            reason="Explicit local selection",
        ),
        observed_at=datetime(2026, 8, 10, tzinfo=UTC),
        expires_at=None,
        reference="trusted-local-adapter",
    )


def _person(
    source: IdentityEvidenceSource,
    *,
    person_id: int = _OWNER,
    display_name: str = "Paula",
    session_id: UUID = _DEFAULT_SESSION_ID,
    assurance: IdentityAssurance = IdentityAssurance.BASIC,
) -> ActivePersonContext:
    """Create an identified context the way `resolve_active_person` would."""
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
        evidence=(_evidence(source, person_id=person_id, session_id=session_id),),
        resolved_at=datetime(2026, 8, 10, tzinfo=UTC),
        assurance=assurance,
    )


def _identified_person(
    *,
    person_id: int = _OWNER,
    display_name: str = "Paula",
    session_id: UUID = _DEFAULT_SESSION_ID,
) -> ActivePersonContext:
    """Create an identified manual context for a trusted internal test adapter."""
    return _person(
        IdentityEvidenceSource.MANUAL,
        person_id=person_id,
        display_name=display_name,
        session_id=session_id,
    )


def _unidentified_person(status: ActivePersonStatus) -> ActivePersonContext:
    """Create an explicit non-identified active-person result for one turn."""
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
        evidence=(),
        resolved_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def _generate(monkeypatch: pytest.MonkeyPatch, *replies: tuple[str, str]) -> AsyncMock:
    """Replace the model call with scripted replies and return the mock."""
    generate = AsyncMock(side_effect=list(replies))
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)
    return generate


def _persistent_context(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace persistent-context retrieval with a spy returning an empty context."""
    prompt_state = AsyncMock(return_value=(MemoryContext(), False, None))
    monkeypatch.setattr(text_turn, "_memory_prompt_state", prompt_state)
    return prompt_state


def _histories(generate: AsyncMock) -> list[list[str] | None]:
    """Return, per model call, the contents of the history it received (None if none)."""
    return [
        None if call.kwargs["history"] is None else [t.content for t in call.kwargs["history"]]
        for call in generate.await_args_list
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stateless_turn_calls_llm_once(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disabled memory should still produce one typed text result."""
    generate = AsyncMock(return_value=("Hola", "joy"))
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    result = await text_turn.process_text_turn(http_client, "Hola", "web-a")

    assert result.response == "Hola"
    assert result.emotion == "joy"
    assert result.duration_ms >= 0
    assert result.llm_failed is False
    generate.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memory_off_never_touches_the_session(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)
    generate = _generate(monkeypatch, ("Hola", "neutral"))
    opened = Mock()
    monkeypatch.setattr(text_turn.continuity, "open_turn", opened)

    await text_turn.process_text_turn(
        http_client, "Hola", "web-a", active_person=_identified_person()
    )

    opened.assert_not_called()
    assert _histories(generate)[0] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_session_follows_the_person_and_not_the_public_conversation_id(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A client-chosen conversation id is not identity (ADR 0020 §3)."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    _persistent_context(monkeypatch)
    generate = _generate(monkeypatch, ("A1", "joy"), ("B1", "sadness"), ("A2", "neutral"))
    person = _identified_person()

    await text_turn.process_text_turn(http_client, "question-a", "web-a", active_person=person)
    await text_turn.process_text_turn(http_client, "question-b", "web-b", active_person=person)
    await text_turn.process_text_turn(http_client, "follow-up-a", "web-a", active_person=person)

    assert _histories(generate) == [
        [],
        ["question-a", "A1"],
        ["question-a", "A1", "question-b", "B1"],
    ]
    assert all(call.kwargs["user_emotion"] is None for call in generate.await_args_list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_another_identified_person_starts_a_fresh_session(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    _persistent_context(monkeypatch)
    generate = _generate(monkeypatch, ("A1", "neutral"), ("B1", "neutral"), ("A2", "neutral"))
    owner = _identified_person()
    visitor = _identified_person(person_id=_VISITOR, display_name="Mateo")

    await text_turn.process_text_turn(http_client, "owner says", "web", active_person=owner)
    await text_turn.process_text_turn(http_client, "visitor says", "web", active_person=visitor)
    await text_turn.process_text_turn(http_client, "owner again", "web", active_person=owner)

    assert _histories(generate) == [[], [], []]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_session_is_keyed_by_person_id_not_by_name_or_evidence_id(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Display names and evidence ids must not scope the session."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    _persistent_context(monkeypatch)
    generate = _generate(
        monkeypatch, ("Primera", "neutral"), ("Segunda", "neutral"), ("Tercera", "neutral")
    )
    first = _identified_person(display_name="Paula")
    renamed = _identified_person(display_name="Paula Ramírez")
    other_evidence = _identified_person(session_id=UUID("33333333-3333-3333-3333-333333333333"))

    await text_turn.process_text_turn(http_client, "primera", "public-a", active_person=first)
    await text_turn.process_text_turn(http_client, "segunda", "public-b", active_person=renamed)
    await text_turn.process_text_turn(
        http_client, "tercera", "public-a", active_person=other_evidence
    )

    assert _histories(generate)[1] == ["primera", "Primera"]
    assert _histories(generate)[2] == [
        "primera",
        "Primera",
        "segunda",
        "Segunda",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manual_identified_turn_schedules_legacy_callback(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only manual identity may reach consolidation and must remain attached."""
    generate = AsyncMock(return_value=("Veo una taza", "neutral"))
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    _persistent_context(monkeypatch)
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    person = _identified_person()
    await text_turn.process_text_turn(
        http_client,
        "¿Qué ves?",
        "vision-a",
        perception="A blue mug",
        schedule_consolidation=scheduler,
        active_person=person,
    )

    assert generate.await_args_list[-1].kwargs["perception"] == "A blue mug"
    assert [turn.content for turn in continuity.open_turn(_OWNER).history] == [
        "¿Qué ves?",
        "Veo una taza",
    ]
    scheduler.assert_called_once_with("¿Qué ves?", "Veo una taza", person)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source, assurance",
    [
        (IdentityEvidenceSource.FACE, IdentityAssurance.BASIC),
        (IdentityEvidenceSource.LOCAL_UNLOCK, IdentityAssurance.STRONG),
    ],
)
async def test_a_face_or_token_identified_turn_has_history_and_nothing_durable(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    source: IdentityEvidenceSource,
    assurance: IdentityAssurance,
) -> None:
    """ADR 0020 §2: continuity opens the history only; the MANUAL gate keeps the rest closed."""
    scheduler = Mock()
    prompt_state = _persistent_context(monkeypatch)
    build_context = AsyncMock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(text_turn, "build_context", build_context)
    generate = _generate(monkeypatch, ("Uno", "neutral"), ("Dos", "neutral"))
    person = _person(source, assurance=assurance)

    for message in ("primero", "segundo"):
        await text_turn.process_text_turn(
            http_client,
            message,
            "web",
            active_person=person,
            schedule_consolidation=scheduler,
        )

    assert _histories(generate) == [[], ["primero", "Uno"]]
    for call in generate.await_args_list:
        assert call.kwargs["context"] is None
        assert call.kwargs["onboarding"] is False
        assert call.kwargs["user_emotion"] is None
    prompt_state.assert_not_awaited()
    build_context.assert_not_awaited()
    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_identified_context_without_assurance_has_no_continuity(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rank rule: `none` never reaches the `basic` minimum, whatever the status says."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    generate = _generate(monkeypatch, ("Uno", "neutral"), ("Dos", "neutral"))
    person = _person(IdentityEvidenceSource.FACE, assurance=IdentityAssurance.NONE)

    await text_turn.process_text_turn(http_client, "primero", "web", active_person=person)
    await text_turn.process_text_turn(http_client, "segundo", "web", active_person=person)

    assert _histories(generate) == [None, None]


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
async def test_a_suspended_turn_reads_nothing_writes_nothing_and_spares_the_session(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    status: ActivePersonStatus,
) -> None:
    """An uncertain person gets one stateless answer; the owner's session survives."""
    build_context = AsyncMock()
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(text_turn, "build_context", build_context)
    prompt_state = _persistent_context(monkeypatch)
    generate = _generate(
        monkeypatch, ("Owner reply", "neutral"), ("Stranger reply", "neutral"), ("Back", "neutral")
    )
    owner = _identified_person()

    await text_turn.process_text_turn(http_client, "owner says", "web", active_person=owner)
    await text_turn.process_text_turn(
        http_client,
        "stranger asks",
        "web",
        active_person=_unidentified_person(status),
        schedule_consolidation=scheduler,
    )
    await text_turn.process_text_turn(http_client, "owner again", "web", active_person=owner)

    assert _histories(generate) == [
        [],
        None,
        ["owner says", "Owner reply"],
    ]
    build_context.assert_not_awaited()
    assert prompt_state.await_count == 2  # the two MANUAL owner turns, never the stranger
    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_suspension_cause_reaches_the_transition_log(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    _generate(monkeypatch, ("Reply", "neutral"))

    with caplog.at_level(logging.INFO, logger=continuity.logger.name):
        await text_turn.process_text_turn(
            http_client,
            "Question",
            "web",
            active_person=_unidentified_person(ActivePersonStatus.AMBIGUOUS),
            suspend_cause=SuspendCause.VETO_MULTIPLE_FACES,
        )

    suspended = [r for r in caplog.records if getattr(r, "reason", None) is Transition.SUSPENDED]
    assert [getattr(r, "cause", None) for r in suspended] == [SuspendCause.VETO_MULTIPLE_FACES]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_turn_leaves_nothing_in_the_session(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public chat turn is unknown: answered and forgotten."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn.llm, "generate_response", AsyncMock(return_value=("Reply", "neutral"))
    )

    await text_turn.process_text_turn(http_client, "Question", "web-a")

    assert continuity.open_turn(_OWNER).history == ()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_fallback_does_not_contaminate_memory(
    http_client: httpx.AsyncClient,
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
        http_client,
        "Question",
        "web-a",
        active_person=_identified_person(),
        schedule_consolidation=scheduler,
    )

    assert result.response == settings.llm_fallback_phrase
    assert result.emotion == "neutral"
    assert result.llm_failed is True
    assert continuity.open_turn(_OWNER).history == ()
    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_connection_refused_logs_without_a_traceback(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unreachable Ollama is expected and already handled (fallback phrase)
    — it must log a short, actionable message, never a full httpx/httpcore
    traceback (Plan 0044 Task 6)."""
    error = LLMError("LLM API call failed")
    error.__cause__ = httpx.ConnectError("refused")
    monkeypatch.setattr(text_turn.llm, "generate_response", AsyncMock(side_effect=error))

    with caplog.at_level(logging.WARNING, logger="server.text_turn"):
        result = await text_turn.process_text_turn(http_client, "Question", "web-b")

    assert result.response == settings.llm_fallback_phrase
    records = [r for r in caplog.records if r.name == "server.text_turn"]
    assert records, "expected a log record for the LLM failure"
    assert all(r.exc_info is None for r in records), "must not log a traceback"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_unexpected_failure_still_logs_a_traceback(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A genuinely unexpected LLM failure (not a connectivity issue) must
    keep its full traceback — only the connectivity case gets quieter."""
    monkeypatch.setattr(
        text_turn.llm, "generate_response", AsyncMock(side_effect=LLMError("malformed output"))
    )

    with caplog.at_level(logging.WARNING, logger="server.text_turn"):
        result = await text_turn.process_text_turn(http_client, "Question", "web-c")

    assert result.response == settings.llm_fallback_phrase
    records = [r for r in caplog.records if r.name == "server.text_turn"]
    assert records, "expected a log record for the LLM failure"
    assert any(r.exc_info is not None for r in records), "must keep the traceback"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memory_failure_degrades_to_generation_without_context(
    http_client: httpx.AsyncClient,
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
        http_client, "Question", "web-a", active_person=_identified_person()
    )

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
