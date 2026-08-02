"""Unit tests for the deterministic visual-intent triggers (V0.5)."""

from __future__ import annotations

import pytest
from server.vision import wants_enroll, wants_vision


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "¿Qué ves?",
        "que ves ahí",
        "Iroko, ¿qué estás viendo?",
        "QUE VES",
        "dime qué ves ahora",
        "mira esto que te traje",
        "¿puedes ver lo que tengo?",
        "¿ves algo raro?",
        "¿qué tengo en la mano?",
        "describe lo que ves",
    ],
)
def test_visual_questions_trigger(text: str) -> None:
    """Visual questions must trigger, with or without accents/case."""
    assert wants_vision(text) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "hola robot, ¿cómo estás?",
        "nos vemos mañana",
        "aunque vestirse rápido es difícil",  # contains "que ves..." inside a word
        "me gusta la televisión",
        "¿cómo se llaman mis hijos?",
        "hoy revisé el motor",
    ],
)
def test_normal_conversation_does_not_trigger(text: str) -> None:
    """Ordinary turns (including tricky substrings) must NOT trigger."""
    assert wants_vision(text) is False


# --- V1: explicit face-enrollment triggers ---


@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected_name",
    [
        ("Iroko, aprende mi cara, soy Felipe", "Felipe"),
        ("recuerda su cara, ella es Valentina", "Valentina"),
        ("te presento a Dominga", "Dominga"),
        ("mírame bien, yo soy Máximo", "Máximo"),
        ("MEMORIZA MI CARA, SOY FELIPE", "Felipe"),
    ],
)
def test_enroll_phrases_capture_the_name(text: str, expected_name: str) -> None:
    """Explicit cue + name in the same utterance → enrollment with consent."""
    assert wants_enroll(text) == expected_name


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "me llamo Felipe",  # onboarding introduction — must NOT hijack the turn
        "yo soy Felipe",  # plain introduction, no face cue
        "aprende mi cara",  # cue without a name
        "hola, ¿cómo estás?",
        "¿qué ves?",  # vision yes, enroll no
    ],
)
def test_non_enroll_phrases_return_none(text: str) -> None:
    """Introductions and cue-less phrases never trigger enrollment."""
    assert wants_enroll(text) is None
