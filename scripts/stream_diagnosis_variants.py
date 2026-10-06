"""How a diagnosis turn is varied, ordered and prompted (Plan 0057).

Each variant removes or moves one factor of a turn (memory context, active person,
history, the contract's position) so that the fallback rate can be attributed to a
factor instead of guessed. The order of the runs is seeded and shuffled.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import enum
import random
from typing import TYPE_CHECKING

from server.llm_streaming import (
    _STREAMING_OUTPUT_CONTRACT,
    _build_messages,
    _build_streaming_base_prompt,
    _stream_local_response,
    _streaming_system_prompt,
)

from server import llm_streaming

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Collection, Sequence

    import httpx
    from server.cognition.identity import ActivePersonContext
    from server.schemas import ConversationTurn, MemoryContext

    from scripts.eval_stream_protocol import StreamTurn

    type StreamGenerator = Callable[..., AsyncIterator[str]]


class StreamVariant(enum.StrEnum):
    """One way of presenting a turn; each removes, moves or repeats a single factor."""

    FULL = "full"
    FULL_REPEAT = "full_repeat"
    NO_CONTEXT = "no_context"
    NO_PERSON = "no_person"
    NO_HISTORY = "no_history"
    QUESTION_ONLY = "question_only"
    CONTRACT_FIRST = "contract_first"
    PUBLIC_WITH_CONTEXT = "public_with_context"


VARIANT_DESCRIPTIONS: dict[StreamVariant, str] = {
    StreamVariant.FULL: "the turn exactly as `just eval-chat --mode stream` sends it (the baseline)",
    StreamVariant.FULL_REPEAT: "`full` again, interleaved: the noise of repeating one condition",
    StreamVariant.NO_CONTEXT: "the memory block removed; person and history kept",
    StreamVariant.NO_PERSON: "the active person removed; memory and history kept",
    StreamVariant.NO_HISTORY: "the history removed; memory and person kept",
    StreamVariant.QUESTION_ONLY: "memory, person and history all removed (several factors at once)",
    StreamVariant.CONTRACT_FIRST: "the output contract moved to the start of the system prompt",
    StreamVariant.PUBLIC_WITH_CONTEXT: "a public question with a golden memory block borrowed in rotation",
}


@dataclass(frozen=True)
class DiagnosisUnit:
    """One turn to stream under one variant."""

    variant: StreamVariant
    turn: StreamTurn


def _same_inputs(first: StreamTurn, second: StreamTurn) -> bool:
    """Whether two turns send the model the same context, history and person."""
    return (
        first.context == second.context
        and (first.history or []) == (second.history or [])
        and first.active_person == second.active_person
    )


def _golden_units(turn: StreamTurn) -> list[DiagnosisUnit]:
    """Return the variants of one golden turn, skipping those that would change nothing.

    A variant is dropped when it sends the same inputs as ``full`` or as a variant kept
    before it (for example ``question_only`` on a turn that has no person and no
    history, where it equals ``no_context``). ``full_repeat`` and ``contract_first``
    keep the same inputs on purpose: one is the noise control, the other moves the
    contract.
    """
    units = [
        DiagnosisUnit(StreamVariant.FULL, turn),
        DiagnosisUnit(StreamVariant.FULL_REPEAT, turn),
        DiagnosisUnit(StreamVariant.CONTRACT_FIRST, turn),
    ]
    candidates = [
        (StreamVariant.NO_CONTEXT, replace(turn, context=None)),
        (StreamVariant.NO_PERSON, replace(turn, active_person=None)),
        (StreamVariant.NO_HISTORY, replace(turn, history=None)),
        (
            StreamVariant.QUESTION_ONLY,
            replace(turn, context=None, history=None, active_person=None),
        ),
    ]
    kept = [turn]
    for variant, candidate in candidates:
        if any(_same_inputs(candidate, earlier) for earlier in kept):
            continue
        kept.append(candidate)
        units.append(DiagnosisUnit(variant, candidate))
    return units


def build_units(
    golden: Sequence[StreamTurn],
    public: Sequence[StreamTurn],
    variants: Collection[StreamVariant] | None = None,
) -> list[DiagnosisUnit]:
    """Expand the golden and public turns into the units of one diagnosis.

    Args:
        golden: The golden context turns (``source == "context"``).
        public: The synthetic context-free turns (``source == "public"``).
        variants: Keep only these variants; every variant when ``None``.

    Returns:
        Units in a fixed order. A variant that would leave a turn unchanged is omitted
        (for example ``NO_PERSON`` on a turn that has no active person).
    """
    units = [unit for turn in golden for unit in _golden_units(turn)]
    for index, turn in enumerate(public):
        units.append(DiagnosisUnit(StreamVariant.FULL, turn))
        units.append(DiagnosisUnit(StreamVariant.FULL_REPEAT, turn))
        units.append(DiagnosisUnit(StreamVariant.CONTRACT_FIRST, turn))
        if golden:
            donor = golden[index % len(golden)].context
            units.append(
                DiagnosisUnit(StreamVariant.PUBLIC_WITH_CONTEXT, replace(turn, context=donor))
            )
    if variants is None:
        return units
    return [unit for unit in units if unit.variant in variants]


def plan_runs(
    units: Sequence[DiagnosisUnit], runs: int, seed: int
) -> list[tuple[DiagnosisUnit, int]]:
    """Return every ``(unit, run)`` once, in an order shuffled by ``seed``.

    Interleaving the variants keeps a slow machine or a warming model from being
    mistaken for a variant effect.
    """
    plan = [(unit, run) for unit in units for run in range(1, runs + 1)]
    random.Random(seed).shuffle(plan)  # noqa: S311  # a reproducible order, not security
    return plan


def contract_first_system_prompt(base_prompt: str) -> str:
    """Put the streaming contract before the base prompt instead of after it."""
    return _STREAMING_OUTPUT_CONTRACT.lstrip("\n") + "\n\n" + base_prompt


async def generate_contract_first(
    client: httpx.AsyncClient,
    text: str,
    *,
    context: MemoryContext | None = None,
    history: list[ConversationTurn] | None = None,
    active_person: ActivePersonContext | None = None,
) -> AsyncIterator[str]:
    """Stream like production does, with the contract at the start of the system prompt."""
    if not text:
        raise ValueError("Input text is empty")
    base_prompt = _build_streaming_base_prompt(
        context,
        onboarding=False,
        onboarding_slot=None,
        user_emotion=None,
        active_person=active_person,
    )
    system_prompt = contract_first_system_prompt(base_prompt)
    messages = _build_messages(text, history)
    async for delta in _stream_local_response(
        client, [{"role": "system", "content": system_prompt}, *messages]
    ):
        yield delta


def generator_for(variant: StreamVariant) -> StreamGenerator:
    """Return the streaming generator a variant is measured with."""
    if variant is StreamVariant.CONTRACT_FIRST:
        return generate_contract_first
    return llm_streaming.generate_response_stream


def prompt_chars(unit: DiagnosisUnit) -> int:
    """Return the characters sent to the model for one unit (system plus messages)."""
    turn = unit.turn
    base_prompt = _build_streaming_base_prompt(
        turn.context,
        onboarding=False,
        onboarding_slot=None,
        user_emotion=None,
        active_person=turn.active_person,
    )
    if unit.variant is StreamVariant.CONTRACT_FIRST:
        system_prompt = contract_first_system_prompt(base_prompt)
    else:
        system_prompt = _streaming_system_prompt(base_prompt)
    messages = _build_messages(turn.text, turn.history)
    return len(system_prompt) + sum(len(message["content"]) for message in messages)
