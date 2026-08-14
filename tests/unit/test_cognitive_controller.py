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
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
    KnowledgeStatus,
)
from server.cognition.response_plan import TextTurnPayload
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
async def test_controller_calculates_explicit_iso_age_without_legacy_delegate() -> None:
    """Reject an age route that asks the legacy text turn to calculate years."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("¿Qué edad tiene alguien nacido el 2017-12-29?"))

    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.tool_results[0].value == 8
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
        active_person_resolver=lambda _event: actor,
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
        active_person_resolver=lambda _event: actor,
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
            value=("Máximo", "Sofía"),
        )
    )
    controller = CognitiveController(
        today=lambda: date(2026, 8, 12),
        legacy_turn=legacy_turn,
        active_person_resolver=lambda _event: actor,
        household_tools=tools,
        consent_resolver=lambda _event, _actor: ConsentStatus.GRANTED,
    )

    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))

    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Tus hijos son Máximo y Sofía."
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
        active_person_resolver=lambda _event: actor,
        household_tools=tools,
        consent_resolver=lambda _event, _actor: ConsentStatus.GRANTED,
    )

    plan = await controller.handle(_event("¿Cuántos hijos tengo?"))

    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Tienes 2 hijos."
    assert plan.tool_results[0].tool_name == "count_children"
    tools.count_children.assert_awaited_once()
    legacy_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_returns_unknown_for_unfounded_relationship_request() -> None:
    """Reject a legacy relation shortcut before P0.4 establishes entity links."""
    legacy_turn = AsyncMock()
    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)

    plan = await controller.handle(_event("¿Quién es mi padre?"))

    assert plan.status is KnowledgeStatus.UNKNOWN
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
