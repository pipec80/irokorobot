"""The master prompt asks for Spanish, last (Plan 0064, Task 2).

A small model weighs the end of its prompt, and the drift to another language was seen on the
streaming route. One rule closes the master prompt (every route uses it) and one sentence closes
the streaming contract.
"""

import pytest
from server.characters import _LANGUAGE_RULE, build_system_prompt, get_character
from server.onboarding import OnboardingSlot
from server.schemas import MemoryContext, MemoryHit
from server.settings import ProfileCardPosition

from server import llm_streaming

pytestmark = pytest.mark.unit

_MEMORY = MemoryContext(
    memories=[
        MemoryHit(
            id=1,
            kind="semantic",
            content="Un dato de prueba.",
            summary=None,
            importance=0.5,
            distance=0.1,
        )
    ]
)
_SLOT = OnboardingSlot(key="nombre", question_hint="cómo se llama")
_SEEN = "Una mesa con una taza."
_CARD = '--- bloque de prueba ---\n- Nombre: "Canary".'


@pytest.mark.parametrize(
    "with_memory, perception, onboarding, emotion, card_position",
    [
        (False, None, False, None, None),
        (True, None, False, None, None),
        (False, _SEEN, False, None, None),
        (False, None, True, None, None),
        (False, None, False, "joy", None),
        (True, _SEEN, True, "sadness", None),
        (True, _SEEN, True, "sadness", "with_memory"),
        (True, _SEEN, True, "sadness", "before_language"),
    ],
    ids=[
        "plain",
        "memory",
        "perception",
        "onboarding",
        "emotion",
        "everything",
        "card",
        "card_before_language",
    ],
)
def test_the_language_rule_is_the_last_part_of_the_master_prompt(
    with_memory: bool,
    perception: str | None,
    onboarding: bool,
    emotion: str | None,
    card_position: ProfileCardPosition | None,
) -> None:
    prompt = build_system_prompt(
        get_character("iroko"),
        _MEMORY if with_memory else None,
        onboarding=onboarding,
        onboarding_slot=_SLOT if onboarding else None,
        user_emotion=emotion,
        perception=perception,
        profile_card=None if card_position is None else _CARD,
        profile_card_position=card_position or "with_memory",
    )

    assert prompt.endswith(_LANGUAGE_RULE)
    assert prompt.count(_LANGUAGE_RULE) == 1


def test_the_rule_asks_for_spanish_with_tuteo() -> None:
    assert "español" in _LANGUAGE_RULE
    assert "tuteo" in _LANGUAGE_RULE


def test_the_streaming_contract_asks_for_spanish_and_still_names_no_tag() -> None:
    prompt = llm_streaming._streaming_system_prompt("base prompt")

    assert "siempre en español" in prompt
    assert "EMOTION" not in prompt.upper()


@pytest.mark.parametrize("position", ["with_memory", "before_language"])
def test_a_none_card_is_byte_identical(position: ProfileCardPosition) -> None:
    profile = get_character("iroko")

    without = build_system_prompt(profile, _MEMORY, perception=_SEEN, user_emotion="joy")
    with_none = build_system_prompt(
        profile,
        _MEMORY,
        perception=_SEEN,
        user_emotion="joy",
        profile_card=None,
        profile_card_position=position,
    )

    assert with_none == without
    assert _CARD not in with_none


def test_the_card_sits_before_the_memory_block_by_default() -> None:
    prompt = build_system_prompt(
        get_character("iroko"), _MEMORY, perception=_SEEN, user_emotion="joy", profile_card=_CARD
    )

    assert prompt.index("The user seems happy") < prompt.index(_CARD)
    assert prompt.index(_CARD) < prompt.index("--- Memoria activa autorizada ---")
    assert prompt.index(_CARD) < prompt.index("Percepción visual")
    assert prompt.count(_CARD) == 1


def test_the_card_sits_before_the_language_rule_when_asked() -> None:
    prompt = build_system_prompt(
        get_character("iroko"),
        _MEMORY,
        perception=_SEEN,
        profile_card=_CARD,
        profile_card_position="before_language",
    )

    assert prompt.index("--- Memoria activa autorizada ---") < prompt.index("Percepción visual")
    assert prompt.index("Percepción visual") < prompt.index(_CARD)
    assert prompt.index(_CARD) < prompt.index(_LANGUAGE_RULE)
    assert prompt.count(_CARD) == 1
