"""The onboarding slot type that the prompt still names until Plan 0076 Task 2 retires it.

The checklist that derived the next slot from the legacy facts table had no caller and went away
with the legacy memory path (Plan 0076 Task 1, ADR 0027 decision 9).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OnboardingSlot:
    """One datum the robot must learn during the first interview.

    Attributes:
        key: Canonical fact predicate that covers the slot.
        question_hint: What to ask, in Spanish, injected into the prompt.
        optional: Declinable slot — "no tengo hijos" covers it with the
            fact object "ninguno".
    """

    key: str
    question_hint: str
    optional: bool = False
