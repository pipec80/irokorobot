"""Who may recall, and the one place a recall reads the diary (ADR 0028 decision 5, Plan 0078).

The order of the profile card's read: the same pre-check (the face-identified speaker at
``basic``), ADR 0019's ``read_personal_conversation_memory`` for the speaker's own ``personal`` /
``normal`` data, the audit row **before** the search, then the search and the worded answer.
Nothing is searched or embedded before the policy allowed it. It never raises: a failing audit
or search answers the fixed «No me acuerdo de eso.».

Each recall logs its route, outcome, hit count and ``best_distance`` (Plan 0078 D-10, the
calibration of ``RECALL_MAX_DISTANCE``); never a text.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
import logging
from typing import TYPE_CHECKING, Final

from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.models import AuthorizationAction, AuthorizationStatus
from server.cognition.response_plan import NO_MEMORY, RecallReply
from server.memory.household_authorization import record_authorization_decision
from server.memory.profile_card_access import may_read_own_memory
from server.memory.recall_answer import word_recall, word_when
from server.memory.recall_search import RecallHit, RecallSearch, household_zone, search_recall

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID
    from zoneinfo import ZoneInfo

    import httpx

    from server.cognition.identity import ActivePersonContext
    from server.cognition.recall_cues import RecallCue
    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator

logger = logging.getLogger(__name__)

__all__ = ["recall_reply"]

type Searcher = Callable[..., Awaitable[RecallSearch]]
type Answerer = Callable[..., Awaitable[str]]

_DISTANCE_DECIMALS: Final = 3


def _logged(
    cue: RecallCue,
    outcome: str,
    *,
    hits: Sequence[RecallHit] = (),
    search: RecallSearch | None = None,
) -> None:
    best = None if search is None or search.best_distance is None else search.best_distance
    logger.info(
        "Recall: %s (%s, %d hit(s))",
        outcome,
        cue.strength.value,
        len(hits),
        extra={
            "event": "recall.read",
            "route": cue.strength.value,
            "outcome": outcome,
            "hits": len(hits),
            "best_distance": None if best is None else round(best, _DISTANCE_DECIMALS),
            "lexical_only": bool(search and search.lexical_only),
            "windowed": cue.window is not None,
            "when": None if cue.when is None else cue.when.value,
        },
    )


async def recall_reply(
    actor: ActivePersonContext,
    cue: RecallCue,
    *,
    question: str,
    correlation_id: UUID,
    now: datetime,
    client: httpx.AsyncClient,
    search: Searcher = search_recall,
    answer: Answerer = word_recall,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> RecallReply:
    """Answer a recall question for the speaker, after the policy and the audit row.

    Args:
        actor: The turn's speaker, resolved by the face (never spends a grant).
        cue: The recall question.
        question: What the owner asked, as transcribed (only for the worded answer).
        correlation_id: The turn's id, so the audit row joins to the rest of the turn.
        now: The caller's clock reading (timezone-aware).
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        search: The search seam; tests inject doubles.
        answer: The wording seam; tests inject doubles.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        ``denied`` when the speaker was not asked or the policy refused; ``NO_MEMORY`` when the
        audit or the search failed; ``text=None`` when nothing qualified; the worded answer with
        ``found`` otherwise. It never raises.
    """
    person_id = actor.person_id
    if person_id is None or not may_read_own_memory(actor):
        _logged(cue, "not_asked")
        return RecallReply(text=None, denied=True)
    request = AuthorizationRequest(
        actor=actor,
        action=AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY,
        target_person_id=person_id,
        visibility=frozenset({DataVisibility.PERSONAL}),
        sensitivity=frozenset({DataSensitivity.NORMAL}),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=correlation_id,
        requested_at=now,
    )
    decision = policy(request)
    try:
        await audit(request, decision)
    except Exception as exc:  # the audit precedes the read; a failing one means no read at all
        logger.warning("Recall audit failed (%s)", type(exc).__name__)
        _logged(cue, "audit_failed")
        return RecallReply(text=NO_MEMORY)
    if decision.decision is not AuthorizationStatus.ALLOWED:
        _logged(cue, "denied")
        return RecallReply(text=None, denied=True)
    return await _search_and_word(
        person_id, cue, question=question, now=now, client=client, search=search, answer=answer
    )


async def _search_and_word(
    person_id: int,
    cue: RecallCue,
    *,
    question: str,
    now: datetime,
    client: httpx.AsyncClient,
    search: Searcher,
    answer: Answerer,
) -> RecallReply:
    """Search, then word what was found; a failure is the fixed phrase.

    A «cuándo» cue is worded by ``word_when``, a fixed table, and the model is not asked.
    """
    tz: ZoneInfo = household_zone()
    today: date = now.astimezone(tz).date()
    try:
        found = await search(person_id, cue, client=client, now=now)
    except Exception as exc:  # a database error answers that it does not remember (d. 6.7)
        logger.warning("Recall search failed (%s)", type(exc).__name__)
        _logged(cue, "search_failed")
        return RecallReply(text=NO_MEMORY)
    if not found.hits:
        _logged(cue, "nothing_found", search=found)
        return RecallReply(text=None)
    if cue.when is None:
        text = await answer(client, question, found.hits, today=today, tz=tz)
    else:
        text = word_when(found.hits, cue.when, today=today, tz=tz)  # a table: no model (D-9)
    _logged(cue, "found", hits=found.hits, search=found)
    return RecallReply(text=text, found=True)
