"""Who may read a document, and the one place a document cue reads them (Plan 0088 D-15).

The order of the recall read (ADR 0028 decision 5): the face-identified speaker at ``basic``, the
``read_personal_document`` action for the speaker's own ``personal`` data, the audit row **before**
the search, then the search and the worded answer. A ``normal`` document is read as
``DataSensitivity.NORMAL``; a ``sensitive`` one as ``PRIVATE``, and only with no second face in
view: then it is left out of the request and of the search, and nothing tells the speaker that
one exists. It never raises: a failing audit or search answers «No lo encuentro en tus
documentos.». Each read logs its route, outcome and counts; never a text.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import TYPE_CHECKING, Final

from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.identity_fusion import FusionReason
from server.cognition.models import AuthorizationAction, AuthorizationStatus
from server.cognition.response_plan import NOT_IN_DOCUMENTS, DocumentReply
from server.memory.document_answer import word_document
from server.memory.document_search import search_documents
from server.memory.household_authorization import record_authorization_decision
from server.memory.profile_card_access import may_read_own_memory
from server.memory.retrieval import GATE_ID

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    import httpx

    from server.cognition.document_cues import DocumentCue
    from server.cognition.identity import ActivePersonContext
    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator
    from server.memory.document_store import DocumentLevel, DocumentSearch

logger = logging.getLogger(__name__)

__all__ = ["NOT_IN_DOCUMENTS", "document_reply", "readable_levels"]

type DocumentSearcher = Callable[..., Awaitable[DocumentSearch]]
type DocumentAnswerer = Callable[..., Awaitable[str]]

_NORMAL_ONLY: Final[frozenset[DocumentLevel]] = frozenset({"normal"})
_BOTH: Final[frozenset[DocumentLevel]] = frozenset({"normal", "sensitive"})


def readable_levels(faces: FusionReason | None) -> frozenset[DocumentLevel]:
    """The levels the speaker may hear: ``sensitive`` only with no second face in view."""
    return _NORMAL_ONLY if faces is FusionReason.VETO_MULTIPLE_FACES else _BOTH


def _logged(cue: DocumentCue, outcome: str, search: DocumentSearch | None = None) -> None:
    logger.info(
        "Document read: %s (%s, %d hit(s))",
        outcome,
        cue.strength.value,
        0 if search is None else len(search.hits),
        extra={
            "event": "document.read",
            "route": cue.strength.value,
            "outcome": outcome,
            "hits": 0 if search is None else len(search.hits),
            "rejected": 0 if search is None else search.rejected,
            "named": len(cue.named),
            "specific": len(cue.specific),
            "gate": GATE_ID,
        },
    )


def _request(
    actor: ActivePersonContext,
    person_id: int,
    levels: frozenset[DocumentLevel],
    correlation_id: UUID,
    now: datetime,
) -> AuthorizationRequest:
    sensitivity = {DataSensitivity.NORMAL}
    if "sensitive" in levels:
        sensitivity.add(DataSensitivity.PRIVATE)
    return AuthorizationRequest(
        actor=actor,
        action=AuthorizationAction.READ_PERSONAL_DOCUMENT,
        target_person_id=person_id,
        visibility=frozenset({DataVisibility.PERSONAL}),
        sensitivity=frozenset(sensitivity),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=correlation_id,
        requested_at=now,
    )


async def document_reply(  # noqa: PLR0911 - one logged return per outcome, as recall_reply
    actor: ActivePersonContext,
    cue: DocumentCue,
    *,
    question: str,
    faces: FusionReason | None,
    correlation_id: UUID,
    now: datetime,
    client: httpx.AsyncClient,
    search: DocumentSearcher = search_documents,
    answer: DocumentAnswerer = word_document,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> DocumentReply:
    """Answer a document question for the speaker, after the policy and the audit row.

    Args:
        actor: The turn's speaker, resolved by the face (never spends a grant).
        cue: The document question.
        question: What the owner asked, as transcribed (only for the worded answer).
        faces: The turn's identity reason; ``VETO_MULTIPLE_FACES`` leaves ``sensitive`` out.
        correlation_id: The turn's id, so the audit row joins to the rest of the turn.
        now: The caller's clock reading (timezone-aware).
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        search: The search (``document_search.search_documents``); tests inject doubles.
        answer: The wording (``document_answer.word_document``); tests inject doubles.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        ``denied`` when the speaker was not asked or the policy refused; the fixed phrase when the
        audit or the search failed; ``scope_found=False`` when no document holds the named words;
        ``text=None`` when nothing qualified; the worded answer with ``found`` otherwise.
    """
    person_id = actor.person_id
    if person_id is None or not may_read_own_memory(actor):
        _logged(cue, "not_asked")
        return DocumentReply(text=None, denied=True)
    levels = readable_levels(faces)
    request = _request(actor, person_id, levels, correlation_id, now)
    decision = policy(request)
    try:
        await audit(request, decision)
    except Exception as exc:  # the audit precedes the read; a failing one means no read at all
        logger.warning("Document audit failed (%s)", type(exc).__name__)
        _logged(cue, "audit_failed")
        return DocumentReply(text=NOT_IN_DOCUMENTS)
    if decision.decision is not AuthorizationStatus.ALLOWED:
        _logged(cue, "denied")
        return DocumentReply(text=None, denied=True)
    try:
        found = await search(person_id, cue, levels=levels, client=client, now=now)
    except Exception as exc:  # a database error answers that it does not find it
        logger.warning("Document search failed (%s)", type(exc).__name__)
        _logged(cue, "search_failed")
        return DocumentReply(text=NOT_IN_DOCUMENTS)
    if not found.scope_found:
        _logged(cue, "no_document", found)
        return DocumentReply(text=None, scope_found=False)
    if not found.hits:
        _logged(cue, "nothing_found", found)
        return DocumentReply(text=None)
    text = await answer(client, question, found)
    _logged(cue, "found", found)
    return DocumentReply(text=text, found=True)
