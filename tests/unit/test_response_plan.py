"""Unit tests for the P0.3 response-plan contracts."""

from datetime import date

from pydantic import ValidationError
import pytest
from server.cognition import CognitiveController, ResponsePlan, TextTurnPayload
from server.cognition.models import KnowledgeStatus
from server.cognition.response_plan import (
    InformationNeed,
    ResponseClaim,
    ResponseSource,
    ToolResult,
)


def test_response_plan_is_immutable_and_uses_existing_knowledge_status() -> None:
    """Reject a mutable response plan or a duplicate status vocabulary."""
    payload = TextTurnPayload(message="¿Qué fecha es hoy?", conversation_id="web-primary")
    result = ToolResult(
        tool_name="get_current_date",
        status=KnowledgeStatus.KNOWN,
        value=date(2026, 8, 12).isoformat(),
    )
    plan = ResponsePlan(
        need=InformationNeed.CURRENT_DATE,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response="Hoy es 2026-08-12.",
        tool_results=(result,),
    )

    assert payload.message == "¿Qué fecha es hoy?"
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.tool_results == (result,)
    with pytest.raises(ValidationError, match="frozen"):
        plan.response = "Otra respuesta"


def test_response_plan_rejects_known_claim_without_known_tool_result() -> None:
    """Reject a factual claim that no deterministic result can support."""
    with pytest.raises(ValueError, match="known claim"):
        ResponsePlan(
            need=InformationNeed.CURRENT_DATE,
            status=KnowledgeStatus.KNOWN,
            source=ResponseSource.DETERMINISTIC,
            response="Hoy es 2026-08-12.",
            claims=(
                ResponseClaim(
                    text="La fecha actual es 2026-08-12.",
                    status=KnowledgeStatus.KNOWN,
                    tool_name="get_current_date",
                ),
            ),
        )


def test_cognition_package_exports_p03_public_contracts() -> None:
    """Keep chat adapters from importing private cognition module paths."""
    assert CognitiveController.__name__ == "CognitiveController"
    assert ResponsePlan.__name__ == "ResponsePlan"
    assert TextTurnPayload.__name__ == "TextTurnPayload"
