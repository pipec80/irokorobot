"""Local text-only chat adapter."""

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header

from server import turn_log
from server.cognition.authorization import evaluate_authorization
from server.cognition.controller import CognitiveController
from server.cognition.household_tools import HouseholdKnowledgeTools
from server.cognition.identity import ActivePersonContext
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import owner_unlock_service
from server.cognition.response_plan import (
    SceneDescriptionRequest,
    TextTurnPayload,
    scene_unavailable_plan,
)
from server.memory.household_authorization import record_authorization_decision
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.resources import ResourcesDep
from server.schemas_chat import ChatRequest, ChatResponse
from server.text_turn import TextTurnResult, process_text_turn

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
async def chat(
    resources: ResourcesDep,
    request: ChatRequest,
    x_iroko_identity_token: Annotated[str | None, Header(alias="X-Iroko-Identity-Token")] = None,
) -> ChatResponse:
    """Process one local text-only conversation turn.

    Args:
        resources: Shared, lifecycle-owned resources (Plan 0039).
        request: Validated text and ephemeral conversation identifier.
        x_iroko_identity_token: Optional one-use owner unlock token. Absent,
            expired, replayed, or malformed tokens resolve to the public
            unknown actor without disclosing which case occurred.

    Returns:
        Generated response, emotion, latency, conversation identifier, and
        whether this turn consumed a fresh owner unlock grant.
    """
    request_identity = owner_unlock_service.for_request(x_iroko_identity_token)

    async def resolve_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        actor = await request_identity.resolve_actor(event)
        turn_log.log_actor("chat", actor)
        return actor

    async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
        """Delegate to text-turn orchestration with the shared HTTP client."""
        return await process_text_turn(resources.http_client, message, conversation_id)

    controller = CognitiveController(
        today=_today,
        legacy_turn=legacy_turn,
        active_person_resolver=resolve_actor,
        policy_evaluator=evaluate_authorization,
        audit_writer=record_authorization_decision,
        household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
        consent_resolver=request_identity.resolve_consent,
    )
    event = _event_from_request(request)
    decision = await controller.decide(event)
    # Chat has no camera round-trip at all — a scene request always gets the
    # fixed unavailable plan.
    if isinstance(decision, SceneDescriptionRequest):
        result = scene_unavailable_plan()
    elif decision is None:
        result = await controller.handle(event)
    else:
        result = decision
    turn_log.log_decision("chat", result)
    return ChatResponse(
        response=result.response,
        emotion=result.emotion,
        duration_ms=result.duration_ms,
        conversation_id=request.conversation_id,
        authentication_consumed=request_identity.consumed,
    )
