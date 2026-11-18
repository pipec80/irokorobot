"""Correct a taste and set a memory aside by voice (Plan 0086 Tasks 6 and 7, D-5 to D-7).

The owner's face and a closed verb; a stranger, a token and a second face hear ordinary
conversation and leave nothing pending. Canary names only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.intent_resolution import parse_memory_answer
from server.cognition.memory_change import parse_memory_change
from server.cognition.models import (
    AuthorizationStatus,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
)
from server.memory import (
    candidate_dialogue,
    candidates,
    continuity,
    conversation_record,
    memory_change_dialogue,
    pending_store,
    recall_store,
    relational_v4,
)
from server.memory.candidate_types import CandidateChannel, ProposedCandidate
from server.memory.care_contacts import ContactRole, write_contact
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.memory.forget_scope import restore_archived
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.memory_change_dialogue import (
    answer_change,
    has_pending_change,
    propose_change,
    reset_pending_changes,
)
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.write_types import WriteChannel
from server.routers.transcribe import _voice_event_from_transcript
from server.settings import settings
from server.timestamps import instant_text

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from server.cognition.response_plan import MemoryAnswerReply, TextTurnPayload

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
_ANSWER = _T0 + timedelta(seconds=20)


def _evidence(source: IdentityEvidenceSource, person_id: int) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_T0,
        reference="canary",
    )


def _actor(person_id: int, *sources: IdentityEvidenceSource) -> ActivePersonContext:
    sources = sources or (IdentityEvidenceSource.FACE,)
    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
    return resolve_active_person(
        evidence=tuple(_evidence(s, person_id) for s in sources),
        lookup_person=lambda pid: person if pid == person_id else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _T0,
    )


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "change.db")
    monkeypatch.setattr(settings, "memory_candidate_answer_seconds", 60)
    db._conn = None
    reset_pending_changes()
    continuity.reset()
    await db.open_db()
    await db.run_migrations()
    try:
        owner_id = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(
            person_entity_id=owner_id, confirmed_person_entity_id=owner_id
        )
        yield owner_id
    finally:
        reset_pending_changes()
        await db.close_db()
        db._conn = None


def _definition(name: str) -> PredicateDefinition:
    definition = resolve_predicate(name)
    assert definition is not None
    return definition


async def _taste(owner: int, value: str, predicate: str = "likes") -> int:
    fact = await relational_v4.assert_literal_fact(
        subject_entity_id=owner,
        definition=_definition(predicate),
        value=value,
        visibility="personal",
        sensitivity="normal",
    )
    return fact.id


async def _tastes(owner: int, predicate: str = "likes") -> list[str]:
    return [
        fact.value_text
        for fact in await relational_v4.get_active_literal_facts(
            subject_entity_id=owner, definition=_definition(predicate)
        )
    ]


async def _propose(message: str, actor: ActivePersonContext) -> MemoryAnswerReply | None:
    change = parse_memory_change(message)
    assert change is not None
    return await propose_change(
        change,
        actor=actor,
        channel=WriteChannel.VOICE_STREAM,
        correlation_id=uuid4(),
        now=_T0,
    )


async def _answer(
    message: str, actor: ActivePersonContext, now: datetime = _ANSWER
) -> MemoryAnswerReply | None:
    answer = parse_memory_answer(message)
    assert answer is not None
    return await answer_change(answer, actor=actor, correlation_id=uuid4(), now=now)


async def _told(owner: int, heard: str, seconds: float) -> int:
    """A verified turn with its recall unit; returns the unit id."""
    turn = make_turn(
        heard,
        "qué bueno",
        voice=TurnVerdict.VERIFIED,
        correlation_id=UUID(int=int(seconds) + 1),
        at=_T0 - timedelta(days=1) + timedelta(seconds=seconds),
    )
    record_id = await conversation_record.append_turn(turn, owner_entity_id=owner, now=turn.at)
    async with db.transaction() as conn:
        return await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn
        )


async def _count(sql: str, *params: object) -> int:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


# --- correct a taste (Task 6) ---------------------------------------------------------------------


async def test_ya_no_me_gusta_reads_back_and_keeps_the_tea_as_history(owner: int) -> None:
    fact_id = await _taste(owner, "el té")
    actor = _actor(owner)

    asked = await _propose("Ya no me gusta el té.", actor)

    assert asked is not None
    assert asked.phrase == "Tenía guardado que te gusta el té. ¿Lo cambio? Dime: sí, autorizo."
    assert asked.expects_short_reply is True
    assert await _tastes(owner) == ["el té"]  # nothing changes before the verb

    done = await _answer("Sí, autorizo.", actor)

    assert done is not None
    assert done.phrase == "Listo, lo cambié."
    assert await _tastes(owner) == []
    fact = await relational_v4.get_literal_fact(fact_id)
    assert fact is not None
    assert fact.lifecycle is relational_v4.AssertionLifecycle.REVOKED
    assert (
        await _count(
            "SELECT COUNT(*) FROM authorization_audit_events WHERE action = 'correct_personal_memory' "
            "AND decision = 'allowed'"
        )
        == 1
    )


async def test_a_new_value_becomes_current_and_the_old_one_superseded(owner: int) -> None:
    old = await _taste(owner, "el café")
    actor = _actor(owner)

    asked = await _propose("Ya no me gusta el café, ahora prefiero el mate.", actor)
    assert asked is not None
    assert asked.phrase == (
        "Tenía guardado que te gusta el café. Ahora guardo que prefieres el mate. "
        "¿Lo cambio? Dime: sí, autorizo."
    )
    assert await _answer("Sí, autorizo.", actor) is not None

    assert await _tastes(owner, "prefers") == ["el mate"]
    assert await _tastes(owner) == []
    previous = await relational_v4.get_literal_fact(old)
    assert previous is not None
    assert previous.lifecycle is relational_v4.AssertionLifecycle.SUPERSEDED
    assert previous.superseded_by is not None


async def test_no_autorizo_changes_nothing(owner: int) -> None:
    await _taste(owner, "el té")
    actor = _actor(owner)
    await _propose("Ya no me gusta el té.", actor)

    declined = await _answer("No autorizo.", actor)

    assert declined is not None
    assert declined.phrase == "Está bien, no cambio nada."
    assert await _tastes(owner) == ["el té"]
    assert not has_pending_change(owner, _ANSWER)


async def test_after_the_window_the_answer_is_ordinary_conversation(owner: int) -> None:
    await _taste(owner, "el té")
    actor = _actor(owner)
    await _propose("Ya no me gusta el té.", actor)

    assert await _answer("Sí, autorizo.", actor, now=_T0 + timedelta(seconds=61)) is None
    assert await _tastes(owner) == ["el té"]


async def test_a_restart_loses_the_pending_change(owner: int) -> None:
    await _taste(owner, "el té")
    actor = _actor(owner)
    await _propose("Ya no me gusta el té.", actor)

    reset_pending_changes()

    assert await _answer("Sí, autorizo.", actor) is None
    assert await _tastes(owner) == ["el té"]


async def test_nothing_stored_is_said_and_nothing_is_pending(owner: int) -> None:
    reply = await _propose("Ya no me gusta el té.", _actor(owner))

    assert reply is not None
    assert reply.phrase == "No tenía guardado que te gusta el té."
    assert not has_pending_change(owner, _T0)


@pytest.mark.parametrize(
    "sources",
    [
        (IdentityEvidenceSource.LOCAL_UNLOCK,),
        (IdentityEvidenceSource.FACE, IdentityEvidenceSource.LOCAL_UNLOCK),
        (IdentityEvidenceSource.VOICE,),
    ],
)
async def test_a_token_or_a_voice_alone_hears_ordinary_conversation(
    owner: int, sources: tuple[IdentityEvidenceSource, ...]
) -> None:
    await _taste(owner, "el té")

    assert await _propose("Ya no me gusta el té.", _actor(owner, *sources)) is None
    assert not has_pending_change(owner, _T0)


async def test_another_face_cannot_answer_the_owners_change(owner: int) -> None:
    await _taste(owner, "el té")
    other = await upsert_entity(name="Canary Other", type="person")
    await _propose("Ya no me gusta el té.", _actor(owner))

    assert await _answer("Sí, autorizo.", _actor(other)) is None
    assert await _tastes(owner) == ["el té"]
    assert has_pending_change(owner, _ANSWER)


async def test_an_answer_that_names_a_value_goes_on_to_the_offer(owner: int) -> None:
    await _taste(owner, "el té")
    await _propose("Ya no me gusta el té.", _actor(owner))

    assert await _answer("Autorizo guardar el mate.", _actor(owner)) is None


async def test_no_offer_is_spoken_while_a_change_waits(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    actor = _actor(owner)
    stored = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_STREAM,
        correlation_id=uuid4(),
        now=_T0,
    )
    assert stored.candidate_id is not None
    await _taste(owner, "el té")

    strong = _actor(owner, IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE)

    async def verify(
        actor: ActivePersonContext,
        *,
        wav_bytes: bytes | None,
        event: CognitiveEvent[TextTurnPayload],
    ) -> ActivePersonContext | None:
        del actor, wav_bytes, event
        return strong

    event = _voice_event_from_transcript("hola")
    offered = await candidate_dialogue.prepare_offer(
        actor, wav_bytes=None, event=event, verify=verify, clock=lambda: _T0
    )
    assert offered is not None

    await _propose("Ya no me gusta el té.", actor)
    blocked = await candidate_dialogue.prepare_offer(
        actor, wav_bytes=None, event=event, verify=verify, clock=lambda: _T0
    )
    assert blocked is None


async def test_a_second_taste_never_supersedes_the_first(owner: int) -> None:
    """Case 3 (D-3): «me gusta más la comida del restaurante La Ola» adds, it does not replace."""
    await _taste(owner, "la comida china del restaurante El Faro")

    await _taste(owner, "la comida del restaurante La Ola")

    assert sorted(await _tastes(owner)) == [
        "la comida china del restaurante El Faro",
        "la comida del restaurante La Ola",
    ]


# --- archive by voice (Task 7) --------------------------------------------------------------------


async def test_a_person_only_talked_about_is_set_aside_and_comes_back(owner: int) -> None:
    first = await _told(owner, "el sábado fui al cine con mi amiga Canaria", 0)
    second = await _told(owner, "ayer almorcé con Canaria en el centro", 60)
    await _told(owner, "hoy llovió toda la tarde", 120)
    actor = _actor(owner)

    asked = await _propose(
        "Mi mejor amiga Canaria me traicionó; no quiero saber nunca más de ella.", actor
    )

    assert asked is not None
    assert asked.phrase == (
        "Encontré 2 recuerdos de Canaria. Los dejo de lado y no te los menciono más. "
        "¿Lo hago? Dime: sí, autorizo."
    )
    done = await _answer("Sí, autorizo.", actor)
    assert done is not None
    assert done.phrase == "Listo, lo dejé de lado."
    now = instant_text(_ANSWER)
    assert (
        await recall_store.lexical_hits(
            owner_entity_id=owner, terms=("canaria",), since=None, until=None, now=now, limit=5
        )
        == []
    )
    cursor = await db.get_conn().execute(
        "SELECT archived_at FROM recall_units WHERE id IN (?, ?)", (first, second)
    )
    instants = {str(row[0]) for row in await cursor.fetchall()}
    await cursor.close()
    assert len(instants) == 1

    async with db.transaction() as conn:
        counts = await restore_archived(conn, at=instants.pop())

    assert counts.units == 2
    assert (
        len(
            await recall_store.lexical_hits(
                owner_entity_id=owner, terms=("canaria",), since=None, until=None, now=now, limit=5
            )
        )
        == 2
    )


async def test_an_alta_entity_takes_its_relations_and_its_topics(owner: int) -> None:
    friend = await upsert_entity(name="Zorzal", type="person")
    relation = await relational_v4.assert_entity_relation(
        source_entity_id=owner, definition=_definition("has_sibling"), target_entity_id=friend
    )
    await _told(owner, "Zorzal me llamó por la tarde", 0)
    record = await conversation_record.list_records()
    async with db.transaction() as conn:
        topic = await pending_store.insert_unnamed(
            conn,
            owner_entity_id=owner,
            record_id=record[0].id,
            correlation_id=uuid4(),
            said_day=date(2026, 11, 17),
            due_day=date(2026, 11, 19),
            heard="mañana veo a Zorzal",
            sensitivity="normal",
            now=_T0,
        )
    assert await pending_store.set_topic(topic, "Zorzal")
    actor = _actor(owner)

    asked = await _propose("No me hables más de Zorzal.", actor)
    assert asked is not None
    assert asked.phrase.startswith("Encontré 3 recuerdos de Zorzal.")
    assert await _answer("Sí, autorizo.", actor) is not None

    assert await relational_v4.list_active_relations(owner) == []
    assert relation.id in [
        row.id for row in await relational_v4.list_active_relations(owner, include_archived=True)
    ]
    assert await pending_store.due_topic(owner, today=date(2026, 11, 20)) is None


async def test_a_care_contact_is_only_changed_in_iroko_admin(owner: int) -> None:
    friend = await upsert_entity(name="Zorzal", type="person")
    await write_contact(
        owner_entity_id=owner,
        contact_entity_id=friend,
        role=ContactRole.TRUSTED,
        phone="+56933333333",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=instant_text(_T0),
    )

    reply = await _propose("No quiero saber más de Zorzal.", _actor(owner))

    assert reply is not None
    assert reply.phrase == "Eso se cambia en iroko-admin, con tu PIN."
    assert not has_pending_change(owner, _T0)


async def test_a_private_relation_is_only_changed_in_iroko_admin(owner: int) -> None:
    friend = await upsert_entity(name="Zorzal", type="person")
    await relational_v4.assert_entity_relation(
        source_entity_id=owner,
        definition=_definition("withhold_from"),
        target_entity_id=friend,
    )

    reply = await _propose("No quiero saber más de Zorzal.", _actor(owner))

    assert reply is not None
    assert reply.phrase == "Eso se cambia en iroko-admin, con tu PIN."


async def test_a_name_found_nowhere_says_so(owner: int) -> None:
    reply = await _propose("No quiero saber más de Zorzal.", _actor(owner))

    assert reply is not None
    assert reply.phrase == "No tengo nada guardado de Zorzal."
    assert not has_pending_change(owner, _T0)


async def test_a_common_word_name_shows_its_true_count(owner: int) -> None:
    """Review focus 5: «Paz» names a person and also a word; the count says how much goes."""
    await _told(owner, "hablé con Paz por teléfono", 0)
    await _told(owner, "por fin hay paz en la casa", 60)
    await _told(owner, "quiero paz y tranquilidad", 120)

    asked = await _propose("No quiero saber más de Paz.", _actor(owner))

    assert asked is not None
    assert asked.phrase.startswith("Encontré 3 recuerdos de Paz.")


async def test_archiving_clears_the_short_term_session(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleared: list[bool] = []
    monkeypatch.setattr(continuity, "reset", lambda: cleared.append(True))
    await _told(owner, "fui al cine con Canaria", 0)
    actor = _actor(owner)
    await _propose("No quiero saber más de Canaria.", actor)

    await _answer("Sí, autorizo.", actor)

    assert cleared == [True]


# --- what a voice change may not do (security review of 4cde5a2) ---------------------------------


async def test_a_new_value_the_taste_gate_refuses_is_only_changed_in_iroko_admin(
    owner: int,
) -> None:
    await _taste(owner, "el café")

    reply = await _propose(
        "Ya no me gusta el café, ahora prefiero el banco de mi barrio.", _actor(owner)
    )

    assert reply is not None
    assert reply.phrase == "Eso se cambia en iroko-admin, con tu PIN."
    assert not has_pending_change(owner, _T0)


async def test_a_relation_that_is_not_personal_is_only_changed_in_iroko_admin(owner: int) -> None:
    friend = await upsert_entity(name="Zorzal", type="person")
    await relational_v4.assert_entity_relation(
        source_entity_id=owner,
        definition=_definition("has_sibling"),
        target_entity_id=friend,
        visibility="household",
    )

    reply = await _propose("No quiero saber más de Zorzal.", _actor(owner))

    assert reply is not None
    assert reply.phrase == "Eso se cambia en iroko-admin, con tu PIN."


# --- review findings of Task 8 --------------------------------------------------------------------


def _denied(request: object) -> object:
    from server.cognition.authorization import evaluate_authorization  # noqa: PLC0415

    decision = evaluate_authorization(request)  # type: ignore[arg-type]  # the real request
    return decision.model_copy(update={"decision": AuthorizationStatus.DENIED})


async def _answer_with(actor: ActivePersonContext, **doubles: object) -> MemoryAnswerReply | None:
    answer = parse_memory_answer("Sí, autorizo.")
    assert answer is not None
    return await answer_change(
        answer,
        actor=actor,
        correlation_id=uuid4(),
        now=_ANSWER,
        **doubles,  # type: ignore[arg-type]  # policy and audit doubles
    )


@pytest.mark.parametrize("failure", ["denied", "audit", "apply"])
async def test_a_refused_or_failed_change_changes_nothing_and_says_so(
    owner: int, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    await _taste(owner, "el café")
    actor = _actor(owner)
    await _propose("Ya no me gusta el café, ahora prefiero el mate.", actor)
    doubles: dict[str, object] = {}
    if failure == "denied":
        doubles["policy"] = _denied
    elif failure == "audit":
        doubles["audit"] = AsyncMock(side_effect=RuntimeError("canary"))
    else:
        monkeypatch.setattr(
            memory_change_dialogue,
            "supersede_literal_fact",
            AsyncMock(side_effect=RuntimeError("canary")),
        )

    reply = await _answer_with(actor, **doubles)

    assert reply is not None
    assert reply.phrase == "No pude hacerlo ahora. Dímelo de nuevo en un rato."
    assert await _tastes(owner) == ["el café"]
    assert await _tastes(owner, "prefers") == []  # the new value rolled back with the rest
    assert not has_pending_change(owner, _ANSWER)


async def test_a_medical_topic_keeps_a_voice_archive_away(owner: int) -> None:
    await _told(owner, "fui al cine con Canaria", 0)
    record = await conversation_record.list_records()
    async with db.transaction() as conn:
        await pending_store.insert_unnamed(
            conn,
            owner_entity_id=owner,
            record_id=record[0].id,
            correlation_id=uuid4(),
            said_day=date(2026, 11, 17),
            due_day=date(2026, 11, 19),
            heard="mañana acompaño a Canaria al médico",
            sensitivity="medical",
            now=_T0,
        )

    reply = await _propose("No quiero saber más de Canaria.", _actor(owner))

    assert reply is not None
    assert reply.phrase == "Eso se cambia en iroko-admin, con tu PIN."


async def test_a_request_that_proposes_nothing_drops_the_older_read_back(owner: int) -> None:
    await _taste(owner, "el té")
    actor = _actor(owner)
    await _propose("Ya no me gusta el té.", actor)

    nothing = await _propose("No quiero saber más de Zorzal.", actor)

    assert nothing is not None
    assert nothing.phrase == "No tengo nada guardado de Zorzal."
    assert await _answer("Sí, autorizo.", actor) is None
    assert await _tastes(owner) == ["el té"]


async def test_a_name_heard_with_a_final_s_still_finds_the_person(owner: int) -> None:
    """Hardware 2026-11-18: Whisper heard «Canarias» for «Canaria» and nothing was found."""
    await _told(owner, "el sábado fui al cine con mi amiga Canaria", 0)

    asked = await _propose("No quiero saber nunca más de Canarias.", _actor(owner))

    assert asked is not None
    assert asked.phrase.startswith("Encontré un recuerdo de Canarias.")
