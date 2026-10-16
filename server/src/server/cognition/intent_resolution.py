"""Pure typed Spanish intent resolution — P0-C5.

Classification lives here, not in the controller: a closed, deterministic
Spanish rule set with no LLM, VLM, embedding, fuzzy match, or database
access. This module never identifies a speaker or grants access — the
controller remains the sole owner of policy, tools, audit, and generation.
"""

from collections.abc import Callable
from enum import StrEnum
from itertools import pairwise
import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

from server.cognition.response_plan import InformationNeed

__all__ = [
    "IntentMatch",
    "IntentResolution",
    "MemoryAnswer",
    "parse_memory_answer",
    "resolve_information_need",
]


class IntentMatch(StrEnum):
    """How one Spanish message resolved to an information need."""

    EXACT = "exact"
    SUPERVISED_STT_ALIAS = "supervised_stt_alias"
    NONE = "none"


class IntentResolution(BaseModel):
    """Immutable outcome of resolving one message against the closed corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    need: InformationNeed
    match: IntentMatch
    rule_id: str | None


class MemoryAnswer(BaseModel):
    """A spoken answer to a memory offer: accept or reject, and the value it names.

    Attributes:
        accept: ``True`` for a verb that accepts («autorizo guardar …»), ``False`` for one that
            rejects («no autorizo guardar …», «olvídalo …»).
        phrase: The value the answer repeats, folded (lower case, no accents); the memory
            layer compares it with the offered candidate. Never logged.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    accept: bool
    phrase: str = Field(repr=False)  # a value: never printed by a stray ``%r``


_NON_WORD_RUN = re.compile(r"[^\w]+", re.UNICODE)

# The closed answer grammar (ADR 0021 decision 9): a closed verb **and** the value. It is closed
# on purpose, so a bare «sí» or a verb alone promotes nothing. The verbs are neutral Spanish
# (tuteo), not voseo.

# Words that may open an answer: a call to the robot, a repeated «sí», «claro».
_ANSWER_OPENERS = frozenset({"iroko", "oye", "bueno", "ok", "claro", "si"})
# Within each prefix tuple the order matters: the first match wins, so the longest verb comes
# first («autorizo guardar» before «autorizo»), or the shorter one would leave its tail in the value.
_ANSWER_ACCEPT_PREFIXES = (
    "autorizo que guardes",
    "apruebo que guardes",
    "autorizo a guardar",
    "apruebo a guardar",
    "autorizo guardar",
    "apruebo guardar",
    "guardalo",
    "guarda",
    "autorizo",
    "apruebo",
)
_ANSWER_REJECT_PREFIXES = (
    "no autorizo que guardes",
    "no apruebo que guardes",
    "no autorizo a guardar",
    "no apruebo a guardar",
    "no autorizo guardar",
    "no apruebo guardar",
    "no lo guardes",
    "no guardes",
    "no autorizo",
    "no apruebo",
    "olvidalo",
    "borralo",
)
# Short verbs that ordinary speech also uses («guarda silencio», «olvídalo, no importa», «bórralo
# todo»): after one of them the value must start with an article, as a spoken taste usually does.
_ANSWER_SHORT_PREFIXES = frozenset(
    {"guardalo", "guarda", "no lo guardes", "no guardes", "olvidalo", "borralo"}
)
# The articles a spoken taste may start with. The memory lexicon holds the same list
# (``lexicon.ARTICLES``); the cognitive core cannot import ``server.memory`` (import-graph
# guard), so a unit test pins both lists together.
_ANSWER_ARTICLES = frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"})
# Courtesy words a speaker adds after the value; they are not part of it.
_ANSWER_TRAILERS = ("por favor", "gracias", "porfa")
# The value is a short noun phrase: at most six words, its article included when it has one.
_MAX_ANSWER_PHRASE_WORDS = 6
# Words that continue the verb rather than start the value («autorizo guardar», «que guardes»).
_ANSWER_CONNECTORS = frozenset({"guardar", "que"})

_POSSESSIVES = frozenset(
    {"mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras"}
)
# Words that name the household on their own, plural forms included.
_HOUSEHOLD_WORDS = frozenset(
    {
        "hijo",
        "hija",
        "hijos",
        "hijas",
        "familia",
        "familias",
        "familiares",
        "preferencia",
        "preferencias",
        "padre",
        "madre",
        "padres",
        "madres",
        "hermano",
        "hermana",
        "hermanos",
        "hermanas",
        "abuelo",
        "abuela",
        "abuelos",
        "abuelas",
        "esposo",
        "esposa",
        "esposos",
        "esposas",
        "marido",
        "maridos",
        "mama",
        "mamas",
        "tio",
        "tia",
        "tios",
        "tias",
        "primo",
        "prima",
        "primos",
        "primas",
    }
)
# Words that mean a relative only with a possessive ("mi mujer") and mean something
# else alone ("papas fritas", "las mujeres astronautas", "la primavera").
_HOUSEHOLD_WORDS_NEEDING_POSSESSIVE = frozenset(
    {
        "nino",
        "nina",
        "ninos",
        "ninas",
        "papa",
        "papas",
        "pareja",
        "parejas",
        "mujer",
        "mujeres",
    }
)
_HOUSEHOLD_PHRASES = ("le gusta", "les gusta")
_BIRTH_WORDS = frozenset({"nacio", "nacimiento", "nacimientos"})
_AGE_WORDS = frozenset({"edad", "edades", "anos"})
_RELATIONSHIP_WORDS = frozenset({"relacion", "relaciones"})
_OWN_CHILDREN_LIST_PATTERNS = ("como se llaman mis hijos", "quienes son mis hijos")
_OWN_CHILDREN_COUNT_PATTERNS = ("cuantos hijos tengo",)
_CURRENT_DATE_PATTERNS = (
    "que dia es hoy",
    "dime la fecha actual",
    "en que fecha estamos",
)
_CURRENT_DATE_STT_ALIASES = frozenset({"me dice la fecha actual"})
_AMBIGUOUS_DATE_ALIASES = frozenset({"que dia soy", "que via es hoy"})
_BIOMETRIC_ENROLLMENT_PATTERNS = (
    "aprende mi cara",
    "aprende su cara",
    "aprende la cara",
    "recuerda mi cara",
    "recuerda su cara",
    "recuerda la cara",
    "memoriza mi cara",
    "memoriza su cara",
    "memoriza la cara",
    "mirame bien",
    "mirala bien",
    "miralo bien",
    "conoce a",
)
_ACTIVE_IDENTITY_PATTERNS = (
    "quien soy",
    "me reconoces",
    "me conoces",
    "sabes quien soy",
    "quien esta aqui",
    "quien esta frente",
)
_SCENE_DESCRIPTION_PATTERNS = (
    "que ves",
    "que estas viendo",
    "que miras",
    "que observas",
    "mira esto",
    "mira lo que",
    "puedes ver",
    "podes ver",
    "ves esto",
    "ves algo",
    "que tengo en la mano",
    "describe lo que ves",
    "dime que ves",
    "decime que ves",
)


def resolve_information_need(message: str) -> IntentResolution:
    """Resolve one bounded information need from reviewed Spanish rules.

    Args:
        message: Raw transcript or chat text in Spanish.

    Returns:
        The closed, deterministic resolution — need, match kind, and a
        privacy-safe rule identifier (``None`` only for generic conversation).
    """
    normalized = normalize_spanish(message)
    for rule in _RULES:
        resolution = rule(normalized)
        if resolution is not None:
            return resolution
    return _resolution(InformationNeed.GENERIC_CONVERSATION, IntentMatch.NONE, None)


def _resolution(need: InformationNeed, match: IntentMatch, rule_id: str | None) -> IntentResolution:
    """Build one immutable resolution from its three closed fields."""
    return IntentResolution(need=need, match=match, rule_id=rule_id)


def _own_children_list_rule(normalized: str) -> IntentResolution | None:
    """Recognize only the two reviewed self-child-list phrasings."""
    if any(_contains_word_phrase(normalized, pattern) for pattern in _OWN_CHILDREN_LIST_PATTERNS):
        return _resolution(
            InformationNeed.OWN_CHILDREN_LIST, IntentMatch.EXACT, "own_children.list.v1"
        )
    return None


def _own_children_count_rule(normalized: str) -> IntentResolution | None:
    """Recognize the reviewed self-child-count phrasing."""
    if any(_contains_word_phrase(normalized, pattern) for pattern in _OWN_CHILDREN_COUNT_PATTERNS):
        return _resolution(
            InformationNeed.OWN_CHILDREN_COUNT, IntentMatch.EXACT, "own_children.count.v1"
        )
    return None


def _names_a_relative(words: list[str]) -> bool:
    """Whether the message names the household, whole words only.

    A kin word that is ambiguous alone counts only right after a possessive, so
    "mi mujer" is protected and "las mujeres astronautas" is not.
    """
    if any(word in _HOUSEHOLD_WORDS for word in words):
        return True
    return any(
        word in _HOUSEHOLD_WORDS_NEEDING_POSSESSIVE and previous in _POSSESSIVES
        for previous, word in pairwise(words)
    )


def _protected_household_rule(normalized: str) -> IntentResolution | None:
    """Recognize a protected household, family-relation, or birth request."""
    words = normalized.split()
    if _names_a_relative(words) or any(
        _contains_word_phrase(normalized, phrase) for phrase in _HOUSEHOLD_PHRASES
    ):
        return _resolution(
            InformationNeed.PROTECTED_HOUSEHOLD, IntentMatch.EXACT, _protected_rule_id(words)
        )
    if any(word in _BIRTH_WORDS for word in words):
        return _resolution(
            InformationNeed.PROTECTED_HOUSEHOLD, IntentMatch.EXACT, "birth.protected.v1"
        )
    return None


def _protected_rule_id(words: list[str]) -> str:
    """Distinguish a birth-specific protected request from a general one."""
    if any(word in _BIRTH_WORDS for word in words):
        return "birth.protected.v1"
    return "household.protected.v1"


def _contains_word_phrase(normalized: str, pattern: str) -> bool:
    """Match *pattern* only as whole space-delimited words, never mid-word.

    Plain substring checks would let "que ves" false-hit inside "aunque
    vestirse" (the "que ves" letters span the word boundary). Padding both
    sides with a single space reproduces the old regex ``\\b...\\b``
    guarantee cheaply, since `normalize_spanish` already collapses every non-word
    run to exactly one space.
    """
    return f" {pattern} " in f" {normalized} "


def _biometric_enrollment_rule(normalized: str) -> IntentResolution | None:
    """Recognize an unequivocal face-learning cue, with or without a name."""
    if any(
        _contains_word_phrase(normalized, pattern) for pattern in _BIOMETRIC_ENROLLMENT_PATTERNS
    ):
        return _resolution(
            InformationNeed.BIOMETRIC_ENROLLMENT, IntentMatch.EXACT, "enrollment.biometric.v1"
        )
    return None


def _active_identity_rule(normalized: str) -> IntentResolution | None:
    """Recognize a request to confirm who the current speaker is."""
    if any(_contains_word_phrase(normalized, pattern) for pattern in _ACTIVE_IDENTITY_PATTERNS):
        return _resolution(InformationNeed.ACTIVE_IDENTITY, IntentMatch.EXACT, "identity.active.v1")
    return None


def _scene_description_rule(normalized: str) -> IntentResolution | None:
    """Recognize a request to describe the current camera scene."""
    if any(_contains_word_phrase(normalized, pattern) for pattern in _SCENE_DESCRIPTION_PATTERNS):
        return _resolution(
            InformationNeed.SCENE_DESCRIPTION, IntentMatch.EXACT, "scene.description.v1"
        )
    return None


def _ambiguous_date_alias_rule(normalized: str) -> IntentResolution | None:
    """Recognize a supervised STT corruption of a date question."""
    if normalized in _AMBIGUOUS_DATE_ALIASES:
        return _resolution(
            InformationNeed.AMBIGUOUS_DATE_QUERY,
            IntentMatch.SUPERVISED_STT_ALIAS,
            "date.ambiguous.stt.v1",
        )
    return None


def _current_date_stt_alias_rule(normalized: str) -> IntentResolution | None:
    """Recognize a supervised STT corruption of a current-date request."""
    if normalized in _CURRENT_DATE_STT_ALIASES:
        return _resolution(
            InformationNeed.CURRENT_DATE, IntentMatch.SUPERVISED_STT_ALIAS, "date.current.stt.v1"
        )
    return None


def _current_date_rule(normalized: str) -> IntentResolution | None:
    """Recognize the reviewed unambiguous current-date phrasings."""
    words = normalized.split()
    matches = ("fecha" in words and "hoy" in words) or any(
        _contains_word_phrase(normalized, pattern) for pattern in _CURRENT_DATE_PATTERNS
    )
    if matches:
        return _resolution(InformationNeed.CURRENT_DATE, IntentMatch.EXACT, "date.current.v1")
    return None


def _explicit_age_rule(normalized: str) -> IntentResolution | None:
    """Recognize an explicit self-age request by its ISO-strict controller tool."""
    if any(word in _AGE_WORDS for word in normalized.split()):
        return _resolution(
            InformationNeed.EXPLICIT_BIRTH_DATE_AGE, IntentMatch.EXACT, "age.explicit.v1"
        )
    return None


def _relationship_rule(normalized: str) -> IntentResolution | None:
    """Recognize a generic relationship/profile question."""
    if any(word in _RELATIONSHIP_WORDS for word in normalized.split()):
        return _resolution(
            InformationNeed.RELATIONSHIP_OR_PROFILE, IntentMatch.EXACT, "relationship.profile.v1"
        )
    return None


def parse_memory_answer(message: str) -> MemoryAnswer | None:
    """Read a spoken answer to a memory offer, or say that *message* is not one.

    Pure and closed (ADR 0021 decision 9): optional openers («Iroko», «sí, claro»), then one
    closed verb, then the value, then optional courtesy words. A rejection starts with «no»,
    «olvídalo» or «bórralo», never with an accepting verb, so the two sets never compete; a
    repeated «no, no» is one «no».

    Args:
        message: Raw transcript or chat text in Spanish.

    Returns:
        The answer and the folded value it repeats, or ``None`` when the message has no closed
        verb, a verb alone with no value, a value longer than a short noun phrase, a value that
        starts with «guardar» or «que», or a short verb without an article («guarda silencio»).
    """
    words = normalize_spanish(message).split()
    while words and words[0] in _ANSWER_OPENERS:
        words.pop(0)
    while words[:2] == ["no", "no"]:
        words.pop(0)
    text = _without_trailers(" ".join(words))
    for prefixes, accept in ((_ANSWER_REJECT_PREFIXES, False), (_ANSWER_ACCEPT_PREFIXES, True)):
        for prefix in prefixes:
            if text.startswith(f"{prefix} "):
                return _answer(prefix, text[len(prefix) :].split(), accept=accept)
    return None


def _without_trailers(text: str) -> str:
    """Drop the courtesy words a speaker adds after the value («…, gracias»)."""
    trimmed = True
    while trimmed:
        trimmed = False
        for trailer in _ANSWER_TRAILERS:
            if text.endswith(f" {trailer}"):
                text = text[: -len(trailer) - 1]
                trimmed = True
    return text


def _answer(prefix: str, phrase: list[str], *, accept: bool) -> MemoryAnswer | None:
    """Return the answer when *phrase* is a value, or ``None``."""
    # «autorizo a guardar» with nothing after it does not match its own prefix (no trailing
    # space) and falls to the shorter «autorizo», leaving «a guardar» as the "value": that is a
    # verb, not a value. «autorizo a guardar el mate» matches the long prefix and names it.
    if phrase[:2] == ["a", "guardar"]:
        phrase = phrase[2:]
    if not phrase or phrase[0] in _ANSWER_CONNECTORS or len(phrase) > _MAX_ANSWER_PHRASE_WORDS:
        return None
    if prefix in _ANSWER_SHORT_PREFIXES and phrase[0] not in _ANSWER_ARTICLES:
        return None
    return MemoryAnswer(accept=accept, phrase=" ".join(phrase))


def _memory_answer_rule(normalized: str) -> IntentResolution | None:
    """Recognize the closed shape of an answer to a memory offer (value included)."""
    if parse_memory_answer(normalized) is not None:
        return _resolution(InformationNeed.MEMORY_ANSWER, IntentMatch.EXACT, "memory.answer.v1")
    return None


# Order matters: the answer shape is the last rule, so a message that also matches a protected,
# dated or identity rule is classified by that rule and never treated as an answer.
_RULES: tuple[Callable[[str], IntentResolution | None], ...] = (
    _own_children_list_rule,
    _own_children_count_rule,
    _protected_household_rule,
    _biometric_enrollment_rule,
    _active_identity_rule,
    _ambiguous_date_alias_rule,
    _current_date_stt_alias_rule,
    _current_date_rule,
    _explicit_age_rule,
    _relationship_rule,
    _scene_description_rule,
    _memory_answer_rule,
)


def normalize_spanish(message: str) -> str:
    """Fold accents/case and collapse punctuation for closed Spanish matching.

    NFD-decomposes, strips combining accents, casefolds, replaces each
    non-word run with one space, then trims — so surrounding punctuation and
    inconsistent whitespace never affect classification. Public because the
    memory layer's closed grammars (ADR 0021) fold text the same way; it is the one
    folding function they share rather than another copy.

    Args:
        message: Raw transcript or chat text.

    Returns:
        The folded text: lower case, no accents, words separated by single spaces.
    """
    decomposed = unicodedata.normalize("NFD", message)
    stripped = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()
    return _NON_WORD_RUN.sub(" ", stripped).strip()
