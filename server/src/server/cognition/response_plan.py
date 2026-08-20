"""Immutable response-planning contracts for the P0.3 chat pilot."""

from enum import StrEnum

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


class ResponseSource(StrEnum):
    """Origin of a response plan's wording and evidence."""

    DETERMINISTIC = "deterministic"
    LEGACY_TEXT_TURN = "legacy_text_turn"


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
