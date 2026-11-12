"""The master prompt asks for Spanish, last (Plan 0064, Task 2), in the speaker's form (Plan 0081).

A small model weighs the end of its prompt, and the drift to another language was seen on the
streaming route. One rule closes the master prompt (every route uses it) and one sentence closes
the streaming contract. The rule follows the address form and names no register word: «tuteo»
was spoken back on hardware.
"""

import pytest
from server.characters import build_system_prompt, get_character, language_rule
from server.memory.profile_card import AddressForm
from server.settings import ProfileCardPosition

from server import llm, llm_streaming

pytestmark = pytest.mark.unit

_SEEN = "Una mesa con una taza."
_CARD = '--- bloque de prueba ---\n- Nombre: "Canary".'


@pytest.mark.parametrize("form", ["tu", "usted"])
@pytest.mark.parametrize(
    "perception, emotion, card_position",
    [
        (None, None, None),
        (_SEEN, None, None),
        (None, "joy", None),
        (_SEEN, "sadness", None),
        (_SEEN, "sadness", "with_memory"),
        (_SEEN, "sadness", "before_language"),
    ],
    ids=["plain", "perception", "emotion", "everything", "card", "card_before_language"],
)
def test_the_prompt_ends_with_the_rule_of_its_form(
    perception: str | None,
    emotion: str | None,
    card_position: ProfileCardPosition | None,
    form: AddressForm,
) -> None:
    prompt = build_system_prompt(
        get_character("iroko"),
        user_emotion=emotion,
        perception=perception,
        profile_card=None if card_position is None else _CARD,
        profile_card_position=card_position or "with_memory",
        address_form=form,
    )

    assert prompt.endswith(language_rule(form))
    assert prompt.count(language_rule(form)) == 1


@pytest.mark.parametrize("form", ["tu", "usted"])
def test_the_rule_names_no_register_word(form: AddressForm) -> None:
    assert "español" in language_rule(form)
    assert "tuteo" not in language_rule(form).casefold()


def test_the_tu_rule_asks_for_tu() -> None:
    assert "háblale de tú" in language_rule("tu")


def test_the_usted_rule_asks_for_usted() -> None:
    assert "trata de usted" in language_rule("usted")
    assert "de tú" not in language_rule("usted")


@pytest.mark.parametrize("name", ["iroko", "nova", "ejemplo_vendedor"])
def test_a_prompt_without_a_card_names_no_register_word(name: str) -> None:
    prompt = build_system_prompt(get_character(name))

    assert "tuteo" not in prompt.casefold()
    assert prompt.endswith(language_rule("tu"))


def test_the_classic_and_stream_prompts_follow_usted() -> None:
    classic = llm._build_classic_base_prompt(
        user_emotion=None,
        active_person=None,
        perception=None,
        profile_card=None,
        address_form="usted",
    )
    stream = llm_streaming._build_streaming_base_prompt(
        user_emotion=None, active_person=None, address_form="usted"
    )

    assert classic.endswith(language_rule("usted"))
    assert stream.endswith(language_rule("usted"))


def test_the_streaming_contract_asks_for_spanish_and_still_names_no_tag() -> None:
    prompt = llm_streaming._streaming_system_prompt("base prompt")

    assert "siempre en español" in prompt
    assert "EMOTION" not in prompt.upper()


@pytest.mark.parametrize("position", ["with_memory", "before_language"])
def test_a_none_card_is_byte_identical(position: ProfileCardPosition) -> None:
    profile = get_character("iroko")

    without = build_system_prompt(profile, perception=_SEEN, user_emotion="joy")
    with_none = build_system_prompt(
        profile,
        perception=_SEEN,
        user_emotion="joy",
        profile_card=None,
        profile_card_position=position,
    )

    assert with_none == without
    assert _CARD not in with_none


def test_the_card_sits_after_the_emotion_and_before_the_perception_by_default() -> None:
    prompt = build_system_prompt(
        get_character("iroko"), perception=_SEEN, user_emotion="joy", profile_card=_CARD
    )

    assert prompt.index("The user seems happy") < prompt.index(_CARD)
    assert prompt.index(_CARD) < prompt.index("Percepción visual")
    assert prompt.count(_CARD) == 1


def test_the_card_sits_before_the_language_rule_when_asked() -> None:
    prompt = build_system_prompt(
        get_character("iroko"),
        perception=_SEEN,
        profile_card=_CARD,
        profile_card_position="before_language",
    )

    assert prompt.index("Percepción visual") < prompt.index(_CARD)
    assert prompt.index(_CARD) < prompt.index(language_rule("tu"))
    assert prompt.count(_CARD) == 1


def test_the_retired_memory_and_onboarding_blocks_never_appear() -> None:
    prompt = build_system_prompt(get_character("iroko"), perception=_SEEN, profile_card=_CARD)

    assert "Memoria activa autorizada" not in prompt
    assert "PRIMER ENCUENTRO" not in prompt
    assert "PRÓXIMO OBJETIVO" not in prompt
