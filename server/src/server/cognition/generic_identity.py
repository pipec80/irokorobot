"""Identify the speaker of a generic turn without side effects (ADR 0020 §1).

A generic turn (conversation that no protected branch claimed) tries to name its speaker so
the identified person can have short-term continuity. It uses only what the request already
carries: the face in the frame and, when the face did not resolve, a presented default-scope
token that is *observed* and never spent. The voice is never consulted (the embedding would
cost about half a second on every chat turn), so no audio is touched here.

A failure never fails the turn: any error degrades the speaker to unknown.
"""

from collections.abc import Callable
from dataclasses import dataclass
import logging
import time

from server.cognition.identity import ActivePersonContext, ActivePersonStatus
from server.cognition.identity_fusion import (
    FusedIdentityResolver,
    FusionReason,
    build_fused_identity_resolver,
)
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import OwnerRequestResolver
from server.cognition.response_plan import TextTurnPayload
from server.memory.continuity import SuspendCause
from server.settings import settings

logger = logging.getLogger(__name__)

__all__ = ["GenericIdentification", "identify_generic_speaker"]

type RequestPinResolver = Callable[[str | None], OwnerRequestResolver]
type ResolverBuilder = Callable[..., FusedIdentityResolver]

_CAUSES: dict[FusionReason, SuspendCause] = {
    FusionReason.VETO_OTHER_PERSON: SuspendCause.VETO_OTHER_PERSON,
    FusionReason.VETO_MULTIPLE_FACES: SuspendCause.VETO_MULTIPLE_FACES,
    FusionReason.BACKEND_UNAVAILABLE: SuspendCause.BACKEND_UNAVAILABLE,
    FusionReason.ERROR: SuspendCause.ERROR,
}


@dataclass(frozen=True)
class GenericIdentification:
    """The outcome of identifying one generic turn's speaker.

    Attributes:
        actor: The resolved actor, or ``None`` when identification was skipped or failed
            before producing one (the turn is then an unknown speaker).
        cause: Why the turn cannot use the session, from the closed set; ``None`` when the
            speaker is identified or identification was skipped on purpose.
    """

    actor: ActivePersonContext | None
    cause: SuspendCause | None


async def identify_generic_speaker(
    for_request: RequestPinResolver,
    *,
    token: str | None,
    frame: bytes | None,
    event: CognitiveEvent[TextTurnPayload],
    build_resolver: ResolverBuilder = build_fused_identity_resolver,
) -> GenericIdentification:
    """Name the speaker of a generic turn from the face and an observed token.

    Args:
        for_request: Builds the request-scoped PIN resolver for a token
            (``OwnerUnlockService.for_request``).
        token: The one-use owner token the request presented, or ``None``. It is observed
            only: this function never spends it.
        frame: The validated webcam frame, or ``None``. No audio is ever passed.
        event: The generic turn's event.
        build_resolver: Composition seam for the fused resolver; tests inject doubles.

    Returns:
        The speaker and, when it cannot use the session, the closed cause. Never raises.
    """
    if not settings.memory_enabled:
        return GenericIdentification(actor=None, cause=None)
    started = time.perf_counter()
    result = await _identify(for_request, token, frame, event, build_resolver)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    outcome = "identified" if result.cause is None else result.cause.value
    # Closed outcome and a duration only: this is how the cost of the face check on a
    # generic turn is measured on real hardware (ADR 0020 §10 d).
    logger.info(
        "Generic identification: %s (%d ms)",
        outcome,
        elapsed_ms,
        extra={"event": "identity.generic", "outcome": outcome, "elapsed_ms": elapsed_ms},
    )
    return result


async def _identify(
    for_request: RequestPinResolver,
    token: str | None,
    frame: bytes | None,
    event: CognitiveEvent[TextTurnPayload],
    build_resolver: ResolverBuilder,
) -> GenericIdentification:
    """Resolve the speaker without side effects; any failure degrades to unknown."""
    try:
        fused = build_resolver(for_request(token), frame=frame, wav_bytes=None)
        actor = await fused.peek_actor(event)
    except Exception as exc:
        # Identification must never fail a conversation turn (ADR 0020 §1): whatever the face
        # model, the identity store or an executor raises, the speaker is simply unknown.
        logger.warning("Generic identification degraded to unknown: %s", type(exc).__name__)
        return GenericIdentification(actor=None, cause=SuspendCause.ERROR)
    if actor.status is ActivePersonStatus.IDENTIFIED:
        return GenericIdentification(actor=actor, cause=None)
    reason = fused.last_reason
    return GenericIdentification(
        actor=actor, cause=_CAUSES.get(reason, SuspendCause.NO_EVIDENCE) if reason else None
    )
