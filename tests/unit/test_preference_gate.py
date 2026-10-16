"""Unit tests for the preference gate (ADR 0021 decision 4): a closed, refusing grammar."""

import pytest
from server.memory.candidate_types import CandidateReason
from server.memory.preference_gate import match_preference

pytestmark = pytest.mark.unit

_LIKES = frozenset({"likes"})
_DISLIKES = frozenset({"dislikes"})
_PREFERS = frozenset({"prefers"})


@pytest.mark.parametrize(
    "text, predicates",
    [
        ("Me gusta el mate.", _LIKES),
        ("me encantan las empanadas", _LIKES),
        ("Amo el jazz", _LIKES),
        ("adoro el chocolate amargo", _LIKES),
        ("No me gusta el cilantro", _DISLIKES),
        ("no soporto el ruido de la licuadora", _DISLIKES),
        ("odio el brócoli", _DISLIKES),
        ("detesto la lluvia fría", _DISLIKES),
        ("Prefiero el té sin azúcar", _PREFERS),
        ("mi color favorito es el verde", _PREFERS),
        ("Mi comida favorita es la pizza", _PREFERS),
        ("la verdad me gusta el rock", _LIKES),
        ("a mí me gusta el mate", _LIKES),
        ("No, me gusta el mate", _LIKES),
        ("me gusta el mate, pero odio el café", frozenset({"likes", "dislikes"})),
        ("me gusta el mate y odio el café", frozenset({"likes", "dislikes"})),
        ("me gusta cantar en la ducha", _LIKES),
    ],
)
def test_a_first_person_taste_passes_with_its_predicates(
    text: str, predicates: frozenset[str]
) -> None:
    result = match_preference(text)

    assert result.predicates == predicates
    assert result.reason is None


@pytest.mark.parametrize(
    "text, reason",
    [
        # not a statement
        ("hola robot", CandidateReason.GATE_NO_MATCH),
        ("", CandidateReason.GATE_NO_MATCH),
        ("¿Te gusta el mate?", CandidateReason.NOT_A_TASTE),
        ("me gusta el mate?", CandidateReason.NOT_A_TASTE),
        ("me gustaría viajar a Japón", CandidateReason.GATE_NO_MATCH),
        ("me gustó la película", CandidateReason.GATE_NO_MATCH),
        # not the speaker's own taste
        ("a mi vecino le gusta el mate", CandidateReason.GATE_NO_MATCH),
        ("mi hermano dice que me gusta el mate", CandidateReason.NOT_A_TASTE),
        ("creo que me gusta el mate", CandidateReason.NOT_A_TASTE),
        # a clause is an instruction to the robot, not a thing
        (
            "Prefiero que no menciones mi mudanza reciente delante de visitas",
            CandidateReason.NOT_A_TASTE,
        ),
        ("me gusta que me hables despacio", CandidateReason.NOT_A_TASTE),
        ("odio cuando llueve", CandidateReason.NOT_A_TASTE),
        ("me gusta", CandidateReason.NOT_A_TASTE),
        # negated forms other than the two triggers
        ("prefiero no hablar de mi divorcio", CandidateReason.NEGATION_UNSUPPORTED),
        ("ya no me gusta el mate", CandidateReason.NEGATION_UNSUPPORTED),
        ("nunca me gusta madrugar", CandidateReason.NEGATION_UNSUPPORTED),
        ("tampoco me gusta el café", CandidateReason.NEGATION_UNSUPPORTED),
        ("odio no poder dormir", CandidateReason.NEGATION_UNSUPPORTED),
        # sensitive vocabulary
        ("odio mi medicación", CandidateReason.SENSITIVE_TOPIC),
        ("amo a mi hijo", CandidateReason.NOT_A_TASTE),
        ("me gusta mi casa", CandidateReason.SENSITIVE_TOPIC),
        ("me gusta vivir en la costa", CandidateReason.SENSITIVE_TOPIC),
        ("prefiero que no digas mi clave", CandidateReason.NOT_A_TASTE),
        ("me gusta mi perro", CandidateReason.SENSITIVE_TOPIC),
    ],
)
def test_everything_else_is_refused_with_a_closed_reason(
    text: str, reason: CandidateReason
) -> None:
    result = match_preference(text)

    assert result.predicates == frozenset()
    assert result.reason is reason


def test_the_sentences_of_the_longitudinal_benchmark_are_refused() -> None:
    """The two sentences the benchmark's disclosure scenario uses never become candidates."""
    for text in (
        "Prefiero que no menciones mi mudanza reciente delante de visitas.",
        "prefiero no hablar de mi divorcio",
    ):
        assert match_preference(text).predicates == frozenset()


def test_a_refused_clause_does_not_veto_a_clean_one() -> None:
    result = match_preference("me gusta el mate, prefiero que no hables de mi casa")

    assert result.predicates == _LIKES


def test_a_leading_negation_is_a_separate_clause_not_a_dislike() -> None:
    """ "No, me gusta el mate" restates a like; folding the comma away would read it as a dislike."""
    assert match_preference("No, me gusta el mate").predicates == _LIKES


def test_the_gate_is_pure_text_in_and_data_out() -> None:
    first = match_preference("me gusta el mate")
    second = match_preference("me gusta el mate")

    assert first == second


@pytest.mark.parametrize(
    "text",
    [
        "mi hija dice: me gusta el helado",
        "El doctor dijo: no me gusta el azúcar",
        "mi hermano comentó, me gusta el mate",
        "dice mi vecino; odio el café",
    ],
)
def test_a_taste_after_an_attribution_and_a_soft_break_is_not_the_speakers(text: str) -> None:
    result = match_preference(text)

    assert result.predicates == frozenset()
    assert result.reason is CandidateReason.NOT_A_TASTE


def test_a_hard_stop_forgets_the_attribution() -> None:
    result = match_preference("Mi hermano odia el café. Me gusta el mate")

    assert result.predicates == frozenset({"likes"})


@pytest.mark.parametrize(
    "text", ["hola Iroko, me gusta el mate", "oye, me gusta el mate", "no, me gusta el mate"]
)
def test_a_greeting_or_a_bare_no_before_a_taste_is_not_an_attribution(text: str) -> None:
    assert match_preference(text).predicates == frozenset({"likes"})


@pytest.mark.parametrize(
    "text",
    ["mi hijo favorito es Pedro", "mi jefe favorito es Pedro", "mi perro favorito es el negro"],
)
def test_a_kinship_word_inside_the_favourite_trigger_is_refused(text: str) -> None:
    result = match_preference(text)

    assert result.predicates == frozenset()
    assert result.reason is CandidateReason.SENSITIVE_TOPIC


@pytest.mark.parametrize(
    "text",
    ["odio a Rodrigo", "amo a mi esposa", "me gusta sin que me mires", "adoro el té que me hace"],
)
def test_a_person_or_a_relative_clause_is_not_a_thing(text: str) -> None:
    assert match_preference(text).predicates == frozenset()


def test_each_taste_carries_the_words_after_its_own_trigger() -> None:
    result = match_preference("me gusta el mate verde, pero odio el cilantro")

    assert [(m.predicate, m.words) for m in result.matches] == [
        ("likes", ("el", "mate", "verde")),
        ("dislikes", ("el", "cilantro")),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "odio los vecinos",
        "me gustan los niños",
        "detesto los médicos",
        "odio las suegras",
        "me encantan los bebés",
        "odio los musulmanes",
        "odio los judíos",
        "odio los políticos",
        "me gustan los hospitales",
        "me gustan los perritos",
        "me gustan las casitas del barrio",
    ],
)
def test_the_deny_lists_cover_plurals_and_diminutives(text: str) -> None:
    result = match_preference(text)

    assert result.predicates == frozenset()
    assert result.reason is CandidateReason.SENSITIVE_TOPIC


@pytest.mark.parametrize(
    "text",
    [
        "me gusta todo menos el café",
        "me gusta el café excepto el descafeinado",
        "me encanta todo salvo el cilantro",
        "prefiero el mate al café",
        "prefiero el mate en vez del café",
        "prefiero el mate en lugar del café",
    ],
)
def test_a_contrast_inside_one_taste_is_not_a_taste(text: str) -> None:
    """The model must not pick which side of "todo menos X" or "A al B" is the taste."""
    result = match_preference(text)

    assert result.predicates == frozenset()
    assert result.reason is CandidateReason.NEGATION_UNSUPPORTED


@pytest.mark.parametrize(
    "text, predicates",
    [("me gusta el pollo al horno", _LIKES), ("Prefiero el té sin azúcar", _PREFERS)],
)
def test_a_modifier_that_is_not_a_contrast_still_passes(
    text: str, predicates: frozenset[str]
) -> None:
    assert match_preference(text).predicates == predicates


@pytest.mark.parametrize(
    "text, predicates",
    [
        ("La verdad es que me gusta el mate.", _LIKES),
        ("es que me encanta el jazz", _LIKES),
        ("oye me gusta el mate", _LIKES),
        ("Es que no me gusta el cilantro", _DISLIKES),
        ("Es que, me gusta el mate", _LIKES),
    ],
)
def test_a_short_closed_list_of_fillers_may_lead_a_taste(
    text: str, predicates: frozenset[str]
) -> None:
    """Plan 0063, Pipec's decision: «la verdad es que», «es que» and «oye» are fillers."""
    result = match_preference(text)

    assert result.predicates == predicates
    assert result.reason is None


@pytest.mark.parametrize(
    "text",
    [
        "creo que me gusta el mate",
        "dice que me gusta el mate",
        "mi hermano dice que me gusta el mate",
        "lo que me gusta es el mate",
        "ya es que me gusta el mate",
        "siempre que me gusta algo lo compro",
        "que me gusta el mate",
        "y que me gusta el jazz",
        "es que es que me gusta el mate",
    ],
)
def test_a_filler_never_admits_a_belief_an_attribution_or_a_negation(text: str) -> None:
    assert match_preference(text).predicates == frozenset()


@pytest.mark.parametrize(
    "text",
    ["Bueno la verdad es que me gusta el mate", "A mí es que me gusta el jazz"],
)
def test_a_filler_that_follows_other_lead_in_words_is_still_dropped(text: str) -> None:
    """The filler is removed from the end of the lead-in, not only when it stands alone."""
    result = match_preference(text)

    assert result.predicates == _LIKES
    assert result.reason is None
