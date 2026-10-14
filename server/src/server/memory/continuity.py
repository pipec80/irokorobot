"""In-process short-term continuity for the identified person (ADR 0020).

One session slot: the device has one microphone and a half-duplex loop, so at most one
conversation is alive. The slot belongs to a person id, never to a ``conversation_id`` (a
client-chosen string that is not identity), and it is never persisted.

Rules: bounded by characters and by silence; another identified person replaces it; an
unknown or ambiguous turn *suspends* it (that turn neither reads nor writes it); a write
carries the generation it read and is dropped when another turn changed the session
meanwhile. Only closed reasons and a person id are logged, never conversation text.

asyncio runs on one thread and every method is synchronous, so no lock is needed.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
import logging
import time
from typing import TYPE_CHECKING

from server.schemas import ConversationTurn
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_USER_AND_ASSISTANT = 2


class Transition(StrEnum):
    """Closed reason of one session transition — the only thing logged about it."""

    CONTINUED = "continued"
    STARTED = "started"
    REPLACED = "replaced"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class SuspendCause(StrEnum):
    """Closed cause of a suspension, so suspensions can be counted by origin."""

    NO_EVIDENCE = "no_evidence"
    VETO_OTHER_PERSON = "veto_other_person"
    VETO_MULTIPLE_FACES = "veto_multiple_faces"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    ERROR = "error"


@dataclass(frozen=True)
class ContinuityTurn:
    """What one generic turn may read and write of the session.

    Attributes:
        history: The previous exchanges, oldest first; empty when the turn is suspended.
        person_id: The person the session belongs to, or ``None`` for a suspended turn.
        generation: The session generation this turn read; a stale write is dropped.
    """

    history: tuple[ConversationTurn, ...]
    person_id: int | None
    generation: int

    @property
    def writable(self) -> bool:
        """Whether this turn may write an exchange (it is not suspended)."""
        return self.person_id is not None


@dataclass
class _Slot:
    person_id: int
    pairs: deque[tuple[str, str]]
    last_written: float


class ContinuitySession:
    """The single short-term conversation of the identified person."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """Create an empty session.

        Args:
            clock: Monotonic seconds; injectable so silence can be tested without sleeping.
        """
        self._clock = clock
        self._slot: _Slot | None = None
        self._generation = 0

    def open_turn(self, person_id: int | None, cause: SuspendCause | None = None) -> ContinuityTurn:
        """Apply the transition for one generic turn's speaker and return what it may read.

        Args:
            person_id: The identified person, or ``None`` when the speaker is unknown,
                ambiguous or could not be identified (the turn is suspended).
            cause: Why the turn is suspended; ``NO_EVIDENCE`` when omitted.

        Returns:
            The turn's view of the session. A suspended turn has no history and cannot write.
        """
        self._drop_if_idle()
        if person_id is None:
            self._log(Transition.SUSPENDED, cause=cause or SuspendCause.NO_EVIDENCE)
            return ContinuityTurn((), None, self._generation)
        slot = self._slot
        if slot is None:
            self._slot = _Slot(person_id, deque(), self._clock())
            self._log(Transition.STARTED, person_id=person_id)
            return ContinuityTurn((), person_id, self._generation)
        if slot.person_id != person_id:
            self._generation += 1
            self._slot = _Slot(person_id, deque(), self._clock())
            self._log(Transition.REPLACED, person_id=person_id)
            return ContinuityTurn((), person_id, self._generation)
        self._log(Transition.CONTINUED, person_id=person_id)
        history: list[ConversationTurn] = []
        for user, assistant in slot.pairs:
            history.append(ConversationTurn(role="user", content=user))
            history.append(ConversationTurn(role="assistant", content=assistant))
        return ContinuityTurn(tuple(history), person_id, self._generation)

    def record_pair(self, turn: ContinuityTurn, user: str, assistant: str) -> bool:
        """Append one exchange read through *turn*, unless the turn can no longer write.

        Args:
            turn: The view returned by :meth:`open_turn` for this same turn.
            user: What the person said.
            assistant: What was answered.

        Returns:
            ``True`` when the exchange was kept. ``False`` for a suspended turn, a stale
            generation (another person replaced the session, or it expired), a message
            limit that cannot hold one exchange (``WORKING_MEMORY_SIZE`` below 2) or a
            single exchange larger than ``WORKING_MEMORY_MAX_CHARS``.
        """
        slot = self._slot
        if turn.person_id is None:
            return False
        if slot is None or slot.person_id != turn.person_id or turn.generation != self._generation:
            logger.info("Continuity: write dropped (stale session)")
            return False
        if settings.working_memory_size < _USER_AND_ASSISTANT:
            logger.info("Continuity: write dropped (WORKING_MEMORY_SIZE keeps no exchange)")
            return False
        if len(user) + len(assistant) > settings.working_memory_max_chars:
            logger.info("Continuity: write dropped (exchange larger than the cap)")
            return False
        slot.pairs.append((user, assistant))
        self._trim(slot)
        slot.last_written = self._clock()
        return True

    def clear(self) -> None:
        """Forget the session and its generation (used by tests)."""
        self._slot = None
        self._generation = 0

    def _drop_if_idle(self) -> None:
        """Delete a session that has not been written for ``WORKING_MEMORY_IDLE_SECONDS``."""
        slot = self._slot
        if slot is None:
            return
        if self._clock() - slot.last_written >= settings.working_memory_idle_seconds:
            self._slot = None
            self._generation += 1
            self._log(Transition.EXPIRED)

    @staticmethod
    def _trim(slot: _Slot) -> None:
        """Drop whole oldest exchanges until the character and message caps hold."""
        max_pairs = settings.working_memory_size // _USER_AND_ASSISTANT
        while slot.pairs and (
            len(slot.pairs) > max_pairs
            or sum(len(user) + len(assistant) for user, assistant in slot.pairs)
            > settings.working_memory_max_chars
        ):
            slot.pairs.popleft()

    @staticmethod
    def _log(
        reason: Transition, *, person_id: int | None = None, cause: SuspendCause | None = None
    ) -> None:
        """Log one transition with its closed reason; never any conversation text."""
        logger.info(
            "Continuity: %s",
            reason.value,
            extra={
                "event": "continuity.transition",
                "reason": reason,
                "cause": cause,
                "person_id": person_id,
            },
        )


_session = ContinuitySession()


def open_turn(person_id: int | None, cause: SuspendCause | None = None) -> ContinuityTurn:
    """Apply one generic turn's transition on the process-wide session.

    Args:
        person_id: The identified person, or ``None`` to suspend the turn.
        cause: Why the turn is suspended; ``NO_EVIDENCE`` when omitted.

    Returns:
        What the turn may read and write.
    """
    return _session.open_turn(person_id, cause)


def record_pair(turn: ContinuityTurn, user: str, assistant: str) -> bool:
    """Append one exchange to the process-wide session; see :meth:`ContinuitySession.record_pair`.

    Args:
        turn: The view returned by :func:`open_turn` for this turn.
        user: What the person said.
        assistant: What was answered.

    Returns:
        Whether the exchange was kept.
    """
    return _session.record_pair(turn, user, assistant)


def reset() -> None:
    """Forget the process-wide session (used by tests)."""
    _session.clear()
