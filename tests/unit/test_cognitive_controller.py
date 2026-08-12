"""Unit tests for the bounded P0.3 cognitive controller."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from server.cognition.controller import CognitiveController
from server.cognition.models import CognitiveEvent, KnowledgeStatus
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
