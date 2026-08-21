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
from server.cognition.household_tools import HouseholdKnowledgeTools, HouseholdToolResult
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.intent_resolution import IntentResolution, resolve_information_need
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
type ActivePersonResolver = Callable[
    [CognitiveEvent[TextTurnPayload]], Awaitable[ActivePersonContext]
]
type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]
type ConsentResolver = Callable[
    [CognitiveEvent[TextTurnPayload], ActivePersonContext], Awaitable[ConsentStatus]
]
type IntentResolver = Callable[[str], IntentResolution]

_ISO_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TWO_ITEMS = 2


async def _unknown_active_person(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
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


async def _not_required_consent(
    _event: CognitiveEvent[TextTurnPayload],
    _actor: ActivePersonContext,
) -> ConsentStatus:
    """Keep public adapters unable to manufacture trusted scoped consent."""
    return ConsentStatus.NOT_REQUIRED


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
        household_tools: HouseholdKnowledgeTools | None = None,
        consent_resolver: ConsentResolver = _not_required_consent,
        intent_resolver: IntentResolver = resolve_information_need,
    ) -> None:
        """Create a controller with injected calendar and legacy-generation seams.

        Args:
            today: Local date boundary owned by the adapter composition root.
            legacy_turn: Existing generic text-turn service for safe fallback.
            active_person_resolver: Trusted internal active-person boundary.
            policy_evaluator: Pure deterministic authorization evaluator.
            audit_writer: Local safe-audit boundary for protected decisions.
            household_tools: Optional closed P0.5-B2 family-tool collaborator.
            consent_resolver: Trusted internal scoped-consent boundary.
            intent_resolver: Pure, typed P0-C5 Spanish intent resolver.
        """
        self._today = today
        self._legacy_turn = legacy_turn
        self._active_person_resolver = active_person_resolver
        self._policy_evaluator = policy_evaluator
        self._audit_writer = audit_writer
        self._household_tools = household_tools
        self._consent_resolver = consent_resolver
        self._intent_resolver = intent_resolver

    async def handle(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan:
        """Produce one bounded response plan for a typed text event.

        Args:
            event: Validated event from the chat adapter.

        Returns:
            Deterministic, safe, or legacy response plan for the event.
        """
        plan = await self.decide(event)
        if plan is not None:
            return plan
        return await self._legacy_plan(event.payload)

    async def decide(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan | None:
        """Resolve closed policy and tool branches without generic generation.

        Args:
            event: Validated event from a text-capable channel adapter.

        Returns:
            A deterministic or policy response plan, or ``None`` when the
            adapter may safely use its generic generation path.
        """
        need = self._intent_resolver(event.payload.message).need
        plan: ResponsePlan | None
        match need:
            case InformationNeed.OWN_CHILDREN_LIST | InformationNeed.OWN_CHILDREN_COUNT:
                plan = await self._own_children_plan(event, need)
            case InformationNeed.PROTECTED_HOUSEHOLD:
                plan = await self._protected_household_plan(event, need)
            case InformationNeed.AMBIGUOUS_DATE_QUERY:
                plan = _ambiguous_date_plan()
            case InformationNeed.RELATIONSHIP_OR_PROFILE:
                plan = _unknown_plan(
                    need, "No tengo relaciones familiares estructuradas verificadas."
                )
            case InformationNeed.CURRENT_DATE:
                plan = _date_plan(get_current_date(self._today()))
            case InformationNeed.EXPLICIT_BIRTH_DATE_AGE:
                plan = _age_plan(_age_result(event.payload.message, self._today()))
            case InformationNeed.GENERIC_CONVERSATION:
                plan = None
        return plan

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
        actor: ActivePersonContext | None = None,
    ) -> ResponsePlan:
        """Authorize and audit a protected branch before any legacy delegation."""
        request = AuthorizationRequest(
            actor=await self._active_person_resolver(event) if actor is None else actor,
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

    async def _own_children_plan(
        self,
        event: CognitiveEvent[TextTurnPayload],
        need: InformationNeed,
    ) -> ResponsePlan:
        """Dispatch only self-child patterns through the closed family-tool seam."""
        actor = await self._active_person_resolver(event)
        if self._household_tools is None or actor.person_id is None:
            return await self._protected_household_plan(event, need, actor)
        consent = await self._consent_resolver(event, actor)
        result = (
            await self._household_tools.get_children(
                parent_entity_id=actor.person_id,
                actor=actor,
                consent=consent,
                correlation_id=event.correlation_id,
                requested_at=event.recorded_at,
            )
            if need is InformationNeed.OWN_CHILDREN_LIST
            else await self._household_tools.count_children(
                parent_entity_id=actor.person_id,
                actor=actor,
                consent=consent,
                correlation_id=event.correlation_id,
                requested_at=event.recorded_at,
            )
        )
        return _household_tool_plan(need, result)


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


def _ambiguous_date_plan() -> ResponsePlan:
    """Ask for a safe clarification when a known STT date form is ambiguous."""
    return _unknown_plan(
        InformationNeed.AMBIGUOUS_DATE_QUERY,
        "No entendí si preguntas por la fecha actual o por información personal. "
        "¿Podrías reformularlo?",
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


def _household_tool_plan(
    need: InformationNeed,
    result: HouseholdToolResult,
) -> ResponsePlan:
    """Translate a closed tool result into deterministic Spanish without an LLM."""
    tool_result = ToolResult(
        tool_name=result.tool_name.value,
        status=result.status,
        value=_response_tool_value(result.value),
        reason=result.reason,
    )
    if result.status is KnowledgeStatus.UNAUTHORIZED:
        return _unauthorized_plan(need)
    if result.status is KnowledgeStatus.CONTRADICTORY:
        return ResponsePlan(
            need=need,
            status=KnowledgeStatus.CONTRADICTORY,
            source=ResponseSource.DETERMINISTIC,
            response="Tengo datos familiares en conflicto y necesito una confirmación autorizada.",
            tool_results=(tool_result,),
        )
    if result.status is not KnowledgeStatus.KNOWN:
        return _unknown_plan(
            need,
            "No tengo información familiar verificada para responder esa pregunta.",
            tool_result,
        )
    if need is InformationNeed.OWN_CHILDREN_LIST and isinstance(result.value, tuple):
        names = _spanish_join(result.value)
        response = f"Tus hijos son {names}."
    elif need is InformationNeed.OWN_CHILDREN_COUNT and isinstance(result.value, int):
        response = f"Tienes {result.value} hijos."
    else:
        return _unknown_plan(
            need,
            "No tengo información familiar verificada para responder esa pregunta.",
            tool_result,
        )
    return ResponsePlan(
        need=need,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=response,
        tool_results=(tool_result,),
        claims=(
            ResponseClaim(
                text=response, status=KnowledgeStatus.KNOWN, tool_name=tool_result.tool_name
            ),
        ),
    )


def _response_tool_value(value: str | int | tuple[str, ...] | None) -> str | int | None:
    """Adapt a closed family-tool value to the narrower P0.3 response contract."""
    return ", ".join(value) if isinstance(value, tuple) else value


def _spanish_join(values: tuple[str, ...]) -> str:
    """Join already-authorized labels with deterministic Spanish punctuation."""
    if len(values) == 1:
        return values[0]
    if len(values) == _TWO_ITEMS:
        return f"{values[0]} y {values[1]}"
    return f"{', '.join(values[:-1])} y {values[-1]}"
