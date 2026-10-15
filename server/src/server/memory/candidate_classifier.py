"""The candidate classifier: accept or drop one extracted pair and fix its classification.

Pure (ADR 0021 decision 5): ``classify`` reads nothing but its arguments, so the model's
untrusted output is judged by a deterministic function and nobody else assigns the
classification. The model's subject is never read: the subject is the identified actor.

The rule everywhere is *on doubt, drop*. An object is kept only as a short noun phrase (or an
infinitive from a closed list) made of letters, placed by the extractor in a closed topic set,
free of person, role, place, health, money, credential and disclosure words, not the name of
anyone the household knows, and literally present in what the user said.
"""

from __future__ import annotations

import re
import unicodedata

from server.cognition.authorization import DataSensitivity, DataVisibility
from server.cognition.identity import ActivePersonContext, ActivePersonStatus
from server.cognition.intent_resolution import normalize_spanish
from server.memory.candidate_types import (
    CandidateReason,
    GateMatch,
    ProposedCandidate,
    RawCandidate,
)
from server.memory.lexicon import (
    ALLOWED_INFINITIVES,
    ARTICLES,
    CANDIDATE_TOPICS,
    candidate_denied_words,
)
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.settings import settings

__all__ = ["CANDIDATE_SENSITIVITY", "CANDIDATE_VISIBILITY", "classify", "comparison_key"]

#: What a CM-3a candidate becomes: the owner's own, ordinary data. The writer passes these
#: explicitly because the registry defaults are the household reader's read contract.
CANDIDATE_VISIBILITY = DataVisibility.PERSONAL
CANDIDATE_SENSITIVITY = DataSensitivity.NORMAL

_MAX_WORDS = 5
_MIN_CHARS = 2
_PHRASE = re.compile(rf"[^\W\d_]+(?: [^\W\d_]+){{0,{_MAX_WORDS - 1}}}")
# An infinitive, with or without a clitic ("cantar", "ser", "ir", "callarme"): a bare verb is an
# activity or a state of the speaker's life, so it passes only from the closed list.
_INFINITIVE = re.compile(r"[a-z]*(?:ar|er|ir)(?:me|te|se|lo|la|le|nos)?")
_WORD = re.compile(r"[^\W\d_]+")
_SENTENCE_END = re.compile(r"[.!?¿¡…\n]+")
_POSSESSIVES = frozenset(
    {"mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras"}
)
_COORDINATORS = frozenset({"y", "e", "ni", "o", "u"})
_URL_WORDS = frozenset({"www", "http", "https", "com", "net", "org"})
_DENIED = candidate_denied_words() | _POSSESSIVES | _URL_WORDS


def comparison_key(phrase: str) -> str:
    """Return the key two spoken phrases are compared by: folded, without a leading article.

    Args:
        phrase: A spoken object ("El Café").

    Returns:
        The folded words without leading articles ("cafe"); empty when nothing remains.
    """
    words = normalize_spanish(phrase).split()
    while words and words[0] in ARTICLES:
        words.pop(0)
    return " ".join(words)


def _shape_refusal(phrase: str, words: list[str]) -> CandidateReason | None:
    """Refuse an object that is not a short noun phrase of letters (the positive grammar)."""
    if not _MIN_CHARS <= len(phrase) <= settings.memory_candidate_value_max_chars:
        return CandidateReason.NOT_A_TASTE
    if _PHRASE.fullmatch(phrase) is None or _COORDINATORS & set(words):
        return CandidateReason.NOT_A_TASTE
    first = words[0]
    if first not in ARTICLES and _INFINITIVE.fullmatch(first) and first not in ALLOWED_INFINITIVES:
        return CandidateReason.NOT_A_TASTE
    return None


def _capitalized_inside_sentences(user_text: str) -> frozenset[str]:
    """Return the folded words the user wrote with a capital that do not open a sentence.

    Speech-to-text capitalizes names of people, places and brands; a taste in one of them
    ("me gusta Rodrigo", "me gusta Madrid") is a third party or a place, never a thing.
    """
    found: set[str] = set()
    for sentence in _SENTENCE_END.split(user_text):
        for word in _WORD.findall(sentence)[1:]:
            if word[0].isupper():
                found.add(normalize_spanish(word))
    return frozenset(found)


def _names_a_known_person(words: list[str], known_person_names: frozenset[str]) -> bool:
    """Return whether any word of the object is a word of a name the household knows."""
    name_words = {
        part for name in known_person_names for part in normalize_spanish(name).split() if part
    }
    return bool(name_words & set(words))


def _pair_refusal(
    actor: ActivePersonContext,
    definition: PredicateDefinition | None,
    topic: str,
    matches: tuple[GateMatch, ...],
) -> CandidateReason | None:
    """Refuse a triple whose subject, predicate or topic is not acceptable."""
    if actor.status is not ActivePersonStatus.IDENTIFIED or actor.person_id is None:
        return CandidateReason.DENIED
    if definition is None or definition.canonical_id not in {m.predicate for m in matches}:
        return CandidateReason.GATE_MISMATCH
    if topic not in CANDIDATE_TOPICS:
        return CandidateReason.SENSITIVE_TOPIC
    return None


def _phrase_refusal(
    phrase: str,
    words: list[str],
    predicate: str,
    user_text: str,
    matches: tuple[GateMatch, ...],
    known_person_names: frozenset[str],
) -> CandidateReason | None:
    """Refuse an object that is malformed, sensitive, a name or not grounded in its own trigger."""
    if not words:
        return CandidateReason.NOT_A_TASTE
    refusal = _shape_refusal(phrase, words)
    if refusal is not None:
        return refusal
    if (
        _DENIED & set(words)
        or _capitalized_inside_sentences(user_text) & set(words)
        or _names_a_known_person(words, known_person_names)
    ):
        return CandidateReason.SENSITIVE_TOPIC
    joined = f" {' '.join(words)} "
    # Grounded only after a trigger of the SAME predicate: the model never chooses the polarity,
    # and a taste somebody else voiced earlier in the text is not in this trigger's words.
    if not any(
        match.predicate == predicate and joined in f" {' '.join(match.words)} " for match in matches
    ):
        return CandidateReason.NOT_GROUNDED
    return None


def classify(
    actor: ActivePersonContext,
    raw: RawCandidate,
    user_text: str,
    *,
    matches: tuple[GateMatch, ...],
    known_person_names: frozenset[str],
) -> ProposedCandidate | CandidateReason:
    """Accept or drop one extracted pair.

    Args:
        actor: The identified actor; their id is the subject, whatever the model said.
        raw: The extractor's untrusted triple.
        user_text: What the user said this turn (never the assistant's reply).
        matches: The tastes the preference gate accepted, each with the words after its own
            trigger: the object must sit there, under the same predicate.
        known_person_names: Names of the people and pets the household knows (an argument,
            so this function stays pure).

    Returns:
        A ``ProposedCandidate`` that carries only the canonical predicate, the spoken phrase
        and its comparison key, or the closed reason it was dropped for.
    """
    definition = resolve_predicate(raw.predicate)
    refusal = _pair_refusal(actor, definition, raw.topic, matches)
    if refusal is not None or definition is None:
        return refusal or CandidateReason.GATE_MISMATCH
    phrase = " ".join(unicodedata.normalize("NFC", raw.object).split())
    words = normalize_spanish(phrase).split()
    refusal = _phrase_refusal(
        phrase, words, definition.canonical_id, user_text, matches, known_person_names
    )
    if refusal is not None:
        return refusal
    key = comparison_key(phrase)
    if not key:
        return CandidateReason.NOT_A_TASTE
    return ProposedCandidate(predicate=definition.canonical_id, value_text=phrase, value_key=key)
