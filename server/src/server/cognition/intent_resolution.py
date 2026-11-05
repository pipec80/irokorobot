"""Pure typed Spanish intent resolution — P0-C5.

Classification lives here, not in the controller: a closed, deterministic
Spanish rule set with no LLM, VLM, embedding, fuzzy match, or database
access. This module never identifies a speaker or grants access — the
controller remains the sole owner of policy, tools, audit, and generation.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from functools import cache
import re

from pydantic import BaseModel, ConfigDict, Field

from server.cognition.household_request import (
    BIRTH_WORDS,
    has_question_mark,
    mentions_the_household,
    opens_with,
    requests_household_data,
    states_a_request,
)
from server.cognition.recall_cues import CueStrength, classify_recall_cue, relation_of
from server.cognition.response_plan import InformationNeed
from server.cognition.sensitive_questions import classify_sensitive_question
from server.secret_values import SecretKind, secret_kind
from server.text_keys import normalize_spanish

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
            layer compares it with the offered candidate. Never logged. ``phrase == ""`` means
            the open offer: the answer is a closed verb alone (Plan 0066) and names no value.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    accept: bool
    phrase: str = Field(repr=False)  # a value: never printed by a stray ``%r``


# The closed answer grammar (ADR 0021 decision 9, Plan 0066): a closed verb, with or without the
# value. It is closed on purpose, so a bare «sí» promotes nothing. A long verb («autorizo»,
# «apruebo», «autoriza», «aprueba») stands alone; the short ones are ordinary speech and need a
# cue: «guarda»/«guárdalo» a leading «sí», «olvídalo»/«bórralo» the value, while «no lo guardes»
# and «no guardes» carry their own «no». The verbs are neutral Spanish (tuteo), not voseo. It
# also admits what the speech-to-text writes for those verbs (Plan 0064, D-3): the third person
# («autoriza», «aprueba»), the openers «ya», «dale» and «po», a trailing «po», and a leading
# «mi»/«mis» before the value.
#
# Plan 0067, D-5 (Pipec: «lo más común es "sí acepto", "sí, guárdala"»): «acepto»/«acepta» are
# long verbs like «autorizo» (also with «guardar», «a guardar», «que guardes»; «no acepto» rejects),
# «guárdala» is a short verb like «guárdalo», and after a long verb «guárdalo», «guárdala» and «sí»
# are courtesy words, not a value («sí, autorizo, guárdalo»). A bare «sí» or «guárdala» still
# resolves nothing.

# Words that may open an answer: a call to the robot, a repeated «sí», «claro», «ya», «po».
_ANSWER_OPENERS = frozenset({"iroko", "oye", "bueno", "ok", "claro", "si", "ya", "dale", "po"})
# Within each prefix tuple the order matters: the first match wins, so the longest verb comes
# first («autorizo guardar» before «autorizo»), or the shorter one would leave its tail in the value.
# Plan 0068, D-1: «que lo guardes» / «que la guardes» follow every long verb, because the retry
# phrase dictates «sí, autorizo que lo guardes» and the answer it asks for must parse.
_ANSWER_ACCEPT_PREFIXES = (
    "autorizo que lo guardes",
    "autorizo que la guardes",
    "apruebo que lo guardes",
    "apruebo que la guardes",
    "autoriza que lo guardes",
    "autoriza que la guardes",
    "aprueba que lo guardes",
    "aprueba que la guardes",
    "acepto que lo guardes",
    "acepto que la guardes",
    "acepta que lo guardes",
    "acepta que la guardes",
    "autorizo que guardes",
    "apruebo que guardes",
    "autoriza que guardes",
    "aprueba que guardes",
    "acepto que guardes",
    "acepta que guardes",
    "autorizo a guardar",
    "apruebo a guardar",
    "autoriza a guardar",
    "aprueba a guardar",
    "acepto a guardar",
    "acepta a guardar",
    "autorizo guardar",
    "apruebo guardar",
    "autoriza guardar",
    "aprueba guardar",
    "acepto guardar",
    "acepta guardar",
    "guardalo",
    "guardala",
    "guarda",
    "autorizo",
    "apruebo",
    "autoriza",
    "aprueba",
    "acepto",
    "acepta",
)
_ANSWER_REJECT_PREFIXES = (
    "no autorizo que lo guardes",
    "no autorizo que la guardes",
    "no apruebo que lo guardes",
    "no apruebo que la guardes",
    "no autoriza que lo guardes",
    "no autoriza que la guardes",
    "no aprueba que lo guardes",
    "no aprueba que la guardes",
    "no acepto que lo guardes",
    "no acepto que la guardes",
    "no acepta que lo guardes",
    "no acepta que la guardes",
    "no autorizo que guardes",
    "no apruebo que guardes",
    "no autoriza que guardes",
    "no aprueba que guardes",
    "no acepto que guardes",
    "no acepta que guardes",
    "no autorizo a guardar",
    "no apruebo a guardar",
    "no autoriza a guardar",
    "no aprueba a guardar",
    "no acepto a guardar",
    "no acepta a guardar",
    "no autorizo guardar",
    "no apruebo guardar",
    "no autoriza guardar",
    "no aprueba guardar",
    "no acepto guardar",
    "no acepta guardar",
    "no lo guardes",
    "no guardes",
    "no autorizo",
    "no apruebo",
    "no autoriza",
    "no aprueba",
    "no acepto",
    "no acepta",
    "olvidalo",
    "borralo",
)
# Short verbs that ordinary speech also uses («guarda silencio», «olvídalo, no importa», «bórralo
# todo»): after one of them the value must start with an article, as a spoken taste usually does.
_ANSWER_SHORT_PREFIXES = frozenset(
    {"guardalo", "guardala", "guarda", "no lo guardes", "no guardes", "olvidalo", "borralo"}
)
# The short verbs that may also stand alone (Plan 0066, D-2 and D-3): the accepting ones only
# after a leading «sí», the rejecting ones always because they carry their own «no».
_ANSWER_SHORT_ALONE_AFTER_YES = frozenset({"guardalo", "guardala", "guarda"})
_ANSWER_SHORT_ALONE = frozenset({"no lo guardes", "no guardes"})
# The folded «sí» among the openers: it marks the intent of a short accepting verb.
_ANSWER_YES = "si"
# The articles a spoken taste may start with. The memory lexicon holds the same list
# (``lexicon.ARTICLES``); the cognitive core cannot import ``server.memory`` (import-graph
# guard), so a unit test pins both lists together.
_ANSWER_ARTICLES = frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"})
# Courtesy words a speaker adds after the value; they are not part of it.
_ANSWER_TRAILERS = ("por favor", "gracias", "porfa", "po")
# Emphatic words a speaker adds after a LONG verb («autorizo, guárdalo», «autorizo, sí»; Plan 0067,
# D-5). They are dropped from the end of the value only for a long verb: after a short one
# «guarda, sí» stays refused, because there the word would be taken as the value.
_ANSWER_LONG_VERB_TRAILERS = frozenset(
    {"guardalo", "guardala", "si", "claro", "autorizo", "autoriza", "apruebo", "aprueba"}
    | {"acepto", "acepta"}
)
# The same emphasis may also open the value («autorizo, sí, el mate»).
_ANSWER_LONG_VERB_LEADERS = frozenset({"si", "claro"})
# «mi café»: the possessive is dropped from the value and counts as the article of a short verb.
_ANSWER_POSSESSIVES = frozenset({"mi", "mis"})
# The value is a short noun phrase: at most six words, its article included when it has one.
_MAX_ANSWER_PHRASE_WORDS = 6
# Words that continue the verb rather than start the value («autorizo guardar», «que guardes»).
_ANSWER_CONNECTORS = frozenset({"guardar", "que"})
# «a guardar», «a guardarlo», «a guardarla»: the verb's infinitive after «a», never a value.
_ANSWER_SAVE_PRONOUN_FORMS = frozenset({"guardarlo", "guardarla"})
_ANSWER_SAVE_FORMS = frozenset({"guardar"}) | _ANSWER_SAVE_PRONOUN_FORMS

_AGE_WORDS = frozenset({"edad", "edades", "anos"})
# One's own age. «Hace dos años fui…» and «a mi edad…» are conversation (Plan 0077).
_OWN_AGE_PATTERNS = ("que edad tengo", "cuantos anos tengo", "edad que tengo")
_OWN_AGE_REQUEST = "mi edad"
_ISO_DATE_WORDS = re.compile(r"\b\d{4} \d{2} \d{2}\b")
_RELATIONSHIP_WORDS = frozenset({"relacion", "relaciones"})
# The closed question. «¿Cuál es la relación entre la luna y las mareas?» is conversation.
_RELATIONSHIP_PATTERNS = (
    "que relacion existe",
    "que relacion hay",
    "que relacion tengo",
    "que relacion tenemos",
    "cual es mi relacion",
    "cual es nuestra relacion",
)
_OWN_CHILDREN_LIST_PATTERNS = ("como se llaman mis hijos", "quienes son mis hijos")
_OWN_CHILDREN_COUNT_PATTERNS = ("cuantos hijos tengo",)
_OWN_CHILD_NAME_PATTERNS = (
    "como se llama mi hija",
    "como se llama mi hijo",
    "quien es mi hija",
    "quien es mi hijo",
)
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
)
# Only as the opening words: «Mi mamá conoce a todos» is a story, not an enrolment (Plan 0077).
_BIOMETRIC_OPENING_PATTERN = "conoce a"
_ACTIVE_IDENTITY_PATTERNS = (
    "quien soy",
    "me reconoces",
    "me conoces",
    "sabes quien soy",
    "quien esta aqui",
    "quien esta frente",
)
# «¿Qué sabes de mí?» and its neighbours (Plan 0074). The message must END with the phrase, so
# «¿qué sabes de mi perro?» (a taste or a pet, not the profile) is not captured.
# «sabe» is what the speech-to-text wrote for «sabes» on Pipec's hardware run of 2026-10-28.
_PROFILE_SUMMARY_PATTERNS = (
    "que sabes de mi",
    "que sabes sobre mi",
    "que sabe de mi",
    "que sabe sobre mi",
    "que te he contado",
    "que te conte",
    "que recuerdas de mi",
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


@dataclass(frozen=True)
class _Utterance:
    """One message as the rules read it.

    Attributes:
        message: The raw text, which keeps the marks and the sentences.
        normalized: The folded text; every closed pattern matches on it.
    """

    message: str
    normalized: str


def resolve_information_need(
    message: str, *, recall: bool = False, sensitive: bool = False, secrets: bool = False
) -> IntentResolution:
    """Resolve one bounded information need from reviewed Spanish rules.

    Args:
        message: Raw transcript or chat text in Spanish.
        recall: Whether the recall and relatives rules run (Plan 0078). Off, every message
            resolves exactly as before them.
        sensitive: Whether the owner's sensitive questions resolve to ``SENSITIVE_READ``
            (Plan 0079): the sensitive reader is wired.
        secrets: Whether a secret value, stated or asked for, resolves to ``SECRET_VALUE``
            (Plan 0079): the secret guard is on.

    Returns:
        The closed, deterministic resolution — need, match kind, and a
        privacy-safe rule identifier (``None`` only for generic conversation).
    """
    utterance = _Utterance(message=message, normalized=normalize_spanish(message))
    for rule in _rules_for(recall, sensitive, secrets):
        resolution = rule(utterance)
        if resolution is not None:
            return resolution
    return _resolution(InformationNeed.GENERIC_CONVERSATION, IntentMatch.NONE, None)


def _resolution(need: InformationNeed, match: IntentMatch, rule_id: str | None) -> IntentResolution:
    """Build one immutable resolution from its three closed fields."""
    return IntentResolution(need=need, match=match, rule_id=rule_id)


def _own_children_list_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize only the two reviewed self-child-list phrasings."""
    normalized = utterance.normalized
    if any(_contains_word_phrase(normalized, pattern) for pattern in _OWN_CHILDREN_LIST_PATTERNS):
        return _resolution(
            InformationNeed.OWN_CHILDREN_LIST, IntentMatch.EXACT, "own_children.list.v1"
        )
    return None


def _own_children_count_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize the reviewed self-child-count phrasing."""
    normalized = utterance.normalized
    if any(_contains_word_phrase(normalized, pattern) for pattern in _OWN_CHILDREN_COUNT_PATTERNS):
        return _resolution(
            InformationNeed.OWN_CHILDREN_COUNT, IntentMatch.EXACT, "own_children.count.v1"
        )
    return None


def _own_child_name_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize the singular «¿cómo se llama mi hija?», answered by the children list.

    Pipec's amendment to Plan 0078 (2026-11-03), with recall on only. The alta does not tell a
    daughter from a son, so the list answers it, as the parents' question names both parents.
    """
    if any(
        _contains_word_phrase(utterance.normalized, pattern) for pattern in _OWN_CHILD_NAME_PATTERNS
    ):
        return _resolution(
            InformationNeed.OWN_CHILDREN_LIST, IntentMatch.EXACT, "own_children.name.v1"
        )
    return None


def _relatives_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a question about the name of a relative or a pet loaded at the alta."""
    if relation_of(utterance.message) is None:
        return None
    return _resolution(InformationNeed.RELATIVES_NAMES, IntentMatch.EXACT, "relatives.names.v1")


def _recall_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a recall question (ADR 0028 decision 4).

    A weak cue about household data («¿te acuerdas qué comen mis hijos?») keeps the protected
    route: only a strong cue about what the owner told goes to the diary before it. The date
    only tells whether a window remains, so the machine's day is enough here.
    """
    cue = classify_recall_cue(utterance.message, today=date.today())
    if cue is None:
        return None
    if cue.strength is CueStrength.WEAK and requests_household_data(utterance.message):
        return None
    return _resolution(InformationNeed.RECALL, IntentMatch.EXACT, f"recall.{cue.strength}.v1")


def _protected_household_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a request for household data, or a family value shaped as a memory answer.

    An answer-shaped message keeps the broad test on purpose: «sí, autorizo guardar a mi hijo»
    never reaches the answer grammar, whatever its form (ADR 0021 decision 9).
    """
    normalized = utterance.normalized
    protected = (
        mentions_the_household(normalized)
        if parse_memory_answer(normalized) is not None
        else requests_household_data(utterance.message)
    )
    if not protected:
        return None
    return _resolution(
        InformationNeed.PROTECTED_HOUSEHOLD,
        IntentMatch.EXACT,
        _protected_rule_id(normalized.split()),
    )


def _protected_rule_id(words: list[str]) -> str:
    """Distinguish a birth-specific protected request from a general one."""
    if any(word in BIRTH_WORDS for word in words):
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


def _biometric_enrollment_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize an unequivocal face-learning cue, with or without a name."""
    normalized = utterance.normalized
    if opens_with(normalized, _BIOMETRIC_OPENING_PATTERN) or any(
        _contains_word_phrase(normalized, pattern) for pattern in _BIOMETRIC_ENROLLMENT_PATTERNS
    ):
        return _resolution(
            InformationNeed.BIOMETRIC_ENROLLMENT, IntentMatch.EXACT, "enrollment.biometric.v1"
        )
    return None


def _active_identity_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a request to confirm who the current speaker is."""
    normalized = utterance.normalized
    if any(_contains_word_phrase(normalized, pattern) for pattern in _ACTIVE_IDENTITY_PATTERNS):
        return _resolution(InformationNeed.ACTIVE_IDENTITY, IntentMatch.EXACT, "identity.active.v1")
    return None


def _profile_summary_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a request to read back what the robot holds about the speaker."""
    normalized = utterance.normalized
    if any(
        normalized == pattern or normalized.endswith(f" {pattern}")
        for pattern in _PROFILE_SUMMARY_PATTERNS
    ):
        return _resolution(InformationNeed.PROFILE_SUMMARY, IntentMatch.EXACT, "profile.summary.v1")
    return None


def _scene_description_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a request to describe the current camera scene."""
    normalized = utterance.normalized
    if any(_contains_word_phrase(normalized, pattern) for pattern in _SCENE_DESCRIPTION_PATTERNS):
        return _resolution(
            InformationNeed.SCENE_DESCRIPTION, IntentMatch.EXACT, "scene.description.v1"
        )
    return None


def _ambiguous_date_alias_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a supervised STT corruption of a date question."""
    normalized = utterance.normalized
    if normalized in _AMBIGUOUS_DATE_ALIASES:
        return _resolution(
            InformationNeed.AMBIGUOUS_DATE_QUERY,
            IntentMatch.SUPERVISED_STT_ALIAS,
            "date.ambiguous.stt.v1",
        )
    return None


def _current_date_stt_alias_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a supervised STT corruption of a current-date request."""
    normalized = utterance.normalized
    if normalized in _CURRENT_DATE_STT_ALIASES:
        return _resolution(
            InformationNeed.CURRENT_DATE, IntentMatch.SUPERVISED_STT_ALIAS, "date.current.stt.v1"
        )
    return None


def _current_date_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize the reviewed unambiguous current-date phrasings."""
    normalized = utterance.normalized
    words = normalized.split()
    matches = ("fecha" in words and "hoy" in words) or any(
        _contains_word_phrase(normalized, pattern) for pattern in _CURRENT_DATE_PATTERNS
    )
    if matches:
        return _resolution(InformationNeed.CURRENT_DATE, IntentMatch.EXACT, "date.current.v1")
    return None


def _explicit_age_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize one's own age, or an age with a strict date; a story about years is not one."""
    normalized = utterance.normalized
    if not any(word in _AGE_WORDS for word in normalized.split()):
        return None
    asked = (
        any(_contains_word_phrase(normalized, pattern) for pattern in _OWN_AGE_PATTERNS)
        or _ISO_DATE_WORDS.search(normalized) is not None
        or (
            _contains_word_phrase(normalized, _OWN_AGE_REQUEST)
            and states_a_request(normalized, marked=has_question_mark(utterance.message))
        )
        or parse_memory_answer(normalized) is not None
    )
    if asked:
        return _resolution(
            InformationNeed.EXPLICIT_BIRTH_DATE_AGE, IntentMatch.EXACT, "age.explicit.v1"
        )
    return None


def _relationship_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize the closed relationship question, not any sentence with the word."""
    normalized = utterance.normalized
    if not any(word in _RELATIONSHIP_WORDS for word in normalized.split()):
        return None
    if parse_memory_answer(normalized) is not None or any(
        _contains_word_phrase(normalized, pattern) for pattern in _RELATIONSHIP_PATTERNS
    ):
        return _resolution(
            InformationNeed.RELATIONSHIP_OR_PROFILE, IntentMatch.EXACT, "relationship.profile.v1"
        )
    return None


def parse_memory_answer(message: str) -> MemoryAnswer | None:
    """Read a spoken answer to a memory offer, or say that *message* is not one.

    Pure and closed (ADR 0021 decision 9, Plan 0066): optional openers («Iroko», «sí, claro»,
    «ya», «dale», «po»), then one closed verb (first or third person: «autorizo»/«autoriza»),
    then optionally the value with one optional leading «mi»/«mis», then optional courtesy words
    (a trailing «po» included). A rejection starts with «no», «olvídalo» or «bórralo», never
    with an accepting verb, so the two sets never compete; a repeated «no, no» is one «no».

    A verb alone answers the one open offer and returns an empty phrase: a long verb («autorizo»,
    «apruebo», «acepto», alone or with «guardar»/«a guardar»/«que guardes»), «guarda»/«guárdalo»/
    «guárdala» after a leading «sí», and «no lo guardes»/«no guardes». «Olvídalo» and «bórralo»
    always need a value. After a long verb, «guárdalo», «guárdala» and «sí» at the end are
    courtesy words, not a value («sí, autorizo, guárdalo»); after a short verb they are refused.

    Args:
        message: Raw transcript or chat text in Spanish.

    Returns:
        The answer and the folded value it repeats (``""`` for a verb alone), or ``None`` when
        the message has no closed verb, a bare «sí», a short verb without its cue («guarda»,
        «olvídalo»), a value longer than a short noun phrase, a value that starts with «guardar»
        or «que», or a short verb followed by a non-article («guarda silencio»).
    """
    words = normalize_spanish(message).split()
    affirmed = False
    while words and words[0] in _ANSWER_OPENERS:
        affirmed = affirmed or words[0] == _ANSWER_YES
        words.pop(0)
    while words[:2] == ["no", "no"]:
        words.pop(0)
    text = _without_trailers(" ".join(words))
    for prefixes, accept in ((_ANSWER_REJECT_PREFIXES, False), (_ANSWER_ACCEPT_PREFIXES, True)):
        for prefix in prefixes:
            if text == prefix or text.startswith(f"{prefix} "):
                return _answer(
                    prefix, text[len(prefix) :].split(), accept=accept, affirmed=affirmed
                )
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


def _answer(prefix: str, phrase: list[str], *, accept: bool, affirmed: bool) -> MemoryAnswer | None:
    """Return the answer when *phrase* is a value or the verb may stand alone, or ``None``.

    Args:
        prefix: The folded closed verb the message started with.
        phrase: The words after the verb.
        accept: Whether the verb accepts the offer.
        affirmed: Whether a leading «sí» was among the openers.
    """
    if prefix not in _ANSWER_SHORT_PREFIXES:
        # A repeated or second closed verb («acepto, acepto», «acepto, autorizo») is emphasis
        # too, never a value; so is the «no» of a repeated rejection («no acepto, no acepto»).
        while phrase and (
            phrase[-1] in _ANSWER_LONG_VERB_TRAILERS or (not accept and phrase[-1] == "no")
        ):
            phrase = phrase[:-1]
        while phrase and phrase[0] in _ANSWER_LONG_VERB_LEADERS:
            phrase = phrase[1:]
    # «a guardar» continues the verb («guarda a guardar …» is not a value): drop it, then one
    # possessive, as before. «autorizo a guardar» alone matches its own long prefix instead. The
    # same goes for the forms with the object pronoun, «a guardarlo»/«a guardarla» and the bare
    # «guardarlo»/«guardarla» (Pipec said «sí, autorizo a guardarlo» on 2026-10-21 and the words
    # were read as the value, which matched no offer).
    if phrase[:1] == ["a"] and phrase[1:2] and phrase[1] in _ANSWER_SAVE_FORMS:
        phrase = phrase[2:]
    elif phrase[:1] and phrase[0] in _ANSWER_SAVE_PRONOUN_FORMS:
        phrase = phrase[1:]
    possessive = bool(phrase) and phrase[0] in _ANSWER_POSSESSIVES
    if possessive:
        phrase = phrase[1:]
    if not phrase:
        # A dangling «mi»/«mis» is a garbled value, not a verb alone (D-6).
        return None if possessive else _answer_alone(prefix, accept=accept, affirmed=affirmed)
    if phrase[0] in _ANSWER_CONNECTORS or len(phrase) > _MAX_ANSWER_PHRASE_WORDS:
        return None
    if prefix in _ANSWER_SHORT_PREFIXES and not possessive and phrase[0] not in _ANSWER_ARTICLES:
        return None
    return MemoryAnswer(accept=accept, phrase=" ".join(phrase))


def _answer_alone(prefix: str, *, accept: bool, affirmed: bool) -> MemoryAnswer | None:
    """Return the answer about the open offer for a verb with no value, or ``None`` (D-2, D-3)."""
    if prefix not in _ANSWER_SHORT_PREFIXES:
        return MemoryAnswer(accept=accept, phrase="")
    if prefix in _ANSWER_SHORT_ALONE or (prefix in _ANSWER_SHORT_ALONE_AFTER_YES and affirmed):
        return MemoryAnswer(accept=accept, phrase="")
    return None


def _memory_answer_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize the closed shape of an answer to a memory offer (value included)."""
    normalized = utterance.normalized
    if parse_memory_answer(normalized) is not None:
        return _resolution(InformationNeed.MEMORY_ANSWER, IntentMatch.EXACT, "memory.answer.v1")
    return None


# Order matters: the answer shape is the last rule, so a message that also matches a protected,
# dated or identity rule is classified by that rule and never treated as an answer.
_RULES: tuple[Callable[[_Utterance], IntentResolution | None], ...] = (
    _own_children_list_rule,
    _own_children_count_rule,
    _protected_household_rule,
    _biometric_enrollment_rule,
    _active_identity_rule,
    _profile_summary_rule,
    _ambiguous_date_alias_rule,
    _current_date_stt_alias_rule,
    _current_date_rule,
    _explicit_age_rule,
    _relationship_rule,
    _scene_description_rule,
    _memory_answer_rule,
)
# With recall on (Plan 0078 D-2): the relatives and recall rules come right before the protected
# household rule; every other rule keeps its place. A recall cue with nothing after it returns
# nothing, so «¿qué te conté?» still reaches the profile summary further down.
_RECALL_RULES: tuple[Callable[[_Utterance], IntentResolution | None], ...] = (
    _own_children_list_rule,
    _own_children_count_rule,
    _own_child_name_rule,
    _relatives_rule,
    _recall_rule,
    *_RULES[2:],
)


def _stated_secret_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a message that states a secret value (Plan 0079, D-2)."""
    if secret_kind(utterance.message) is SecretKind.STATED:
        return _resolution(InformationNeed.SECRET_VALUE, IntentMatch.EXACT, "secret.stated.v1")
    return None


def _asked_secret_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a message that asks for a secret value in the closed grammar (Plan 0079, D-2)."""
    if secret_kind(utterance.message) is SecretKind.ASKED:
        return _resolution(InformationNeed.SECRET_VALUE, IntentMatch.EXACT, "secret.asked.v1")
    return None


def _sensitive_question_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize the owner's first-person sensitive question (Plan 0079, D-3)."""
    query = classify_sensitive_question(utterance.message)
    if query is None:
        return None
    return _resolution(
        InformationNeed.SENSITIVE_READ, IntentMatch.EXACT, f"sensitive.{query.topic.value}.v1"
    )


@cache
def _rules_for(
    recall: bool, sensitive: bool, secrets: bool
) -> tuple[Callable[[_Utterance], IntentResolution | None], ...]:
    """Return the rule tuple of one flag set, built once (Plan 0079, D-1).

    The new rules go first, in this order: a stated secret, a sensitive question, an asked secret;
    then the rules of today for the ``recall`` flag. With the new flags off the tuple of today is
    returned itself.

    Args:
        recall: Whether the recall and relatives rules run.
        sensitive: Whether the sensitive question rule runs.
        secrets: Whether the two secret value rules run.

    Returns:
        The ordered rules, a stable object per flag set.
    """
    base = _RECALL_RULES if recall else _RULES
    if not (sensitive or secrets):
        return base
    stated = (_stated_secret_rule,) if secrets else ()
    question = (_sensitive_question_rule,) if sensitive else ()
    asked = (_asked_secret_rule,) if secrets else ()
    return (*stated, *question, *asked, *base)
