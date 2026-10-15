"""How much candidate extraction one process may run: one at a time, and so many per hour.

Extraction is a local-model call of tens of seconds on the shared laptop (ADR 0021 decision 4).
Two limits keep it from taking the machine from the conversation:

* **one in flight**: a matching turn that finds an extraction running is dropped (``busy``), not
  queued; a restated taste is easy, a growing queue of 40-second calls is not;
* **a rolling hourly budget** (``MEMORY_CANDIDATE_EXTRACTIONS_PER_HOUR``) of extraction starts.

Both live in process memory, like the session slot (one worker, ADR 0010). The clock is
injectable so the hour can be tested without waiting.
"""

from __future__ import annotations

from collections import deque
import time
from typing import TYPE_CHECKING

from server.memory.candidate_types import CandidateReason
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["ExtractionLimiter", "limiter"]

_HOUR_SECONDS = 3600.0


class ExtractionLimiter:
    """One extraction at a time and a rolling hourly budget of starts."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """Create an idle limiter.

        Args:
            clock: Monotonic seconds; injectable so the hour needs no real waiting.
        """
        self._clock = clock
        self._busy = False
        self._starts: deque[float] = deque()

    @property
    def busy(self) -> bool:
        """Whether an extraction is in flight."""
        return self._busy

    def try_acquire(self) -> CandidateReason | None:
        """Take the slot for one extraction, if it is free and the hour has budget left.

        Returns:
            ``None`` when the slot is now held (the caller must ``release`` it), ``BUSY`` when
            another extraction is running, ``BUDGET`` when the rolling hour is spent. There is
            no ``await`` between the check and the take, so two turns cannot both pass.
        """
        if self._busy:
            return CandidateReason.BUSY
        now = self._clock()
        while self._starts and now - self._starts[0] >= _HOUR_SECONDS:
            self._starts.popleft()
        if len(self._starts) >= settings.memory_candidate_extractions_per_hour:
            return CandidateReason.BUDGET
        self._busy = True
        self._starts.append(now)
        return None

    def release(self) -> None:
        """Free the slot (idempotent). The start stays counted against the hour."""
        self._busy = False

    def reset(self) -> None:
        """Forget the slot and the hour (used by tests)."""
        self._busy = False
        self._starts.clear()


#: The process-wide limiter.
limiter = ExtractionLimiter()
