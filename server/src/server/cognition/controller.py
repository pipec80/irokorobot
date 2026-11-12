"""Small sequential cognitive controller for the P0.3 chat pilot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import re
from typing import TYPE_CHECKING

from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.calendar_tools import calculate_age, get_current_date
from server.cognition.family_sides import Side, SidedNames, SideGroup
from server.cognition.household_request import names_someone_known, requests_data_of_a_name
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.intent_resolution import (
    IntentResolution,
    MemoryAnswer,
    parse_memory_answer,
    resolve_information_need,
)
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
    KnowledgeStatus,
)
from server.cognition.recall_cues import (
    CueStrength,
    RecallCue,
    classify_recall_cue,
    relation_of,
)
from server.cognition.relatives_answers import (
    CHILDREN_LIST_SENTENCE,
    relatives_sentence,
    sided_sentence,
)
from server.cognition.response_plan import (
    NO_MEMORY,
    NOT_ALONE,
    NOT_REGISTERED,
    SECRET_REFUSAL,
    SECURITY_VOICE_RETRY,
    InformationNeed,
    MemoryAnswerReply,
    ProfileSummaryReply,
    RecallReply,
    ResponseClaim,
    ResponsePlan,
    ResponseSource,
    SceneDescriptionRequest,
    SensitiveOutcome,
    SensitiveReply,
    TextTurnPayload,
    ToolResult,
    unclear_speech_plan,
)
from server.cognition.sensitive_answers import spanish_join
from server.cognition.sensitive_questions import classify_sensitive_question
from server.secret_values import secret_kind

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from server.cognition.household_tools import HouseholdKnowledgeTools, HouseholdToolResult
    from server.cognition.response_plan import SensitiveReader
    from server.text_turn import TextTurnResult

logger = logging.getLogger(__name__)

type LegacyTextTurn = Callable[[str, str], Awaitable[TextTurnResult]]
type ActivePersonResolver = Callable[
    [CognitiveEvent[TextTurnPayload]], Awaitable[ActivePersonContext]
]
type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]
type ConsentResolver = Callable[
    [CognitiveEvent[TextTurnPayload], ActivePersonContext], Awaitable[ConsentStatus]
]
#: Called with the message, and with each of ``recall=True``, ``sensitive=True`` and
#: ``secrets=True`` only when its collaborator is wired (the bare call stays today's).
type IntentResolver = Callable[..., IntentResolution]
#: Resolves a spoken answer to a memory offer for an actor already resolved from face and voice
#: (ADR 0021 decision 9). Only the voice routes inject one; it returns the fixed reply (a phrase
#: and whether to listen again, Plan 0068), or ``None`` so the turn falls through to ordinary
#: generation, byte for byte.
type MemoryAnswerer = Callable[
    [MemoryAnswer, ActivePersonContext, CognitiveEvent[TextTurnPayload]],
    Awaitable[MemoryAnswerReply | None],
]
#: Reads the speaker's own profile card for «¿qué sabes de mí?» (Plan 0074, ADR 0026 decision 5).
#: Only the voice routes inject one; it owns the policy and the audit row and never raises.
type ProfileSummarizer = Callable[
    [ActivePersonContext, CognitiveEvent[TextTurnPayload]], Awaitable[ProfileSummaryReply]
]
#: Answers a recall question (Plan 0078, ADR 0028): it owns the policy, the audit row, the search
#: and the wording, and never raises. Only the voice routes inject one, with RECALL_ENABLED on.
type RecallAnswerer = Callable[
    [ActivePersonContext, RecallCue, CognitiveEvent[TextTurnPayload]], Awaitable[RecallReply]
]
#: The household's stored names and aliases (Plan 0077). It never raises: a store failure is an
#: empty set, and the turn stays conversation, where the model holds no stored household value.
type HouseholdNameReader = Callable[[], Awaitable[frozenset[str]]]
type ControllerDecision = ResponsePlan | SceneDescriptionRequest | None

_BIOMETRIC_ENROLLMENT_RESPONSE = (
    "Todavía no puedo registrar rostros: hace falta administración local y consentimiento."
)
_ACTIVE_IDENTITY_UNKNOWN_RESPONSE = "Todavía no puedo confirmar quién eres."
# One phrase for a stranger and for an identified person the policy refused: no oracle (ADR 0026).
_PROFILE_SUMMARY_UNKNOWN_RESPONSE = (
    "Todavía no puedo confirmar quién eres para contarte lo que sé de ti."
)
# Reserved for an audit or database failure, which is not a refusal.
_PROFILE_SUMMARY_UNAVAILABLE_RESPONSE = (
    "Ahora no puedo revisar lo que sé de ti. Inténtalo de nuevo en un rato."
)

_ISO_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_HOUSEHOLD_READERS = frozenset({HouseholdRole.OWNER, HouseholdRole.ADULT})


def _may_read_the_household(actor: ActivePersonContext) -> bool:
    """Whether the policy could let this actor read household data (`_evaluate_public_read`)."""
    return actor.status is ActivePersonStatus.IDENTIFIED and actor.role in _HOUSEHOLD_READERS


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
        observed_person_resolver: ActivePersonResolver = _unknown_active_person,
        policy_evaluator: PolicyEvaluator = evaluate_authorization,
        audit_writer: AuditWriter = _discard_audit,
        household_tools: HouseholdKnowledgeTools | None = None,
        consent_resolver: ConsentResolver = _not_required_consent,
        intent_resolver: IntentResolver = resolve_information_need,
        memory_answerer: MemoryAnswerer | None = None,
        profile_summarizer: ProfileSummarizer | None = None,
        household_names: HouseholdNameReader | None = None,
        recall_answerer: RecallAnswerer | None = None,
        sensitive_reader: SensitiveReader | None = None,
        secret_guard: bool = False,
        alta_read: bool = False,
        occurred_time: bool = False,
    ) -> None:
        """Create a controller with injected calendar and legacy-generation seams.

        Args:
            today: Local date boundary owned by the adapter composition root.
            legacy_turn: Existing generic text-turn service for safe fallback.
            active_person_resolver: Trusted internal active-person boundary that may
                spend a one-use grant; awaited only by the branch that reads data.
            observed_person_resolver: The same actor seen from the evidence already on
                the request, without spending any grant (ADR-0015); used by the
                branches that read nothing. Defaults to the public unknown actor.
            policy_evaluator: Pure deterministic authorization evaluator.
            audit_writer: Local safe-audit boundary for protected decisions.
            household_tools: Optional closed P0.5-B2 family-tool collaborator.
            consent_resolver: Trusted internal scoped-consent boundary.
            intent_resolver: Pure, typed P0-C5 Spanish intent resolver.
            memory_answerer: The answer to a memory offer (ADR 0021 decision 9); injected
                only by the voice routes with the candidate kill-switch on. When absent an
                answer-shaped message is ordinary conversation.
            profile_summarizer: Reads the speaker's profile card for «¿qué sabes de mí?»
                (Plan 0074); injected only by the voice routes with the card switch on. When
                absent the question is ordinary conversation, byte for byte.
            household_names: Reads the household's stored names, so that «¿Cuándo nació
                <name>?» from the owner or an adult takes the protected path (Plan 0077). When
                absent such a question is ordinary conversation.
            recall_answerer: Answers «¿qué te conté ayer?» from the owner's diary (Plan 0078);
                injected only by the voice routes with the recall switch on. When absent the
                recall and relatives rules never run, so every message resolves as before.
            sensitive_reader: Reads the owner's own sensitive data for a recognized question
                (Plan 0079); injected only by the voice routes with the read switch on. When
                absent such a question is ordinary conversation, byte for byte.
            secret_guard: Whether a stated or asked secret value hears a fixed refusal, with no
                model call and no actor (Plan 0079). Off, a secret is ordinary conversation.
            alta_read: Whether the sensitive reader also answers the rest of the alta (Plan
                0082): the contacts, devices, mobility, hearing, vision, coverage, dwelling and
                «vive solo». It does nothing without ``sensitive_reader``.
            occurred_time: Whether a recall question reads with the occurred time on (Plan 0083):
                years and seasons as windows, the usted forms as cues. It does nothing without
                ``recall_answerer``.
        """
        self._today = today
        self._legacy_turn = legacy_turn
        self._active_person_resolver = active_person_resolver
        self._observed_person_resolver = observed_person_resolver
        self._policy_evaluator = policy_evaluator
        self._audit_writer = audit_writer
        self._household_tools = household_tools
        self._consent_resolver = consent_resolver
        self._intent_resolver = intent_resolver
        self._memory_answerer = memory_answerer
        self._profile_summarizer = profile_summarizer
        self._household_names = household_names
        self._recall_answerer = recall_answerer
        self._sensitive_reader = sensitive_reader
        self._secret_guard = secret_guard
        self._alta_read = alta_read
        self._occurred_time = occurred_time
        # The same cache for a sensitive read: one read and one audit row per event.
        self._sensitive_reads: dict[UUID, ResponsePlan | None] = {}
        # The classic route's two calls again: one search and one audit row per event.
        self._recalls: dict[UUID, ResponsePlan | None] = {}
        # The classic route calls decide() twice on a turn that falls through (decide, then
        # handle), with the same event: keyed by event_id, an answer is attempted once per
        # event, so no audit row is written twice. The controller is built per request and
        # lives for one request, so the cache is never evicted.
        self._answers: dict[UUID, ResponsePlan | None] = {}
        # The same two calls, the same event: the store is read once per event.
        self._named_requests: dict[UUID, bool] = {}

    async def handle(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan:
        """Produce one bounded response plan for a typed text event.

        Args:
            event: Validated event from the chat adapter.

        Returns:
            Deterministic, safe, or legacy response plan for the event.

        Raises:
            RuntimeError: If `decide()` returns a `SceneDescriptionRequest` —
                only a camera-capable adapter may fulfill that capability;
                `handle()` must never leak it into legacy text generation.
        """
        decision = await self.decide(event)
        if isinstance(decision, SceneDescriptionRequest):
            raise RuntimeError(
                "SceneDescriptionRequest must be fulfilled by a camera-capable "
                "adapter, not CognitiveController.handle()"
            )
        if decision is not None:
            return decision
        return await self._legacy_plan(event.payload)

    async def decide(self, event: CognitiveEvent[TextTurnPayload]) -> ControllerDecision:
        """Resolve closed policy and tool branches without generic generation.

        Args:
            event: Validated event from a text-capable channel adapter.

        Returns:
            A deterministic or policy response plan, a capability request
            that only a camera-capable adapter may fulfill, or ``None`` when
            the adapter may safely use its generic generation path.
        """
        need = await self._resolved_need(event)
        decision = await self._decision_for(event, need)
        if decision is None and need is InformationNeed.SENSITIVE_READ:
            # The reader said the question is no sensitive one (a birthday of someone who is no
            # child of the house): resolve it again as today, so «el cumpleaños de mi tía» keeps
            # its protected path and «¿cuándo nació Mozart?» stays conversation (Plan 0079 D-5).
            need = await self._resolved_need(event, sensitive=False)
            decision = await self._decision_for(event, need)
        return decision

    async def _decision_for(
        self, event: CognitiveEvent[TextTurnPayload], need: InformationNeed
    ) -> ControllerDecision:
        """Dispatch one resolved need: the secret guard, the sensitive read or a closed branch."""
        if need is InformationNeed.SECRET_VALUE:
            return _secret_plan(event.payload.message)
        if need is InformationNeed.SENSITIVE_READ:
            return await self._sensitive_plan(event)
        return await self._closed_decision(event, need)

    async def _closed_decision(
        self, event: CognitiveEvent[TextTurnPayload], need: InformationNeed
    ) -> ControllerDecision:
        """Run the branch of every need that existed before Plan 0079."""
        decision: ControllerDecision
        match need:
            case InformationNeed.OWN_CHILDREN_LIST | InformationNeed.OWN_CHILDREN_COUNT:
                decision = await self._own_children_plan(event, need)
            case InformationNeed.PROTECTED_HOUSEHOLD:
                decision = await self._protected_household_plan(event, need)
            case InformationNeed.AMBIGUOUS_DATE_QUERY:
                decision = _ambiguous_date_plan()
            case InformationNeed.RELATIONSHIP_OR_PROFILE:
                decision = _unknown_plan(
                    need, "No tengo relaciones familiares estructuradas verificadas."
                )
            case InformationNeed.CURRENT_DATE:
                decision = _date_plan(get_current_date(self._today()))
            case InformationNeed.EXPLICIT_BIRTH_DATE_AGE:
                decision = _age_plan(_age_result(event.payload.message, self._today()))
            case InformationNeed.BIOMETRIC_ENROLLMENT:
                decision = _biometric_enrollment_plan()
            case InformationNeed.ACTIVE_IDENTITY:
                decision = await self._active_identity_plan(event)
            case InformationNeed.SCENE_DESCRIPTION:
                decision = SceneDescriptionRequest()
            case (
                InformationNeed.MEMORY_ANSWER
                | InformationNeed.PROFILE_SUMMARY
                | InformationNeed.RECALL
                | InformationNeed.RELATIVES_NAMES
            ):
                decision = await self._voice_dialogue_plan(event, need)
            case InformationNeed.UNCLEAR_SPEECH:
                # The voice routes answer it before the controller (Plan 0069 D-11); no text
                # resolves to it, but if one ever did, it is the fixed phrase, never generation.
                decision = unclear_speech_plan(expects_short_reply=False)
            case (
                InformationNeed.GENERIC_CONVERSATION
                | InformationNeed.SENSITIVE_READ
                | InformationNeed.SECRET_VALUE
            ):
                # The last two never get here: ``_decision_for`` routes them first.
                decision = None
        return decision

    async def _resolved_need(
        self, event: CognitiveEvent[TextTurnPayload], *, sensitive: bool = True
    ) -> InformationNeed:
        """Resolve the closed need, then let a stored name turn a question into a protected one.

        Each resolver flag is passed only when its collaborator is wired, so the bare call of
        today stays exactly as it was. ``sensitive=False`` resolves a question as if the sensitive
        reader were not wired.
        """
        message = event.payload.message
        flags: dict[str, bool] = {}
        if self._recall_answerer is not None:
            flags["recall"] = True
            if self._occurred_time:
                flags["occurred"] = True
        if sensitive and self._sensitive_reader is not None:
            flags["sensitive"] = True
            if self._alta_read:
                flags["alta"] = True
        if self._secret_guard:
            flags["secrets"] = True
        need = self._intent_resolver(message, **flags).need
        if need is InformationNeed.GENERIC_CONVERSATION and await self._asks_about_known_name(
            event
        ):
            return InformationNeed.PROTECTED_HOUSEHOLD
        return need

    async def _sensitive_plan(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan | None:
        """Answer a sensitive question through the reader, or fall through (``None``).

        ADR 0029. The actor is only observed (never spends a grant) and is handed to the reader,
        which owns the audience check, the level, the consent, the policy and the audit row. The
        reader is called once per event, since the classic route decides twice on a turn that
        falls through. A sensitive answer never enters continuity: only the legacy text turn
        writes it, and this plan never reaches it.
        """
        if self._sensitive_reader is None:
            return None
        if event.event_id not in self._sensitive_reads:
            query = classify_sensitive_question(event.payload.message, alta=self._alta_read)
            if query is None:
                self._sensitive_reads[event.event_id] = None
            else:
                actor = await self._observed_person_resolver(event)
                reply = await self._sensitive_reader(actor, query, event)
                self._sensitive_reads[event.event_id] = _sensitive_reply_plan(reply)
        return self._sensitive_reads[event.event_id]

    async def _asks_about_known_name(self, event: CognitiveEvent[TextTurnPayload]) -> bool:
        """Tell whether the owner or an adult asks for a datum of someone the household knows.

        The names are compared first: one read of the store, while judging the face and the voice
        costs seconds, and «¿sabes…?» or «¿quién es…?» are everyday questions. A visitor never
        reaches this path: their question stays conversation, where the model holds no stored
        household value, so the reply cannot tell a stored name from any other. Neither does a child or a
        guest: only the roles the policy lets read household data reach the protected path, or
        the refusal would confirm the name. It never spends a grant.
        """
        message = event.payload.message
        if self._household_names is None or not requests_data_of_a_name(message):
            return False
        if event.event_id not in self._named_requests:
            names = await self._household_names()
            self._named_requests[event.event_id] = names_someone_known(
                message, names
            ) and _may_read_the_household(await self._observed_person_resolver(event))
        return self._named_requests[event.event_id]

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
            offer=result.offer,
        )

    async def _protected_household_plan(
        self,
        event: CognitiveEvent[TextTurnPayload],
        need: InformationNeed,
        actor: ActivePersonContext | None = None,
    ) -> ResponsePlan:
        """Authorize and audit a protected branch before any legacy delegation.

        When the caller did not already resolve the actor, it is only observed: this
        branch answers "not connected yet" and reads no data, so it never spends a grant.
        """
        request = AuthorizationRequest(
            actor=await self._observed_person_resolver(event) if actor is None else actor,
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

    async def _active_identity_plan(
        self,
        event: CognitiveEvent[TextTurnPayload],
    ) -> ResponsePlan:
        """Confirm the speaker only from the evidence already on this request.

        Uses the observed actor and never spends a one-use grant (ADR-0015): a
        bystander asking "who am I" cannot burn the owner's read grant.
        """
        actor = await self._observed_person_resolver(event)
        if actor.status is ActivePersonStatus.IDENTIFIED and actor.display_name is not None:
            return ResponsePlan(
                need=InformationNeed.ACTIVE_IDENTITY,
                status=KnowledgeStatus.KNOWN,
                source=ResponseSource.DETERMINISTIC,
                response=f"Eres {actor.display_name}.",
            )
        return _unknown_plan(InformationNeed.ACTIVE_IDENTITY, _ACTIVE_IDENTITY_UNKNOWN_RESPONSE)

    async def _memory_answer_plan(
        self,
        event: CognitiveEvent[TextTurnPayload],
    ) -> ResponsePlan | None:
        """Answer a memory offer, or fall through to ordinary generation (``None``).

        No oracle (ADR 0021 decision 9): when an answerer is wired, the actor is resolved
        **first** for every message of this shape, whether or not an offer exists, so the
        cost never reveals whether one does; only then does the answerer read the actor's own
        candidates. The face-and-voice actor comes from the route's observing resolver, so
        no PIN grant is ever spent: a token never answers a memory offer.
        """
        answer = parse_memory_answer(event.payload.message)
        if self._memory_answerer is None or answer is None:
            return None
        if event.event_id in self._answers:
            return self._answers[event.event_id]
        actor = await self._observed_person_resolver(event)
        reply = await self._memory_answerer(answer, actor, event)
        plan = (
            None
            if reply is None
            else ResponsePlan(
                need=InformationNeed.MEMORY_ANSWER,
                status=KnowledgeStatus.KNOWN,
                source=ResponseSource.DETERMINISTIC,
                response=reply.phrase,
                expects_short_reply=reply.expects_short_reply,
            )
        )
        self._answers[event.event_id] = plan
        return plan

    async def _voice_dialogue_plan(
        self,
        event: CognitiveEvent[TextTurnPayload],
        need: InformationNeed,
    ) -> ResponsePlan | None:
        """Answer one of the needs only a voice route wires, or fall through (``None``).

        Each stays inert, byte for byte, until its collaborator is injected.
        """
        if need is InformationNeed.MEMORY_ANSWER:
            return await self._memory_answer_plan(event)
        if need is InformationNeed.RECALL:
            return await self._recall_plan(event)
        if need is InformationNeed.RELATIVES_NAMES:
            return await self._relatives_plan(event)
        return await self._profile_summary_plan(event)

    async def _recall_plan(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan | None:
        """Answer a recall question from the owner's diary, or fall through (``None``).

        ADR 0028 decisions 4 and 5. The actor is only observed (never spends a grant). A strong
        cue answers: the worded memories, or the fixed «No me acuerdo de eso.» when nothing
        qualified or the search failed; a stranger and a refused speaker hear the profile
        refusal, so a refusal is no oracle. A weak cue answers only when something was found;
        otherwise the turn is ordinary conversation. The answer never enters continuity: a
        plan returned here is never written to it.
        """
        if self._recall_answerer is None:
            return None
        if event.event_id not in self._recalls:
            self._recalls[event.event_id] = await self._recall_decision(event)
        return self._recalls[event.event_id]

    async def _relatives_plan(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan:
        """Read the owner's relatives loaded at the alta with a fixed template (ADR 0028 d. 9).

        Resolved only with recall on. Without the household tools the question keeps today's
        protected answer. The actor is only observed (never spends a grant); a stranger and a
        refused speaker hear the profile refusal; nothing stored is «No tengo registrado eso.».
        """
        predicate = relation_of(event.payload.message)
        if self._household_tools is None or predicate is None:
            return await self._protected_household_plan(event, InformationNeed.PROTECTED_HOUSEHOLD)
        actor = await self._observed_person_resolver(event)
        if actor.status is not ActivePersonStatus.IDENTIFIED or actor.person_id is None:
            return _unknown_plan(InformationNeed.RELATIVES_NAMES, _PROFILE_SUMMARY_UNKNOWN_RESPONSE)
        consent = await self._consent_resolver(event, actor)
        sided = await self._sided_relatives_plan(event, actor, consent, predicate)
        if sided is not None:
            return sided
        result = await self._household_tools.get_relatives(
            owner_entity_id=actor.person_id,
            predicate=predicate,
            actor=actor,
            consent=consent,
            correlation_id=event.correlation_id,
            requested_at=event.recorded_at,
        )
        if result.status is KnowledgeStatus.UNAUTHORIZED:
            return _unknown_plan(InformationNeed.RELATIVES_NAMES, _PROFILE_SUMMARY_UNKNOWN_RESPONSE)
        if result.status is not KnowledgeStatus.KNOWN or not isinstance(result.value, tuple):
            return _unknown_plan(InformationNeed.RELATIVES_NAMES, NOT_REGISTERED)
        return _relatives_plan_of(relatives_sentence(predicate, result.value))

    async def _sided_relatives_plan(
        self,
        event: CognitiveEvent[TextTurnPayload],
        actor: ActivePersonContext,
        consent: ConsentStatus,
        predicate: str,
    ) -> ResponsePlan | None:
        """Read the parents or one child by recorded side; ``None`` for any other relation.

        The consent is the one the children list uses (``_consent_resolver``); the actor is the
        observed one, so nothing here spends a grant.
        """
        tools = self._household_tools
        if tools is None or actor.person_id is None:
            return None
        if predicate in _PARENT_SIDES:
            parents = await tools.get_parents(
                owner_entity_id=actor.person_id,
                actor=actor,
                consent=consent,
                correlation_id=event.correlation_id,
                requested_at=event.recorded_at,
            )
            return _sided_plan(SideGroup.PARENTS, parents, _PARENT_SIDES[predicate])
        if predicate in _CHILD_SIDES:
            children = await tools.get_children_by_side(
                parent_entity_id=actor.person_id,
                actor=actor,
                consent=consent,
                correlation_id=event.correlation_id,
                requested_at=event.recorded_at,
            )
            return _sided_plan(SideGroup.CHILDREN, children, _CHILD_SIDES[predicate])
        return None

    async def _recall_decision(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan | None:
        """Decide the recall plan of one event (cached by ``_recall_plan``)."""
        message, today = event.payload.message, self._today()
        cue = (
            classify_recall_cue(message, today=today, occurred=True)
            if self._occurred_time
            else classify_recall_cue(message, today=today)
        )
        if cue is None or self._recall_answerer is None:
            return None
        strong = cue.strength is CueStrength.STRONG
        actor = await self._observed_person_resolver(event)
        reply = (
            RecallReply(text=None, denied=True)
            if actor.status is not ActivePersonStatus.IDENTIFIED
            else await self._recall_answerer(actor, cue, event)
        )
        if reply.found and reply.text is not None:
            return ResponsePlan(
                need=InformationNeed.RECALL,
                status=KnowledgeStatus.KNOWN,
                source=ResponseSource.DETERMINISTIC,
                response=reply.text,
            )
        if not strong:
            return None
        if reply.denied:
            return _unknown_plan(InformationNeed.RECALL, _PROFILE_SUMMARY_UNKNOWN_RESPONSE)
        return _unknown_plan(InformationNeed.RECALL, NO_MEMORY)

    async def _profile_summary_plan(
        self,
        event: CognitiveEvent[TextTurnPayload],
    ) -> ResponsePlan | None:
        """Read back the speaker's own profile card, or fall through (``None``) without a seam.

        The actor is only observed (never spends a grant). A stranger and an identified person
        the policy refused hear the same phrase, so a refusal is no oracle (ADR 0026 decision 5);
        a failed audit or read is told apart because it is not a refusal.
        """
        if self._profile_summarizer is None:
            return None
        actor = await self._observed_person_resolver(event)
        if actor.status is not ActivePersonStatus.IDENTIFIED:
            return _unknown_plan(InformationNeed.PROFILE_SUMMARY, _PROFILE_SUMMARY_UNKNOWN_RESPONSE)
        reply = await self._profile_summarizer(actor, event)
        if reply.denied:
            return _unknown_plan(InformationNeed.PROFILE_SUMMARY, _PROFILE_SUMMARY_UNKNOWN_RESPONSE)
        if reply.text is None:
            return _unknown_plan(
                InformationNeed.PROFILE_SUMMARY, _PROFILE_SUMMARY_UNAVAILABLE_RESPONSE
            )
        return ResponsePlan(
            need=InformationNeed.PROFILE_SUMMARY,
            status=KnowledgeStatus.KNOWN,
            source=ResponseSource.DETERMINISTIC,
            response=reply.text,
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


#: The fixed phrase of every sensitive outcome that carries no text of its own.
_SENSITIVE_PHRASES: dict[SensitiveOutcome, str] = {
    SensitiveOutcome.NOT_ALONE: NOT_ALONE,
    SensitiveOutcome.RETRY_VOICE: SECURITY_VOICE_RETRY,
    SensitiveOutcome.DENIED: _PROFILE_SUMMARY_UNKNOWN_RESPONSE,
    SensitiveOutcome.UNAVAILABLE: _PROFILE_SUMMARY_UNAVAILABLE_RESPONSE,
}


def _sensitive_reply_plan(reply: SensitiveReply) -> ResponsePlan | None:
    """Map the reader's outcome to a plan; ``None`` is ordinary conversation (not a house topic)."""
    need = InformationNeed.SENSITIVE_READ
    match reply.outcome:
        case SensitiveOutcome.NOT_HOUSEHOLD:
            return None
        case SensitiveOutcome.ANSWERED if reply.text is not None:
            return ResponsePlan(
                need=need,
                status=KnowledgeStatus.KNOWN,
                source=ResponseSource.DETERMINISTIC,
                response=reply.text,
            )
        case SensitiveOutcome.NOT_REGISTERED:
            return _unknown_plan(need, NOT_REGISTERED if reply.text is None else reply.text)
        case _:
            # An answer without a text is a reader bug: say it could not be read, never guess.
            return _unknown_plan(
                need, _SENSITIVE_PHRASES.get(reply.outcome, _PROFILE_SUMMARY_UNAVAILABLE_RESPONSE)
            )


def _secret_plan(message: str) -> ResponsePlan:
    """Refuse a stated or asked secret value: no model, no actor, nothing stored (ADR 0029).

    One log line per secret turn with its kind, never a text.
    """
    kind = secret_kind(message)
    if kind is not None:
        logger.info(
            "Secret turn: %s", kind.value, extra={"event": "secret.turn", "kind": kind.value}
        )
    return _unknown_plan(InformationNeed.SECRET_VALUE, SECRET_REFUSAL)


def _biometric_enrollment_plan() -> ResponsePlan:
    """Reject face enrollment without ever touching a camera or a model."""
    return ResponsePlan(
        need=InformationNeed.BIOMETRIC_ENROLLMENT,
        status=KnowledgeStatus.UNKNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=_BIOMETRIC_ENROLLMENT_RESPONSE,
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
        names = spanish_join(result.value)
        response = CHILDREN_LIST_SENTENCE.format(names)
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


# The relations whose side is recorded, and the side each question asks for (Plan 0080 D-4):
# ``None`` is the plural question, which asks for every member of the group.
_PARENT_SIDES: dict[str, Side | None] = {
    "has_mother": Side.FEMALE,
    "has_father": Side.MALE,
    "has_parent": None,
}
# One child asked for by side: the marker the question stands for (Plan 0080 D-4).
_CHILD_SIDES: dict[str, Side] = {"daughter_of": Side.FEMALE, "son_of": Side.MALE}


def _relatives_plan_of(sentence: str) -> ResponsePlan:
    """The deterministic plan of a relatives sentence; it never enters continuity."""
    return ResponsePlan(
        need=InformationNeed.RELATIVES_NAMES,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=sentence,
    )


def _sided_plan(group: SideGroup, names: SidedNames, asked: Side | None) -> ResponsePlan:
    """Word a group read by side: the refusal, «No tengo registrado eso.» or the sentence."""
    if names.status is KnowledgeStatus.UNAUTHORIZED:
        return _unknown_plan(InformationNeed.RELATIVES_NAMES, _PROFILE_SUMMARY_UNKNOWN_RESPONSE)
    sentence = (
        sided_sentence(group, asked, names) if names.status is KnowledgeStatus.KNOWN else None
    )
    if sentence is None:
        return _unknown_plan(InformationNeed.RELATIVES_NAMES, NOT_REGISTERED)
    return _relatives_plan_of(sentence)
