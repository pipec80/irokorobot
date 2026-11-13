"""Immutable response-planning contracts for the P0.3 chat pilot."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.cognition.models import CognitiveEvent, KnowledgeStatus

if TYPE_CHECKING:
    from server.cognition.identity import ActivePersonContext
    from server.cognition.sensitive_questions import SensitiveQuery

# Semantic upper bound for one conversational turn's text — chat message,
# transcribed voice turn, or visual question. Roughly 4x the longest
# plausible spoken turn and ~700 words typed: comfortably a single turn,
# far below what would waste tokenization and LLM time. The raw ASGI body
# limit in `main.py` is the outer, byte-level bound; this is the semantic
# one. A plain constant, not a `Settings` field: it follows the same
# in-layer convention as `conversation_id`'s `max_length=64`, and Pydantic
# `Field` constraints must be literals.
MAX_TURN_MESSAGE_CHARS = 4000


class TextTurnPayload(BaseModel):
    """Validated text payload carried by one cognitive event."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=MAX_TURN_MESSAGE_CHARS)
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
    # A spoken answer to a memory offer: a closed verb and the offered value (ADR 0021 decision 9).
    MEMORY_ANSWER = "memory_answer"
    # «¿Qué sabes de mí?»: the speaker's own profile card read back (Plan 0074, ADR 0026 decision 5).
    PROFILE_SUMMARY = "profile_summary"
    # Whisper doubted the transcript; the turn never reached the controller (Plan 0069 D-11).
    UNCLEAR_SPEECH = "unclear_speech"
    # «¿Qué te conté ayer?»: the owner's diary and own words searched (Plan 0078, ADR 0028).
    RECALL = "recall"
    # «¿Cómo se llaman mis papás?»: the relatives loaded at the alta (ADR 0028 decision 9).
    RELATIVES_NAMES = "relatives_names"
    # «¿Qué remedios tomo?»: the owner's own sensitive data read back by voice (Plan 0079, ADR 0029).
    SENSITIVE_READ = "sensitive_read"
    # A secret value said or asked for («mi clave es 1234»): never kept, never answered (ADR 0029).
    SECRET_VALUE = "secret_value"  # noqa: S105  # pragma: allowlist secret - a need name


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
    # The phrase spoken after the response: a memory offer (ADR 0021 decision 9) or, when no
    # offer is spoken, the pending-topic follow-up (Plan 0084 D-11). Only the classic voice
    # route speaks it, synthesized with the response and never returned in `llm_response`;
    # `stream_response_plan` and chat ignore it.
    offer: str | None = Field(default=None, min_length=1, repr=False)  # carries a value
    # The turn ended with a question the client should listen to once, with a short reply in
    # mind (Plan 0068, D-3). `stream_response_plan` copies it into `done`; the classic route and
    # chat ignore it.
    expects_short_reply: bool = False

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


@dataclass(frozen=True)
class MemoryAnswerReply:
    """What the memory answerer says back: a fixed phrase, and whether to listen again.

    Lives in the cognitive core so the controller can map it without importing
    ``server.memory`` (ADR 0021 decision 9, Plan 0068 D-4).

    Attributes:
        phrase: The fixed sentence to speak; it never carries a stored value.
        expects_short_reply: ``True`` when the sentence asks a question and the client should
            listen once for a short answer (the retry of Plan 0068).
    """

    phrase: str
    expects_short_reply: bool = False


#: Spoken when a recall question finds nothing it may say (ADR 0028 decisions 4 and 8).
NO_MEMORY: Final = "No me acuerdo de eso."
#: Spoken when the alta loaded no relative of the kind asked about (ADR 0028 decision 9).
NOT_REGISTERED: Final = "No tengo registrado eso."


@dataclass(frozen=True)
class RecallReply:
    """What the recall answerer says back to the controller (Plan 0078, ADR 0028).

    Lives in the cognitive core so the controller can map it without importing
    ``server.memory``. Hidden from ``repr``: ``text`` carries the owner's memories.

    Attributes:
        text: The spoken answer; ``None`` when nothing qualified (the controller decides by the
            cue's strength), or the fixed ``NO_MEMORY`` when the audit or the search failed.
        denied: ``True`` when the pre-check or the policy refused; answered like a stranger.
        found: ``True`` when *text* was worded from found memories.
    """

    text: str | None = field(repr=False)
    denied: bool = False
    found: bool = False


@dataclass(frozen=True)
class ProfileSummaryReply:
    """What the profile summarizer says back to the controller (Plan 0074, ADR 0026 decision 5).

    Lives in the cognitive core so the controller can map it without importing
    ``server.memory``. Hidden from ``repr``: ``text`` carries stored values.

    Attributes:
        text: The spoken summary, or ``None`` when the read failed (the audit or the database).
        denied: ``True`` when the policy or the pre-check refused; the controller then answers
            exactly as it does for a stranger, so a refusal cannot be told apart from one.
    """

    text: str | None = field(repr=False)
    denied: bool = False


#: Spoken when a child's or relative's birth date is not registered (Plan 0079, D-6 and Ruling 15).
NO_BIRTH_DATE: Final = "No tengo registrada su fecha."
#: Spoken to the owner when a second face is in view of a sensitive question (Plan 0079, D-6).
NOT_ALONE: Final = "Te lo digo cuando estemos solos."
#: Spoken when a security question reaches the owner by face alone and the voice is worth a retry.
SECURITY_VOICE_RETRY: Final = (
    "No reconocí bien tu voz. Pregúntamelo de nuevo con una frase completa."
)
#: Spoken for a stated or asked secret value: it is neither kept nor repeated (ADR 0029).
SECRET_REFUSAL: Final = "Las claves y los códigos no los guardo ni los repito."  # noqa: S105  # pragma: allowlist secret - a spoken phrase


class SensitiveOutcome(StrEnum):
    """How one sensitive read ended; also the ``outcome`` of its log line (Plan 0079, D-12)."""

    ANSWERED = "answered"
    NOT_ALONE = "not_alone"
    RETRY_VOICE = "retry_voice"
    DENIED = "denied"
    NOT_REGISTERED = "not_registered"
    UNAVAILABLE = "unavailable"
    NOT_HOUSEHOLD = "not_household"


@dataclass(frozen=True)
class SensitiveReply:
    """What the sensitive reader says back to the controller (Plan 0079, ADR 0029).

    Lives in the cognitive core so the controller can map it without importing
    ``server.memory``. Hidden from ``repr``: ``text`` carries the owner's stored values.

    Attributes:
        outcome: How the read ended; the controller picks the fixed phrase of every outcome but
            ``ANSWERED``.
        text: The spoken answer for ``ANSWERED``; ``NO_BIRTH_DATE`` for a not-registered birth
            date; ``None`` otherwise.
    """

    outcome: SensitiveOutcome
    text: str | None = field(default=None, repr=False)


#: Reads the owner's own sensitive data for a recognized question (Plan 0079): it owns the audience
#: check, the level, the consent, the policy, the audit row and the wording, and never raises.
#: ``faces`` and the voice check are the route's business, so the route binds them.
type SensitiveReader = Callable[
    [ActivePersonContext, SensitiveQuery, CognitiveEvent[TextTurnPayload]],
    Awaitable[SensitiveReply],
]

#: What the opt-in spoken-text log shows instead of a profile summary: the summary carries stored
#: values, so it is spoken to the person and recorded nowhere (Plan 0074, decision D-8).
PROFILE_SUMMARY_LOGGED_TEXT = "«resumen del perfil»"
#: The same for a recall answer and a relatives answer: they carry memories and names (Plan 0078
#: D-11).
RECALL_LOGGED_TEXT = "[recuerdo leído]"
RELATIVES_LOGGED_TEXT = "[parientes leídos]"
#: Replaces the robot's answer to a sensitive read in the conversation record and the opt-in spoken
#: log (Plan 0079, D-8): the answer carries the owner's stored values.
SENSITIVE_RECORDED_TEXT: Final = "[dato sensible leído]"
#: Replaces the heard words of a secret turn in the conversation record (Plan 0079, D-8).
SECRET_RECORDED_TEXT: Final = "[dato de seguridad omitido]"  # noqa: S105  # pragma: allowlist secret - a marker


def spoken_log_text(plan: ResponsePlan) -> str | None:
    """Return what the spoken-text log may show instead of the plan's response, if anything.

    Args:
        plan: The plan about to be spoken.

    Returns:
        A fixed marker for a known profile summary, recall answer, relatives answer or sensitive
        read (their text carries stored values), or ``None`` when the response itself may be
        logged: every fixed phrase, a refusal included.
    """
    if plan.status is not KnowledgeStatus.KNOWN:
        return None
    match plan.need:
        case InformationNeed.PROFILE_SUMMARY:
            return PROFILE_SUMMARY_LOGGED_TEXT
        case InformationNeed.RECALL:
            return RECALL_LOGGED_TEXT
        case InformationNeed.RELATIVES_NAMES:
            return RELATIVES_LOGGED_TEXT
        case InformationNeed.SENSITIVE_READ:
            return SENSITIVE_RECORDED_TEXT
        case _:
            return None


def recorded_exchange(plan: ResponsePlan, heard: str) -> tuple[str, str]:
    """Return the pair the conversation record keeps for one turn (Plan 0079, D-8).

    A secret turn keeps a marker instead of the heard words, since the speaker may have said the
    value; a known sensitive read keeps a marker instead of the answer, which carries stored
    values. Every other turn is recorded as it happened.

    Args:
        plan: The plan the turn was answered with.
        heard: What the speaker said, as transcribed.

    Returns:
        ``(heard, spoken)`` to record, with the markers applied.
    """
    if plan.need is InformationNeed.SECRET_VALUE:
        return SECRET_RECORDED_TEXT, plan.response
    if plan.need is InformationNeed.SENSITIVE_READ and plan.status is KnowledgeStatus.KNOWN:
        return heard, SENSITIVE_RECORDED_TEXT
    return heard, plan.response


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


#: Spoken when Whisper doubted what it heard (Plan 0069 D-11), in neutral tuteo.
UNCLEAR_SPEECH_PHRASE = "No te entendí bien. ¿Me lo repites?"


def unclear_speech_plan(*, expects_short_reply: bool) -> ResponsePlan:
    """Build the fixed reply for a transcript Whisper doubted.

    Nothing is decided from the doubtful text: no controller, no write, no grant.

    Args:
        expects_short_reply: The request was a short reply (reply mode); the stream then
            listens in reply mode once more, so an answer heard badly is asked for again.

    Returns:
        A deterministic plan that asks the person to repeat.
    """
    return ResponsePlan(
        need=InformationNeed.UNCLEAR_SPEECH,
        status=KnowledgeStatus.UNKNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=UNCLEAR_SPEECH_PHRASE,
        expects_short_reply=expects_short_reply,
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
