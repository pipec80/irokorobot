"""Local text-only chat adapter."""

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter

from server import turn_log
from server.cognition.authorization import evaluate_authorization
from server.cognition.controller import CognitiveController
from server.cognition.household_tools import HouseholdKnowledgeTools
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.response_plan import TextTurnPayload
from server.memory.household_authorization import record_authorization_decision
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
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


def _public_unknown_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
    """Return the public chat actor without accepting identity from HTTP input."""
    actor = ActivePersonContext(
        person_id=None,
        display_name=None,
        status=ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason="Public chat provides no trusted identity evidence",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=event.occurred_at,
    )
    turn_log.log_actor("chat", actor)
    return actor


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process one local text-only conversation turn.

    Args:
        request: Validated text and ephemeral conversation identifier.

    Returns:
        Generated response, emotion, latency, and conversation identifier.
    """
    controller = CognitiveController(
        today=_today,
        legacy_turn=process_text_turn,
        active_person_resolver=_public_unknown_actor,
        policy_evaluator=evaluate_authorization,
        audit_writer=record_authorization_decision,
        household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
    )
    result = await controller.handle(_event_from_request(request))
    turn_log.log_decision("chat", result)
    return ChatResponse(
        response=result.response,
        emotion=result.emotion,
        duration_ms=result.duration_ms,
        conversation_id=request.conversation_id,
    )
