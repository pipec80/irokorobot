"""Local text-only chat adapter."""

from fastapi import APIRouter

from server.schemas_chat import ChatRequest, ChatResponse
from server.text_turn import process_text_turn

router = APIRouter(tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process one local text-only conversation turn.

    Args:
        request: Validated text and ephemeral conversation identifier.

    Returns:
        Generated response, emotion, latency, and conversation identifier.
    """
    result = await process_text_turn(request.message, request.conversation_id)
    return ChatResponse(
        response=result.response,
        emotion=result.emotion,
        duration_ms=result.duration_ms,
        conversation_id=request.conversation_id,
    )
