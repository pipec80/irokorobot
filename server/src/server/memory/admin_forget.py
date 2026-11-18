"""Delete a memory for good, and list or restore what was set aside (Plan 0086 D-13).

The ``iroko-admin`` side of ADR 0032 decision 3: by voice a memory is only corrected or archived;
a deletion for good needs the owner's PIN here, with the server stopped. ``plan_forget`` says what
one command would delete (counts and ids only), ``forget_for_good`` deletes it through the deletion
register (``deletion_register.forget``) and writes one audit row, and ``archive_groups`` and
``restore_archive_group`` read and undo a voice archive. No outcome, audit row or log line holds a
value; the archive listing shows short texts to the owner under the PIN, on this terminal only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from server import db
from server.memory import (
    conversation_episodes,
    conversation_record,
    pending_store,
    recall_store,
    relational_v4,
)
from server.memory.admin_audit import (
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    record_admin_operation,
)
from server.memory.candidates import facts_confirmed_from_turn
from server.memory.deletion_register import Deletion, DeletionKind, forget
from server.memory.forget_scope import person_deletions, person_scope, restore_archived

if TYPE_CHECKING:
    from server.memory.admin_ops import AdminActor
    from server.memory.write_types import ArchiveCounts

__all__ = [
    "ArchiveGroup",
    "ForgetKind",
    "ForgetPlan",
    "archive_groups",
    "audit_refused_forget",
    "forget_for_good",
    "plan_forget",
    "restore_archive_group",
]

_SHORT_TEXT = 60


class ForgetKind(StrEnum):
    """What ``iroko-admin forget`` deletes."""

    FACT = "fact"
    RELATION = "relation"
    TURN = "turn"
    EPISODE = "episode"
    PERSON = "person"


@dataclass(frozen=True)
class ForgetPlan:
    """What one ``forget`` would delete; ``lines`` are Spanish, counts and ids only."""

    deletions: tuple[Deletion, ...]
    target: TargetKind
    field_id: str
    lines: tuple[str, ...]
    refusal: str | None = None


@dataclass(frozen=True)
class ArchiveGroup:
    """Everything one voice archive set aside, by its instant; ``texts`` only under the PIN."""

    at: str
    facts: int
    relations: int
    units: int
    topics: int
    texts: tuple[str, ...] = field(repr=False)


def _refused(target: TargetKind, field_id: str, reason: str) -> ForgetPlan:
    return ForgetPlan((), target, field_id, (), refusal=reason)


async def _plan_fact(row_id: int) -> ForgetPlan:
    field_id = f"fact:{row_id}"
    if await relational_v4.get_literal_fact(row_id) is None:
        return _refused(TargetKind.POOL_LITERAL, field_id, "No hay un dato con ese número.")
    return ForgetPlan(
        (Deletion(DeletionKind.LITERAL_FACT, row_id),),
        TargetKind.POOL_LITERAL,
        field_id,
        (f"Se borra para siempre el dato {row_id}, con su historia.",),
    )


async def _plan_relation(row_id: int) -> ForgetPlan:
    field_id = f"relation:{row_id}"
    if await relational_v4.get_entity_relation(row_id) is None:
        return _refused(TargetKind.POOL_RELATION, field_id, "No hay una relación con ese número.")
    return ForgetPlan(
        (Deletion(DeletionKind.ENTITY_RELATION, row_id),),
        TargetKind.POOL_RELATION,
        field_id,
        (f"Se borra para siempre la relación {row_id}.",),
    )


async def _plan_turn(row_id: int) -> ForgetPlan:
    field_id = f"turn:{row_id}"
    record_id = await conversation_record.turn_record_id(row_id)
    if record_id is None:
        return _refused(TargetKind.CONVERSATION_RECORD, field_id, "No hay un turno con ese número.")
    kept = await facts_confirmed_from_turn(row_id)
    lines = [
        f"Se borra para siempre el turno {row_id} y el resumen completo de la conversación "
        f"{record_id} (un resumen no se puede borrar a medias)."
    ]
    if kept:
        lines.append(
            f"De esa conversación guardé también: {len(kept)} datos. Siguen guardados; "
            f"bórralos con `forget fact` ({', '.join(str(fact) for fact in kept)})."
        )
    return ForgetPlan(
        (Deletion(DeletionKind.TURN, row_id), Deletion(DeletionKind.EPISODE, record_id)),
        TargetKind.CONVERSATION_RECORD,
        field_id,
        tuple(lines),
    )


async def _plan_episode(record_id: int) -> ForgetPlan:
    field_id = f"episode:{record_id}"
    if await conversation_episodes.get_episode(record_id) is None:
        return _refused(
            TargetKind.CONVERSATION_RECORD, field_id, "Esa conversación no tiene resumen."
        )
    deletions = [Deletion(DeletionKind.EPISODE, record_id)]
    if await conversation_record.record_turn_count(record_id) == 0:
        # A record kept only for its episode (Plan 0086 D-11) has nothing left without it.
        deletions.append(Deletion(DeletionKind.RECORD, record_id))
    return ForgetPlan(
        tuple(deletions),
        TargetKind.CONVERSATION_RECORD,
        field_id,
        (f"Se borra para siempre el resumen de la conversación {record_id}; sus turnos quedan.",),
    )


async def _plan_person(
    owner_entity_id: int, *, row_id: int | None, words: str | None, now: str
) -> ForgetPlan:
    field_id = "person" if row_id is None else f"person:{row_id}"
    scope = await person_scope(
        owner_entity_id, now=now, entity_id=row_id, words=words, for_deletion=True
    )
    if scope.enrolled:
        return _refused(
            TargetKind.POOL_RELATION,
            field_id,
            "Es una persona enrolada (rol, consentimiento o credencial): revoca eso primero.",
        )
    if scope.empty:
        return _refused(TargetKind.POOL_RELATION, field_id, "No hay nada guardado de esa persona.")
    lines = (
        "Se borra para siempre todo lo de esa persona:",
        f"  contactos: {len(scope.contacts)}",
        f"  datos y relaciones: {len(scope.facts) + len(scope.relations)}",
        f"  turnos que la nombran: {len(scope.turns)}",
        f"  resúmenes de conversaciones: {len(scope.episodes)}",
        f"  recuerdos y temas pendientes que la nombran: {len(scope.units) + len(scope.topics)}",
        f"  datos tuyos que la nombran: {len(scope.owner_facts)}",
        f"  la persona misma: {'sí' if scope.entity_id is not None else 'no (solo se habló de ella)'}",
    )
    return ForgetPlan(tuple(person_deletions(scope)), TargetKind.POOL_RELATION, field_id, lines)


async def plan_forget(
    kind: ForgetKind,
    *,
    owner_entity_id: int,
    row_id: int | None,
    words: str | None,
    now: str,
) -> ForgetPlan:
    """Say what one ``iroko-admin forget`` would delete, deleting nothing.

    Args:
        kind: What to delete.
        owner_entity_id: The owner whose memory it is.
        row_id: The id the command names (a person may be named by ``words`` instead).
        words: A person's name as said, for ``forget person --name``.
        now: The current instant.

    Returns:
        The plan; ``refusal`` is set when there is nothing to delete or it may not be deleted.
    """
    if kind is ForgetKind.PERSON:
        return await _plan_person(owner_entity_id, row_id=row_id, words=words, now=now)
    if row_id is None:
        return _refused(TargetKind.POOL_LITERAL, kind.value, "Falta el número (id).")
    match kind:
        case ForgetKind.FACT:
            return await _plan_fact(row_id)
        case ForgetKind.RELATION:
            return await _plan_relation(row_id)
        case ForgetKind.TURN:
            return await _plan_turn(row_id)
        case ForgetKind.EPISODE:
            return await _plan_episode(row_id)


async def _audit(
    actor: AdminActor,
    operation: AdminOperationKind,
    target: TargetKind,
    field_id: str,
    *,
    refused: str | None,
    now: str,
) -> None:
    await record_admin_operation(
        actor_label=actor.label,
        actor_role=actor.role,
        operation=operation,
        target_kind=target,
        field_id=field_id,
        target_entity_id=None,  # the entity may be the row deleted; the id is in `field_id`
        outcome=AdminOutcomeStatus.REFUSED if refused else AdminOutcomeStatus.APPLIED,
        reason=refused,
        recorded_at=now,
    )


async def forget_for_good(plan: ForgetPlan, *, actor: AdminActor, now: str) -> int:
    """Delete what *plan* names through the deletion register, then audit it.

    Args:
        plan: A plan without a refusal, from ``plan_forget``.
        actor: Who runs the command.
        now: The deletion instant.

    Returns:
        How many rows went.
    """
    result = await forget(plan.deletions, now=datetime.fromisoformat(now))
    await _audit(
        actor, AdminOperationKind.DELETE, plan.target, plan.field_id, refused=None, now=now
    )
    return result.rows


async def audit_refused_forget(
    plan: ForgetPlan, *, actor: AdminActor, reason: str, now: str
) -> None:
    """Audit a ``forget`` refused before anything was deleted (no PIN, nothing to delete)."""
    await _audit(
        actor, AdminOperationKind.DELETE, plan.target, plan.field_id, refused=reason, now=now
    )


def _short(text: str) -> str:
    return text if len(text) <= _SHORT_TEXT else text[: _SHORT_TEXT - 1] + "…"


async def archive_groups() -> list[ArchiveGroup]:
    """Everything set aside, grouped by the instant of its archive, oldest first."""
    facts, relations = await relational_v4.archived_v4_rows()
    units = await recall_store.archived_units()
    topics = await pending_store.archived_topics()
    instants = sorted(
        {fact.archived_at for fact in facts if fact.archived_at is not None}
        | {rel.archived_at for rel in relations if rel.archived_at is not None}
        | {at for _, at, _ in units}
        | {at for _, at, _ in topics}
    )
    groups: list[ArchiveGroup] = []
    for at in instants:
        texts = [
            *(
                f"dato {f.id}: {f.predicate} {_short(f.value_text)}"
                for f in facts
                if f.archived_at == at
            ),
            *(f"relación {r.id}: {r.predicate}" for r in relations if r.archived_at == at),
            *(f"recuerdo {i}: {_short(body)}" for i, a, body in units if a == at),
            *(f"tema {i}: {_short(text)}" for i, a, text in topics if a == at),
        ]
        groups.append(
            ArchiveGroup(
                at=at,
                facts=sum(1 for f in facts if f.archived_at == at),
                relations=sum(1 for r in relations if r.archived_at == at),
                units=sum(1 for _, a, _ in units if a == at),
                topics=sum(1 for _, a, _ in topics if a == at),
                texts=tuple(texts),
            )
        )
    return groups


async def restore_archive_group(at: str, *, actor: AdminActor, now: str) -> ArchiveCounts:
    """Bring back one archive group and audit it (``change``, no value).

    Args:
        at: The instant of the group, as ``archive list`` shows it.
        actor: Who runs the command.
        now: The current instant.

    Returns:
        How many rows of each kind came back.
    """
    async with db.transaction() as conn:
        counts = await restore_archived(conn, at=at)
    await _audit(
        actor, AdminOperationKind.CHANGE, TargetKind.POOL_LITERAL, "archive", refused=None, now=now
    )
    return counts
