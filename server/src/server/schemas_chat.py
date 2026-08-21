"""Pydantic schemas for the local text-only chat boundary."""

from pydantic import BaseModel, ConfigDict, Field

_CONVERSATION_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"


class ChatRequest(BaseModel):
    """Request body for one text-only conversation turn.

    Attributes:
        message: Non-empty user text after whitespace trimming.
        conversation_id: Ephemeral working-memory identifier.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1)
    conversation_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=_CONVERSATION_ID_PATTERN,
    )


class ChatResponse(BaseModel):
    """Response body for one completed text-only turn.

    Attributes:
        response: Generated assistant text or safe local fallback.
        emotion: Emotion detected during generation.
        duration_ms: Complete text-turn latency in milliseconds.
        conversation_id: Working-memory identifier from the request.
        authentication_consumed: True only if this turn consumed a fresh
            one-use owner unlock grant.
    """

    response: str
    emotion: str
    duration_ms: int = Field(ge=0)
    conversation_id: str
    authentication_consumed: bool = Field(
        default=False,
        description="Whether this turn consumed a fresh one-use owner unlock grant",
    )
