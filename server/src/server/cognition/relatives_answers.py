"""What the robot says about the owner's relatives: fixed sentences, no model (ADR 0028 d. 9).

The spoken strings are Spanish with tuteo (Plan 0064). The names are joined with ``spanish_join``
and every sentence is a template, so the 3B model never words a name.
"""

from typing import Final

from server.cognition.household_tools import Side, SidedNames, SideGroup
from server.cognition.sensitive_answers import spanish_join

__all__ = ["relatives_sentence", "sided_sentence"]

# «Tu papá o tu mamá se llama A.» / «Tus papás se llaman A y B.» (Plan 0078 D-9). A relation whose
# side is not told apart says both words for one name; a pet or a partner has one word.
_RELATIVES_TEMPLATES: Final[dict[str, tuple[str, str]]] = {
    "has_parent": ("Tu papá o tu mamá se llama {}.", "Tus papás se llaman {}."),
    "has_sibling": ("Tu hermano o hermana se llama {}.", "Tus hermanos se llaman {}."),
    "has_grandparent": ("Tu abuelo o abuela se llama {}.", "Tus abuelos se llaman {}."),
    "has_grandchild": ("Tu nieto o nieta se llama {}.", "Tus nietos se llaman {}."),
    "partner_of": ("Tu pareja se llama {}.", "Tus parejas se llaman {}."),
    "pet_of": ("Tu mascota se llama {}.", "Tus mascotas se llaman {}."),
}

# The relations whose side is recorded (Plan 0080 D-5): one sentence per asked side, singular and
# plural, and the word the «no tengo claro» answer uses for the asked side.
_SIDED_TEMPLATES: Final[dict[tuple[SideGroup, Side], tuple[str, str]]] = {
    (SideGroup.PARENTS, Side.FEMALE): ("Tu mamá se llama {}.", "Tus mamás se llaman {}."),
    (SideGroup.PARENTS, Side.MALE): ("Tu papá se llama {}.", "Tus papás se llaman {}."),
}
_ASKED_WORD: Final[dict[tuple[SideGroup, Side], str]] = {
    (SideGroup.PARENTS, Side.FEMALE): "tu mamá",
    (SideGroup.PARENTS, Side.MALE): "tu papá",
}
# The whole group, when its sides are not told apart: the unsided template of the relation.
_WHOLE_GROUP: Final[dict[SideGroup, str]] = {SideGroup.PARENTS: "has_parent"}
_UNCLEAR: Final = "No tengo claro cuál de ellos es {}. {}"
_UNCLEAR_ONE: Final = "No tengo claro si es {}. {}"


def relatives_sentence(predicate: str, names: tuple[str, ...]) -> str:
    """Word the names of one relation with its fixed singular or plural template.

    Args:
        predicate: ``has_parent``, ``has_sibling``, ``has_grandparent``, ``has_grandchild``,
            ``partner_of`` or ``pet_of``.
        names: The names, sorted.

    Returns:
        The Spanish sentence, singular for one name and plural for several.
    """
    one, several = _RELATIVES_TEMPLATES[predicate]
    return (one if len(names) == 1 else several).format(spanish_join(names))


def sided_sentence(group: SideGroup, asked: Side | None, names: SidedNames) -> str | None:
    """Word the answer about a group of relatives whose side is recorded.

    Args:
        group: The relatives asked about.
        asked: The side asked for, or ``None`` for the plural question about the whole group
            (a group of one member is told with that member's recorded side).
        names: The names read for the group, by recorded side.

    Returns:
        The sentence; ``None`` when the controller must say «No tengo registrado eso.»: the
        group is empty, or the asked side is absent while no member lacks a side. A side that
        was not recorded is never guessed: when some member has no side the answer says so and
        names the whole group.
    """
    everyone = tuple(sorted((*names.female, *names.male, *names.unlabelled)))
    if not everyone:
        return None
    whole = relatives_sentence(_WHOLE_GROUP[group], everyone)
    if asked is None:
        # One person keeps the side that is recorded for them; several are named together.
        asked = _side_of_the_only_member(names) if len(everyone) == 1 else None
        if asked is None:
            return whole
    recorded = tuple(sorted(names.female if asked is Side.FEMALE else names.male))
    if recorded:
        one, several = _SIDED_TEMPLATES[(group, asked)]
        return (one if len(recorded) == 1 else several).format(spanish_join(recorded))
    if names.unlabelled:
        unclear = _UNCLEAR_ONE if len(everyone) == 1 else _UNCLEAR
        return unclear.format(_ASKED_WORD[(group, asked)], whole)
    return None


def _side_of_the_only_member(names: SidedNames) -> Side | None:
    """The recorded side of a group of exactly one member, or ``None`` when it is not recorded."""
    if names.female:
        return Side.FEMALE
    return Side.MALE if names.male else None
