"""Unit tests for server.memory.continuity — the short-term continuity slot (ADR 0020).

One session slot for the identified person: bounded by characters and by silence, replaced by
another identified person, suspended (never read or written) by an unknown or ambiguous turn.
"""

import logging

import pytest
from server.memory import continuity
from server.memory.continuity import ContinuitySession, SuspendCause, Transition
from server.schemas import ConversationTurn
from server.settings import settings

pytestmark = pytest.mark.unit

_OWNER = 7
_VISITOR = 8
_IDLE_S = 180.0


class _Clock:
    """A hand-driven monotonic clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def session(clock: _Clock) -> ContinuitySession:
    return ContinuitySession(clock=clock)


def _say(session: ContinuitySession, person_id: int, user: str, reply: str) -> bool:
    """Open a turn for *person_id* and record one exchange; return whether it was written."""
    return session.record_pair(session.open_turn(person_id), user, reply)


def _contents(turn: continuity.ContinuityTurn) -> list[str]:
    return [item.content for item in turn.history]


# --- who has a session ----------------------------------------------------


def test_the_first_identified_turn_starts_an_empty_session(session: ContinuitySession) -> None:
    turn = session.open_turn(_OWNER)

    assert turn.history == ()
    assert turn.person_id == _OWNER
    assert turn.writable


def test_the_same_person_continues_with_the_previous_exchange(session: ContinuitySession) -> None:
    assert _say(session, _OWNER, "hola", "hola humano")

    turn = session.open_turn(_OWNER)

    assert all(isinstance(item, ConversationTurn) for item in turn.history)
    assert [(item.role, item.content) for item in turn.history] == [
        ("user", "hola"),
        ("assistant", "hola humano"),
    ]


def test_another_identified_person_replaces_the_session_and_reads_nothing(
    session: ContinuitySession,
) -> None:
    _say(session, _OWNER, "mi clave es COBALTO", "anotado")

    visitor = session.open_turn(_VISITOR)

    assert visitor.history == ()
    assert session.open_turn(_OWNER).history == ()  # the owner's session is gone, not hidden


def test_a_turn_of_the_replaced_person_cannot_write_into_the_new_session(
    session: ContinuitySession,
) -> None:
    in_flight = session.open_turn(_OWNER)
    session.open_turn(_VISITOR)  # replaces: the generation moves on

    assert not session.record_pair(in_flight, "pregunta", "respuesta")
    assert _contents(session.open_turn(_VISITOR)) == []


# --- suspension -----------------------------------------------------------


@pytest.mark.parametrize("cause", list(SuspendCause))
def test_a_suspended_turn_reads_nothing_and_cannot_write(
    session: ContinuitySession, cause: SuspendCause
) -> None:
    _say(session, _OWNER, "dato privado", "ok")

    suspended = session.open_turn(None, cause)

    assert suspended.history == ()
    assert suspended.person_id is None
    assert not suspended.writable
    assert not session.record_pair(suspended, "otra cosa", "respuesta")


def test_the_owner_resumes_after_a_suspension(session: ContinuitySession) -> None:
    _say(session, _OWNER, "primero", "uno")
    session.open_turn(None, SuspendCause.NO_EVIDENCE)
    session.open_turn(None, SuspendCause.VETO_MULTIPLE_FACES)

    turn = session.open_turn(_OWNER)

    assert _contents(turn) == ["primero", "uno"]


def test_a_suspension_does_not_invalidate_a_write_in_flight(session: ContinuitySession) -> None:
    """A stranger's turn never drops the owner's concurrent write (ADR 0020 §3)."""
    in_flight = session.open_turn(_OWNER)
    session.open_turn(None, SuspendCause.NO_EVIDENCE)

    assert session.record_pair(in_flight, "pregunta", "respuesta")
    assert _contents(session.open_turn(_OWNER)) == ["pregunta", "respuesta"]


def test_two_overlapping_turns_of_the_same_person_both_write_in_order(
    session: ContinuitySession,
) -> None:
    first = session.open_turn(_OWNER)
    second = session.open_turn(_OWNER)

    assert session.record_pair(first, "uno", "1")
    assert session.record_pair(second, "dos", "2")
    assert _contents(session.open_turn(_OWNER)) == ["uno", "1", "dos", "2"]


# --- silence --------------------------------------------------------------


def test_a_session_survives_just_under_the_idle_limit(
    session: ContinuitySession, clock: _Clock
) -> None:
    _say(session, _OWNER, "hola", "hola")
    clock.now += _IDLE_S - 0.1

    assert _contents(session.open_turn(_OWNER)) == ["hola", "hola"]


def test_a_session_expires_at_the_idle_limit(session: ContinuitySession, clock: _Clock) -> None:
    _say(session, _OWNER, "hola", "hola")
    clock.now += _IDLE_S

    assert session.open_turn(_OWNER).history == ()


def test_a_suspended_session_keeps_ageing(session: ContinuitySession, clock: _Clock) -> None:
    _say(session, _OWNER, "hola", "hola")
    clock.now += 100
    session.open_turn(None, SuspendCause.NO_EVIDENCE)  # does not extend the silence
    clock.now += 80

    assert session.open_turn(_OWNER).history == ()


def test_a_suspended_turn_drops_an_expired_session(
    session: ContinuitySession, clock: _Clock
) -> None:
    in_flight = session.open_turn(_OWNER)
    clock.now += _IDLE_S
    session.open_turn(None, SuspendCause.NO_EVIDENCE)

    assert not session.record_pair(in_flight, "tarde", "tarde")  # the generation moved on


def test_writing_extends_the_silence(session: ContinuitySession, clock: _Clock) -> None:
    _say(session, _OWNER, "uno", "1")
    clock.now += 150
    _say(session, _OWNER, "dos", "2")
    clock.now += 150

    assert _contents(session.open_turn(_OWNER)) == ["uno", "1", "dos", "2"]


# --- size -----------------------------------------------------------------


def test_whole_pairs_leave_oldest_first_when_the_character_cap_is_exceeded(
    session: ContinuitySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "working_memory_max_chars", 20)
    _say(session, _OWNER, "aaaaa", "bbbbb")  # 10 chars
    _say(session, _OWNER, "ccccc", "ddddd")  # 20 chars in total: still fits

    assert _say(session, _OWNER, "eeeee", "fffff")  # 30: the oldest pair leaves whole

    assert _contents(session.open_turn(_OWNER)) == ["ccccc", "ddddd", "eeeee", "fffff"]


def test_a_single_pair_larger_than_the_cap_is_not_kept(
    session: ContinuitySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "working_memory_max_chars", 10)
    _say(session, _OWNER, "ok", "ok")

    assert not _say(session, _OWNER, "x" * 8, "y" * 8)

    assert _contents(session.open_turn(_OWNER)) == ["ok", "ok"]


def test_the_message_limit_is_an_upper_bound(
    session: ContinuitySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "working_memory_size", 4)
    for index in range(4):
        _say(session, _OWNER, f"u{index}", f"a{index}")

    assert _contents(session.open_turn(_OWNER)) == ["u2", "a2", "u3", "a3"]


# --- logging --------------------------------------------------------------


def test_every_transition_is_logged_with_a_closed_reason_and_no_content(
    session: ContinuitySession, clock: _Clock, caplog: pytest.LogCaptureFixture
) -> None:
    said = "mi clave es COBALTO"
    with caplog.at_level(logging.INFO, logger=continuity.logger.name):
        _say(session, _OWNER, said, "anotado")  # started
        session.open_turn(_OWNER)  # continued
        session.open_turn(None, SuspendCause.VETO_OTHER_PERSON)  # suspended
        session.open_turn(_VISITOR)  # replaced
        clock.now += _IDLE_S
        session.open_turn(_VISITOR)  # expired, then started

    reasons = [getattr(record, "reason", None) for record in caplog.records]
    assert reasons == [
        Transition.STARTED,
        Transition.CONTINUED,
        Transition.SUSPENDED,
        Transition.REPLACED,
        Transition.EXPIRED,
        Transition.STARTED,
    ]
    assert said not in caplog.text
    assert "anotado" not in caplog.text
    suspended = next(
        record
        for record in caplog.records
        if getattr(record, "reason", None) is Transition.SUSPENDED
    )
    assert getattr(suspended, "cause", None) is SuspendCause.VETO_OTHER_PERSON


def test_the_suspension_causes_are_the_closed_set_of_the_adr() -> None:
    assert {cause.value for cause in SuspendCause} == {
        "no_evidence",
        "veto_other_person",
        "veto_multiple_faces",
        "backend_unavailable",
        "error",
    }
    assert {reason.value for reason in Transition} == {
        "continued",
        "started",
        "replaced",
        "suspended",
        "expired",
    }


# --- the process-wide slot ------------------------------------------------


def test_the_module_functions_use_one_process_wide_slot() -> None:
    first = continuity.open_turn(_OWNER)
    assert continuity.record_pair(first, "hola", "hola")

    assert [item.content for item in continuity.open_turn(_OWNER).history] == ["hola", "hola"]

    continuity.reset()
    assert continuity.open_turn(_OWNER).history == ()


def test_a_message_limit_that_cannot_hold_one_exchange_keeps_nothing(
    session: ContinuitySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`WORKING_MEMORY_SIZE` counts messages: below 2 no exchange fits, and nothing is reported kept."""
    monkeypatch.setattr(settings, "working_memory_size", 1)

    assert not _say(session, _OWNER, "hola", "hola")

    assert session.open_turn(_OWNER).history == ()
