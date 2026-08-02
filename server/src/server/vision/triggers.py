"""Deterministic visual-intent lexicons — no LLM tool-calling.

A 3B chat model decides unreliably when to use tools, so intent triggers
live in code (same pattern as ``memory/lexicon.py``). Word boundaries
prevent false hits like "aunque VEStirse"; matching is accent-folded.
"""

from __future__ import annotations

import re
import unicodedata

# "¿qué ves?" and friends — includes the recognition questions ("¿quién
# soy?") because they need a camera frame exactly like a description does.
_VISION_TRIGGERS = tuple(
    re.compile(rf"\b{pattern}\b")
    for pattern in (
        r"que\s+ves",
        r"que\s+estas\s+viendo",
        r"que\s+miras",
        r"que\s+observas",
        r"mira\s+esto",
        r"mira\s+lo\s+que",
        r"puedes\s+ver",
        r"podes\s+ver",
        r"ves\s+esto",
        r"ves\s+algo",
        r"que\s+tengo\s+en\s+la\s+mano",
        r"describe\s+lo\s+que\s+ves",
        r"dime\s+que\s+ves",
        r"decime\s+que\s+ves",
        # V1 — recognition questions
        r"quien\s+soy",
        r"me\s+reconoces",
        r"me\s+conoces",
        r"sabes\s+quien\s+soy",
        r"quien\s+esta\s+(aqui|frente)",
    )
)

# V1 — explicit face-learning cues. Deliberately NOT "me llamo X" or plain
# "yo soy X": those belong to the onboarding interview and must never
# hijack a turn into the camera flow. Enrolling requires an explicit,
# consent-bearing phrase (docs/audit/05 §5).
_ENROLL_CUES = tuple(
    re.compile(rf"\b{pattern}\b")
    for pattern in (
        r"aprende\s+(mi|su|la)\s+cara",
        r"recuerda\s+(mi|su|la)\s+cara",
        r"memoriza\s+(mi|su|la)\s+cara",
        r"mira(me|la|lo)\s+bien",
        r"te\s+presento\s+a",
        r"conoce\s+a",
    )
)

# Name capture runs on the ORIGINAL text (accents preserved for the
# entities table); the cue check runs folded.
_ENROLL_NAME = re.compile(
    r"\b(?:soy|es|se\s+llama|te\s+presento\s+a|conoce\s+a)\s+"
    r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)",
    re.IGNORECASE,
)

# Words that follow "soy/es" without being a name ("soy de Santiago").
_NON_NAME_WORDS = frozenset({"de", "del", "el", "la", "un", "una", "muy", "yo", "tu", "su"})


def _fold(text: str) -> str:
    """Lowercase *text* and strip accents for trigger matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def wants_vision(text: str) -> bool:
    """Return ``True`` when the user's words ask the robot to look.

    Args:
        text: Transcribed user speech for this turn.
    """
    folded = _fold(text)
    return any(trigger.search(folded) for trigger in _VISION_TRIGGERS)


def wants_enroll(text: str) -> str | None:
    """Return the name to enroll when the user asks to learn a face.

    Both halves are required: an explicit face-learning cue ("aprende mi
    cara", "te presento a") AND a name in the same utterance. The spoken
    phrase itself is the verbal consent the privacy design demands —
    enrolling is never automatic.

    Args:
        text: Transcribed user speech for this turn.

    Returns:
        The captured name title-cased, or ``None`` when this turn does
        not ask for enrollment.
    """
    folded = _fold(text)
    if not any(cue.search(folded) for cue in _ENROLL_CUES):
        return None
    match = _ENROLL_NAME.search(text)
    if match is None:
        return None
    name = match.group(1)
    if name.casefold() in _NON_NAME_WORDS:
        return None
    return name.title()
