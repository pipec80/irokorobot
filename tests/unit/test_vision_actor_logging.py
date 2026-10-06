"""The public visual controller keeps logging its actor on the non-spending branches."""

from datetime import UTC, datetime
import logging
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from server.cognition.models import CognitiveEvent
from server.cognition.response_plan import TextTurnPayload
from server.routers import vision
from server.routers.vision import _vision_controller

_OCCURRED_AT = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _event(message: str) -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID("11111111-1111-1111-1111-111111111111"),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_OCCURRED_AT,
        recorded_at=_OCCURRED_AT,
        source="web.chat",
        correlation_id=UUID("22222222-2222-2222-2222-222222222222"),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=message, conversation_id="vision-actor-log"),
    )


@pytest.mark.unit
@pytest.mark.parametrize("message", ["¿Quién soy?", "¿Cómo se llama mi esposa?"])
async def test_a_branch_that_reads_nothing_still_logs_the_public_vision_actor(
    message: str, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vision, "record_authorization_decision", AsyncMock())
    controller = _vision_controller(AsyncMock())

    with caplog.at_level(logging.INFO):
        await controller.handle(_event(message))

    assert "Turn actor: channel=vision" in "\n".join(r.getMessage() for r in caplog.records)
