"""Local text-only chat adapter."""

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter

from server.cognition.controller import CognitiveController
from server.cognition.models import CognitiveEvent
from server.cognition.response_plan import TextTurnPayload
from server.schemas_chat import ChatRequest, ChatResponse
from server.text_turn import process_text_turn

router = APIRouter(tags=["Chat"])


def _today() -> date:
    """Return the adapter-owned local date for deterministic P0.3 tools."""
    return date.today()


def _event_from_request(request: ChatRequest) -> CognitiveEvent[TextTurnPayload]:
    """Translate validated HTTP input into one fresh cognitive event."""
    now = datetime.now(UTC)
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=now,
        recorded_at=now,
        source="web.chat",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(
            message=request.message,
            conversation_id=request.conversation_id,
        ),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process one local text-only conversation turn.

    Args:
        request: Validated text and ephemeral conversation identifier.

    Returns:
        Generated response, emotion, latency, and conversation identifier.
    """
    controller = CognitiveController(today=_today, legacy_turn=process_text_turn)
    result = await controller.handle(_event_from_request(request))
    return ChatResponse(
        response=result.response,
        emotion=result.emotion,
        duration_ms=result.duration_ms,
        conversation_id=request.conversation_id,
    )
