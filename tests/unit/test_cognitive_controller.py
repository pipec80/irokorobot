"""Unit tests for the bounded P0.3 cognitive controller."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
)
from server.cognition.controller import CognitiveController
from server.cognition.household_tools import HouseholdToolName, HouseholdToolResult
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.intent_resolution import IntentMatch, IntentResolution, MemoryAnswer
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
    KnowledgeStatus,
)
from server.cognition.response_plan import (
    InformationNeed,
    MemoryAnswerReply,
    ResponsePlan,
    ResponseSource,
    SceneDescriptionRequest,
    TextTurnPayload,
)
from server.text_turn import TextTurnResult


def _event(message: str) -> CognitiveEvent[TextTurnPayload]:
    """Build one deterministic chat event for controller tests."""
    occurred_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    return CognitiveEvent(
        event_id=UUID("11111111-1111-1111-1111-111111111111"),
        schema_version=1,
        event_type="text.turn",
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        source="web.chat",
        correlation_id=UUID("22222222-2222-2222-2222-222222222222"),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=message, conversation_id="web-primary"),
    )


def _actor(role: HouseholdRole, person_id: int | None) -> ActivePersonContext:
    """Build one explicit internal actor without deriving identity from text."""
    return ActivePersonContext(
        person_id=person_id,
        display_name="Ada" if person_id is not None else None,
        status=ActivePersonStatus.IDENTIFIED
        if person_id is not None
        else ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=1.0 if person_id is not None else 0.0,
            basis=ConfidenceBasis.ASSERTED
            if person_id is not None
            else ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
        ),
        role=role,
        evidence=(),
        resolved_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
    )


def _resolver(actor: ActivePersonContext):
    """Build an async active-person resolver returning a fixed actor."""

    async def _resolve(_event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        return actor

    return _resolve


def _consent(status: ConsentStatus):
    """Build an async consent resolver returning a fixed status."""

    async def _resolve(
        _event: CognitiveEvent[TextTurnPayload], _actor: ActivePersonContext
    ) -> ConsentStatus:
        return status

    return _resolve


def _decision(request: AuthorizationRequest, status: AuthorizationStatus) -> AuthorizationDecision:
    """Build a request-scoped decision for controller policy fakes."""
    return AuthorizationDecision(
        decision=status,
        action=request.action,
        data_categories=frozenset({"household", "private"}),
        policy_id="test-policy",
        reason="test-safe-reason",
        evaluated_at=request.requested_at,
        correlation_id=request.correlation_id,
    )


@pytest.mark.asyncio
async def test_controller_answers_current_date_without_legacy_delegate() -> None:
    """Reject a date route that sends deterministic knowledge to the LLM path."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("¿Qué fecha es hoy?"))

    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Hoy es 2026-08-12."
    assert plan.tool_results[0].value == "2026-08-12"
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_decide_returns_date_plan_without_legacy_delegate() -> None:
    """Expose a deterministic plan without starting generic text generation."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.decide(_event("¿Qué fecha es hoy?"))

    assert isinstance(plan, ResponsePlan)
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Hoy es 2026-08-12."
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_decide_defers_generic_conversation_without_legacy_delegate() -> None:
    """Allow streaming adapters to retain generic sentence generation."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.decide(_event("Hola, Iroko"))

    assert plan is None
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_calculates_explicit_iso_age_without_legacy_delegate() -> None:
    """Reject an age route that asks the legacy text turn to calculate years."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("¿Qué edad tiene alguien nacido el 2016-10-14?"))

    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.tool_results[0].value == 9
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_denies_private_household_request_before_legacy_delegate() -> None:
    """Reject a protected request that could reach memory or generation first."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))

    assert plan.status is KnowledgeStatus.UNAUTHORIZED
    assert "información familiar privada" in plan.response
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "¿Cómo se llama mi esposa?",
        "¿Cuándo nació Joaquín?",
        "¿Quién es mi mamá?",
        "¿Qué preferencias tiene mi hija?",
    ],
)
async def test_controller_denies_extended_protected_requests_before_legacy_delegate(
    message: str,
) -> None:
    """Expanded household wording must use the existing protected boundary."""
    legacy_turn = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    audit = AsyncMock()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        audit_writer=audit,
    )

    plan = await controller.handle(_event(message))

    assert plan.status is KnowledgeStatus.UNAUTHORIZED
    assert "información familiar privada" in plan.response
    audit.assert_awaited_once()
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_clarifies_ambiguous_stt_date_without_legacy_delegate() -> None:
    """A known STT corruption must not become an incorrect date or LLM turn."""
    legacy_turn = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    audit = AsyncMock()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        audit_writer=audit,
    )

    plan = await controller.handle(_event("¿Qué día soy?"))

    assert plan.status is KnowledgeStatus.UNKNOWN
    assert plan.response == (
        "No entendí si preguntas por la fecha actual o por información personal. "
        "¿Podrías reformularlo?"
    )
    audit.assert_not_awaited()
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_audits_denial_before_protected_legacy_delegate() -> None:
    """A denied household request is audited before any generation can see it."""
    calls: list[str] = []
    legacy_turn = AsyncMock()
    actor = _actor(HouseholdRole.UNKNOWN, None)

    def policy(request: AuthorizationRequest) -> AuthorizationDecision:
        calls.append("policy")
        assert request.action is AuthorizationAction.READ_HOUSEHOLD_DATA
        assert request.visibility == frozenset({DataVisibility.HOUSEHOLD})
        assert request.sensitivity == frozenset({DataSensitivity.PRIVATE})
        assert request.consent is ConsentStatus.NOT_REQUIRED
        return _decision(request, AuthorizationStatus.DENIED)

    async def audit(request: AuthorizationRequest, decision: AuthorizationDecision) -> None:
        calls.append("audit")
        assert decision.decision is AuthorizationStatus.DENIED
        assert request.actor is actor

    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        active_person_resolver=_resolver(actor),
        policy_evaluator=policy,
        audit_writer=audit,
    )

    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))

    assert plan.status is KnowledgeStatus.UNAUTHORIZED
    assert calls == ["policy", "audit"]
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_keeps_allowed_household_request_unknown_until_v4_cutover() -> None:
    """Policy permission alone must not fabricate an unconnected v4 result."""
    legacy_turn = AsyncMock()
    actor = _actor(HouseholdRole.OWNER, 7)
    audit = AsyncMock()
    policy = Mock(side_effect=lambda request: _decision(request, AuthorizationStatus.ALLOWED))
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        active_person_resolver=_resolver(actor),
        policy_evaluator=policy,
        audit_writer=audit,
    )

    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))

    assert plan.status is KnowledgeStatus.UNKNOWN
    assert "todavía" in plan.response
    audit.assert_awaited_once()
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_dispatches_trusted_child_names_without_legacy_delegate() -> None:
    """Use only the injected family tool for the narrow self-child name pattern."""
    legacy_turn = AsyncMock()
    actor = _actor(HouseholdRole.OWNER, 7)
    tools = Mock()
    tools.get_children = AsyncMock(
        return_value=HouseholdToolResult(
            tool_name=HouseholdToolName.GET_CHILDREN,
            status=KnowledgeStatus.KNOWN,
            value=("Joaquín", "Paula"),
        )
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        active_person_resolver=_resolver(actor),
        household_tools=tools,
        consent_resolver=_consent(ConsentStatus.GRANTED),
    )

    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))

    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Tus hijos son Joaquín y Paula."
    assert plan.tool_results[0].tool_name == "get_children"
    tools.get_children.assert_awaited_once()
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_dispatches_trusted_child_count_without_legacy_delegate() -> None:
    """Count children through the injected deterministic tool only."""
    legacy_turn = AsyncMock()
    actor = _actor(HouseholdRole.OWNER, 7)
    tools = Mock()
    tools.count_children = AsyncMock(
        return_value=HouseholdToolResult(
            tool_name=HouseholdToolName.COUNT_CHILDREN,
            status=KnowledgeStatus.KNOWN,
            value=2,
        )
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        active_person_resolver=_resolver(actor),
        household_tools=tools,
        consent_resolver=_consent(ConsentStatus.GRANTED),
    )

    plan = await controller.handle(_event("¿Cuántos hijos tengo?"))

    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Tienes 2 hijos."
    assert plan.tool_results[0].tool_name == "count_children"
    tools.count_children.assert_awaited_once()
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_denies_personal_relationship_request_before_legacy_delegate() -> None:
    """A personal relationship request must not enter legacy generation."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("¿Quién es mi padre?"))

    assert plan.status is KnowledgeStatus.UNAUTHORIZED
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_delegates_generic_conversation_with_original_inputs() -> None:
    """Preserve the existing local text path for safe generic conversation."""
    legacy_turn = AsyncMock(return_value=TextTurnResult("Hola", "joy", 42, False))
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("Hola, Iroko"))

    assert plan.response == "Hola"
    assert plan.emotion == "joy"
    assert plan.duration_ms == 42
    legacy_turn.assert_awaited_once_with("Hola, Iroko", "web-primary")


@pytest.mark.asyncio
async def test_controller_dispatches_the_north_star_children_phrasing() -> None:
    """The exact Plan 0026 acceptance phrasing must reach the deterministic tool."""
    legacy_turn = AsyncMock()
    actor = _actor(HouseholdRole.OWNER, 7)
    tools = Mock()
    tools.get_children = AsyncMock(
        return_value=HouseholdToolResult(
            tool_name=HouseholdToolName.GET_CHILDREN,
            status=KnowledgeStatus.KNOWN,
            value=("Joaquín", "Martina"),
        )
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        active_person_resolver=_resolver(actor),
        household_tools=tools,
        consent_resolver=_consent(ConsentStatus.GRANTED),
    )

    plan = await controller.handle(_event("¿Quiénes son mis hijos?"))

    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Tus hijos son Joaquín y Martina."
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_identity_and_consent_resolve_only_for_protected_branches() -> None:
    """Generic and date requests must never await actor or consent resolution."""
    legacy_turn = AsyncMock(return_value=TextTurnResult("Hola", "joy", 42, False))
    actor = _actor(HouseholdRole.OWNER, 7)
    resolver = AsyncMock(return_value=actor)
    consent = AsyncMock(return_value=ConsentStatus.GRANTED)
    tools = Mock()
    tools.get_children = AsyncMock(
        return_value=HouseholdToolResult(
            tool_name=HouseholdToolName.GET_CHILDREN,
            status=KnowledgeStatus.KNOWN,
            value=("Joaquín", "Martina"),
        )
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        active_person_resolver=resolver,
        household_tools=tools,
        consent_resolver=consent,
    )

    await controller.handle(_event("Hola, Iroko"))
    resolver.assert_not_awaited()
    consent.assert_not_awaited()

    await controller.handle(_event("¿Qué fecha es hoy?"))
    resolver.assert_not_awaited()
    consent.assert_not_awaited()

    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))
    resolver.assert_awaited_once()
    consent.assert_awaited_once()
    assert plan.status is KnowledgeStatus.KNOWN


@pytest.mark.asyncio
async def test_unknown_actor_never_reaches_the_household_tool() -> None:
    """An unresolved actor must fall back to the protected denial, not the tool."""
    legacy_turn = AsyncMock()
    unknown = _actor(HouseholdRole.UNKNOWN, None)
    tools = Mock()
    tools.get_children = AsyncMock()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        active_person_resolver=_resolver(unknown),
        household_tools=tools,
    )

    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))

    assert plan.status is KnowledgeStatus.UNAUTHORIZED
    tools.get_children.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_consumes_the_injected_resolver_instead_of_classifying() -> None:
    """C5: the controller must use the injected resolver, not an inline classifier."""
    legacy_turn = AsyncMock()
    resolver = Mock(
        return_value=IntentResolution(
            need=InformationNeed.CURRENT_DATE, match=IntentMatch.EXACT, rule_id="test.date"
        )
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn, intent_resolver=resolver
    )

    plan = await controller.handle(_event("cualquier texto de prueba"))

    resolver.assert_called_once_with("cualquier texto de prueba")
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Hoy es 2026-08-12."
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_defers_to_legacy_when_resolver_returns_generic() -> None:
    """A resolver returning GENERIC_CONVERSATION must leave decide() returning None."""
    legacy_turn = AsyncMock(return_value=TextTurnResult("Hola", "joy", 42, False))
    resolver = Mock(
        return_value=IntentResolution(
            need=InformationNeed.GENERIC_CONVERSATION, match=IntentMatch.NONE, rule_id=None
        )
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn, intent_resolver=resolver
    )

    decided = await controller.decide(_event("cualquier texto"))
    assert decided is None

    plan = await controller.handle(_event("cualquier texto"))
    assert plan.response == "Hola"
    legacy_turn.assert_awaited_once()


@pytest.mark.asyncio
async def test_controller_rejects_non_iso_age_without_legacy_delegate() -> None:
    """A non-ISO age request stays a safe deterministic unknown, never generic LLM."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("¿Qué edad tengo?"))

    assert plan.status is KnowledgeStatus.UNKNOWN
    assert plan.response == "No puedo calcular la edad sin una fecha de nacimiento ISO válida."
    legacy_turn.assert_not_awaited()
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_decide_returns_scene_capability_without_legacy_or_policy() -> None:
    """C7: a scene request is a capability, never a closed plan or legacy delegate."""
    legacy_turn = AsyncMock()
    policy_evaluator = Mock()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        policy_evaluator=policy_evaluator,
    )

    decision = await controller.decide(_event("¿Qué ves?"))

    assert decision == SceneDescriptionRequest()
    legacy_turn.assert_not_awaited()
    policy_evaluator.assert_not_called()


@pytest.mark.asyncio
async def test_controller_handle_raises_for_scene_capability_instead_of_delegating() -> None:
    """`handle()` must never leak a scene capability into legacy text generation."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    with pytest.raises(RuntimeError):
        await controller.handle(_event("¿Qué ves?"))

    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_biometric_enrollment_returns_fixed_denial_without_camera_or_legacy() -> (
    None
):
    """Any unequivocal enrollment cue is rejected without camera, model, or legacy text."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("Aprende mi cara, soy PersonaDePrueba"))

    assert isinstance(plan, ResponsePlan)
    assert plan.status is KnowledgeStatus.UNKNOWN
    assert (
        plan.response
        == "Todavía no puedo registrar rostros: hace falta administración local y consentimiento."
    )
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_active_identity_greets_the_authenticated_owner() -> None:
    """ACTIVE_IDENTITY names the observed owner and never spends a grant (ADR-0015)."""
    legacy_turn = AsyncMock()
    owner = _actor(HouseholdRole.OWNER, person_id=1)
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        observed_person_resolver=_resolver(owner),
    )

    plan = await controller.handle(_event("¿Quién soy?"))

    assert isinstance(plan, ResponsePlan)
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Eres Ada."
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_active_identity_denies_without_fresh_evidence() -> None:
    """Without a fresh owner grant, ACTIVE_IDENTITY stays the fixed unknown copy."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("¿Quién soy?"))

    assert isinstance(plan, ResponsePlan)
    assert plan.status is KnowledgeStatus.UNKNOWN
    assert plan.response == "Todavía no puedo confirmar quién eres."
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_who_am_i_never_awaits_the_resolver_that_spends_the_grant() -> None:
    """The answer comes from the observed actor; the consuming resolver stays untouched."""
    owner = _actor(HouseholdRole.OWNER, person_id=1)
    spending = AsyncMock(return_value=owner)
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=AsyncMock(),
        active_person_resolver=spending,
        observed_person_resolver=_resolver(owner),
    )

    plan = await controller.handle(_event("¿Quién soy?"))

    assert plan.response == "Eres Ada."
    spending.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_household_question_that_reads_nothing_never_spends_the_grant() -> None:
    """The "not connected yet" answer reads no data, so it must not burn the owner's grant."""
    owner = _actor(HouseholdRole.OWNER, person_id=7)
    spending = AsyncMock(return_value=owner)
    audit = AsyncMock()
    seen: list[ActivePersonContext] = []

    def policy(request: AuthorizationRequest) -> AuthorizationDecision:
        seen.append(request.actor)
        return _decision(request, AuthorizationStatus.ALLOWED)

    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=AsyncMock(),
        active_person_resolver=spending,
        observed_person_resolver=_resolver(owner),
        policy_evaluator=policy,
        audit_writer=audit,
    )

    plan = await controller.handle(_event("¿Cómo se llama mi esposa?"))

    assert plan.status is KnowledgeStatus.UNKNOWN
    assert "todavía" in plan.response
    spending.assert_not_awaited()
    assert seen == [owner]  # the policy still judged the observed actor
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_observed_stranger_is_denied_a_household_question() -> None:
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=AsyncMock(),
        observed_person_resolver=_resolver(_actor(HouseholdRole.UNKNOWN, None)),
    )

    plan = await controller.handle(_event("¿Cómo se llama mi esposa?"))

    assert plan.status is KnowledgeStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_the_children_read_is_the_only_branch_that_spends_the_grant() -> None:
    """Only the branch that reads authorized data awaits the consuming resolver."""
    owner = _actor(HouseholdRole.OWNER, person_id=7)
    spending = AsyncMock(return_value=owner)
    observed = AsyncMock(return_value=owner)
    tools = Mock()
    tools.get_children = AsyncMock(
        return_value=HouseholdToolResult(
            tool_name=HouseholdToolName.GET_CHILDREN,
            status=KnowledgeStatus.KNOWN,
            value=("Joaquín",),
        )
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=AsyncMock(),
        active_person_resolver=spending,
        observed_person_resolver=observed,
        household_tools=tools,
        consent_resolver=AsyncMock(return_value=ConsentStatus.GRANTED),
    )

    await controller.handle(_event("¿Quién soy?"))
    await controller.handle(_event("¿Cómo se llama mi esposa?"))
    spending.assert_not_awaited()

    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))

    spending.assert_awaited_once()
    assert plan.status is KnowledgeStatus.KNOWN


# --- the answer to a memory offer (Plan 0063, ADR 0021 decision 9) ----------------------------


def _legacy(response: str = "Respuesta normal.") -> AsyncMock:
    return AsyncMock(
        return_value=TextTurnResult(
            response=response, emotion="neutral", duration_ms=5, llm_failed=False
        )
    )


@pytest.mark.asyncio
async def test_an_answer_resolves_the_actor_first_and_speaks_the_fixed_result() -> None:
    """The actor is resolved (face and voice) before the answerer reads anything."""
    order: list[str] = []
    actor = _actor(HouseholdRole.OWNER, 7)

    async def observe(_event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        order.append("actor")
        return actor

    async def answer(
        parsed: MemoryAnswer, who: ActivePersonContext, event: CognitiveEvent[TextTurnPayload]
    ) -> MemoryAnswerReply | None:
        order.append("answer")
        assert parsed == MemoryAnswer(accept=True, phrase="el mate")
        assert who is actor
        assert event.correlation_id == UUID("22222222-2222-2222-2222-222222222222")
        return MemoryAnswerReply("Listo, lo guardé.")

    legacy_turn = _legacy()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        observed_person_resolver=observe,
        memory_answerer=answer,
    )

    plan = await controller.handle(_event("Sí, autorizo guardar el mate"))

    assert order == ["actor", "answer"]
    assert plan.need is InformationNeed.MEMORY_ANSWER
    assert plan.response == "Listo, lo guardé."
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, expected",
    [
        ("Sí, autorizo.", MemoryAnswer(accept=True, phrase="")),
        ("No autorizo.", MemoryAnswer(accept=False, phrase="")),
    ],
)
async def test_a_verb_alone_resolves_the_actor_first_and_reaches_the_answerer(
    message: str, expected: MemoryAnswer
) -> None:
    """The short answer is the same shape as the long one: the actor first, then the answerer."""
    order: list[str] = []
    actor = _actor(HouseholdRole.OWNER, 7)

    async def observe(_event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        order.append("actor")
        return actor

    async def answer(
        parsed: MemoryAnswer, who: ActivePersonContext, _event: CognitiveEvent[TextTurnPayload]
    ) -> MemoryAnswerReply | None:
        order.append("answer")
        assert parsed == expected
        assert who is actor
        return MemoryAnswerReply("Listo, lo guardé.")

    legacy_turn = _legacy()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        observed_person_resolver=observe,
        memory_answerer=answer,
    )

    plan = await controller.handle(_event(message))

    assert order == ["actor", "answer"]
    assert plan.need is InformationNeed.MEMORY_ANSWER
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_answer_nobody_can_use_falls_through_to_the_ordinary_turn() -> None:
    """No offer, a weaker actor or a refusal: the reply is exactly the generic one."""
    observe = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
    answer = AsyncMock(return_value=None)
    legacy_turn = _legacy("Claro, el mate es rico.")
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        observed_person_resolver=observe,
        memory_answerer=answer,
    )

    event = _event("Sí, autorizo guardar el mate")
    assert await controller.decide(event) is None
    plan = await controller.handle(event)

    assert plan.need is InformationNeed.GENERIC_CONVERSATION
    assert plan.response == "Claro, el mate es rico."
    legacy_turn.assert_awaited_once()
    # The classic route runs decide() then handle(): the answer is tried once per event.
    observe.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_channel_without_the_answerer_never_resolves_the_actor_for_an_answer() -> None:
    """/chat and /vision/respond inject no answerer: the shape falls through untouched."""
    observe = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
    legacy_turn = _legacy()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        observed_person_resolver=observe,
    )

    assert await controller.decide(_event("Sí, autorizo guardar el mate")) is None
    observe.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_answer_branch_never_spends_a_grant() -> None:
    """The answer uses the observing resolver; the spending one is never awaited."""
    spend = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
    observe = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=_legacy(),
        active_person_resolver=spend,
        observed_person_resolver=observe,
        memory_answerer=AsyncMock(return_value=MemoryAnswerReply("Está bien, no lo guardo.")),
    )

    plan = await controller.decide(_event("No autorizo guardar el mate"))

    assert isinstance(plan, ResponsePlan)
    assert plan.response == "Está bien, no lo guardo."
    spend.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_generic_plan_carries_the_offer_apart_from_the_response() -> None:
    """The offer is spoken after the reply; it is never part of the reply's text."""
    legacy_turn = AsyncMock(
        return_value=TextTurnResult(
            response="Hola.",
            emotion="neutral",
            duration_ms=5,
            llm_failed=False,
            offer="Antes me dijiste que te gusta el mate.",
        )
    )
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("hola"))

    assert plan.response == "Hola."
    assert plan.offer == "Antes me dijiste que te gusta el mate."


def test_an_empty_offer_is_refused_by_the_plan() -> None:
    with pytest.raises(ValueError, match="offer"):
        ResponsePlan(
            need=InformationNeed.GENERIC_CONVERSATION,
            status=KnowledgeStatus.UNKNOWN,
            source=ResponseSource.LEGACY_TEXT_TURN,
            response="Hola.",
            offer="",
        )


@pytest.mark.asyncio
async def test_a_repeated_decide_of_the_same_event_answers_the_offer_once() -> None:
    """D-13: the plan is cached by event id, so decide() then handle() cannot answer twice."""
    observe = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
    answer = AsyncMock(return_value=MemoryAnswerReply("Listo, lo guardé."))
    legacy_turn = _legacy()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        observed_person_resolver=observe,
        memory_answerer=answer,
    )
    event = _event("Sí, autorizo guardar el mate")

    first = await controller.decide(event)
    second = await controller.decide(event)
    handled = await controller.handle(event)

    assert isinstance(first, ResponsePlan)
    assert second is first
    assert handled is first
    answer.assert_awaited_once()
    observe.assert_awaited_once()
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_events_with_the_same_message_are_each_answered() -> None:
    """The cache key is the event id, never the message: a second event is a second answer."""
    answer = AsyncMock(
        side_effect=[
            MemoryAnswerReply("Listo, lo guardé."),
            MemoryAnswerReply("Está bien, no lo guardo."),
        ]
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=_legacy(),
        observed_person_resolver=AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7)),
        memory_answerer=answer,
    )
    first_event = _event("Sí, autorizo guardar el mate")
    second_event = first_event.model_copy(
        update={"event_id": UUID("33333333-3333-3333-3333-333333333333")}
    )

    first = await controller.decide(first_event)
    second = await controller.decide(second_event)

    assert isinstance(first, ResponsePlan)
    assert isinstance(second, ResponsePlan)
    assert first.response == "Listo, lo guardé."
    assert second.response == "Está bien, no lo guardo."
    assert answer.await_count == 2


# --- the retry: only the voice failed (Plan 0068, D-3 and D-4) ---------------------------------


@pytest.mark.asyncio
async def test_a_retry_reply_becomes_a_deterministic_plan_that_expects_a_short_reply() -> None:
    """The typed reply carries the hint into the plan; the actor is still resolved first."""
    order: list[str] = []
    actor = _actor(HouseholdRole.OWNER, 7)

    async def observe(_event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        order.append("actor")
        return actor

    async def answer(
        _parsed: MemoryAnswer, who: ActivePersonContext, _event: CognitiveEvent[TextTurnPayload]
    ) -> MemoryAnswerReply | None:
        order.append("answer")
        assert who is actor
        return MemoryAnswerReply("Dímelo un poco más largo.", expects_short_reply=True)

    legacy_turn = _legacy()
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        observed_person_resolver=observe,
        memory_answerer=answer,
    )

    plan = await controller.handle(_event("Sí, autorizo."))

    assert order == ["actor", "answer"]
    assert plan.need is InformationNeed.MEMORY_ANSWER
    assert plan.source is ResponseSource.DETERMINISTIC
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Dímelo un poco más largo."
    assert plan.expects_short_reply is True
    assert plan.offer is None
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_plain_reply_leaves_the_plan_without_the_hint() -> None:
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=_legacy(),
        observed_person_resolver=AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7)),
        memory_answerer=AsyncMock(return_value=MemoryAnswerReply("Listo, lo guardé.")),
    )

    plan = await controller.handle(_event("Sí, autorizo."))

    assert plan.expects_short_reply is False


@pytest.mark.asyncio
async def test_the_retry_is_cached_per_event_like_any_answer() -> None:
    """decide() then handle() on the classic route must not ask the answerer twice."""
    answer = AsyncMock(return_value=MemoryAnswerReply("Otra vez.", expects_short_reply=True))
    observe = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=_legacy(),
        observed_person_resolver=observe,
        memory_answerer=answer,
    )
    event = _event("Sí, autorizo.")

    first = await controller.decide(event)
    handled = await controller.handle(event)

    assert isinstance(first, ResponsePlan)
    assert handled is first
    assert first.expects_short_reply is True
    answer.assert_awaited_once()
    observe.assert_awaited_once()


def test_a_plan_expects_no_short_reply_unless_told() -> None:
    plan = ResponsePlan(
        need=InformationNeed.CURRENT_DATE,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response="Hoy es 2026-08-12.",
    )

    assert plan.expects_short_reply is False


def test_the_typed_reply_is_frozen_and_defaults_to_no_hint() -> None:
    reply = MemoryAnswerReply("Hola.")

    assert reply.expects_short_reply is False
    with pytest.raises(AttributeError):
        reply.phrase = "otra"  # type: ignore[misc]  # mutation is what this test refutes
