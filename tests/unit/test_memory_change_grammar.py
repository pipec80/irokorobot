"""The closed grammar of changing a memory by voice (Plan 0086 Task 5, D-4). Canaries only."""

from __future__ import annotations

import pytest
from server.cognition.intent_resolution import resolve_information_need
from server.cognition.memory_change import MemoryChange, parse_memory_change
from server.cognition.response_plan import InformationNeed
from server.memory.preference_gate import match_preference

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "message, expected",
    [
        (
            "Ya no me gusta el té.",
            MemoryChange("correct", "likes", "el té", None, None),
        ),
        (
            "Ya no me gusta el té, ahora prefiero el café.",
            MemoryChange("correct", "likes", "el té", "el café", "prefers"),
        ),
        (
            "Me equivoqué, ya no me gustan los porotos.",
            MemoryChange("correct", "likes", "los porotos", None, None),
        ),
        (
            "Ya no odio el brócoli, ahora me gusta el brócoli.",
            MemoryChange("correct", "dislikes", "el brócoli", "el brócoli", "likes"),
        ),
        ("Ya no prefiero el mate.", MemoryChange("correct", "prefers", "el mate", None, None)),
        (
            "No quiero saber nunca más de Canaria.",
            MemoryChange("archive", None, "Canaria", None, None),
        ),
        (
            "Mi mejor amiga Canaria me traicionó; no quiero saber nunca más de ella.",
            MemoryChange("archive", None, "Canaria", None, None),
        ),
        ("No me hables más de Canaria.", MemoryChange("archive", None, "Canaria", None, None)),
        (
            "No me recuerdes más lo del paseo.",
            MemoryChange("archive", None, "paseo", None, None),
        ),
        ("Olvídate de Canaria, por favor.", MemoryChange("archive", None, "Canaria", None, None)),
    ],
)
def test_each_form_parses(message: str, expected: MemoryChange) -> None:
    assert parse_memory_change(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "¿Ya no me gusta el té?",
        "Si ya no me gusta el té, ¿qué tomo?",
        "A mi hermano ya no le gusta el té.",
        "Ya no me gusta.",
        "Olvídalo.",
        "Olvídalo, no importa.",
        "Mi amiga Canaria y mi amigo Zorzal pelearon; no quiero saber más de ella.",
        "No quiero saber más de ella.",
        "Ya no me gusta que me hables así.",
        "Me gusta el té.",
    ],
)
def test_these_do_not_parse(message: str) -> None:
    assert parse_memory_change(message) is None


def test_a_refinement_is_neither_a_change_nor_a_taste() -> None:
    """Case 3 (D-3): a side remark is just a new story in the diary."""
    message = "Fuimos al restaurante La Ola y me gustó más."

    assert parse_memory_change(message) is None
    assert match_preference(message).matches == ()


def test_the_gate_still_refuses_ya_no_me_gusta() -> None:
    assert match_preference("Ya no me gusta el té.").matches == ()


def test_the_need_resolves_only_with_the_flag() -> None:
    message = "Ya no me gusta el té."

    assert resolve_information_need(message).need is InformationNeed.GENERIC_CONVERSATION
    assert resolve_information_need(message, changes=True).need is InformationNeed.MEMORY_CHANGE
    assert (
        resolve_information_need("¿Qué hora es?", changes=True).need
        is not InformationNeed.MEMORY_CHANGE
    )
