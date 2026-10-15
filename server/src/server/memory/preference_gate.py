"""The preference gate: does this text declare a first-person taste, and under which predicates?

Pure and cheap (ADR 0021 decision 4): a closed list of Spanish patterns matched clause by
clause after case and accent folding. The gate decides nothing durable. It only says whether
spending a voice check and a model call is worth it, and it refuses on doubt:

* a question or conditional;
* a clause rather than a thing (``me gusta que ...``, ``prefiero que ...``), which is an
  instruction to the robot and belongs to CM-3b;
* any negation other than the triggers ``no me gusta(n)`` and ``no soporto``, so ``ya no me
  gusta`` (a correction, CM-6) and ``prefiero no hablar de ...`` never pass;
* a third person or a lead-in the grammar does not know (``mi hermano dice que me gusta``), and a
  taste that follows an attribution after a soft break (``mi hija dice: me gusta el helado``);
* an object (the words from the trigger to the next coordinator) that names a person, a place,
  health, money, a credential or a disclosure, in the singular, the plural or a diminutive;
* a contrast inside one taste (``todo menos el café``, ``prefiero el mate al café``): the model
  never picks which side of it is the taste.

Each accepted taste is returned with the words that follow its own trigger, so the classifier can
tie the model's object to a trigger of the same predicate (the model never decides the polarity).
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from server.cognition.intent_resolution import normalize_spanish
from server.memory.candidate_types import CandidateReason, GateMatch
from server.memory.lexicon import (
    CLAUSE_OPENERS,
    GREETING_WORDS,
    LEAD_IN_WORDS,
    NEGATORS,
    PREFERENCE_FAVOURITE,
    PREFERENCE_TRIGGERS,
    candidate_denied_words,
)

__all__ = ["GateMatch", "GateResult", "match_preference"]

# Punctuation ends a clause; a coordinating word ends a taste inside a clause ("me gusta el
# mate pero odio el café"). A hard stop forgets an attribution, a soft break keeps it.
_CLAUSE_SPLIT = re.compile(r"([,;:.!?¿¡…\n]+)")
_HARD_STOP = re.compile(r"[.!?¿¡…\n]")
_COORDINATION = re.compile(r"\s(?:pero|y|e|ni|aunque|sino)\s")
_PREFERS = "prefers"
_OBJECT_OPENING_PREPOSITIONS = frozenset({"a", "al"})
# Inside ONE taste these words say "this one, not that one": which side is the taste is not
# something the model may pick ("me gusta todo menos el café"), so the whole taste is dropped.
_EXCLUSION_WORDS = frozenset({"menos", "excepto", "salvo"})
# After "prefiero", "al" and "en vez de / en lugar de" introduce the thing that is NOT preferred.
_PREFERS_CONTRAST_WORDS = frozenset({"al"})
_PREFERS_CONTRAST_PHRASES = (" en vez ", " en lugar ")
_PREFIX_WORDS = LEAD_IN_WORDS | GREETING_WORDS | NEGATORS


def _trigger_pattern() -> re.Pattern[str]:
    """Build one alternation, longest phrase first, bounded by whole words."""
    phrases = sorted(PREFERENCE_TRIGGERS, key=len, reverse=True)
    alternatives = "|".join(
        [*(re.escape(phrase) for phrase in phrases), PREFERENCE_FAVOURITE.pattern]
    )
    return re.compile(rf"(?<![a-z])(?:{alternatives})(?![a-z])")


_TRIGGER = _trigger_pattern()
_DENIED = candidate_denied_words()


@dataclass(frozen=True)
class GateResult:
    """Outcome of the gate for one transcript.

    Attributes:
        matches: Each accepted taste with the words after its own trigger; empty when refused.
        reason: Why the text was refused; ``None`` exactly when ``matches`` is not empty.
    """

    matches: tuple[GateMatch, ...]
    reason: CandidateReason | None

    @property
    def predicates(self) -> frozenset[str]:
        """The canonical predicates the text may carry."""
        return frozenset(match.predicate for match in self.matches)


def _predicate_of(trigger: str) -> str:
    """Return the canonical predicate a matched trigger declares."""
    if PREFERENCE_FAVOURITE.fullmatch(trigger):
        return _PREFERS
    return PREFERENCE_TRIGGERS[trigger]


def _lead_refusal(lead: list[str]) -> CandidateReason | None:
    """Refuse a negated or unknown lead-in: only a short closed list may precede a trigger."""
    if any(word in NEGATORS for word in lead):
        return CandidateReason.NEGATION_UNSUPPORTED
    if any(word not in LEAD_IN_WORDS for word in lead):
        return CandidateReason.NOT_A_TASTE
    return None


def _contrast_refusal(predicate: str, trailing: list[str]) -> CandidateReason | None:
    """Refuse a taste that sets one thing against another inside its own words."""
    if any(word in _EXCLUSION_WORDS for word in trailing):
        return CandidateReason.NEGATION_UNSUPPORTED
    if predicate == _PREFERS:
        padded = f" {' '.join(trailing)} "
        if any(word in _PREFERS_CONTRAST_WORDS for word in trailing[1:]) or any(
            phrase in padded for phrase in _PREFERS_CONTRAST_PHRASES
        ):
            return CandidateReason.NEGATION_UNSUPPORTED
    return None


def _object_refusal(trigger_and_object: list[str], trailing: list[str]) -> CandidateReason | None:
    """Refuse what follows a trigger unless it is a plain, positive, non-sensitive thing."""
    if not trailing or trailing[0] in CLAUSE_OPENERS or "que" in trailing:
        return CandidateReason.NOT_A_TASTE
    if trailing[0] in NEGATORS:
        return CandidateReason.NEGATION_UNSUPPORTED
    if trailing[0] in _OBJECT_OPENING_PREPOSITIONS:
        return CandidateReason.NOT_A_TASTE  # "odio a Rodrigo": a person, never a thing
    if any(word in _DENIED for word in trigger_and_object):
        return CandidateReason.SENSITIVE_TOPIC
    return None


def _match_part(folded: str) -> GateMatch | CandidateReason | None:
    """Return a taste, the reason this part was refused, or ``None`` for no trigger."""
    found = _TRIGGER.search(folded)
    if found is None:
        return None
    lead = folded[: found.start()].split()
    trailing = folded[found.end() :].split()
    # The favourite trigger carries words ("mi hijo favorito es"): they are checked too.
    predicate = _predicate_of(found.group(0))
    refusal = (
        _lead_refusal(lead)
        or _object_refusal(folded[found.start() :].split(), trailing)
        or _contrast_refusal(predicate, trailing)
    )
    if refusal is not None:
        return refusal
    return GateMatch(predicate=predicate, words=tuple(trailing))


def match_preference(text: str) -> GateResult:
    """Decide whether *text* may declare a first-person taste.

    Args:
        text: The user's own transcript for this turn (never the assistant's reply).

    Returns:
        The tastes a part of the text declares, each with the words after its trigger, or the
        first closed reason the text was refused for. A text with no trigger at all is
        ``GATE_NO_MATCH``.
    """
    if "?" in text or "¿" in text:
        return GateResult((), CandidateReason.NOT_A_TASTE)
    matches: list[GateMatch] = []
    refusal: CandidateReason | None = None
    attributed = False  # words that are not a lead-in preceded this clause after a soft break
    pieces = _CLAUSE_SPLIT.split(text)
    for index in range(0, len(pieces), 2):
        folded_clause = normalize_spanish(pieces[index])
        delimiter = pieces[index + 1] if index + 1 < len(pieces) else ""
        outcomes = [_match_part(part) for part in _COORDINATION.split(folded_clause)]
        has_trigger = any(outcome is not None for outcome in outcomes)
        if has_trigger and attributed:
            refusal = refusal or CandidateReason.NOT_A_TASTE
        else:
            for outcome in outcomes:
                if isinstance(outcome, CandidateReason):
                    refusal = refusal or outcome
                elif outcome is not None:
                    matches.append(outcome)
        if not has_trigger and any(word not in _PREFIX_WORDS for word in folded_clause.split()):
            attributed = True
        if _HARD_STOP.search(delimiter):
            attributed = False
    if matches:
        return GateResult(tuple(matches), None)
    return GateResult((), refusal or CandidateReason.GATE_NO_MATCH)
