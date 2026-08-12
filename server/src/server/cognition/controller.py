"""Small sequential cognitive controller for the P0.3 chat pilot."""

from collections.abc import Awaitable, Callable
from datetime import date
import re

from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.calendar_tools import calculate_age, get_current_date
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
    KnowledgeStatus,
)
from server.cognition.response_plan import (
    InformationNeed,
    ResponseClaim,
    ResponsePlan,
    ResponseSource,
    TextTurnPayload,
    ToolResult,
)
from server.text_turn import TextTurnResult

type LegacyTextTurn = Callable[[str, str], Awaitable[TextTurnResult]]
type ActivePersonResolver = Callable[[CognitiveEvent[TextTurnPayload]], ActivePersonContext]
type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]

_ISO_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_PRIVATE_HOUSEHOLD_TERMS = ("hijo", "hija", "familia", "preferencia", "le gusta")
_RELATIONSHIP_TERMS = ("padre", "madre", "hermano", "pareja", "relación")


def _unknown_active_person(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
    """Build the safe public actor without deriving identity from HTTP input."""
    return ActivePersonContext(
        person_id=None,
        display_name=None,
        status=ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason="No trusted active-person evidence",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=event.occurred_at,
    )


async def _discard_audit(
    _request: AuthorizationRequest,
    _decision: AuthorizationDecision,
) -> None:
    """Keep isolated controller tests free of persistence unless they inject it."""


class CognitiveController:
    """Coordinate the closed deterministic branches before legacy generation."""

    def __init__(
        self,
        *,
        today: Callable[[], date],
        legacy_turn: LegacyTextTurn,
        active_person_resolver: ActivePersonResolver = _unknown_active_person,
        policy_evaluator: PolicyEvaluator = evaluate_authorization,
        audit_writer: AuditWriter = _discard_audit,
    ) -> None:
        """Create a controller with injected calendar and legacy-generation seams.

        Args:
            today: Local date boundary owned by the adapter composition root.
            legacy_turn: Existing generic text-turn service for safe fallback.
            active_person_resolver: Trusted internal active-person boundary.
            policy_evaluator: Pure deterministic authorization evaluator.
            audit_writer: Local safe-audit boundary for protected decisions.
        """
        self._today = today
        self._legacy_turn = legacy_turn
        self._active_person_resolver = active_person_resolver
        self._policy_evaluator = policy_evaluator
        self._audit_writer = audit_writer

    async def handle(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan:
        """Produce one bounded response plan for a typed text event.

        Args:
            event: Validated event from the chat adapter.

        Returns:
            Deterministic, safe, or legacy response plan for the event.
        """
        need = _classify_information_need(event.payload.message)
        match need:
            case InformationNeed.PROTECTED_HOUSEHOLD:
                return await self._protected_household_plan(event, need)
            case InformationNeed.RELATIONSHIP_OR_PROFILE:
                return _unknown_plan(
                    need, "No tengo relaciones familiares estructuradas verificadas."
                )
            case InformationNeed.CURRENT_DATE:
                return _date_plan(get_current_date(self._today()))
            case InformationNeed.EXPLICIT_BIRTH_DATE_AGE:
                return _age_plan(_age_result(event.payload.message, self._today()))
            case InformationNeed.GENERIC_CONVERSATION:
                return await self._legacy_plan(event.payload)

    async def _legacy_plan(self, payload: TextTurnPayload) -> ResponsePlan:
        """Delegate only an unclassified safe request to the existing text path."""
        result = await self._legacy_turn(payload.message, payload.conversation_id)
        return ResponsePlan(
            need=InformationNeed.GENERIC_CONVERSATION,
            status=KnowledgeStatus.UNKNOWN,
            source=ResponseSource.LEGACY_TEXT_TURN,
            response=result.response,
            emotion=result.emotion,
            duration_ms=result.duration_ms,
        )

    async def _protected_household_plan(
        self,
        event: CognitiveEvent[TextTurnPayload],
        need: InformationNeed,
    ) -> ResponsePlan:
        """Authorize and audit a protected branch before any legacy delegation."""
        request = AuthorizationRequest(
            actor=self._active_person_resolver(event),
            action=AuthorizationAction.READ_HOUSEHOLD_DATA,
            visibility=frozenset({DataVisibility.HOUSEHOLD}),
            sensitivity=frozenset({DataSensitivity.PRIVATE}),
            consent=ConsentStatus.NOT_REQUIRED,
            correlation_id=event.correlation_id,
            requested_at=event.recorded_at,
        )
        decision = self._policy_evaluator(request)
        await self._audit_writer(request, decision)
        if decision.decision is not AuthorizationStatus.ALLOWED:
            return _unauthorized_plan(need)
        return _unknown_plan(
            need,
            "La información familiar autorizada todavía no está conectada a consultas verificadas.",
        )


def _classify_information_need(message: str) -> InformationNeed:
    """Classify only the documented P0.3 text patterns without model inference."""
    normalized = message.casefold()
    if any(term in normalized for term in _PRIVATE_HOUSEHOLD_TERMS):
        return InformationNeed.PROTECTED_HOUSEHOLD
    if _is_current_date_request(normalized):
        return InformationNeed.CURRENT_DATE
    if "edad" in normalized or "años" in normalized:
        return InformationNeed.EXPLICIT_BIRTH_DATE_AGE
    if any(term in normalized for term in _RELATIONSHIP_TERMS):
        return InformationNeed.RELATIONSHIP_OR_PROFILE
    return InformationNeed.GENERIC_CONVERSATION


def _is_current_date_request(message: str) -> bool:
    """Recognize the narrow current-date forms supported by P0.3."""
    return ("fecha" in message and "hoy" in message) or "qué día es hoy" in message


def _age_result(message: str, today: date) -> ToolResult:
    """Calculate age only when the request supplies one strict ISO date."""
    match = _ISO_DATE_PATTERN.search(message)
    if match is None:
        return ToolResult(
            tool_name="calculate_age",
            status=KnowledgeStatus.UNKNOWN,
            reason="a strict ISO birth date is required",
        )
    return calculate_age(match.group(), today)


def _date_plan(result: ToolResult) -> ResponsePlan:
    """Build the deterministic current-date response plan."""
    return ResponsePlan(
        need=InformationNeed.CURRENT_DATE,
        status=result.status,
        source=ResponseSource.DETERMINISTIC,
        response=f"Hoy es {result.value}.",
        tool_results=(result,),
        claims=(
            ResponseClaim(
                text=f"La fecha actual es {result.value}.",
                status=KnowledgeStatus.KNOWN,
                tool_name=result.tool_name,
            ),
        ),
    )


def _age_plan(result: ToolResult) -> ResponsePlan:
    """Build an evidence-backed age answer or an explicit unknown response."""
    if result.status is KnowledgeStatus.UNKNOWN:
        return _unknown_plan(
            InformationNeed.EXPLICIT_BIRTH_DATE_AGE,
            "No puedo calcular la edad sin una fecha de nacimiento ISO válida.",
            result,
        )
    return ResponsePlan(
        need=InformationNeed.EXPLICIT_BIRTH_DATE_AGE,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=f"La edad calculada es {result.value} años.",
        tool_results=(result,),
        claims=(
            ResponseClaim(
                text=f"La edad calculada es {result.value} años.",
                status=KnowledgeStatus.KNOWN,
                tool_name=result.tool_name,
            ),
        ),
    )


def _unknown_plan(
    need: InformationNeed,
    response: str,
    result: ToolResult | None = None,
) -> ResponsePlan:
    """Build an explicit unknown outcome without calling legacy generation."""
    return ResponsePlan(
        need=need,
        status=KnowledgeStatus.UNKNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=response,
        tool_results=() if result is None else (result,),
    )


def _unauthorized_plan(need: InformationNeed) -> ResponsePlan:
    """Build a non-disclosing protected-household response."""
    return ResponsePlan(
        need=need,
        status=KnowledgeStatus.UNAUTHORIZED,
        source=ResponseSource.DETERMINISTIC,
        response="No puedo acceder a información familiar privada sin una autorización comprobada.",
    )
