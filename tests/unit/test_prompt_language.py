"""The master prompt asks for Spanish, last (Plan 0064, Task 2).

A small model weighs the end of its prompt, and the drift to another language was seen on the
streaming route. One rule closes the master prompt (every route uses it) and one sentence closes
the streaming contract.
"""

import pytest
from server.characters import _LANGUAGE_RULE, build_system_prompt, get_character
from server.onboarding import OnboardingSlot
from server.schemas import MemoryContext, MemoryHit

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


@pytest.mark.parametrize(
    "with_memory, perception, onboarding, emotion",
    [
        (False, None, False, None),
        (True, None, False, None),
        (False, _SEEN, False, None),
        (False, None, True, None),
        (False, None, False, "joy"),
        (True, _SEEN, True, "sadness"),
    ],
    ids=["plain", "memory", "perception", "onboarding", "emotion", "everything"],
)
def test_the_language_rule_is_the_last_part_of_the_master_prompt(
    with_memory: bool, perception: str | None, onboarding: bool, emotion: str | None
) -> None:
    prompt = build_system_prompt(
        get_character("iroko"),
        _MEMORY if with_memory else None,
        onboarding=onboarding,
        onboarding_slot=_SLOT if onboarding else None,
        user_emotion=emotion,
        perception=perception,
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
