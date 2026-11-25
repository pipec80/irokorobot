"""Audio endpoint — transcribe speech, generate a response, synthesize it.

Audio contract: WAV · 16000 Hz · mono · int16.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import partial
import logging
import time
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
import httpx

from server import turn_log
from server.audio_contract import validate_wav_contract
from server.cognition.authorization import evaluate_authorization
from server.cognition.clock import utc_now
from server.cognition.controller import (
    ActivePersonResolver,
    CognitiveController,
    ConsentResolver,
    DocumentAnswerer,
    MemoryAnswerer,
    MemoryChanger,
    ProfileSummarizer,
    ReadingKeeper,
    RecallAnswerer,
    TextReader,
)
from server.cognition.document_cues import DocumentCue
from server.cognition.generic_identity import (
    GenericIdentification,
    identify_generic_speaker,
)
from server.cognition.household_tools import HouseholdKnowledgeTools
from server.cognition.identity import ActivePersonContext
from server.cognition.identity_fusion import FusedIdentityResolver, build_fused_identity_resolver
from server.cognition.intent_resolution import MemoryAnswer
from server.cognition.memory_change import MemoryChange
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import OwnerUnlockService
from server.cognition.recall_cues import RecallCue
from server.cognition.response_plan import (
    DocumentReply,
    InformationNeed,
    KeepOutcome,
    MemoryAnswerReply,
    ProfileSummaryReply,
    ReadingOutcome,
    ReadingReply,
    RecallReply,
    ResponsePlan,
    SceneDescriptionRequest,
    SensitiveReader,
    SensitiveReply,
    TextTurnPayload,
    current_perception_plan,
    recorded_exchange,
    scene_failed_plan,
    scene_unavailable_plan,
    spoken_log_text,
    unclear_speech_plan,
)
from server.cognition.sensitive_questions import SensitiveQuery
from server.cognition.spoken_dates import day_month_label
from server.dependencies import IdentityTokenDep, OwnerUnlockServiceDep, ResourcesDep
from server.exceptions import (
    AudioContractError,
    UnclearSpeechError,
    UploadTooLargeError,
    VisionError,
)
from server.memory.candidate_dialogue import (
    OfferPreparer,
    PendingOffer,
    answer_offer,
    prepare_offer,
)
from server.memory.candidate_proposal import propose_candidates
from server.memory.candidate_types import CandidateChannel
from server.memory.continuity import ContinuityTurn
from server.memory.conversation_capture import capture_turn
from server.memory.document_access import document_reply
from server.memory.document_index import backfill_sections
from server.memory.document_secrets import flags_secret
from server.memory.entity_labels import read_household_names
from server.memory.household_authorization import record_authorization_decision
from server.memory.household_time import household_day, household_today
from server.memory.memory_change_dialogue import (
    answer_change,
    has_any_pending_change,
    propose_change,
)
from server.memory.pending_follow_up import (
    FollowUpPreparer,
    PendingFollowUp,
    prepare_follow_up,
)
from server.memory.pending_store import pending_topics_on
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.profile_card import PromptCard
from server.memory.profile_card_access import (
    may_read_own_memory,
    profile_summary_text,
    prompt_card_for_turn,
)
from server.memory.reading_offer import READING_SLOT, keep_reading
from server.memory.recall_access import recall_reply
from server.memory.recall_store import occurred_time_on
from server.memory.sensitive_access import sensitive_reply
from server.memory.write_types import WriteChannel
from server.pipeline import (
    _elapsed_ms,
    _log_pipeline_timing,
    _run_stt,
    _run_tts,
)
from server.routers.image_upload import read_contract_image
from server.schemas import IdentitySource, TranscribeResponse, error_responses
from server.schemas_streaming import StreamEvent
from server.settings import settings
from server.streaming import (
    guarantee_terminal_event,
    stream_looking_plan,
    stream_pipeline,
    stream_response_plan,
)
from server.stt import SHORT_REPLY_HOTWORDS
from server.text_turn import (
    ProfileCardProvider,
    ProposalScheduler,
    TextTurnResult,
    TurnRecorder,
    new_interaction_scope,
    prepare_text_turn,
    process_text_turn,
)
from server.uploads import read_limited_upload
from server.vision.perception import perceive_scene
from server.vision.read_text import read_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transcribe", tags=["Audio"])

# «Iroko, lee esto» (Plan 0088 D-17): the read text spoken at most this long (about 25 s),
# and the kept note titled by the day and its first words.
_MAX_READING_CHARS = 400
_TITLE_WORDS = 5
_MAX_NOTE_TITLE = 120
# Sections embedded right after a note is kept (a note is a few sections; older ones wait).
_KEPT_NOTE_EMBEDS = 10

type SpeakerIdentifier = Callable[[], Awaitable[GenericIdentification]]


class NDJSONStreamingResponse(StreamingResponse):
    """A streaming response whose media type is `application/x-ndjson`.

    Used as the `response_class` for `POST /transcribe/stream` so the
    generated OpenAPI documents the real wire contract — one JSON object
    per line — instead of the `application/json` FastAPI infers from a bare
    `StreamingResponse` return. The handler still returns its own response
    instance directly (Plan 0041: a pre-stream `HTTPException` must surface
    as a real 413/422/500, which returning through the generator would
    prevent).
    """

    media_type = "application/x-ndjson"


# Prose contract for the streaming 200, shown in `/docs` alongside the
# per-line event schemas (`StreamEvent`).
_STREAM_200_DESCRIPTION = (
    "NDJSON stream — one JSON object per line, in order: an optional "
    "`text_heard` event, one `emotion` event, zero or more `audio` events "
    "(one per synthesized sentence), then exactly one terminal `done` "
    "(per-stage timing) or `error` (stable `code`, fixed client-safe "
    "`detail`, `retryable`). Every started stream ends in exactly one "
    "terminal event followed by EOF (ADR-0012). `done` carries `expects_short_reply`, "
    "true when the turn ended with a spoken question the client should listen to once."
)

# `response_class=NDJSONStreamingResponse` also drives the media type of
# this route's *error* responses, so the pre-stream 413 (a plain JSON
# `{"detail": ...}` body, not NDJSON) is re-pinned to `application/json`
# explicitly. The `$ref` is the component name FastAPI itself assigns to
# `ErrorResponse` — stable, and asserted by `test_api_contract.py`.
_STREAM_413_RESPONSE = {
    "description": "Audio or attached frame exceeds the upload size limit",
    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
}


def _today() -> date:
    """Return the household's day for deterministic P0 tools (``HOUSEHOLD_TIMEZONE``, never the
    machine's own zone: a server in UTC disagrees with a household in Chile for hours a night)."""
    return household_today()


def _voice_event_from_transcript(message: str) -> CognitiveEvent[TextTurnPayload]:
    """Translate one STT transcript into a fresh typed cognitive event."""
    now = datetime.now(UTC)
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=now,
        recorded_at=now,
        source="audio.transcribe",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(
            message=message,
            conversation_id=new_interaction_scope(),
        ),
    )


@dataclass
class _RequestIdentity:
    """Uniform per-request actor/consent resolver over the fused identity evidence.

    Attributes:
        resolve_actor: The actor resolver to hand to the controller; it may spend the grant.
        peek_actor: The same actor observed without spending any grant (ADR-0015).
        resolve_consent: The matching consent resolver.
        fused: The fusion resolver, the source of `.consumed` and `.identity_source`.
        last_actor: The actor the controller last resolved or observed for this request, or
            ``None`` when it resolved none; the conversation record uses it for a
            deterministic reply (Plan 0076).
    """

    resolve_actor: ActivePersonResolver
    peek_actor: ActivePersonResolver
    resolve_consent: ConsentResolver
    fused: FusedIdentityResolver
    last_actor: ActivePersonContext | None = None

    @property
    def consumed(self) -> bool:
        """Whether this request consumed a fresh one-use owner PIN unlock grant."""
        return self.fused.consumed

    @property
    def identity_source(self) -> IdentitySource | None:
        """Which evidence identified the actor, or `None` for none."""
        return self.fused.source


def _build_request_identity(
    owner_unlock_service: OwnerUnlockService,
    token: str | None,
    frame: bytes | None,
    wav_bytes: bytes | None,
) -> _RequestIdentity:
    """Compose this request's actor/consent resolver (Plan 0054, ADR 0016).

    Args:
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).
        token: Optional one-use owner PIN unlock token from the request header.
        frame: Optional validated webcam frame; `None` when absent or face
            authentication is off.
        wav_bytes: The turn's own audio — WAV, 16 000 Hz, mono, int16.

    Returns:
        A `_RequestIdentity` over one `FusedIdentityResolver`.
    """
    pin = owner_unlock_service.for_request(token)
    fused = build_fused_identity_resolver(pin, frame=frame, wav_bytes=wav_bytes)
    return _RequestIdentity(
        resolve_actor=fused.resolve_actor,
        peek_actor=fused.peek_actor,
        resolve_consent=fused.resolve_consent,
        fused=fused,
    )


def _logged_voice_actor_resolver(
    request_identity: _RequestIdentity,
) -> ActivePersonResolver:
    """Wrap a request-scoped resolver to preserve the existing actor log line."""

    async def resolve_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        actor = await request_identity.resolve_actor(event)
        request_identity.last_actor = actor
        turn_log.log_actor("voice", actor)
        return actor

    return resolve_actor


def _logged_voice_observer(
    request_identity: _RequestIdentity,
) -> ActivePersonResolver:
    """Wrap the observing resolver to keep the actor log line without spending a grant."""

    async def observe_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        actor = await request_identity.peek_actor(event)
        request_identity.last_actor = actor
        turn_log.log_actor("voice", actor)
        return actor

    return observe_actor


def _voice_controller(
    client: httpx.AsyncClient,
    *,
    request_identity: _RequestIdentity | None = None,
    identify_speaker: SpeakerIdentifier | None = None,
    schedule_proposal: ProposalScheduler | None = None,
    prepare_offer: OfferPreparer | None = None,
    memory_answerer: MemoryAnswerer | None = None,
    memory_changer: MemoryChanger | None = None,
    profile_card_provider: ProfileCardProvider | None = None,
    profile_summarizer: ProfileSummarizer | None = None,
    record_turn: TurnRecorder | None = None,
    recall_answerer: RecallAnswerer | None = None,
    follow_up_preparer: FollowUpPreparer | None = None,
    frame: bytes | None = None,
) -> CognitiveController:
    """Compose the bounded controller used by a public voice turn.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039), closed over
            by the legacy-turn delegate.
        request_identity: Optional request-scoped actor/consent resolver over
            the fused face, voice and PIN evidence (Plan 0054). When omitted,
            the controller falls back to its own public-unknown defaults.
        identify_speaker: Names the speaker of a generic turn from the face and an
            observed token (Plan 0061, ADR 0020); when omitted the speaker is unknown.
        schedule_proposal: Schedules the background candidate proposal of a successful
            generic turn (Plan 0062); when omitted nothing is proposed.
        prepare_offer: Prepares the memory offer spoken after a generic reply (ADR 0021
            decision 9); when omitted nothing is offered.
        memory_answerer: Answers a memory offer (ADR 0021 decision 9). Only used together
            with ``request_identity``, the resolver it needs; when omitted an answer-shaped
            message is ordinary conversation.
        memory_changer: Reads back a spoken correction or archive (Plan 0086). Only used
            together with ``request_identity``; when omitted the change grammar never runs.
        profile_card_provider: Renders the speaker's profile card for the prompt of a generic
            turn (Plan 0074); when omitted the turn reads no card.
        profile_summarizer: Answers «¿qué sabes de mí?» from the same card. Only used together
            with ``request_identity``, like ``memory_answerer``; when omitted the question is
            ordinary conversation.
        record_turn: Schedules the capture of the generic turn into the conversation record
            (Plan 0076); when omitted nothing is recorded.
        recall_answerer: Answers a recall question from the owner's diary (Plan 0078). Only
            used together with ``request_identity``; when omitted the recall and relatives rules
            never run.
        follow_up_preparer: Prepares the pending-topic follow-up spoken after a generic reply
            (Plan 0084); when omitted no topic is picked up.
    """

    async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
        """Name the speaker, then converse through the existing text service."""
        speaker = (
            await identify_speaker()
            if identify_speaker is not None
            else GenericIdentification(actor=None, cause=None)
        )
        if speaker.actor is not None:
            turn_log.log_actor("voice", speaker.actor)
        return await process_text_turn(
            client,
            message,
            conversation_id,
            active_person=speaker.actor,
            suspend_cause=speaker.cause,
            schedule_proposal=schedule_proposal,
            prepare_offer=prepare_offer,
            profile_card_provider=profile_card_provider,
            record_turn=record_turn,
            prepare_follow_up=follow_up_preparer,
        )

    household_tools = HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())
    if request_identity is None:
        return CognitiveController(
            today=_today,
            legacy_turn=legacy_turn,
            policy_evaluator=evaluate_authorization,
            audit_writer=record_authorization_decision,
            household_tools=household_tools,
            secret_guard=settings.memory_enabled,
        )
    return CognitiveController(
        today=_today,
        legacy_turn=legacy_turn,
        active_person_resolver=_logged_voice_actor_resolver(request_identity),
        observed_person_resolver=_logged_voice_observer(request_identity),
        policy_evaluator=evaluate_authorization,
        audit_writer=record_authorization_decision,
        household_tools=household_tools,
        consent_resolver=request_identity.resolve_consent,
        memory_answerer=memory_answerer,
        memory_changer=memory_changer,
        profile_summarizer=profile_summarizer,
        household_names=read_household_names if settings.memory_enabled else None,
        recall_answerer=recall_answerer,
        sensitive_reader=_sensitive_reader(request_identity, household_tools),
        secret_guard=settings.memory_enabled,
        # Plan 0082: the rest of the alta joins the sensitive read; inert without the reader.
        alta_read=settings.alta_read_enabled,
        # Plan 0083: when a told event happened; inert without the recall answerer.
        occurred_time=occurred_time_on(),
        document_answerer=_document_answerer(client, request_identity),
        text_reader=_text_reader(client, request_identity, frame),
        reading_keeper=_reading_keeper(client, request_identity),
    )


def _proposal_scheduler(
    client: httpx.AsyncClient,
    background_tasks: BackgroundTasks,
    *,
    event: CognitiveEvent[TextTurnPayload],
    wav_bytes: bytes,
    channel: CandidateChannel,
) -> ProposalScheduler:
    """Adapt FastAPI background tasks to the text service's proposal callback (ADR 0021 decision 10).

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039) — safe to
            close over here, since the app's lifespan outlives any single
            request's background tasks.
        background_tasks: Queue used to run the proposal after the response was sent.
        event: The turn's event; its correlation id joins audit rows to candidates.
        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — held in memory only,
            for the voice check that runs before anything is extracted.
        channel: The voice route the proposal belongs to.
    """

    def schedule(message: str, active_person: ActivePersonContext) -> None:
        background_tasks.add_task(
            propose_candidates,
            client,
            message,
            active_person,
            event=event,
            wav_bytes=wav_bytes,
            channel=channel,
        )

    return schedule


def _turn_recorder(
    background_tasks: BackgroundTasks,
    *,
    event: CognitiveEvent[TextTurnPayload],
    wav_bytes: bytes,
    client: httpx.AsyncClient,
) -> TurnRecorder | None:
    """Adapt FastAPI background tasks to the conversation-record callback (ADR 0027).

    Args:
        background_tasks: Queue used to run the capture after the response was sent.
        event: The turn's event; its correlation id joins the exchange to the turn.
        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — held in memory only,
            for the voice verdict; never stored.
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the vector of the turn's
            recall unit; passed only with ``RECALL_ENABLED`` (ADR 0028).

    Returns:
        The callback, or ``None`` with ``MEMORY_ENABLED`` or ``CONVERSATION_RECORD_ENABLED``
        off.
    """
    if not (settings.memory_enabled and settings.conversation_record_enabled):
        return None
    at = utc_now()
    capture = partial(capture_turn, client=client) if settings.recall_enabled else capture_turn

    def record(heard: str, said: str, actor: ActivePersonContext | None) -> None:
        background_tasks.add_task(
            capture, heard, said, actor, wav_bytes=wav_bytes, event=event, at=at
        )

    return record


def _record_plan(
    record_turn: TurnRecorder | None,
    heard: str,
    plan: ResponsePlan,
    request_identity: _RequestIdentity,
) -> None:
    """Record a deterministic reply with the speaker the controller resolved for it, if any.

    A reply the controller answered without resolving anyone (the date) is ``not_checked``;
    one it answered for a resolved speaker (a protected household question) carries that
    speaker, so the owner's verified words are not lost to the diary (Plan 0076 D-7). A secret
    turn and a sensitive answer keep a marker instead of the words (Plan 0079 D-8).
    """
    if record_turn is not None:
        record_turn(*recorded_exchange(plan, heard), request_identity.last_actor)


def _offer_preparer(
    *, event: CognitiveEvent[TextTurnPayload], wav_bytes: bytes
) -> OfferPreparer | None:
    """Bind the turn's clip and event to the memory-offer preparation (ADR 0021 decision 9).

    Args:
        event: The turn's event; its correlation id stamps the audit row and the offer.
        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — held in memory only,
            for the voice check that runs only when a candidate waits.

    Returns:
        The preparation, or ``None`` with ``MEMORY_ENABLED`` or ``MEMORY_CANDIDATES_ENABLED``
        off.
    """
    if not (settings.memory_enabled and settings.memory_candidates_enabled):
        return None

    async def prepare(actor: ActivePersonContext) -> PendingOffer | None:
        return await prepare_offer(actor, wav_bytes=wav_bytes, event=event)

    return prepare


def _follow_up_preparer(event: CognitiveEvent[TextTurnPayload]) -> FollowUpPreparer | None:
    """Bind the turn's id and the household day to the pending-topic follow-up (Plan 0084).

    Args:
        event: The turn's event; its correlation id stamps the audit row.

    Returns:
        The preparation, or ``None`` unless ``pending_topics_on()`` (the switch, memory and the
        record). Only the two voice routes bind it; ``/chat`` and ``/vision/respond`` never do.
    """
    if not pending_topics_on():
        return None
    correlation_id = event.correlation_id

    async def prepare(
        actor: ActivePersonContext, session: ContinuityTurn
    ) -> PendingFollowUp | None:
        return await prepare_follow_up(
            actor,
            session,
            today=household_day(utc_now()),
            correlation_id=correlation_id,
        )

    return prepare


def _memory_answerer() -> MemoryAnswerer | None:
    """Return the answer to a memory offer or change for a voice route, or ``None`` with memory off.

    A closed verb first answers the speaker's pending change (Plan 0086), then, with
    ``MEMORY_CANDIDATES_ENABLED`` on, their open offer. With ``MEMORY_ENABLED`` off, or with the
    candidates off and no change read back in the last answer window, an answer-shaped message is
    ordinary conversation and the actor is not even resolved for it (a change, like an offer, was
    said aloud in the room, so binding the answer while one waits reveals nothing new).
    """
    if not settings.memory_enabled:
        return None
    offers = settings.memory_candidates_enabled
    if not offers and not has_any_pending_change(utc_now()):
        return None

    async def answer(
        parsed: MemoryAnswer,
        actor: ActivePersonContext,
        event: CognitiveEvent[TextTurnPayload],
    ) -> MemoryAnswerReply | None:
        now = utc_now()
        changed = await answer_change(
            parsed, actor=actor, correlation_id=event.correlation_id, now=now
        )
        if changed is not None or not offers:
            return changed
        return await answer_offer(parsed, actor=actor, correlation_id=event.correlation_id, now=now)

    return answer


def _memory_changer(channel: WriteChannel) -> MemoryChanger | None:
    """Return the change read-back for a voice route (Plan 0086), or ``None`` with memory off.

    Args:
        channel: The route's write channel, for a correction's new fact.
    """
    if not settings.memory_enabled:
        return None

    async def change(
        parsed: MemoryChange,
        actor: ActivePersonContext,
        event: CognitiveEvent[TextTurnPayload],
    ) -> MemoryAnswerReply | None:
        return await propose_change(
            parsed, actor=actor, channel=channel, correlation_id=event.correlation_id, now=utc_now()
        )

    return change


def _profile_card_provider(correlation_id: UUID) -> ProfileCardProvider | None:
    """Return the profile card seam of a voice turn, or ``None`` with a switch off (ADR 0026).

    With ``MEMORY_ENABLED`` or ``PROFILE_CARD_ENABLED`` off the turn reads no card and writes no
    audit row. Only the two voice routes bind it; ``/chat`` and ``/vision/respond`` never do.

    Args:
        correlation_id: The turn's id, so the audit row of the read joins to the rest of the turn.
    """
    if not (settings.memory_enabled and settings.profile_card_enabled):
        return None

    async def provide(actor: ActivePersonContext, message: str) -> PromptCard | None:
        return await prompt_card_for_turn(
            actor, message, correlation_id=correlation_id, now=utc_now()
        )

    return provide


def _profile_summarizer() -> ProfileSummarizer | None:
    """Return the answer to «¿qué sabes de mí?» for a voice route, or ``None`` with a switch off.

    With ``MEMORY_ENABLED`` or ``PROFILE_CARD_ENABLED`` off the question is ordinary conversation
    and the actor is not even resolved for it.
    """
    if not (settings.memory_enabled and settings.profile_card_enabled):
        return None

    async def summarize(
        actor: ActivePersonContext, event: CognitiveEvent[TextTurnPayload]
    ) -> ProfileSummaryReply:
        return await profile_summary_text(actor, correlation_id=event.correlation_id, now=utc_now())

    return summarize


def _recall_answerer(client: httpx.AsyncClient) -> RecallAnswerer | None:
    """Return the answer to a recall question for a voice route, or ``None`` with a switch off.

    With ``MEMORY_ENABLED`` or ``RECALL_ENABLED`` off every message resolves as before Plan 0078
    and nothing reads the diary.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the embedding and the
            worded answer.
    """
    if not (settings.memory_enabled and settings.recall_enabled):
        return None

    async def answer(
        actor: ActivePersonContext, cue: RecallCue, event: CognitiveEvent[TextTurnPayload]
    ) -> RecallReply:
        return await recall_reply(
            actor,
            cue,
            question=event.payload.message,
            correlation_id=event.correlation_id,
            now=utc_now(),
            client=client,
        )

    return answer


def _document_answerer(
    client: httpx.AsyncClient, request_identity: _RequestIdentity
) -> DocumentAnswerer | None:
    """Return the answer to a document question for a voice route, or ``None`` with a switch off.

    With ``MEMORY_ENABLED`` or ``DOCUMENTS_ENABLED`` off every message resolves as before Plan
    0088 and nothing reads a document. The face fusion's reason (a second face in view leaves the
    ``sensitive`` documents out) is read when the controller calls it, after it resolved the
    actor.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the embedding and the answer.
        request_identity: This request's identity resolver (the fusion reason).
    """
    if not (settings.memory_enabled and settings.documents_enabled):
        return None

    async def answer(
        actor: ActivePersonContext, cue: DocumentCue, event: CognitiveEvent[TextTurnPayload]
    ) -> DocumentReply:
        return await document_reply(
            actor,
            cue,
            question=event.payload.message,
            faces=request_identity.fused.last_reason,
            correlation_id=event.correlation_id,
            now=utc_now(),
            client=client,
        )

    return answer


def _reading_on() -> bool:
    """«Iroko, lee esto» needs memory, the documents, the vision model and the face check, which
    is what carries the turn's frame (Plan 0088 D-17)."""
    return (
        settings.memory_enabled
        and settings.documents_enabled
        and settings.vision_enabled
        and settings.face_authentication_enabled
    )


def _cap_reading(text: str) -> str:
    """The read text as it is spoken: at most ``_MAX_READING_CHARS`` (about 25 s of speech)."""
    flat = " ".join(text.split())
    if len(flat) <= _MAX_READING_CHARS:
        return flat
    return flat[: _MAX_READING_CHARS - 1].rsplit(" ", 1)[0] + "…"


def _text_reader(
    client: httpx.AsyncClient, request_identity: _RequestIdentity, frame: bytes | None
) -> TextReader | None:
    """Return the reading of the turn's own frame, or ``None`` with a switch off (D-17).

    The frame is the one the route already validated for face authentication; it is read in
    memory by the VLM and never stored or logged. A text the document secret detector flags is not
    read and nothing waits to be kept.
    """
    if not _reading_on():
        return None

    async def read(event: CognitiveEvent[TextTurnPayload]) -> ReadingReply:
        if frame is None:
            return ReadingReply(outcome=ReadingOutcome.NO_FRAME)
        try:
            text = _cap_reading(await read_text(client, frame))
        except VisionError as exc:
            logger.warning("Reading failed (%s)", type(exc).__name__)
            return ReadingReply(outcome=ReadingOutcome.FAILED)
        if flags_secret(text):
            READING_SLOT.clear()
            return ReadingReply(outcome=ReadingOutcome.SECRET)
        try:
            actor = await request_identity.peek_actor(event)
        except Exception as exc:  # seam boundary: the text is read aloud, it just cannot be kept
            logger.warning("Reading speaker unknown (%s)", type(exc).__name__)
            READING_SLOT.clear()
            return ReadingReply(outcome=ReadingOutcome.READ, text=text)
        READING_SLOT.offer(text, speaker=actor.person_id, now=utc_now())
        return ReadingReply(outcome=ReadingOutcome.READ, text=text)

    return read


def _note_title(text: str, now: datetime) -> str:
    """«Nota del {día}: {primeras palabras}», or «Nota del {día}» when they hold a digit."""
    day = day_month_label(household_day(now)).replace("el ", "del ", 1)
    words = " ".join(text.split()[:_TITLE_WORDS])
    if not words or any(character.isdigit() for character in words):
        return f"Nota {day}"
    return f"Nota {day}: {words}"[:_MAX_NOTE_TITLE]


def _reading_keeper(
    client: httpx.AsyncClient, request_identity: _RequestIdentity
) -> ReadingKeeper | None:
    """Return the keeper of the waiting reading, or ``None`` with a switch off (D-17).

    Every turn empties the slot unless it is «sí, guárdalo» from the owner's face within 60
    seconds, from the speaker the reading was bound to (or anyone, when it was bound to nobody).
    A kept note is embedded at once, as ``iroko-admin docs add`` does: a question that names
    nothing specific finds a section only by its distance (ADR 0040), and the conversation job
    does not run while the conversation is open.
    """
    if not _reading_on():
        return None

    async def keep(event: CognitiveEvent[TextTurnPayload], wants: bool) -> KeepOutcome:
        try:
            return await _keep(event, wants)
        except Exception as exc:  # seam boundary: a failed keep is no keep, the turn goes on
            logger.warning("Reading not kept (%s)", type(exc).__name__)
            READING_SLOT.clear()
            return KeepOutcome.NOT_KEPT

    async def _keep(event: CognitiveEvent[TextTurnPayload], wants: bool) -> KeepOutcome:
        now = utc_now()
        if not READING_SLOT.is_open(now):
            READING_SLOT.clear()
            return KeepOutcome.NO_SLOT
        if not wants:
            READING_SLOT.clear()
            return KeepOutcome.NOT_KEPT
        actor = await request_identity.peek_actor(event)
        if actor.person_id is None or not may_read_own_memory(actor):
            READING_SLOT.clear()
            return KeepOutcome.NOT_KEPT
        text = READING_SLOT.take(actor.person_id, now)
        if text is None:
            return KeepOutcome.NOT_KEPT
        await keep_reading(actor.person_id, text, title=_note_title(text, now), now=now)
        await backfill_sections(client, limit=_KEPT_NOTE_EMBEDS)
        return KeepOutcome.KEPT

    return keep


def _sensitive_reader(
    request_identity: _RequestIdentity, household_tools: HouseholdKnowledgeTools
) -> SensitiveReader | None:
    """Return the owner's sensitive read for a voice route, or ``None`` with a switch off.

    With ``MEMORY_ENABLED`` or ``SENSITIVE_READ_ENABLED`` off a sensitive question is ordinary
    conversation, and the actor is not even resolved for it. The face fusion's reason and the
    consent are read when the controller calls the reader, that is after it resolved the actor.

    Args:
        request_identity: This request's identity resolver (the fusion reason and the consent).
        household_tools: The controller's own tools, for the children's birth dates.
    """
    if not (settings.memory_enabled and settings.sensitive_read_enabled):
        return None

    async def read(
        actor: ActivePersonContext,
        query: SensitiveQuery,
        event: CognitiveEvent[TextTurnPayload],
    ) -> SensitiveReply:
        consent = await request_identity.resolve_consent(event, actor)
        return await sensitive_reply(
            actor,
            query,
            faces=request_identity.fused.last_reason,
            face_consent=consent,
            voice_check=settings.speaker_authentication_enabled,
            correlation_id=event.correlation_id,
            now=utc_now(),
            household_tools=household_tools,
        )

    return read


async def _synthesize_reply(plan: ResponsePlan) -> tuple[str, int, int]:
    """Synthesize the response and the memory offer as one WAV; the offer never costs the reply.

    The spoken-text log carries the response only: the offer holds a value (ADR 0021 decision 9). When
    the combined synthesis fails, the response is synthesized alone, so a failing offer never
    turns a good reply into a 500. The first failure is already logged by ``_run_tts`` at error
    level, with the exception class only, since the combined text carries a value.

    Args:
        plan: The authorized plan; ``plan.offer``, when set, is spoken right after the response
            in the same clip.

    Returns:
        Tuple of (base64 WAV audio — 16 kHz, mono, int16, TTS-reported synthesis ms, elapsed
        TTS ms), as ``_run_tts`` returns.

    Raises:
        HTTPException: 500 when even the response alone cannot be synthesized.
    """
    # A profile summary carries stored values: the opt-in spoken-text log shows a marker instead.
    logged_text = spoken_log_text(plan)
    if plan.offer is None:
        return await _run_tts(plan.response, logged_text=logged_text)
    try:
        return await _run_tts(
            f"{plan.response} {plan.offer}", logged_text=logged_text or plan.response
        )
    except HTTPException:
        logger.warning("Memory offer not synthesized; speaking the reply alone")
        return await _run_tts(plan.response, logged_text=logged_text)


async def _transcribe_turn(audio_bytes: bytes, hotwords: list[str]) -> tuple[str, int, bool]:
    """Run the speech-to-text; a transcript Whisper doubted comes back flagged, not raised.

    Args:
        audio_bytes: Raw WAV bytes — 16kHz, mono, int16.
        hotwords: Extra hotwords for this request.

    Returns:
        The transcript, the STT milliseconds and whether it is unclear (Plan 0069 D-11). An
        unclear transcript must never reach the controller.
    """
    start = time.perf_counter()
    try:
        text, stt_ms = await _run_stt(audio_bytes, hotwords)
    except UnclearSpeechError as exc:
        logger.info(
            "STT unclear (%d chars) — asking to repeat",
            len(exc.text),
            extra={"event": "stt.unclear", "chars": len(exc.text)},
        )
        return exc.text, _elapsed_ms(start), True
    return text, stt_ms, False


async def _classic_reply(
    plan: ResponsePlan,
    *,
    text_heard: str,
    stt_ms: int,
    request_start: float,
    request_identity: _RequestIdentity,
) -> TranscribeResponse:
    """Speak one plan on the classic route and build its response.

    Args:
        plan: The turn's plan.
        text_heard: What the speech-to-text heard.
        stt_ms: Speech-to-text milliseconds.
        request_start: ``time.perf_counter()`` at the start of the request.
        request_identity: This request's identity resolver.

    Returns:
        The classic response, its WAV 16 kHz, mono, int16 carried as base64.
    """
    turn_log.log_decision("voice", plan)
    # One WAV carries the reply and the memory offer; `llm_response` and the spoken-text log
    # carry the reply only (ADR 0021 decision 9).
    audio_base64, duration_ms, tts_ms = await _synthesize_reply(plan)

    total_ms = _elapsed_ms(request_start)
    _log_pipeline_timing(f"voice.{plan.source.value}", stt_ms, plan.duration_ms, tts_ms, total_ms)
    return TranscribeResponse(
        text_heard=text_heard,
        llm_response=plan.response,
        audio_base64=audio_base64,
        duration_ms=duration_ms,
        emotion=plan.emotion,
        stt_ms=stt_ms,
        llm_ms=plan.duration_ms,
        tts_ms=tts_ms,
        total_ms=total_ms,
        authentication_consumed=request_identity.consumed,
        # A generic reply never reports identity (ADR 0020), including an answer-shaped message
        # that fell through after its actor was resolved: the wire is the ordinary one.
        identity_source=None
        if plan.need is InformationNeed.GENERIC_CONVERSATION
        else request_identity.identity_source,
    )


def _scene_on() -> bool:
    """Whether a streaming scene turn may read its frame (Plan 0089 D-3).

    The frame travels only with face authentication on; no memory, document or identity is
    needed, because a scene description reads no household store.
    """
    return settings.vision_enabled and settings.face_authentication_enabled


async def _look(client: httpx.AsyncClient, frame: bytes) -> ResponsePlan:
    """Describe the scene from the turn's own frame (Plan 0089 D-4); never raises.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        frame: The turn's validated frame (JPEG/PNG/WebP/GIF/BMP, max 1280x720). Processed in
            memory and never stored or logged.

    Returns:
        The description, or the fixed failure phrase when the vision model fails (its cause is
        already logged).
    """
    try:
        return current_perception_plan(await perceive_scene(client, frame))
    except VisionError:
        return scene_failed_plan()


def _stream_plan(
    plan: ResponsePlan,
    *,
    text_heard: str,
    stt_ms: int,
    request_start: float,
    request_identity: _RequestIdentity,
) -> NDJSONStreamingResponse:
    """Stream one deterministic plan (its WAV chunks 16 kHz, mono, int16) and its `done`.

    Args:
        plan: The turn's plan.
        text_heard: What the speech-to-text heard.
        stt_ms: Speech-to-text milliseconds.
        request_start: ``time.perf_counter()`` at the start of the request.
        request_identity: This request's identity resolver.

    Returns:
        The NDJSON response, guaranteed to end in one terminal event.
    """
    return NDJSONStreamingResponse(
        guarantee_terminal_event(
            stream_response_plan(
                text_heard=text_heard,
                plan=plan,
                stt_ms=stt_ms,
                request_start=request_start,
                authentication_consumed=request_identity.consumed,
                identity_source=request_identity.identity_source,
            )
        )
    )


async def _read_audio_upload(audio: UploadFile) -> bytes:
    """Read and validate WAV 16kHz, mono, int16 upload bytes."""
    try:
        audio_bytes = await read_limited_upload(audio, limit=settings.max_audio_upload_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large — max {exc.limit // 1024 // 1024} MB",
        ) from exc
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="Audio file is empty")
    try:
        validate_wav_contract(audio_bytes, max_duration_s=settings.max_audio_duration_s)
    except AudioContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return audio_bytes


@router.post(
    "",
    responses=error_responses((413, "Audio or attached frame exceeds the upload size limit")),
)
async def transcribe(
    resources: ResourcesDep,
    owner_unlock_service: OwnerUnlockServiceDep,
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16")],
    background_tasks: BackgroundTasks,
    x_iroko_identity_token: IdentityTokenDep = None,
    frame: Annotated[
        UploadFile | None,
        File(
            description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · optional owner-authentication frame"
        ),
    ] = None,
) -> TranscribeResponse:
    """Transcribe audio, generate a robot response, and synthesize speech.

    Args:
        audio: WAV at 16kHz, mono, int16, within MAX_AUDIO_UPLOAD_BYTES.
        background_tasks: Queue for the candidate proposal of a successful voice turn.
        x_iroko_identity_token: Optional one-use owner unlock token. Absent,
            expired, replayed, or malformed tokens resolve to the public
            unknown actor without disclosing which case occurred.
        frame: Optional webcam frame attached for in-request face
            authentication (Plan 0029). Only read and decoded when
            `settings.face_authentication_enabled` is `True` — otherwise
            accepted but completely inert. A malformed or oversized frame
            degrades to no frame instead of failing the turn.

    Returns:
        Existing audio response contract with text, WAV, emotion, timings,
        whether this turn consumed a fresh owner unlock grant, and which
        evidence source (face/face_voice/local_unlock/none) identified the actor.

    Raises:
        HTTPException: 413 for size, 422 for WAV/speech, or 500 for STT/TTS.
    """
    request_start = time.perf_counter()
    turn_log.log_start("voice")
    frame_bytes: bytes | None = None
    if settings.face_authentication_enabled and frame is not None:
        try:
            frame_bytes = await read_contract_image(frame, noun="Frame")
        except HTTPException as exc:
            logger.warning(
                "Owner-authentication frame rejected — continuing without it: %s", exc.detail
            )
    audio_bytes = await _read_audio_upload(audio)
    request_identity = _build_request_identity(
        owner_unlock_service, x_iroko_identity_token, frame_bytes, audio_bytes
    )

    text_heard, stt_ms, unclear = await _transcribe_turn(audio_bytes, [])

    if not text_heard.strip():
        logger.warning("STT returned empty transcript — audio was silence or too short")
        raise HTTPException(status_code=422, detail="No speech detected in audio")
    if unclear:
        return await _classic_reply(
            unclear_speech_plan(expects_short_reply=False),
            text_heard=text_heard,
            stt_ms=stt_ms,
            request_start=request_start,
            request_identity=request_identity,
        )

    event = _voice_event_from_transcript(text_heard)
    record_turn = _turn_recorder(
        background_tasks, event=event, wav_bytes=audio_bytes, client=resources.http_client
    )
    controller = _voice_controller(
        resources.http_client,
        request_identity=request_identity,
        identify_speaker=partial(
            identify_generic_speaker,
            owner_unlock_service.for_request,
            token=x_iroko_identity_token,
            frame=frame_bytes,
            event=event,
        ),
        schedule_proposal=_proposal_scheduler(
            resources.http_client,
            background_tasks,
            event=event,
            wav_bytes=audio_bytes,
            channel=CandidateChannel.VOICE_CLASSIC,
        ),
        prepare_offer=_offer_preparer(event=event, wav_bytes=audio_bytes),
        memory_answerer=_memory_answerer(),
        memory_changer=_memory_changer(WriteChannel.VOICE_CLASSIC),
        profile_card_provider=_profile_card_provider(event.correlation_id),
        profile_summarizer=_profile_summarizer(),
        record_turn=record_turn,
        recall_answerer=_recall_answerer(resources.http_client),
        follow_up_preparer=_follow_up_preparer(event),
        frame=frame_bytes,
    )
    decision = await controller.decide(event)

    plan: ResponsePlan
    if isinstance(decision, SceneDescriptionRequest):
        if settings.vision_enabled:
            # V0.5/V1 — a visual question needs a camera frame the classic
            # request did not carry: answer NOW with a short spoken cue and
            # ask the client for one (second round via /vision/respond). The
            # cue phrase covers the VLM latency; this stub turn is not
            # recorded in memory — the real exchange lands in round two.
            logger.info(
                "Scene description requested (%d chars) — requesting a frame",
                len(text_heard),
                extra={"event": "vision.frame_requested", "chars": len(text_heard)},
            )
            audio_base64, duration_ms, tts_ms = await _run_tts(settings.vision_look_phrase)
            total_ms = _elapsed_ms(request_start)
            _log_pipeline_timing("voice.vision-cue", stt_ms, 0, tts_ms, total_ms)
            return TranscribeResponse(
                text_heard=text_heard,
                llm_response=settings.vision_look_phrase,
                audio_base64=audio_base64,
                duration_ms=duration_ms,
                emotion="neutral",
                vision_requested=True,
                stt_ms=stt_ms,
                tts_ms=tts_ms,
                total_ms=total_ms,
                authentication_consumed=request_identity.consumed,
                identity_source=request_identity.identity_source,
            )
        plan = scene_unavailable_plan()
    elif decision is None:
        plan = await controller.handle(event)
    else:
        plan = decision
    if decision is not None:
        # A deterministic reply (or the fixed scene-unavailable one); a generic turn was
        # recorded by the text service, with its speaker.
        _record_plan(record_turn, text_heard, plan, request_identity)

    return await _classic_reply(
        plan,
        text_heard=text_heard,
        stt_ms=stt_ms,
        request_start=request_start,
        request_identity=request_identity,
    )


@router.post(
    "/stream",
    response_class=NDJSONStreamingResponse,
    responses={
        200: {"model": StreamEvent, "description": _STREAM_200_DESCRIPTION},
        413: _STREAM_413_RESPONSE,
    },
)
async def transcribe_stream(
    resources: ResourcesDep,
    owner_unlock_service: OwnerUnlockServiceDep,
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16")],
    background_tasks: BackgroundTasks,
    x_iroko_identity_token: IdentityTokenDep = None,
    frame: Annotated[
        UploadFile | None,
        File(
            description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · optional owner-authentication frame"
        ),
    ] = None,
    short_reply: Annotated[
        bool,
        Form(description="Optional: the clip is a short reply; biases the speech-to-text only"),
    ] = False,
) -> NDJSONStreamingResponse:
    """Transcribe audio and stream the robot's reply sentence by sentence (R3).

    Args:
        audio: WAV at 16kHz, mono, int16, within MAX_AUDIO_UPLOAD_BYTES.
        background_tasks: Queue for the candidate proposal of a successful voice turn.
        x_iroko_identity_token: Optional one-use owner unlock token — same
            contract as classic /transcribe (Plan 0027).
        frame: Optional webcam frame attached for in-request face
            authentication (Plan 0029). Only read and decoded when
            `settings.face_authentication_enabled` is `True` — otherwise
            accepted but completely inert. A malformed or oversized frame
            degrades to no frame instead of failing the turn.
        short_reply: The client listened for a short reply (Plan 0067). It only adds the
            fixed `SHORT_REPLY_HOTWORDS` to the speech-to-text; identity, the grammar and
            everything after the transcript are exactly those of any other turn.

    Returns:
        NDJSON events ordered as text, emotion, audio chunks, then timings.
        The terminal `done` event additionally reports whether this turn
        consumed a fresh owner unlock grant and which evidence source
        (face/face_voice/local_unlock/none) identified the actor.

    Raises:
        HTTPException: 413 for size, 422 for WAV/speech, or 500 for STT.
    """
    request_start = time.perf_counter()
    turn_log.log_start("stream")
    frame_bytes: bytes | None = None
    if settings.face_authentication_enabled and frame is not None:
        try:
            frame_bytes = await read_contract_image(frame, noun="Frame")
        except HTTPException as exc:
            logger.warning(
                "Owner-authentication frame rejected — continuing without it: %s", exc.detail
            )
    audio_bytes = await _read_audio_upload(audio)
    request_identity = _build_request_identity(
        owner_unlock_service, x_iroko_identity_token, frame_bytes, audio_bytes
    )

    text_heard, stt_ms, unclear = await _transcribe_turn(
        audio_bytes, list(SHORT_REPLY_HOTWORDS) if short_reply else []
    )
    decide_started = time.perf_counter()

    if not text_heard.strip():
        logger.warning("STT returned empty transcript — audio was silence or too short")
        raise HTTPException(status_code=422, detail="No speech detected in audio")
    if unclear:
        unclear_plan = unclear_speech_plan(expects_short_reply=short_reply)
        turn_log.log_decision("stream", unclear_plan, decide_ms=_elapsed_ms(decide_started))
        return _stream_plan(
            unclear_plan,
            text_heard=text_heard,
            stt_ms=stt_ms,
            request_start=request_start,
            request_identity=request_identity,
        )

    event = _voice_event_from_transcript(text_heard)
    decision = await _voice_controller(
        resources.http_client,
        request_identity=request_identity,
        memory_answerer=_memory_answerer(),
        memory_changer=_memory_changer(WriteChannel.VOICE_STREAM),
        profile_summarizer=_profile_summarizer(),
        recall_answerer=_recall_answerer(resources.http_client),
        frame=frame_bytes,
    ).decide(event)
    record_turn = _turn_recorder(
        background_tasks, event=event, wav_bytes=audio_bytes, client=resources.http_client
    )
    if isinstance(decision, SceneDescriptionRequest) and _scene_on() and frame_bytes is not None:
        # The scene is described from the turn's own frame, after a spoken cue (Plan 0089 D-2).
        turn_frame = frame_bytes

        def decided(plan: ResponsePlan) -> None:
            turn_log.log_decision("stream", plan, decide_ms=_elapsed_ms(decide_started))
            _record_plan(record_turn, event.payload.message, plan, request_identity)

        return NDJSONStreamingResponse(
            guarantee_terminal_event(
                stream_looking_plan(
                    text_heard=event.payload.message,
                    cue=settings.vision_look_phrase,
                    look=lambda: _look(resources.http_client, turn_frame),
                    on_plan=decided,
                    stt_ms=stt_ms,
                    request_start=request_start,
                    authentication_consumed=request_identity.consumed,
                    identity_source=request_identity.identity_source,
                )
            )
        )
    plan: ResponsePlan | None = (
        scene_unavailable_plan() if isinstance(decision, SceneDescriptionRequest) else decision
    )
    turn_log.log_decision("stream", plan, decide_ms=_elapsed_ms(decide_started))
    if plan is not None:
        _record_plan(record_turn, event.payload.message, plan, request_identity)
        return _stream_plan(
            plan,
            text_heard=event.payload.message,
            stt_ms=stt_ms,
            request_start=request_start,
            request_identity=request_identity,
        )

    speaker = await identify_generic_speaker(
        owner_unlock_service.for_request,
        token=x_iroko_identity_token,
        frame=frame_bytes,
        event=event,
    )
    if speaker.actor is not None:
        turn_log.log_actor("voice", speaker.actor)
    prepared = await prepare_text_turn(
        event.payload.message,
        event.payload.conversation_id,
        active_person=speaker.actor,
        suspend_cause=speaker.cause,
        profile_card_provider=_profile_card_provider(event.correlation_id),
    )

    return NDJSONStreamingResponse(
        guarantee_terminal_event(
            stream_pipeline(
                client=resources.http_client,
                prepared=prepared,
                stt_ms=stt_ms,
                request_start=request_start,
                schedule_proposal=_proposal_scheduler(
                    resources.http_client,
                    background_tasks,
                    event=event,
                    wav_bytes=audio_bytes,
                    channel=CandidateChannel.VOICE_STREAM,
                ),
                prepare_offer=_offer_preparer(event=event, wav_bytes=audio_bytes),
                record_turn=record_turn,
                prepare_follow_up=_follow_up_preparer(event),
            )
        )
    )
