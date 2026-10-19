import asyncio
from datetime import UTC, datetime
import inspect
import logging
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
from server.claim_guard import REPLACEMENT
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
from server.memory.candidate_dialogue import PendingOffer
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
async def test_a_reply_that_claims_to_have_saved_is_replaced(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing the model says stores anything (Plan 0064, D-2): the claim is false."""
    monkeypatch.setattr(settings, "memory_enabled", False)
    _generate(monkeypatch, ("Perfecto, lo guardé.", "joy"))

    result = await text_turn.process_text_turn(http_client, "Me gusta el mate", "web-a")

    assert result.response == REPLACEMENT
    assert result.emotion == "joy"
    assert result.llm_failed is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_reply_without_a_claim_reaches_the_response_unchanged(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)
    _generate(monkeypatch, ("Anotado. ¿Y qué más te gusta?", "neutral"))

    result = await text_turn.process_text_turn(http_client, "Me gusta el mate", "web-a")

    assert result.response == "Anotado. ¿Y qué más te gusta?"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_claim_is_never_recorded_in_the_session_history(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The history keeps what was actually said, so the model never reads its own false claim."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn, "_memory_prompt_state", AsyncMock(return_value=(None, False, None))
    )
    _generate(monkeypatch, ("Lo guardé.", "neutral"))

    await text_turn.process_text_turn(
        http_client, "Me gusta el mate", "web-a", active_person=_identified_person()
    )

    assert [turn.content for turn in continuity.open_turn(_OWNER).history] == [
        "Me gusta el mate",
        REPLACEMENT,
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_fallback_phrase_is_not_touched_by_the_guard(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(settings, "llm_fallback_phrase", "Lo guardé, dame unos segundos.")
    monkeypatch.setattr(text_turn.llm, "generate_response", AsyncMock(side_effect=LLMError("down")))

    result = await text_turn.process_text_turn(http_client, "Hola", "web-a")

    assert result.response == "Lo guardé, dame unos segundos."
    assert result.llm_failed is True


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
async def test_a_face_identified_turn_schedules_a_proposal_with_the_users_words_only(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0021 §10: the callback gets the user's text and the actor, never the reply."""
    generate = AsyncMock(return_value=("Veo una taza", "neutral"))
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)
    person = _person(IdentityEvidenceSource.FACE)

    await text_turn.process_text_turn(
        http_client,
        "me gusta el mate",
        "web",
        schedule_proposal=scheduler,
        active_person=person,
    )

    scheduler.assert_called_once_with("me gusta el mate", person)
    assert "Veo una taza" not in str(scheduler.call_args)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_manual_identified_turn_keeps_its_history_but_proposes_nothing(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retired MANUAL gate no longer reaches a writer; the persistent context keeps it."""
    generate = AsyncMock(return_value=("Veo una taza", "neutral"))
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    _persistent_context(monkeypatch)
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    person = _identified_person()
    await text_turn.process_text_turn(
        http_client,
        "¿Qué ves?",
        "vision-a",
        perception="A blue mug",
        schedule_proposal=scheduler,
        active_person=person,
    )

    assert generate.await_args_list[-1].kwargs["perception"] == "A blue mug"
    assert [turn.content for turn in continuity.open_turn(_OWNER).history] == [
        "¿Qué ves?",
        "Veo una taza",
    ]
    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_kill_switch_stops_the_proposal_before_it_is_scheduled(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    _generate(monkeypatch, ("Uno", "neutral"))

    await text_turn.process_text_turn(
        http_client,
        "me gusta el mate",
        "web",
        schedule_proposal=scheduler,
        active_person=_person(IdentityEvidenceSource.FACE),
    )

    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [IdentityEvidenceSource.LOCAL_UNLOCK, IdentityEvidenceSource.MANUAL],
)
async def test_a_token_or_manual_turn_never_proposes(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, source: IdentityEvidenceSource
) -> None:
    """A PIN grant proves the PIN, not the speaker: no candidate from a token (ADR 0021 §3)."""
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    _persistent_context(monkeypatch)
    _generate(monkeypatch, ("Uno", "neutral"))

    await text_turn.process_text_turn(
        http_client,
        "me gusta el mate",
        "web",
        schedule_proposal=scheduler,
        active_person=_person(source, assurance=IdentityAssurance.STRONG),
    )

    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [ActivePersonStatus.UNKNOWN, ActivePersonStatus.PROBABLE, ActivePersonStatus.AMBIGUOUS],
)
async def test_an_unidentified_turn_never_proposes(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, status: ActivePersonStatus
) -> None:
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    _generate(monkeypatch, ("Uno", "neutral"))

    await text_turn.process_text_turn(
        http_client,
        "me gusta el mate",
        "web",
        schedule_proposal=scheduler,
        active_person=_unidentified_person(status),
    )

    scheduler.assert_not_called()


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
            schedule_proposal=scheduler,
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
        schedule_proposal=scheduler,
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
        schedule_proposal=scheduler,
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


# --- the spoken offer (Plan 0063, ADR 0021 decision 9) ----------------------------------------


def _pending() -> PendingOffer:
    return PendingOffer(
        candidate_id=1,
        subject_person_id=_OWNER,
        phrase="Antes me dijiste que te gusta el mate.",
        actor=_person(IdentityEvidenceSource.FACE, assurance=IdentityAssurance.STRONG),
        correlation_id=UUID(int=1),
    )


def _offer_on(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    commit = AsyncMock(return_value="Antes me dijiste que te gusta el mate.")
    monkeypatch.setattr(text_turn, "commit_offer", commit)
    return commit


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_offer_is_prepared_while_the_reply_is_generated(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The voice check runs concurrently: generation waits for it and does not deadlock."""
    commit = _offer_on(monkeypatch)
    prepared = asyncio.Event()

    async def generate(*_args: object, **_kwargs: object) -> tuple[str, str]:
        await asyncio.wait_for(prepared.wait(), timeout=2)
        return "Hola.", "neutral"

    async def prepare(_actor: ActivePersonContext) -> PendingOffer:
        prepared.set()
        return _pending()

    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    result = await text_turn.process_text_turn(
        http_client,
        "hola",
        "voice",
        active_person=_person(IdentityEvidenceSource.FACE),
        prepare_offer=prepare,
    )

    assert result.response == "Hola."
    assert result.offer == "Antes me dijiste que te gusta el mate."
    commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_offer_never_enters_the_session_history(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offer_on(monkeypatch)
    _generate(monkeypatch, ("Hola.", "neutral"))

    await text_turn.process_text_turn(
        http_client,
        "hola",
        "voice",
        active_person=_person(IdentityEvidenceSource.FACE),
        prepare_offer=AsyncMock(return_value=_pending()),
    )

    assert [turn.content for turn in continuity.open_turn(_OWNER).history] == ["hola", "Hola."]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_fallback_reply_carries_no_offer(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = _offer_on(monkeypatch)
    monkeypatch.setattr(text_turn.llm, "generate_response", AsyncMock(side_effect=LLMError("down")))

    result = await text_turn.process_text_turn(
        http_client,
        "hola",
        "voice",
        active_person=_person(IdentityEvidenceSource.FACE),
        prepare_offer=AsyncMock(return_value=_pending()),
    )

    assert result.llm_failed
    assert result.offer is None
    commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor",
    [
        _person(IdentityEvidenceSource.LOCAL_UNLOCK),
        _person(IdentityEvidenceSource.MANUAL),
        _unidentified_person(ActivePersonStatus.UNKNOWN),
        None,
    ],
)
async def test_only_a_face_identified_speaker_is_ever_offered_anything(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    actor: ActivePersonContext | None,
) -> None:
    _offer_on(monkeypatch)
    _generate(monkeypatch, ("Hola.", "neutral"))
    prepare = AsyncMock(return_value=_pending())

    result = await text_turn.process_text_turn(
        http_client, "hola", "voice", active_person=actor, prepare_offer=prepare
    )

    assert result.offer is None
    prepare.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("switch", ["memory_enabled", "memory_candidates_enabled"])
async def test_either_switch_off_prepares_no_offer(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, switch: str
) -> None:
    _offer_on(monkeypatch)
    monkeypatch.setattr(settings, switch, False)
    _generate(monkeypatch, ("Hola.", "neutral"))
    prepare = AsyncMock(return_value=_pending())

    result = await text_turn.process_text_turn(
        http_client,
        "hola",
        "voice",
        active_person=_person(IdentityEvidenceSource.FACE),
        prepare_offer=prepare,
    )

    assert result.offer is None
    prepare.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_offer_the_policy_or_the_store_refused_is_not_spoken(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = _offer_on(monkeypatch)
    commit.return_value = None
    _generate(monkeypatch, ("Hola.", "neutral"))

    result = await text_turn.process_text_turn(
        http_client,
        "hola",
        "voice",
        active_person=_person(IdentityEvidenceSource.FACE),
        prepare_offer=AsyncMock(return_value=_pending()),
    )

    assert result.offer is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_committing_the_offer_never_counts_as_generation_time(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = _offer_on(monkeypatch)

    async def slow_commit(_pending: PendingOffer) -> str:
        await asyncio.sleep(0.3)
        return "Antes me dijiste que te gusta el mate."

    commit.side_effect = slow_commit
    _generate(monkeypatch, ("Hola.", "neutral"))

    result = await text_turn.process_text_turn(
        http_client,
        "hola",
        "voice",
        active_person=_person(IdentityEvidenceSource.FACE),
        prepare_offer=AsyncMock(return_value=_pending()),
    )

    assert result.offer is not None
    assert result.duration_ms < 200


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_turn_cancels_the_offer_it_was_preparing(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offer_on(monkeypatch)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def never_answers(*_args: object, **_kwargs: object) -> tuple[str, str]:
        await asyncio.Event().wait()
        return "x", "neutral"

    async def prepare(_actor: ActivePersonContext) -> PendingOffer:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return _pending()

    monkeypatch.setattr(text_turn.llm, "generate_response", never_answers)
    turn = asyncio.create_task(
        text_turn.process_text_turn(
            http_client,
            "hola",
            "voice",
            active_person=_person(IdentityEvidenceSource.FACE),
            prepare_offer=prepare,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)

    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    await asyncio.wait_for(cancelled.wait(), timeout=2)


async def test_a_preparation_that_raises_costs_the_reply_nothing() -> None:
    """A seam injected later may raise: the built reply must not turn into a 500."""

    async def boom() -> PendingOffer | None:
        raise RuntimeError("canary")

    task = asyncio.ensure_future(boom())

    assert await text_turn.finish_offer(task, reply_failed=False) is None


def test_the_offer_never_shows_in_the_repr_of_a_turn_result() -> None:
    """A stray ``%s`` of the result must not print the value the offer carries."""
    result = text_turn.TextTurnResult(
        response="hola",
        emotion="neutral",
        duration_ms=1,
        llm_failed=False,
        offer="Antes me dijiste que te gusta el quokka.",
    )

    assert "quokka" not in repr(result)
