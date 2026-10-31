"""The synthetic memory block the chat evaluations inject (Plan 0076).

The legacy ``MemoryContext`` and its prompt block left the server with the legacy memory path
(ADR 0027 decision 9). The faithfulness evaluation still asks whether the model sticks to an
authorized block of data and invents nothing, so the golden cases keep their synthetic context,
modelled here, and the evaluations hand it to the model through the production slot that
carries authorized data today: the profile card (``profile_card``). Evaluation-only: nothing
under ``server`` imports this module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from server.schemas import EntityType  # noqa: TC002 — Pydantic resolves this field at runtime

__all__ = [
    "EvalEntity",
    "EvalFact",
    "EvalMemoryContext",
    "EvalMemoryHit",
    "render_memory_block",
]

_HEADER = "--- Memoria activa autorizada ---"
_SUMMARY_CHARS = 120


class EvalFact(BaseModel):
    """One synthetic fact of an entity."""

    predicate: str
    object_value: str
    confidence: float = Field(ge=0, le=1, default=1.0)


class EvalEntity(BaseModel):
    """One synthetic entity with its facts."""

    id: int
    name: str
    type: EntityType
    facts: list[EvalFact] = Field(default_factory=list)


class EvalMemoryHit(BaseModel):
    """One synthetic recalled memory."""

    id: int
    kind: Literal["episodic", "semantic", "reflection"]
    content: str
    summary: str | None
    importance: float
    distance: float


class EvalMemoryContext(BaseModel):
    """The synthetic memory of one golden case."""

    entities: list[EvalEntity] = Field(default_factory=list)
    memories: list[EvalMemoryHit] = Field(default_factory=list)


def render_memory_block(context: EvalMemoryContext | None) -> str | None:
    """Render the synthetic memory as the authorized block the model receives.

    Args:
        context: The case's synthetic memory, or ``None``.

    Returns:
        The block, passed as ``profile_card``; ``None`` when there is nothing to show.
    """
    if context is None or not (context.entities or context.memories):
        return None
    lines = [_HEADER]
    for entity in context.entities:
        facts = ", ".join(f"{fact.predicate}: {fact.object_value}" for fact in entity.facts)
        label = f"- {entity.name} ({entity.type})"
        lines.append(f"{label}: {facts}" if facts else label)
    for memory in context.memories:
        lines.append(f"- [recuerdo] {memory.summary or memory.content[:_SUMMARY_CHARS]}")
    return "\n".join(lines)
