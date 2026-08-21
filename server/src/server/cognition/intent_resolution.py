"""Pure typed Spanish intent resolution — P0-C5.

Classification lives here, not in the controller: a closed, deterministic
Spanish rule set with no LLM, VLM, embedding, fuzzy match, or database
access. This module never identifies a speaker or grants access — the
controller remains the sole owner of policy, tools, audit, and generation.
"""

from collections.abc import Callable
from enum import StrEnum
import re
import unicodedata

from pydantic import BaseModel, ConfigDict

from server.cognition.response_plan import InformationNeed

__all__ = ["IntentMatch", "IntentResolution", "resolve_information_need"]


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


_NON_WORD_RUN = re.compile(r"[^\w]+", re.UNICODE)

_PRIVATE_HOUSEHOLD_TERMS = (
    "hijo",
    "hija",
    "nino",
    "nina",
    "familia",
    "preferencia",
    "le gusta",
    "padre",
    "madre",
    "papa",
    "mama",
    "hermano",
    "pareja",
    "esposa",
    "esposo",
    "marido",
    "mujer",
    "abuelo",
    "abuela",
    "tio",
    "tia",
    "primo",
    "prima",
)
_BIRTH_INFORMATION_TERMS = ("nacio", "nacimiento")
_RELATIONSHIP_TERMS = ("relacion",)
_OWN_CHILDREN_LIST_PATTERNS = ("como se llaman mis hijos", "quienes son mis hijos")
_OWN_CHILDREN_COUNT_PATTERNS = ("cuantos hijos tengo",)
_CURRENT_DATE_PATTERNS = (
    "que dia es hoy",
    "dime la fecha actual",
    "en que fecha estamos",
)
_CURRENT_DATE_STT_ALIASES = frozenset({"me dice la fecha actual"})
_AMBIGUOUS_DATE_ALIASES = frozenset({"que dia soy", "que via es hoy"})


def resolve_information_need(message: str) -> IntentResolution:
    """Resolve one bounded information need from reviewed Spanish rules.

    Args:
        message: Raw transcript or chat text in Spanish.

    Returns:
        The closed, deterministic resolution — need, match kind, and a
        privacy-safe rule identifier (``None`` only for generic conversation).
    """
    normalized = _normalize(message)
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
    if any(pattern in normalized for pattern in _OWN_CHILDREN_LIST_PATTERNS):
        return _resolution(
            InformationNeed.OWN_CHILDREN_LIST, IntentMatch.EXACT, "own_children.list.v1"
        )
    return None


def _own_children_count_rule(normalized: str) -> IntentResolution | None:
    """Recognize the reviewed self-child-count phrasing."""
    if any(pattern in normalized for pattern in _OWN_CHILDREN_COUNT_PATTERNS):
        return _resolution(
            InformationNeed.OWN_CHILDREN_COUNT, IntentMatch.EXACT, "own_children.count.v1"
        )
    return None


def _protected_household_rule(normalized: str) -> IntentResolution | None:
    """Recognize any protected household, family-relation, or birth term."""
    if any(term in normalized for term in (*_PRIVATE_HOUSEHOLD_TERMS, *_BIRTH_INFORMATION_TERMS)):
        return _resolution(
            InformationNeed.PROTECTED_HOUSEHOLD, IntentMatch.EXACT, _protected_rule_id(normalized)
        )
    return None


def _protected_rule_id(normalized: str) -> str:
    """Distinguish a birth-specific protected request from a general one."""
    if any(term in normalized for term in _BIRTH_INFORMATION_TERMS):
        return "birth.protected.v1"
    return "household.protected.v1"


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
    matches = ("fecha" in normalized and "hoy" in normalized) or any(
        pattern in normalized for pattern in _CURRENT_DATE_PATTERNS
    )
    if matches:
        return _resolution(InformationNeed.CURRENT_DATE, IntentMatch.EXACT, "date.current.v1")
    return None


def _explicit_age_rule(normalized: str) -> IntentResolution | None:
    """Recognize an explicit self-age request by its ISO-strict controller tool."""
    if "edad" in normalized or "anos" in normalized:
        return _resolution(
            InformationNeed.EXPLICIT_BIRTH_DATE_AGE, IntentMatch.EXACT, "age.explicit.v1"
        )
    return None


def _relationship_rule(normalized: str) -> IntentResolution | None:
    """Recognize a generic relationship/profile question."""
    if any(term in normalized for term in _RELATIONSHIP_TERMS):
        return _resolution(
            InformationNeed.RELATIONSHIP_OR_PROFILE, IntentMatch.EXACT, "relationship.profile.v1"
        )
    return None


_RULES: tuple[Callable[[str], IntentResolution | None], ...] = (
    _own_children_list_rule,
    _own_children_count_rule,
    _protected_household_rule,
    _ambiguous_date_alias_rule,
    _current_date_stt_alias_rule,
    _current_date_rule,
    _explicit_age_rule,
    _relationship_rule,
)


def _normalize(message: str) -> str:
    """Fold accents/case and collapse punctuation for closed Spanish matching.

    NFD-decomposes, strips combining accents, casefolds, replaces each
    non-word run with one space, then trims — so surrounding punctuation and
    inconsistent whitespace never affect classification.
    """
    decomposed = unicodedata.normalize("NFD", message)
    stripped = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()
    return _NON_WORD_RUN.sub(" ", stripped).strip()
