"""Unit tests for the candidate classifier (ADR 0021 decision 5): pure, on doubt drop."""

from datetime import UTC, datetime

import pytest
from server.cognition.authorization import DataSensitivity, DataVisibility
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
)
from server.cognition.intent_resolution import normalize_spanish
from server.cognition.models import Confidence, ConfidenceBasis
from server.memory.candidate_classifier import (
    CANDIDATE_SENSITIVITY,
    CANDIDATE_VISIBILITY,
    classify,
    comparison_key,
)
from server.memory.candidate_types import (
    CandidateReason,
    GateMatch,
    ProposedCandidate,
    RawCandidate,
)
from server.memory.preference_gate import match_preference
from server.settings import settings

pytestmark = pytest.mark.unit

_OWNER = 7
_PREDICATES = ("likes", "dislikes", "prefers")


def _everywhere(text: str) -> tuple[GateMatch, ...]:
    """Every predicate matched over all the words of *text*: the grounding rule alone is tested."""
    words = tuple(normalize_spanish(text).split())
    return tuple(GateMatch(predicate=predicate, words=words) for predicate in _PREDICATES)


_NAMES = frozenset({"Aldana Quiroga", "Tomasito"})
_REFERENCE = datetime(2026, 10, 14, tzinfo=UTC)


def _actor(
    status: ActivePersonStatus = ActivePersonStatus.IDENTIFIED, person_id: int | None = _OWNER
) -> ActivePersonContext:
    return ActivePersonContext(
        person_id=person_id if status is ActivePersonStatus.IDENTIFIED else None,
        display_name="Canary" if status is ActivePersonStatus.IDENTIFIED else None,
        status=status,
        confidence=Confidence(
            score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False, reason="canary"
        ),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=_REFERENCE,
        assurance=IdentityAssurance.BASIC,
    )


def _raw(obj: str, *, predicate: str = "likes", topic: str = "food") -> RawCandidate:
    return RawCandidate(predicate=predicate, object=obj, topic=topic)


def _classify(
    obj: str,
    text: str,
    *,
    predicate: str = "likes",
    topic: str = "food",
    matches: tuple[GateMatch, ...] | None = None,
    names: frozenset[str] = _NAMES,
    actor: ActivePersonContext | None = None,
) -> ProposedCandidate | CandidateReason:
    return classify(
        actor or _actor(),
        _raw(obj, predicate=predicate, topic=topic),
        text,
        matches=_everywhere(text) if matches is None else matches,
        known_person_names=names,
    )


def test_a_grounded_taste_is_accepted_with_its_phrase_and_key() -> None:
    result = _classify("el mate", "me gusta el mate")

    assert result == ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate")


def test_the_candidate_is_always_the_owners_own_ordinary_data() -> None:
    assert CANDIDATE_VISIBILITY is DataVisibility.PERSONAL
    assert CANDIDATE_SENSITIVITY is DataSensitivity.NORMAL


@pytest.mark.parametrize(
    "alias, canonical",
    [("le_gusta", "likes"), ("odia", "dislikes"), ("prefiere", "prefers"), ("LIKES", "likes")],
)
def test_the_predicate_resolves_through_the_registry(alias: str, canonical: str) -> None:
    result = _classify("el mate", "me gusta el mate", predicate=alias)

    assert isinstance(result, ProposedCandidate)
    assert result.predicate == canonical


def test_a_predicate_the_gate_did_not_return_is_a_mismatch() -> None:
    assert (
        _classify(
            "el mate",
            "me gusta el mate",
            predicate="dislikes",
            matches=match_preference("me gusta el mate").matches,
        )
        is CandidateReason.GATE_MISMATCH
    )


@pytest.mark.parametrize("predicate", ["lives_in", "child_of", "birth_date", "inventado"])
def test_a_predicate_outside_the_three_is_a_mismatch(predicate: str) -> None:
    assert _classify("el mate", "me gusta el mate", predicate=predicate) is (
        CandidateReason.GATE_MISMATCH
    )


@pytest.mark.parametrize("topic", ["health", "family", "place", "", "FOOD"])
def test_a_topic_outside_the_closed_set_is_dropped(topic: str) -> None:
    assert _classify("el mate", "me gusta el mate", topic=topic) is CandidateReason.SENSITIVE_TOPIC


def test_the_model_cannot_choose_the_subject() -> None:
    """A subject is not even part of the model's triple: the identified actor is the subject."""
    assert "subject" not in RawCandidate.__dataclass_fields__


def test_an_actor_who_is_not_identified_gets_nothing() -> None:
    assert (
        _classify("el mate", "me gusta el mate", actor=_actor(ActivePersonStatus.UNKNOWN))
        is CandidateReason.DENIED
    )


@pytest.mark.parametrize(
    "obj",
    ["mi hijo", "mi perro", "los gatos", "mi jefe", "la casa", "mi medicación", "la clave"],
)
def test_a_person_a_pet_a_place_or_a_sensitive_word_is_dropped(obj: str) -> None:
    text = f"me gusta {obj}"

    assert _classify(obj, text) is CandidateReason.SENSITIVE_TOPIC


def test_the_name_of_a_known_person_is_dropped() -> None:
    assert _classify("Tomasito", "me gusta Tomasito") is CandidateReason.SENSITIVE_TOPIC
    assert _classify("el pilar", "me gusta el pilar", names=frozenset({"Pilar"})) is (
        CandidateReason.SENSITIVE_TOPIC
    )


def test_an_object_the_user_did_not_say_is_not_grounded() -> None:
    assert _classify("el té", "me gusta el mate") is CandidateReason.NOT_GROUNDED


def test_grounding_ignores_case_accents_and_punctuation() -> None:
    result = _classify("el CAFÉ", "Me gusta el café, la verdad.")

    assert isinstance(result, ProposedCandidate)
    assert result.value_key == "cafe"


def test_grounding_is_by_whole_words() -> None:
    assert _classify("mate", "me gusta el cogollo de matear") is CandidateReason.NOT_GROUNDED


@pytest.mark.parametrize(
    "obj",
    [
        "el mate 2",
        "el mate\u200b",
        "el mate\u202e",
        "el_mate",
        "el mate!",
        "https mate",
        "uno dos tres cuatro cinco seis",
        "el mate y el cafe",
        "x",
    ],
)
def test_an_object_that_is_not_a_short_noun_phrase_of_letters_is_dropped(obj: str) -> None:
    result = _classify(obj, f"me gusta {obj}")

    assert result in {CandidateReason.NOT_A_TASTE, CandidateReason.SENSITIVE_TOPIC}


def test_a_value_longer_than_the_setting_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_candidate_value_max_chars", 10)

    assert _classify("el dulce de leche", "me gusta el dulce de leche") is (
        CandidateReason.NOT_A_TASTE
    )


@pytest.mark.parametrize("obj", ["cantar", "bailar en la cocina"])
def test_an_allowed_infinitive_is_a_thing(obj: str) -> None:
    result = _classify(obj, f"me gusta {obj}", topic="pastime")

    assert isinstance(result, ProposedCandidate)


@pytest.mark.parametrize("obj", ["vivir en la costa", "mudarme", "hablar de política"])
def test_an_infinitive_outside_the_list_is_dropped(obj: str) -> None:
    result = _classify(obj, f"me gusta {obj}", topic="pastime")

    assert isinstance(result, CandidateReason)


def test_a_noun_that_ends_like_an_infinitive_is_kept_with_its_article() -> None:
    result = _classify("el mar", "me gusta el mar", topic="weather")

    assert isinstance(result, ProposedCandidate)


def test_the_comparison_key_drops_the_article_and_folds() -> None:
    assert comparison_key("El Café") == "cafe"
    assert comparison_key("las empanadas") == "empanadas"
    assert comparison_key("la") == ""
    assert comparison_key("Té   verde") == "te verde"


def test_value_text_keeps_the_spoken_phrase_with_its_article() -> None:
    result = _classify("  la   pizza ", "mi comida favorita es la pizza", predicate="prefers")

    assert isinstance(result, ProposedCandidate)
    assert result.value_text == "la pizza"
    assert result.value_key == "pizza"


def test_classification_is_pure() -> None:
    assert _classify("el mate", "me gusta el mate") == _classify("el mate", "me gusta el mate")


def test_an_object_must_sit_after_a_trigger_of_its_own_predicate() -> None:
    """The model never chooses the polarity: "el cafe" follows "odio", not "me gusta"."""
    text = "me gusta el mate pero odio el cafe"
    matches = match_preference(text).matches

    assert _classify("el cafe", text, predicate="likes", matches=matches) is (
        CandidateReason.NOT_GROUNDED
    )
    assert isinstance(
        _classify("el cafe", text, predicate="dislikes", matches=matches), ProposedCandidate
    )
    assert isinstance(
        _classify("el mate", text, predicate="likes", matches=matches), ProposedCandidate
    )


def test_a_taste_somebody_else_voiced_earlier_in_the_text_is_not_the_speakers() -> None:
    text = "me gusta el mate. Mi hermano odia el cafe"
    matches = match_preference(text).matches

    assert _classify("el cafe", text, predicate="dislikes", matches=matches) is (
        CandidateReason.GATE_MISMATCH
    )
    assert _classify("el cafe", text, predicate="likes", matches=matches) is (
        CandidateReason.NOT_GROUNDED
    )


@pytest.mark.parametrize("obj", ["Rodrigo", "Madrid", "Café Martínez"])
def test_a_capitalised_word_inside_a_sentence_is_a_name_not_a_thing(obj: str) -> None:
    result = _classify(obj, f"Me gusta {obj}", topic="drink")

    assert result is CandidateReason.SENSITIVE_TOPIC


def test_a_capital_that_only_opens_a_sentence_is_not_a_name() -> None:
    result = _classify("el mate", "Me gusta el mate. Gracias")

    assert isinstance(result, ProposedCandidate)


@pytest.mark.parametrize("obj", ["callarme", "quedarme en silencio", "ser", "ir", "cantarte"])
def test_a_short_or_clitic_infinitive_is_dropped_unless_listed(obj: str) -> None:
    result = _classify(obj, f"me gusta {obj}", topic="pastime")

    assert result is CandidateReason.NOT_A_TASTE


@pytest.mark.parametrize("obj", ["el catolicismo", "la cocaína", "los inmigrantes", "la política"])
def test_religion_politics_drugs_and_hate_vocabulary_is_dropped(obj: str) -> None:
    assert _classify(obj, f"me gusta {obj}") is CandidateReason.SENSITIVE_TOPIC
