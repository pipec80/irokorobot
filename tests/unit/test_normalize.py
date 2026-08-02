"""Unit tests for extraction guardrails — cases taken from real QA output.

Every scenario here was observed verbatim in the 2026-07-06 live session
with qwen2.5:3b (invented predicates, inverted relations, empty objects,
owner identity split across 'usuario' and the real name).
"""

import pytest
from server.memory.normalize import normalize_extraction
from server.schemas import ExtractedEntity, ExtractedFact, TurnExtraction


def _extraction(facts: list[ExtractedFact]) -> TurnExtraction:
    return TurnExtraction(entities=[], facts=facts, episodic_summary=None, importance=0.5)


@pytest.mark.unit
def test_invented_predicate_variant_is_mapped_to_canonical() -> None:
    """qwen emitted 'tiene_hijo_de' — must become 'hijo_de'."""
    dirty = _extraction(
        [ExtractedFact(subject="máximo", predicate="tiene_hijo_de", object="Felipe")]
    )

    clean = normalize_extraction(dirty)

    assert clean.facts[0].predicate == "hijo_de"


@pytest.mark.unit
def test_unknown_predicate_is_dropped() -> None:
    dirty = _extraction([ExtractedFact(subject="Felipe", predicate="estado_animo", object="feliz")])

    assert normalize_extraction(dirty).facts == []


@pytest.mark.unit
def test_empty_object_is_dropped() -> None:
    """qwen emitted ('Felipe', 'trabaja_en', '') — garbage, drop it."""
    dirty = _extraction([ExtractedFact(subject="Felipe", predicate="trabaja_en", object="  ")])

    assert normalize_extraction(dirty).facts == []


@pytest.mark.unit
def test_owner_alias_subject_resolved_to_owner_name() -> None:
    """Facts under 'usuario' must merge into the real owner identity."""
    dirty = _extraction(
        [ExtractedFact(subject="usuario", predicate="le_gusta", object="andar en bicicleta")]
    )

    clean = normalize_extraction(dirty, owner_name="Felipe")

    assert clean.facts[0].subject == "Felipe"


@pytest.mark.unit
def test_inverted_child_relation_is_swapped_to_child() -> None:
    """Observed: ('usuario', 'tiene_hijo_de', 'máximo') with owner Felipe.

    Must become ('Máximo', 'hijo_de', 'Felipe') so the reverse relational
    lookup ("¿cómo se llaman mis hijos?") finds the child.
    """
    dirty = _extraction(
        [ExtractedFact(subject="usuario", predicate="tiene_hijo_de", object="máximo")]
    )

    clean = normalize_extraction(dirty, owner_name="Felipe")

    fact = clean.facts[0]
    assert fact.subject == "Máximo"
    assert fact.predicate == "hijo_de"
    assert fact.object == "Felipe"


@pytest.mark.unit
def test_inverted_pet_relation_is_swapped() -> None:
    dirty = _extraction([ExtractedFact(subject="Felipe", predicate="tiene_mascota", object="luna")])

    clean = normalize_extraction(dirty, owner_name="Felipe")

    fact = clean.facts[0]
    assert (fact.subject, fact.predicate, fact.object) == ("Luna", "mascota_de", "Felipe")


@pytest.mark.unit
def test_correct_direction_is_left_untouched() -> None:
    dirty = _extraction([ExtractedFact(subject="Valentina", predicate="hijo_de", object="Felipe")])

    clean = normalize_extraction(dirty, owner_name="Felipe")

    fact = clean.facts[0]
    assert (fact.subject, fact.predicate, fact.object) == ("Valentina", "hijo_de", "Felipe")


@pytest.mark.unit
def test_entity_names_are_title_cased() -> None:
    """Whisper lowercases proper nouns ('dominga') — dedup needs stable casing."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="dominga", type="person")],
        facts=[],
        episodic_summary=None,
        importance=0.5,
    )

    assert normalize_extraction(dirty).entities[0].name == "Dominga"


@pytest.mark.unit
def test_owner_alias_entity_is_dropped() -> None:
    """A 'usuario' entity must not exist alongside the real owner entity."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="usuario", type="person")],
        facts=[],
        episodic_summary=None,
        importance=0.5,
    )

    assert normalize_extraction(dirty, owner_name="Felipe").entities == []


@pytest.mark.unit
def test_ungrounded_relation_fact_is_dropped() -> None:
    """Observed live: Iroko invented a child, and the extractor turned the
    hallucination into a fact with importance 1.0. Relations must be grounded
    in the USER's literal words."""
    dirty = _extraction([ExtractedFact(subject="Valentina", predicate="hijo_de", object="Felipe")])

    clean = normalize_extraction(
        dirty, owner_name="Felipe", user_text="¿te acordás el nombre de mis hijos?"
    )

    assert clean.facts == []


@pytest.mark.unit
def test_grounded_relation_fact_survives() -> None:
    dirty = _extraction([ExtractedFact(subject="Valentina", predicate="hijo_de", object="Felipe")])

    clean = normalize_extraction(dirty, owner_name="Felipe", user_text="mi hija se llama valentina")

    assert clean.facts[0].subject == "Valentina"


@pytest.mark.unit
def test_ungrounded_person_entity_is_dropped() -> None:
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="Valentina", type="person")],
        facts=[],
        episodic_summary=None,
        importance=0.5,
    )

    clean = normalize_extraction(dirty, user_text="¿cómo se llaman mis hijos?")

    assert clean.entities == []


@pytest.mark.unit
def test_non_person_entity_needs_no_grounding() -> None:
    """Places/concepts can come from context — only people are strict."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="Cocina", type="place")],
        facts=[],
        episodic_summary=None,
        importance=0.5,
    )

    clean = normalize_extraction(dirty, user_text="hola")

    assert clean.entities[0].name == "Cocina"


@pytest.mark.unit
def test_without_owner_name_alias_fact_is_dropped() -> None:
    """Owner unknown: a literal 'usuario' entity is junk the checklist can
    never match (observed live 2026-07-13: entity 'usuario' with vive_en).
    The checklist re-asks the slot once the owner is anchored."""
    dirty = _extraction([ExtractedFact(subject="usuario", predicate="le_gusta", object="café")])

    clean = normalize_extraction(dirty, owner_name=None)

    assert clean.facts == []


@pytest.mark.unit
def test_relation_object_alias_resolved_to_owner() -> None:
    """Observed live 2026-07-13: facts persisted as hijo_de='Usuario' — the
    alias in the OBJECT position was never resolved to the real owner."""
    dirty = _extraction([ExtractedFact(subject="Máximo", predicate="hijo_de", object="Usuario")])

    clean = normalize_extraction(dirty, owner_name="Felipe", user_text="mi hijo Máximo")

    assert clean.facts[0].object == "Felipe"


@pytest.mark.unit
def test_declined_relation_stays_on_owner_with_canonical_object() -> None:
    """'no tengo hijos' → fact on the owner with object 'ninguno' — no
    inversion (there is no child named 'Ninguno') and no grounding check."""
    dirty = _extraction([ExtractedFact(subject="usuario", predicate="hijo_de", object="ninguno")])

    clean = normalize_extraction(dirty, owner_name="Felipe", user_text="no tengo hijos")

    fact = clean.facts[0]
    assert (fact.subject, fact.predicate, fact.object) == ("Felipe", "hijo_de", "ninguno")


@pytest.mark.unit
def test_declined_relation_variants_are_canonicalized() -> None:
    """Extractor drift ('ninguna', 'no tiene') must collapse to 'ninguno'."""
    dirty = _extraction([ExtractedFact(subject="usuario", predicate="pareja_de", object="Ninguna")])

    clean = normalize_extraction(dirty, owner_name="Felipe", user_text="no tengo pareja")

    assert clean.facts[0].object == "ninguno"


# --- Guardrails from the 2026-07-14 live interview ---


@pytest.mark.unit
@pytest.mark.parametrize(
    "junk_name",
    [
        "Ocho Años",
        "10 Años",
        "13 De Noviembre Del 2017",
        "29 De Diciembre De 017",
        "6 De Octubre De 1981",
        "2017",
    ],
)
def test_temporal_junk_entities_are_dropped(junk_name: str) -> None:
    """Observed live 2026-07-14: dates and ages landed as entities."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name=junk_name, type="event")],
        facts=[],
    )

    assert normalize_extraction(dirty).entities == []


@pytest.mark.unit
def test_real_entities_survive_temporal_filter() -> None:
    """People and places must NOT be mistaken for temporal junk."""
    dirty = TurnExtraction(
        entities=[
            ExtractedEntity(name="Máximo", type="person"),
            ExtractedEntity(name="Santiago de Chile", type="place"),
        ],
        facts=[],
    )

    clean = normalize_extraction(dirty, user_text="Máximo vive en Santiago de Chile")

    assert [e.name for e in clean.entities] == ["Máximo", "Santiago De Chile"]


@pytest.mark.unit
def test_fact_with_temporal_junk_subject_is_dropped() -> None:
    """A date subject would resurrect the junk entity via implicit creation."""
    dirty = _extraction(
        [ExtractedFact(subject="13 de noviembre del 2017", predicate="edad", object="8")]
    )

    assert normalize_extraction(dirty).facts == []


@pytest.mark.unit
def test_preference_pointing_at_person_is_dropped() -> None:
    """Observed live 2026-07-14: 'Máximo es un nombre precioso' became
    ('Felipe Castro', 'le_gusta', 'Máximo')."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="Máximo", type="person")],
        facts=[ExtractedFact(subject="usuario", predicate="le_gusta", object="Máximo")],
    )

    clean = normalize_extraction(
        dirty, owner_name="Felipe Castro", user_text="mi hijo se llama Máximo"
    )

    assert clean.facts == []


@pytest.mark.unit
def test_normal_preference_still_survives() -> None:
    """'me gusta el rock' has no person object — must pass untouched."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="Máximo", type="person")],
        facts=[ExtractedFact(subject="usuario", predicate="le_gusta", object="el rock")],
    )

    clean = normalize_extraction(dirty, owner_name="Felipe", user_text="a Máximo le gusta el rock")

    assert clean.facts[0].object == "el rock"


@pytest.mark.unit
def test_preference_mentioning_person_in_phrase_survives() -> None:
    """Exact match only: 'jugar con Máximo' is an activity, not a person."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="Máximo", type="person")],
        facts=[ExtractedFact(subject="usuario", predicate="le_gusta", object="jugar con Máximo")],
    )

    clean = normalize_extraction(dirty, owner_name="Felipe", user_text="me gusta jugar con Máximo")

    assert clean.facts[0].object == "jugar con Máximo"


@pytest.mark.unit
def test_pet_typed_as_person_is_retyped_to_other() -> None:
    """Observed 2026-07-14: Emma and Trufa landed as [person] — an entity
    holding especie/mascota_de facts this turn is a pet."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="Emma", type="person")],
        facts=[
            ExtractedFact(subject="Emma", predicate="especie", object="perro"),
            ExtractedFact(subject="Emma", predicate="mascota_de", object="usuario"),
        ],
    )

    clean = normalize_extraction(dirty, owner_name="Felipe", user_text="mi perrita Emma")

    assert clean.entities[0].type == "other"


@pytest.mark.unit
def test_owner_with_declined_pets_is_not_retyped() -> None:
    """'no tengo mascotas' puts mascota_de=ninguno on the OWNER — the owner
    must stay a person."""
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="Felipe", type="person")],
        facts=[ExtractedFact(subject="usuario", predicate="mascota_de", object="ninguno")],
    )

    clean = normalize_extraction(
        dirty, owner_name="Felipe", user_text="soy Felipe y no tengo mascotas"
    )

    assert clean.entities[0].type == "person"
