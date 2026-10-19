"""The closed grammar of a spoken answer to a memory offer (ADR 0021 decision 9, Plans 0063, 0066).

Pipec's decision of 2026-10-19 (Plan 0066, D-1 to D-3): a closed verb alone is an answer, and the
value stays optional; when it is present it must still be a short noun phrase. A bare «sí», and the
short ordinary verbs without their «sí» («guarda», «olvídalo»), are never an answer.
"""

import pytest
from server.cognition.intent_resolution import (
    _ANSWER_ARTICLES,
    _MAX_ANSWER_PHRASE_WORDS,
    _RULES,
    MemoryAnswer,
    _memory_answer_rule,
    normalize_spanish,
    parse_memory_answer,
    resolve_information_need,
)
from server.cognition.response_plan import InformationNeed
from server.memory.candidate_classifier import _MAX_WORDS
from server.memory.lexicon import ARTICLES

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "message, accept, phrase",
    [
        ("Sí, autorizo guardar el mate.", True, "el mate"),
        ("autorizo guardar el mate", True, "el mate"),
        ("Sí, apruebo guardar el mate", True, "el mate"),
        ("apruebo que guardes el jazz", True, "el jazz"),
        ("Guárdalo, el mate", True, "el mate"),
        ("sí, guarda el mate", True, "el mate"),
        ("Iroko, sí, autorizo guardar las empanadas", True, "las empanadas"),
        ("Oye, autorizo guardar el café", True, "el cafe"),
        ("No autorizo guardar el mate", False, "el mate"),
        ("no apruebo que guardes el mate", False, "el mate"),
        ("No lo guardes, el mate", False, "el mate"),
        ("no guardes el mate", False, "el mate"),
        ("Olvídalo, el mate", False, "el mate"),
        ("bórralo, el mate", False, "el mate"),
        ("Sí, autorizo guardar lo picante", True, "lo picante"),
        ("Sí, sí, autorizo guardar el mate", True, "el mate"),
        ("Sí, claro, autorizo guardar el mate", True, "el mate"),
        ("Sí, autorizo a guardar el mate", True, "el mate"),
        ("Sí, autorizo guardar el mate, gracias", True, "el mate"),
        ("autorizo guardar el mate por favor", True, "el mate"),
        ("No, no autorizo guardar el mate", False, "el mate"),
        ("No. No autorizo guardar el mate.", False, "el mate"),
        ("Sí, autorizo guardar bailar", True, "bailar"),
    ],
)
def test_a_closed_verb_and_the_value_make_an_answer(
    message: str, accept: bool, phrase: str
) -> None:
    assert parse_memory_answer(message) == MemoryAnswer(accept=accept, phrase=phrase)
    resolution = resolve_information_need(message)
    assert resolution.need is InformationNeed.MEMORY_ANSWER
    assert resolution.rule_id == "memory.answer.v1"


@pytest.mark.parametrize(
    "message, accept, phrase",
    [
        ("Sí, autoriza a guardar mi café", True, "cafe"),
        ("Autoriza guardar el mate", True, "el mate"),
        ("Ya, autorizo guardar el mate", True, "el mate"),
        ("Sí po, autorizo guardar el mate", True, "el mate"),
        ("Dale, autorizo guardar el mate", True, "el mate"),
        ("Autorizo guardar el mate po", True, "el mate"),
        ("Aprueba guardar las empanadas", True, "las empanadas"),
        ("Autoriza que guardes el mate", True, "el mate"),
        ("Autoriza guardar mis empanadas", True, "empanadas"),
        ("No autoriza guardar el jazz", False, "el jazz"),
        ("No, no autoriza a guardar mi jazz", False, "jazz"),
        ("Guarda mi café", True, "cafe"),
    ],
)
def test_the_answer_survives_how_the_speech_to_text_writes_it(
    message: str, accept: bool, phrase: str
) -> None:
    """Whisper writes the third person, «po», «ya», «dale» and a leading «mi» (Plan 0064, D-3)."""
    assert parse_memory_answer(message) == MemoryAnswer(accept=accept, phrase=phrase)
    assert resolve_information_need(message).need is InformationNeed.MEMORY_ANSWER


@pytest.mark.parametrize(
    "message",
    [
        "Sí po",
        "Ya",
        "Dale",
        "Guarda silencio",
        "Guarda mi",
        "Autorizo mi",
        "Sí, autorizo mis",
        "Sí, guarda mi",
        "Ya, guarda silencio",
        "Autorizo guardar uno dos tres cuatro cinco seis siete",
        "Autoriza guardar el mate de la abuela de mi vecino de al lado",
    ],
)
def test_the_wider_grammar_still_refuses_what_is_not_an_answer(message: str) -> None:
    assert parse_memory_answer(message) is None


@pytest.mark.parametrize(
    "message",
    [
        "sí",
        "guárdalo",
        "Guarda",
        "olvídalo",
        "Olvídalo",
        "Bórralo",
        "Sí, olvídalo",
        "Sí, bórralo",
        "dale",
        "ok",
        "no",
        "sí, por favor",
        "me gusta el mate",
        "Guarda silencio, por favor",
        "Sí, guarda silencio",
        "Olvídalo, no importa",
        "Bórralo todo",
        "no guardes nada",
        "",
        "   ",
    ],
)
def test_a_bare_yes_or_a_short_ordinary_verb_is_never_an_answer(message: str) -> None:
    """A bare «sí», and «guarda»/«olvídalo»/«bórralo» without their cue, resolve nothing (D-1, D-3)."""
    assert parse_memory_answer(message) is None
    assert resolve_information_need(message).need is not InformationNeed.MEMORY_ANSWER


@pytest.mark.parametrize(
    "message, accept",
    [
        ("Autorizo.", True),
        ("Sí, autorizo.", True),
        ("Autoriza", True),
        ("Apruebo, gracias", True),
        ("Aprueba po", True),
        ("Dale, apruebo", True),
        ("Sí, autorizo guardar", True),
        ("Autorizo a guardar", True),
        ("Sí, autorizo a guardar", True),
        ("Autoriza que guardes", True),
        ("Sí, guarda", True),
        ("Sí, guárdalo", True),
        ("Sí po, guárdalo", True),
        ("No autorizo", False),
        ("No, no apruebo", False),
        ("No autoriza guardar", False),
        ("No lo guardes", False),
        ("No guardes", False),
    ],
)
def test_a_closed_verb_alone_is_an_answer_about_the_open_offer(message: str, accept: bool) -> None:
    """Plan 0066, D-1 to D-3: the empty phrase means «the one open offer»."""
    assert parse_memory_answer(message) == MemoryAnswer(accept=accept, phrase="")
    resolution = resolve_information_need(message)
    assert resolution.need is InformationNeed.MEMORY_ANSWER
    assert resolution.rule_id == "memory.answer.v1"


@pytest.mark.parametrize(
    "message, accept, phrase",
    [
        ("Sí, autorizo guardar el mate", True, "el mate"),
        ("Autorizo comer", True, "comer"),
        ("No autorizo guardar el mate", False, "el mate"),
        ("Sí, guarda el mate", True, "el mate"),
    ],
)
def test_a_value_that_is_present_is_still_read_as_the_value(
    message: str, accept: bool, phrase: str
) -> None:
    """The verb alone is new; a value after it is still parsed, and later compared (D-6)."""
    assert parse_memory_answer(message) == MemoryAnswer(accept=accept, phrase=phrase)


def test_a_closed_rule_resolved_earlier_wins_over_the_shape_of_an_answer() -> None:
    """A protected or dated message is never read as an answer: those rules run first."""
    assert resolve_information_need("guarda la fecha de hoy").need is InformationNeed.CURRENT_DATE
    assert (
        resolve_information_need("sí, autorizo guardar a mi hijo").need
        is InformationNeed.PROTECTED_HOUSEHOLD
    )


def test_the_value_is_a_short_phrase() -> None:
    long_value = "uno dos tres cuatro cinco seis siete"

    assert parse_memory_answer(f"sí, autorizo guardar {long_value}") is None
    assert parse_memory_answer("sí, autorizo guardar uno dos tres cuatro cinco seis") == (
        MemoryAnswer(accept=True, phrase="uno dos tres cuatro cinco seis")
    )


def test_the_answer_is_frozen() -> None:
    answer = MemoryAnswer(accept=True, phrase="el mate")

    with pytest.raises(ValueError, match="frozen"):
        answer.phrase = "el cafe"  # type: ignore[misc]  # mutation is what this test refutes


def test_the_repeated_value_never_shows_in_the_repr_of_an_answer() -> None:
    answer = parse_memory_answer("Sí, autorizo guardar el quokka")

    assert answer is not None
    assert "quokka" not in repr(answer)


@pytest.mark.parametrize("article", sorted(ARTICLES))
def test_every_article_the_classifier_admits_follows_a_short_verb(article: str) -> None:
    """The grammar keeps its own copy of the list (the core cannot import the memory layer)."""
    assert parse_memory_answer(f"guarda {article} mate") is not None


def test_the_grammar_admits_no_article_the_classifier_does_not() -> None:
    assert _ANSWER_ARTICLES == ARTICLES


@pytest.mark.parametrize("message", ["apruebo el examen", "Apruebo la propuesta."])
def test_an_ordinary_apruebo_sentence_has_the_shape_of_an_answer(message: str) -> None:
    """«Apruebo» is a long prefix, so it needs no article and these two sentences parse.

    The shape alone resolves to ``MEMORY_ANSWER`` with the repeated value as the phrase. That is
    accepted on purpose: only an open offer whose value is exactly «el examen» or «la propuesta»
    can use it, and with no such offer the answerer returns ``None`` and the message falls
    through to the ordinary turn (the controller test pins that fall-through). This test pins the
    grammar's side, so that a change to the long prefixes is a visible decision.
    """
    answer = parse_memory_answer(message)

    assert answer is not None
    assert answer.accept is True
    assert answer.phrase == normalize_spanish(message).removeprefix("apruebo ")
    assert resolve_information_need(message).need is InformationNeed.MEMORY_ANSWER


# One answer-shaped body per rule that runs before the answer rule. Each body starts with an
# article and is at most six words, so the verb plus the body alone would be an answer: only the
# order of the rules keeps the earlier rule's need.
_PREEMPTING_BODIES = [
    ("own_children.list.v1", InformationNeed.OWN_CHILDREN_LIST, "la como se llaman mis hijos"),
    ("own_children.count.v1", InformationNeed.OWN_CHILDREN_COUNT, "el cuantos hijos tengo"),
    ("household.protected.v1", InformationNeed.PROTECTED_HOUSEHOLD, "el cumpleanos de mi hijo"),
    ("household.protected.v1", InformationNeed.PROTECTED_HOUSEHOLD, "lo que le gusta"),
    ("birth.protected.v1", InformationNeed.PROTECTED_HOUSEHOLD, "la fecha de nacimiento"),
    (
        "enrollment.biometric.v1",
        InformationNeed.BIOMETRIC_ENROLLMENT,
        "la cara aprende mi cara",
    ),
    ("identity.active.v1", InformationNeed.ACTIVE_IDENTITY, "la pregunta quien soy"),
    ("date.current.v1", InformationNeed.CURRENT_DATE, "el que dia es hoy"),
    ("age.explicit.v1", InformationNeed.EXPLICIT_BIRTH_DATE_AGE, "la edad que tengo"),
    ("relationship.profile.v1", InformationNeed.RELATIONSHIP_OR_PROFILE, "la relacion"),
    ("scene.description.v1", InformationNeed.SCENE_DESCRIPTION, "lo que ves"),
]
# The two supervised STT aliases match the whole message only, so a verb in front takes the
# message out of their reach; they are exercised bare.
_BARE_ALIASES = [
    ("date.ambiguous.stt.v1", InformationNeed.AMBIGUOUS_DATE_QUERY, "que dia soy"),
    ("date.current.stt.v1", InformationNeed.CURRENT_DATE, "me dice la fecha actual"),
]


@pytest.mark.parametrize("verb", ["guarda", "autorizo guardar"])
@pytest.mark.parametrize("rule_id, need, body", _PREEMPTING_BODIES)
def test_an_earlier_rule_keeps_its_need_over_the_shape_of_an_answer(
    verb: str, rule_id: str, need: InformationNeed, body: str
) -> None:
    """Order matters: a protected, dated or identity message is never read as an answer."""
    message = f"{verb} {body}"

    assert parse_memory_answer(message) is not None  # the shape alone would be an answer
    resolution = resolve_information_need(message)
    assert resolution.rule_id == rule_id
    assert resolution.need is need
    assert resolution.rule_id != "memory.answer.v1"


@pytest.mark.parametrize("rule_id, need, message", _BARE_ALIASES)
def test_a_bare_stt_alias_is_not_an_answer(
    rule_id: str, need: InformationNeed, message: str
) -> None:
    resolution = resolve_information_need(message)

    assert resolution.rule_id == rule_id
    assert resolution.need is need


def test_every_rule_before_the_answer_rule_has_a_case_that_it_wins() -> None:
    """A new rule placed before the answer rule must add a case above, or this fails."""
    assert _RULES[-1] is _memory_answer_rule
    corpus = [
        normalize_spanish(f"{verb} {body}")
        for verb in ("guarda", "autorizo guardar")
        for _, _, body in _PREEMPTING_BODIES
    ] + [normalize_spanish(message) for _, _, message in _BARE_ALIASES]

    unexercised = [
        rule.__name__ for rule in _RULES[:-1] if not any(rule(text) is not None for text in corpus)
    ]

    assert unexercised == []


_VALUE_WORDS = ("mate", "verde", "muy", "dulce", "claro", "fuerte", "suave", "tibio", "rico")


@pytest.mark.parametrize("verb", ["autorizo guardar", "guarda"])
def test_the_parser_admits_every_value_the_classifier_can_offer(verb: str) -> None:
    """The offer's value is at most ``_MAX_WORDS`` words with its article; the answer repeats it.

    If the classifier ever admitted a longer value than the parser, an offer could be made that
    its own answer could never accept.
    """
    assert _MAX_ANSWER_PHRASE_WORDS >= _MAX_WORDS
    value = " ".join(("el", *_VALUE_WORDS[: _MAX_WORDS - 1]))
    assert len(value.split()) == _MAX_WORDS

    answer = parse_memory_answer(f"{verb} {value}")

    assert answer == MemoryAnswer(accept=True, phrase=value)
