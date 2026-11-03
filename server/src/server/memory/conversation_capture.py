"""Capture one spoken exchange into the conversation record (ADR 0027, Plan 0076).

It runs as a background task after the reply was sent and never touches the user's request: every
failure is swallowed and logged by class. Order: the kill-switch, the ready owner, the owner's
consent, the turn's voice verdict, then the append.

The verdict (Plan 0076 D-1): a turn is the owner's only when the face names the owner **and** the
voice of the turn's own clip verifies against the owner — the check the candidate path runs. A
token, an unknown face or another person is ``not_owner`` and the voice is never computed for it;
a deterministic reply (no speaker resolved) is ``not_checked``.

Audio contract for the clip: WAV, 16 000 Hz, mono, signed int16. It is held in memory only and is
never stored. Logs carry the outcome, the verdict and the correlation id — never a text.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from server.cognition.clock import utc_now
from server.cognition.strong_actor import VoiceVerifier, is_face_actor, verify_face_and_voice
from server.memory.conversation_consent import has_active_conversation_consent
from server.memory.conversation_record import append_turn
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.owner_credentials import get_ready_owner
from server.memory.recall_index import embed_unit
from server.memory.recall_store import insert_turn_unit
from server.settings import settings

if TYPE_CHECKING:
    from datetime import datetime

    import aiosqlite
    import httpx

    from server.cognition.identity import ActivePersonContext
    from server.cognition.models import CognitiveEvent
    from server.cognition.response_plan import TextTurnPayload
    from server.memory.conversation_record import TurnIndexer
    from server.memory.conversation_types import RecordedTurn

logger = logging.getLogger(__name__)

__all__ = ["CaptureOutcome", "capture_turn", "turn_verdict"]

type OwnerReader = Callable[[], Awaitable[int | None]]
type ConsentReader = Callable[[int], Awaitable[bool]]
type Clock = Callable[[], datetime]


class CaptureOutcome(StrEnum):
    """What one capture did, in closed terms."""

    RECORDED = "recorded"
    DISABLED = "disabled"
    NO_OWNER = "no_owner"
    NO_CONSENT = "no_consent"
    FAILED = "failed"


async def turn_verdict(
    actor: ActivePersonContext | None,
    *,
    owner_id: int,
    wav_bytes: bytes | None,
    event: CognitiveEvent[TextTurnPayload],
    verify: VoiceVerifier = verify_face_and_voice,
) -> TurnVerdict:
    """Decide whose turn this was for memory (Plan 0076 D-1).

    Args:
        actor: The turn's speaker, or ``None`` for a deterministic reply.
        owner_id: The ready owner's entity id.
        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — or ``None``.
        event: The turn's event; the voice check stamps its evidence from it.
        verify: The voice-check seam; tests inject doubles.

    Returns:
        The verdict; the voice is computed only for the owner's face.
    """
    if actor is None:
        return TurnVerdict.NOT_CHECKED
    if not is_face_actor(actor) or actor.person_id != owner_id:
        return TurnVerdict.NOT_OWNER
    fused = await verify(actor, wav_bytes=wav_bytes, event=event)
    if fused is not None and fused.person_id == owner_id:
        return TurnVerdict.VERIFIED
    return TurnVerdict.NOT_VERIFIED


async def capture_turn(
    heard: str,
    said: str,
    actor: ActivePersonContext | None,
    *,
    wav_bytes: bytes | None,
    event: CognitiveEvent[TextTurnPayload],
    at: datetime,
    verify: VoiceVerifier = verify_face_and_voice,
    owner: OwnerReader = get_ready_owner,
    consented: ConsentReader = has_active_conversation_consent,
    clock: Clock = utc_now,
    client: httpx.AsyncClient | None = None,
) -> CaptureOutcome:
    """Append one spoken exchange to the record, when the switch and the consent allow it.

    With ``RECALL_ENABLED`` a ``VERIFIED`` exchange also gets its recall unit in the same
    transaction, and with *client* its vector right after (ADR 0028 decisions 1 and 2).

    Args:
        heard: What the speech-to-text heard.
        said: What the robot said.
        actor: The turn's speaker, or ``None`` for a deterministic reply.
        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — held in memory only.
        event: The turn's event; its correlation id joins the exchange to the turn.
        at: When the turn was taken (timezone-aware).
        verify: The voice-check seam; tests inject doubles.
        owner: Reader of the ready owner; tests inject doubles.
        consented: Reader of the owner's consent; tests inject doubles.
        clock: The time a segment closed by this append is stamped with.
        client: Shared, lifecycle-owned HTTP client (Plan 0039) for the unit's vector, or
            ``None`` to leave it to the conversation job.

    Returns:
        The closed outcome. Never raises: this runs after the user already got the reply.
    """
    verdict: TurnVerdict | None = None
    try:
        if not (settings.memory_enabled and settings.conversation_record_enabled):
            return _logged(CaptureOutcome.DISABLED, None, event)
        owner_id = await owner()
        if owner_id is None:
            return _logged(CaptureOutcome.NO_OWNER, None, event)
        if not await consented(owner_id):
            return _logged(CaptureOutcome.NO_CONSENT, None, event)
        verdict = await turn_verdict(
            actor, owner_id=owner_id, wav_bytes=wav_bytes, event=event, verify=verify
        )
        turn = make_turn(heard, said, voice=verdict, correlation_id=event.correlation_id, at=at)
        units: list[int] = []
        await append_turn(
            turn,
            owner_entity_id=owner_id,
            now=clock(),
            index=_recall_indexer(turn, owner_id, units),
        )
        if client is not None and units:
            await embed_unit(client, units[0], turn.heard)
    except Exception as exc:  # background boundary: nothing may reach the user's request
        # Only the class is logged: the message of a failure could carry a text.
        logger.warning(
            "Conversation capture failed (%s)",
            type(exc).__name__,
            extra={"event": "conversation.capture_error", "error_type": type(exc).__name__},
        )
        return _logged(CaptureOutcome.FAILED, verdict, event)
    return _logged(CaptureOutcome.RECORDED, verdict, event)


def _recall_indexer(turn: RecordedTurn, owner_id: int, units: list[int]) -> TurnIndexer | None:
    """Return the indexer that writes the turn's recall unit, or ``None`` when it gets none.

    Only a ``VERIFIED`` turn with words, and only with ``RECALL_ENABLED`` (ADR 0028 decision 1).
    The new unit's id is appended to *units*, so the caller can embed it after the commit.
    """
    if not settings.recall_enabled or turn.voice is not TurnVerdict.VERIFIED:
        return None
    if not turn.heard.strip():
        return None

    async def index(conn: aiosqlite.Connection, record_id: int, recorded: RecordedTurn) -> int:
        unit_id = await insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner_id, turn=recorded
        )
        units.append(unit_id)
        return unit_id

    return index


def _logged(
    outcome: CaptureOutcome, verdict: TurnVerdict | None, event: CognitiveEvent[TextTurnPayload]
) -> CaptureOutcome:
    """Log one capture with its closed outcome and verdict; never a text."""
    logger.info(
        "Conversation capture: %s",
        outcome.value,
        extra={
            "event": "conversation.capture",
            "outcome": outcome,
            "verdict": verdict,
            "correlation_id": str(event.correlation_id),
        },
    )
    return outcome
