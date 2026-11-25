"""Per-turn trace logging shared by every channel adapter.

One turn emits a short sequence of INFO lines that all start with ``Turn`` so an
operator watching ``just run-server`` can follow a single request through
identity, cognition, memory, and generation without attaching a debugger.

Only markers are logged: enum values, counts, tool names, and integer IDs. A
household value, a retrieved memory, a person name, or a biometric datum is
never written to a trace line.
"""

import logging

from server import system_memory
from server.cognition.identity import ActivePersonContext
from server.cognition.response_plan import ResponsePlan

logger = logging.getLogger(__name__)

_ABSENT = "-"


def log_actor(channel: str, actor: ActivePersonContext) -> None:
    """Log the identity resolved for one turn.

    Args:
        channel: Adapter that owns the turn, e.g. ``"voice"`` or ``"chat"``.
        actor: Identity context resolved by the adapter for this turn only.
    """
    logger.info(
        "Turn actor: channel=%s status=%s role=%s person_id=%s evidence=%d",
        channel,
        actor.status.value,
        actor.role.value,
        _ABSENT if actor.person_id is None else actor.person_id,
        len(actor.evidence),
        extra={
            "event": "turn.actor",
            "channel": channel,
            "status": actor.status.value,
            "role": actor.role.value,
            "person_id": actor.person_id,
            "evidence": len(actor.evidence),
        },
    )


def log_start(channel: str) -> None:
    """Log that one turn started, with the machine's free memory (Plan 0089 D-13).

    Args:
        channel: Adapter that owns the turn, e.g. ``"voice"`` or ``"stream"``.
    """
    ram_free_mb = system_memory.available_ram_mb()
    logger.info(
        "Turn start: channel=%s ram_free_mb=%s",
        channel,
        ram_free_mb,
        extra={"event": "turn.start", "channel": channel, "ram_free_mb": ram_free_mb},
    )


def log_decision(channel: str, plan: ResponsePlan | None, *, decide_ms: int | None = None) -> None:
    """Log the controller outcome without exposing any protected value.

    Args:
        channel: Adapter that owns the turn.
        plan: Immutable response plan, or ``None`` when the controller returned
            no plan and the channel must run its own generation.
        decide_ms: How long the identity check and the controller took, from the end of the
            speech-to-text to the decision (Plan 0089 D-13), when the adapter measured it.
    """
    if plan is None:
        logger.info(
            "Turn decision: channel=%s outcome=no-plan-channel-generates decide_ms=%s",
            channel,
            decide_ms,
            extra={
                "event": "turn.decision",
                "channel": channel,
                "outcome": "no-plan-channel-generates",
                "decide_ms": decide_ms,
            },
        )
        return
    tools = ",".join(result.tool_name for result in plan.tool_results) or _ABSENT
    logger.info(
        "Turn decision: channel=%s need=%s status=%s source=%s tools=%s llm_ms=%d decide_ms=%s",
        channel,
        plan.need.value,
        plan.status.value,
        plan.source.value,
        tools,
        plan.duration_ms,
        decide_ms,
        extra={
            "event": "turn.decision",
            "channel": channel,
            "need": plan.need.value,
            "status": plan.status.value,
            "source": plan.source.value,
            "tools": tools,
            "llm_ms": plan.duration_ms,
            "decide_ms": decide_ms,
        },
    )


def log_memory(outcome: str, reason: str) -> None:
    """Log whether persistent memory took part in this turn.

    Args:
        outcome: Marker such as ``"loaded"``, ``"skipped"``, or ``"discarded"``.
        reason: Short technical explanation. Never user or household content.
    """
    logger.info(
        "Turn memory: %s (%s)",
        outcome,
        reason,
        extra={"event": "turn.memory", "outcome": outcome, "reason": reason},
    )
