"""Immutable response-planning contracts for the P0.3 chat pilot."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.cognition.models import KnowledgeStatus


class TextTurnPayload(BaseModel):
    """Validated text payload carried by one cognitive event."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1, max_length=64)


class InformationNeed(StrEnum):
    """Closed P0.3 information needs selected without a model."""

    GENERIC_CONVERSATION = "generic_conversation"
    CURRENT_DATE = "current_date"
    EXPLICIT_BIRTH_DATE_AGE = "explicit_birth_date_age"
    RELATIONSHIP_OR_PROFILE = "relationship_or_profile"
    PROTECTED_HOUSEHOLD = "protected_household"
    OWN_CHILDREN_LIST = "own_children_list"
    OWN_CHILDREN_COUNT = "own_children_count"
    AMBIGUOUS_DATE_QUERY = "ambiguous_date_query"
    SCENE_DESCRIPTION = "scene_description"
    ACTIVE_IDENTITY = "active_identity"
    BIOMETRIC_ENROLLMENT = "biometric_enrollment"


class ResponseSource(StrEnum):
    """Origin of a response plan's wording and evidence."""

    DETERMINISTIC = "deterministic"
    LEGACY_TEXT_TURN = "legacy_text_turn"
    CURRENT_PERCEPTION = "current_perception"


class ToolResult(BaseModel):
    """Typed local result available to a response plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_name: str = Field(min_length=1)
    status: KnowledgeStatus
    value: str | int | None = None
    reason: str | None = None


class ResponseClaim(BaseModel):
    """A user-facing claim with an optional supporting deterministic tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    status: KnowledgeStatus
    tool_name: str | None = None


class ResponsePlan(BaseModel):
    """Immutable, bounded outcome for one cognitive text event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    need: InformationNeed
    status: KnowledgeStatus
    source: ResponseSource
    response: str = Field(min_length=1)
    emotion: str = "neutral"
    duration_ms: int = Field(default=0, ge=0)
    tool_results: tuple[ToolResult, ...] = ()
    claims: tuple[ResponseClaim, ...] = ()

    @model_validator(mode="after")
    def _known_claims_require_known_tools(self) -> "ResponsePlan":
        """Reject claims that assert a fact without a known tool result."""
        known_tools = {
            result.tool_name
            for result in self.tool_results
            if result.status is KnowledgeStatus.KNOWN
        }
        for claim in self.claims:
            if claim.status is KnowledgeStatus.KNOWN and claim.tool_name not in known_tools:
                raise ValueError("known claim requires a known tool result")
        return self


class SceneDescriptionRequest(BaseModel):
    """Capability request: only a camera-capable adapter may fulfill this.

    Returned by the controller instead of a closed ``ResponsePlan`` so that
    non-camera channels (chat, streaming) can safely translate it into a
    fixed unavailable plan without ever reading a frame or calling the VLM.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    need: Literal[InformationNeed.SCENE_DESCRIPTION] = InformationNeed.SCENE_DESCRIPTION


def current_perception_plan(description: str) -> ResponsePlan:
    """Build the response plan for a grounded scene description.

    The VLM's description goes directly to speech — never through the
    textual LLM — so this carries `source=CURRENT_PERCEPTION` rather than
    `DETERMINISTIC` or `LEGACY_TEXT_TURN`: current perception is not
    household truth (`KnowledgeStatus.UNKNOWN`), it is what the camera saw
    right now.
    """
    return ResponsePlan(
        need=InformationNeed.SCENE_DESCRIPTION,
        status=KnowledgeStatus.UNKNOWN,
        source=ResponseSource.CURRENT_PERCEPTION,
        response=description,
    )


def scene_unavailable_plan() -> ResponsePlan:
    """Build the fixed response for a scene request this channel cannot fulfill.

    Used by every channel that cannot complete the camera round-trip: vision
    disabled, or a channel (streaming, chat) that has no second-round frame
    upload at all. Never reads a frame or calls the VLM.
    """
    return ResponsePlan(
        need=InformationNeed.SCENE_DESCRIPTION,
        status=KnowledgeStatus.UNKNOWN,
        source=ResponseSource.DETERMINISTIC,
        response="Ahora mismo no puedo mirar desde este canal.",
    )
