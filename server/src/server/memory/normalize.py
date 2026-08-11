"""Deterministic guardrails over LLM extraction output.

Small local models drift from the canonical predicate vocabulary no matter
how firm the prompt is (observed with qwen2.5:3b: invented predicates,
inverted relations, empty objects, split owner identity). Discipline lives
in code, not prompts: every ``TurnExtraction`` passes through
``normalize_extraction`` before persistence.
"""

from __future__ import annotations

import logging
import re

from server.schemas import ExtractedEntity, ExtractedFact, TurnExtraction

logger = logging.getLogger(__name__)

CANONICAL_PREDICATES = frozenset(
    {
        "nombre",
        "fecha_nacimiento",
        "edad",
        "vive_en",
        "trabaja_en",
        "hijo_de",
        "pareja_de",
        "mascota_de",
        "especie",
        "le_gusta",
        "odia",
        "prefiere",
        "alergico_a",
    }
)

# Drift variants observed (or likely) in the wild → canonical predicate.
_PREDICATE_ALIASES: dict[str, str] = {
    "tiene_hijo_de": "hijo_de",
    "tiene_hijo": "hijo_de",
    "tiene_hijos": "hijo_de",
    "hijo": "hijo_de",
    "hija": "hijo_de",
    "hija_de": "hijo_de",
    "tiene_mascota": "mascota_de",
    "mascota": "mascota_de",
    "pareja": "pareja_de",
    "esposa_de": "pareja_de",
    "esposo_de": "pareja_de",
    "casado_con": "pareja_de",
    "nacimiento": "fecha_nacimiento",
    "fecha_de_nacimiento": "fecha_nacimiento",
    "cumpleanos": "fecha_nacimiento",
    "cumpleaños": "fecha_nacimiento",
    "nacio_el": "fecha_nacimiento",
    "gusta": "le_gusta",
    "gustos": "le_gusta",
    "hobby": "le_gusta",
    "trabaja": "trabaja_en",
    "trabajo": "trabaja_en",
    "profesion": "trabaja_en",
    "profesión": "trabaja_en",
    "vive": "vive_en",
    "alergia": "alergico_a",
    "alergico": "alergico_a",
}

# Predicates whose subject is a PERSON/PET related to the owner: when the
# model inverts them (subject=owner, object=child), the fact gets swapped.
_RELATION_PREDICATES = frozenset({"hijo_de", "pareja_de", "mascota_de"})

_OWNER_ALIASES = frozenset({"usuario", "el usuario", "user", "dueño", "dueno", "owner"})

#: Canonical object value for a declined relation slot ("no tengo hijos").
NO_RELATION_VALUE = "ninguno"

# Variants the extractor may emit for a declined relation.
_NO_VALUES = frozenset({"ninguno", "ninguna", "nadie", "no", "no tiene", "no tengo"})

# Dates and ages are FACTS about people, never entities of their own —
# observed live 2026-07-14: "Ocho Años" (preference), "13 De Noviembre Del
# 2017" (event) and three more junk rows landed in one interview.
_MONTHS = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre"
_TEMPORAL_JUNK_PATTERNS = (
    re.compile(rf"^(el\s+)?\d{{1,2}}\s+de\s+({_MONTHS})(\s+(de|del)\s*\d{{1,4}})?$"),
    re.compile(r"^(\d+|[a-záéíóúüñ]+)\s+años?$"),
    re.compile(r"^[\d\s./-]+$"),
)

# Preferences whose object is a person are extractor confusion ("Máximo es
# un nombre precioso" → le_gusta: Máximo, observed live 2026-07-14).
_PREFERENCE_PREDICATES = frozenset({"le_gusta", "odia", "prefiere"})

# A subject holding one of these facts this turn IS a pet — the extractor
# typed Emma and Trufa as "person" (observed 2026-07-14) and the entities
# table separates dedup by type.
_PET_PREDICATES = frozenset({"especie", "mascota_de"})


def _is_temporal_junk(name: str) -> bool:
    """True when *name* is a bare date, age, or number — not a real entity."""
    folded = name.strip().casefold()
    return any(pattern.match(folded) for pattern in _TEMPORAL_JUNK_PATTERNS)


def _canonical_predicate(raw: str) -> str | None:
    """Map a raw predicate to the canonical vocabulary, or ``None`` to drop it."""
    pred = raw.strip().casefold().replace(" ", "_")
    pred = _PREDICATE_ALIASES.get(pred, pred)
    return pred if pred in CANONICAL_PREDICATES else None


def _clean_name(name: str) -> str:
    """Normalise an entity/person name: trimmed and title-cased.

    Whisper lowercases proper nouns ("dominga") — title-casing keeps the
    entities table consistent for upsert dedup by (name, type).
    """
    return name.strip().title()


def _resolve_subject(subject: str, active_person_name: str | None) -> str:
    """Replace turn-local person aliases ("usuario") with a validated name."""
    if active_person_name and subject.strip().casefold() in _OWNER_ALIASES:
        return active_person_name
    return subject.strip()


def _is_grounded(name: str, user_text: str | None) -> bool:
    """True when *name* literally appears in the user's own words.

    Anti-poisoning: the model extracts from the whole exchange and will
    happily turn the assistant's confabulated names into facts (observed
    live: an invented child got consolidated with importance 1.0). New
    people and relations must be grounded in what the USER said.
    """
    if user_text is None:
        return True
    return name.casefold() in user_text.casefold()


def _normalize_relation(
    fact: ExtractedFact,
    subject: str,
    object_value: str,
    predicate: str,
    active_person_name: str | None,
    user_text: str | None,
) -> ExtractedFact | None:
    """Normalize a relation fact (hijo_de/pareja_de/mascota_de), or drop it.

    Args:
        fact: Original fact (source of the confidence score).
        subject: Alias-resolved subject.
        object_value: Raw object value.
        predicate: Canonical relation predicate.
        active_person_name: Validated turn-local active-person reference.
        user_text: The user's message, used for grounding.

    Returns:
        Cleaned fact, or ``None`` when the relation must be dropped.
    """
    object_value = _resolve_subject(object_value, active_person_name)
    if object_value.casefold() in _OWNER_ALIASES:
        # Same as subjects: an unresolvable "Usuario" object would persist
        # a relation the checklist can never match.
        logger.warning("Dropping relation with unresolved owner object: %s", predicate)
        return None
    if object_value.casefold() in _NO_VALUES:
        # Declined slot ("no tengo hijos") — record on the subject, skip
        # inversion and grounding: no related person exists.
        return ExtractedFact(
            subject=_clean_name(subject),
            predicate=predicate,
            object=NO_RELATION_VALUE,
            confidence=fact.confidence,
        )
    if active_person_name and subject.casefold() == active_person_name.casefold():
        # Inverted by the model: the relation belongs on the child/partner
        # /pet entity, pointing back at the owner.
        subject, object_value = object_value, active_person_name
    subject = _clean_name(subject)
    if not _is_grounded(subject, user_text):
        logger.warning(
            "Dropping ungrounded relation fact: %s %s %s", subject, predicate, object_value
        )
        return None
    return ExtractedFact(
        subject=subject,
        predicate=predicate,
        object=_clean_name(object_value),
        confidence=fact.confidence,
    )


def _validate_fact_parts(
    fact: ExtractedFact, active_person_name: str | None
) -> tuple[str, str, str] | None:
    """Resolve and structurally validate a fact's parts, or drop it.

    Args:
        fact: Raw fact from the LLM extraction.
        active_person_name: Validated turn-local active-person reference.

    Returns:
        Tuple ``(predicate, subject, object_value)`` cleaned, or ``None``
        when the fact fails a structural rule.
    """
    predicate = _canonical_predicate(fact.predicate)
    if predicate is None:
        logger.warning("Dropping fact with non-canonical predicate: %r", fact.predicate)
        return None
    object_value = fact.object.strip()
    if not object_value:
        logger.warning("Dropping fact with empty object: %s", predicate)
        return None
    subject = _resolve_subject(fact.subject, active_person_name)
    if not subject:
        return None
    if subject.casefold() in _OWNER_ALIASES:
        # Owner still unknown — persisting a literal "usuario" entity is
        # junk the checklist can never match (observed 2026-07-13).
        logger.warning("Dropping owner-alias fact — owner unknown yet: %s", predicate)
        return None
    if _is_temporal_junk(subject):
        # A date/age subject would resurrect the junk entity via the
        # implicit-entity path in consolidation.
        logger.warning("Dropping fact with temporal-junk subject: %r", subject)
        return None
    return predicate, subject, object_value


def _normalize_fact(
    fact: ExtractedFact,
    active_person_name: str | None,
    user_text: str | None,
    person_names: frozenset[str],
) -> ExtractedFact | None:
    """Normalize one fact through every deterministic rule, or drop it.

    Args:
        fact: Raw fact from the LLM extraction.
        active_person_name: Validated turn-local active-person reference.
        user_text: The user's message, used for grounding.
        person_names: Folded names of every person the extractor saw this
            turn — preferences pointing at one of them are confusion.

    Returns:
        Cleaned fact, or ``None`` when the fact must be dropped.
    """
    parts = _validate_fact_parts(fact, active_person_name)
    if parts is None:
        return None
    predicate, subject, object_value = parts
    if predicate in _PREFERENCE_PREDICATES and object_value.casefold() in person_names:
        logger.warning(
            "Dropping preference pointing at a person: %s %s %s", subject, predicate, object_value
        )
        return None
    if predicate in _RELATION_PREDICATES:
        return _normalize_relation(
            fact,
            subject,
            object_value,
            predicate,
            active_person_name,
            user_text,
        )
    return ExtractedFact(
        subject=subject,
        predicate=predicate,
        object=object_value,
        confidence=fact.confidence,
    )


def normalize_extraction(
    extraction: TurnExtraction,
    *,
    active_person_name: str | None = None,
    user_text: str | None = None,
    owner_name: str | None = None,
) -> TurnExtraction:
    """Return a cleaned copy of *extraction* safe to persist.

    Applied rules (all deterministic):
    - Predicates mapped to the canonical vocabulary; unknown ones dropped.
    - Facts with an empty object value dropped.
    - Person aliases ("usuario") in subjects AND relation objects resolved
      to a validated turn-local active-person reference; when it is absent, alias facts
      are dropped instead of persisting a literal "usuario" entity.
    - Declined relations ("no tengo hijos" → object "ninguno") kept on the
      resolved subject with the canonical object, skipping inversion and
      grounding — there is no related person to ground.
    - Inverted relations repaired using the turn-local person reference.
    - Person/entity names title-cased for stable upsert dedup.
    - Grounding: new person entities and relation facts are dropped unless
      the person's name appears in *user_text* (the user's literal words).

    Args:
        extraction: Raw extraction from the LLM.
        active_person_name: Validated turn-local person reference, not authorization.
        user_text: The user's message for this turn, used for grounding.
        owner_name: Legacy caller compatibility only; not current-speaker identity.

    Returns:
        New ``TurnExtraction`` with cleaned entities and facts.
    """
    if active_person_name is not None and owner_name is not None:
        raise ValueError("only one active-person reference may be supplied")
    person_reference = active_person_name or owner_name
    entities: list[ExtractedEntity] = []
    for ent in extraction.entities:
        name = _clean_name(ent.name)
        if not name or name.casefold() in _OWNER_ALIASES:
            logger.debug("Dropping owner-alias/empty entity: %r", ent.name)
            continue
        if _is_temporal_junk(name):
            logger.warning("Dropping temporal-junk entity: %r", name)
            continue
        if ent.type == "person" and not _is_grounded(name, user_text):
            logger.warning("Dropping ungrounded person entity: %r", name)
            continue
        entities.append(
            ExtractedEntity(
                name=name, type=ent.type, attributes=ent.attributes, aliases=ent.aliases
            )
        )

    # Every person the extractor saw this turn (pre-grounding on purpose:
    # a hallucinated person can still poison a preference object).
    person_names = frozenset(
        _clean_name(ent.name).casefold() for ent in extraction.entities if ent.type == "person"
    )

    facts = [
        clean
        for fact in extraction.facts
        if (clean := _normalize_fact(fact, person_reference, user_text, person_names)) is not None
    ]

    # Retype pets: declined relations excluded — their subject is the OWNER
    # ("Felipe mascota_de ninguno") and must stay a person.
    pet_names = {
        fact.subject.casefold()
        for fact in facts
        if fact.predicate in _PET_PREDICATES and fact.object != NO_RELATION_VALUE
    }
    entities = [
        ExtractedEntity(name=ent.name, type="other", attributes=ent.attributes, aliases=ent.aliases)
        if ent.type == "person" and ent.name.casefold() in pet_names
        else ent
        for ent in entities
    ]

    return TurnExtraction(
        entities=entities,
        facts=facts,
        episodic_summary=extraction.episodic_summary,
        importance=extraction.importance,
    )
