"""What the robot says about the owner's relatives (Plan 0078 D-9, Plan 0080 D-4 and D-5).

Canary names only. The word of a side is a relation, never an attribute: the sentence builder
tells the mother from the father, and never labels a name that was not recorded with a side.
"""

from __future__ import annotations

import pytest
from server.cognition.household_tools import Side, SidedNames, SideGroup
from server.cognition.models import KnowledgeStatus
from server.cognition.relatives_answers import relatives_sentence, sided_sentence

pytestmark = pytest.mark.unit


def _parents(
    *,
    female: tuple[str, ...] = (),
    male: tuple[str, ...] = (),
    unlabelled: tuple[str, ...] = (),
) -> SidedNames:
    return SidedNames(status=KnowledgeStatus.KNOWN, female=female, male=male, unlabelled=unlabelled)


def test_the_mother_is_told_when_she_is_recorded() -> None:
    names = _parents(female=("Zeta",), male=("Omega",))

    assert sided_sentence(SideGroup.PARENTS, Side.FEMALE, names) == "Tu mamá se llama Zeta."


def test_the_father_is_told_when_he_is_recorded() -> None:
    names = _parents(female=("Zeta",), male=("Omega",))

    assert sided_sentence(SideGroup.PARENTS, Side.MALE, names) == "Tu papá se llama Omega."


def test_two_mothers_use_the_plural() -> None:
    names = _parents(female=("Zeta", "Canary"))

    assert (
        sided_sentence(SideGroup.PARENTS, Side.FEMALE, names)
        == "Tus mamás se llaman Canary y Zeta."
    )


def test_two_fathers_use_the_plural() -> None:
    names = _parents(male=("Zeta", "Omega"))

    assert (
        sided_sentence(SideGroup.PARENTS, Side.MALE, names) == "Tus papás se llaman Omega y Zeta."
    )


def test_the_plural_question_names_both_sorted() -> None:
    names = _parents(female=("Zeta",), male=("Omega",))

    assert sided_sentence(SideGroup.PARENTS, None, names) == "Tus papás se llaman Omega y Zeta."


def test_the_plural_question_names_every_side_and_the_unlabelled() -> None:
    names = _parents(female=("Zeta",), male=("Omega",), unlabelled=("Canary",))

    assert (
        sided_sentence(SideGroup.PARENTS, None, names)
        == "Tus papás se llaman Canary, Omega y Zeta."
    )


def test_the_plural_question_with_one_unlabelled_name_says_both_words() -> None:
    names = _parents(unlabelled=("Zeta",))

    assert sided_sentence(SideGroup.PARENTS, None, names) == "Tu papá o tu mamá se llama Zeta."


def test_the_plural_question_with_one_mother_keeps_her_side() -> None:
    names = _parents(female=("Zeta",))

    assert sided_sentence(SideGroup.PARENTS, None, names) == "Tu mamá se llama Zeta."


def test_the_plural_question_with_one_father_keeps_his_side() -> None:
    names = _parents(male=("Omega",))

    assert sided_sentence(SideGroup.PARENTS, None, names) == "Tu papá se llama Omega."


def test_the_mother_asked_when_the_parents_have_no_side_does_not_guess() -> None:
    names = _parents(unlabelled=("Omega", "Zeta"))

    assert (
        sided_sentence(SideGroup.PARENTS, Side.FEMALE, names)
        == "No tengo claro cuál de ellos es tu mamá. Tus papás se llaman Omega y Zeta."
    )


def test_the_father_asked_when_the_parents_have_no_side_does_not_guess() -> None:
    names = _parents(unlabelled=("Zeta",))

    assert (
        sided_sentence(SideGroup.PARENTS, Side.MALE, names)
        == "No tengo claro si es tu papá. Tu papá o tu mamá se llama Zeta."
    )


def test_the_mother_asked_of_one_parent_without_a_side_does_not_say_which_of_them() -> None:
    names = _parents(unlabelled=("Zeta",))

    assert (
        sided_sentence(SideGroup.PARENTS, Side.FEMALE, names)
        == "No tengo claro si es tu mamá. Tu papá o tu mamá se llama Zeta."
    )


def test_the_unclear_answer_names_every_member_of_the_group() -> None:
    names = _parents(male=("Omega",), unlabelled=("Zeta",))

    assert (
        sided_sentence(SideGroup.PARENTS, Side.FEMALE, names)
        == "No tengo claro cuál de ellos es tu mamá. Tus papás se llaman Omega y Zeta."
    )


def test_the_asked_side_absent_while_the_other_side_is_complete_has_no_answer() -> None:
    names = _parents(female=("Zeta",))

    assert sided_sentence(SideGroup.PARENTS, Side.MALE, names) is None


def test_no_parent_of_any_kind_has_no_answer() -> None:
    assert sided_sentence(SideGroup.PARENTS, Side.FEMALE, _parents()) is None
    assert sided_sentence(SideGroup.PARENTS, Side.MALE, _parents()) is None
    assert sided_sentence(SideGroup.PARENTS, None, _parents()) is None


def test_the_names_stay_out_of_the_representation() -> None:
    names = _parents(female=("Zeta",), male=("Omega",), unlabelled=("Canary",))

    shown = repr(names)

    assert "Zeta" not in shown
    assert "Omega" not in shown
    assert "Canary" not in shown


@pytest.mark.parametrize(
    "predicate, names, said",
    [
        ("has_parent", ("Zeta",), "Tu papá o tu mamá se llama Zeta."),
        ("has_parent", ("Omega", "Zeta"), "Tus papás se llaman Omega y Zeta."),
        ("has_sibling", ("Zeta",), "Tu hermano o hermana se llama Zeta."),
        ("has_grandparent", ("Omega", "Zeta"), "Tus abuelos se llaman Omega y Zeta."),
        ("has_grandchild", ("Zeta",), "Tu nieto o nieta se llama Zeta."),
        ("partner_of", ("Zeta",), "Tu pareja se llama Zeta."),
        ("pet_of", ("Omega", "Zeta"), "Tus mascotas se llaman Omega y Zeta."),
    ],
)
def test_the_other_relations_keep_their_templates(
    predicate: str, names: tuple[str, ...], said: str
) -> None:
    assert relatives_sentence(predicate, names) == said
