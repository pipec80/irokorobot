"""Who may read the profile card, and the one place that reads it (Plan 0074, ADR 0026 decision 3).

``read_card`` asks ADR 0019's ``read_personal_conversation_memory`` for the speaker's **own**
``personal`` / ``normal`` data, writes the audit row **before** the read (a denial is audited
too), then reads through the card's only query. It never raises: a failing audit or read means
no card, and the turn is answered without one.

It does not use ``PolicyGatedV4Reader``: that reader keeps only rows whose stored labels equal the
registry defaults (``household`` for ``likes``), and the owner's rows are stored ``personal``, so
it would withhold them. It does not use ``candidate_policy.authorize_step`` either: that step
demands the face-and-voice composite, and the card needs only the face at ``basic``.

Logs carry a closed reason, never a value, a message or an exception's text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from server.cognition.authorization import (
    ASSURANCE_RANK,
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.identity import ActivePersonStatus, IdentityAssurance
from server.cognition.models import AuthorizationAction, AuthorizationStatus
from server.cognition.response_plan import ProfileSummaryReply
from server.cognition.strong_actor import is_face_actor
from server.memory.household_authorization import record_authorization_decision
from server.memory.profile_card import (
    CARD_PREDICATES,
    ProfileCard,
    build_card,
    render_prompt_card,
    render_summary,
)
from server.memory.relational_v4 import list_card_literals

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime
    from uuid import UUID

    from server.cognition.identity import ActivePersonContext
    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator
    from server.memory.relational_v4 import LiteralFactV4

logger = logging.getLogger(__name__)

__all__ = [
    "CardOutcome",
    "CardRead",
    "profile_summary_text",
    "prompt_card_text",
    "read_card",
]

type CardReader = Callable[..., Awaitable[list[LiteralFactV4]]]


class CardOutcome(StrEnum):
    """How a card read ended."""

    ALLOWED = "allowed"
    DENIED = "denied"  # not asked, not an owner, policy refused, or audit refused
    UNAVAILABLE = "unavailable"  # the audit or the read failed


class _Reason(StrEnum):
    """The closed reasons a read is logged with."""

    NOT_ASKED = "not_asked"
    DENIED = "denied"
    AUDIT_FAILED = "audit_failed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CardRead:
    """The result of one card read.

    Attributes:
        outcome: How the read ended.
        card: The card, set only when ``outcome`` is ``ALLOWED``. Hidden from ``repr``.
    """

    outcome: CardOutcome
    card: ProfileCard | None = None


def _refused(outcome: CardOutcome, reason: _Reason) -> CardRead:
    logger.info("Profile card: not read (%s)", reason.value)
    return CardRead(outcome)


def _may_be_asked(actor: ActivePersonContext) -> bool:
    """Whether the policy is worth asking: the face-identified speaker at ``basic`` or more.

    The same test ``start_offer`` uses, so a token speaker never reaches the policy and never
    writes a denial row per turn.
    """
    return (
        actor.status is ActivePersonStatus.IDENTIFIED
        and actor.person_id is not None
        and ASSURANCE_RANK[actor.assurance] >= ASSURANCE_RANK[IdentityAssurance.BASIC]
        and is_face_actor(actor)
    )


async def read_card(
    actor: ActivePersonContext,
    *,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
    reader: CardReader = list_card_literals,
) -> CardRead:
    """Read the speaker's own profile card, after the policy and the audit row.

    Args:
        actor: The turn's resolved speaker.
        correlation_id: The turn's id, so the audit row joins to the rest of the turn.
        now: The caller's clock reading.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.
        reader: The card's query; tests inject doubles.

    Returns:
        ``ALLOWED`` with the card; ``DENIED`` when the speaker was not asked, is not the owner,
        the policy refused or the audit row was refused; ``UNAVAILABLE`` when the audit or the
        read failed. It never raises.
    """
    person_id = actor.person_id
    if person_id is None or not _may_be_asked(actor):
        return _refused(CardOutcome.DENIED, _Reason.NOT_ASKED)
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
        logger.warning("Profile card audit failed (%s)", type(exc).__name__)
        return _refused(CardOutcome.UNAVAILABLE, _Reason.AUDIT_FAILED)
    if decision.decision is not AuthorizationStatus.ALLOWED:
        return _refused(CardOutcome.DENIED, _Reason.DENIED)
    try:
        rows = await reader(subject_entity_id=person_id, predicates=CARD_PREDICATES)
        return CardRead(CardOutcome.ALLOWED, build_card(rows))
    except Exception as exc:  # a corrupt row raises a pydantic ValueError, not only a db error
        logger.warning("Profile card read failed (%s)", type(exc).__name__)
        return _refused(CardOutcome.UNAVAILABLE, _Reason.UNAVAILABLE)


async def prompt_card_text(
    actor: ActivePersonContext, *, correlation_id: UUID, now: datetime
) -> str | None:
    """Return the prompt block for the speaker, or ``None`` when there is no card to show.

    Args:
        actor: The turn's resolved speaker.
        correlation_id: The turn's id for the audit row.
        now: The caller's clock reading.

    Returns:
        The rendered block when the read was allowed and the card is not empty, else ``None``.
    """
    read = await read_card(actor, correlation_id=correlation_id, now=now)
    if read.outcome is not CardOutcome.ALLOWED or read.card is None:
        return None
    return render_prompt_card(read.card)


async def profile_summary_text(
    actor: ActivePersonContext, *, correlation_id: UUID, now: datetime
) -> ProfileSummaryReply:
    """Return what the speaker's card says, for the explicit question «¿qué sabes de mí?».

    Args:
        actor: The turn's resolved speaker.
        correlation_id: The turn's id for the audit row.
        now: The caller's clock reading.

    Returns:
        The summary text when allowed (an empty card has its own fixed text), ``denied`` when
        the policy or the pre-check refused, and ``text=None`` when the read failed.
    """
    read = await read_card(actor, correlation_id=correlation_id, now=now)
    match read.outcome:
        case CardOutcome.ALLOWED if read.card is not None:
            return ProfileSummaryReply(text=render_summary(read.card))
        case CardOutcome.DENIED:
            return ProfileSummaryReply(text=None, denied=True)
        case _:
            return ProfileSummaryReply(text=None)
