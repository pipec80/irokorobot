"""The owner's profile card: a closed list, small, rendered as data (Plan 0074, ADR 0026 decision 2).

Pure: it takes rows the caller already authorized and returns text. It reads nothing, asks no
policy and logs only counts. Two renderers exist: the prompt block the model sees on every
identified voice turn, and the sentence the controller speaks on «¿qué sabes de mí?».

Nothing about the person other than the allow-listed values enters: no entity name, id, role,
sensitivity or relative. A value is cleaned to one short quoted line so a stored taste can never
read as an instruction.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final, Literal
import unicodedata

from server.cognition.authorization import DataSensitivity, DataVisibility
from server.memory.relational_v4 import AssertionLifecycle

if TYPE_CHECKING:
    from collections.abc import Sequence

    from server.memory.relational_v4 import LiteralFactV4

logger = logging.getLogger(__name__)

__all__ = [
    "CARD_HEADER",
    "CARD_PREDICATES",
    "MAX_CARD_CHARS",
    "MAX_CARD_TASTES",
    "MAX_VALUE_CHARS",
    "CardTaste",
    "ProfileCard",
    "build_card",
    "render_prompt_card",
    "render_summary",
]

_PREFERRED_NAME: Final = "preferred_name"
_ADDRESS_FORM: Final = "address_form"
_TASTE_PREDICATES: Final = ("likes", "dislikes", "prefers")
CARD_PREDICATES: Final = frozenset({_PREFERRED_NAME, _ADDRESS_FORM, *_TASTE_PREDICATES})
MAX_CARD_CHARS: Final = 600
MAX_CARD_TASTES: Final = 12
MAX_VALUE_CHARS: Final = 80
CARD_HEADER: Final = "--- Lo que sabes de la persona con quien hablas ---"

_CARD_FOOTER: Final = (
    "Es memoria autorizada: apóyate en ella solo si viene al caso y no inventes nada "
    "que no esté aquí."
)
_EMPTY_SUMMARY: Final = "Todavía no me has contado cosas que pueda recordar."
_SUMMARY_OPENING: Final = "Esto es lo que sé de ti."
_ADDRESS_FORMS: Final = {"tu": "tú", "usted": "usted"}
# Zero width joiner: kept so a joined emoji sequence survives; every other format character
# (bidirectional overrides among them) is dropped with the control characters.
_ZERO_WIDTH_JOINER: Final = "‍"
_DROPPED_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})

# Prompt line label and spoken label per taste predicate.
_PROMPT_LABELS: Final = {"likes": "Le gusta", "dislikes": "No le gusta", "prefers": "Prefiere"}
_SPOKEN_PREFIXES: Final = {
    "likes": "Me has dicho que te gusta",
    "dislikes": "Me has dicho que no te gusta",
    "prefers": "Prefieres",
}


@dataclass(frozen=True)
class CardTaste:
    """One taste of the card."""

    predicate: Literal["likes", "dislikes", "prefers"]
    value: str


@dataclass(frozen=True)
class ProfileCard:
    """What the robot has at hand about the person it is talking to.

    Attributes:
        preferred_name: How the person likes to be called, or ``None``.
        address_form: ``tu`` or ``usted``, or ``None``.
        tastes: The person's tastes, newest first.
    """

    preferred_name: str | None
    address_form: Literal["tu", "usted"] | None
    tastes: tuple[CardTaste, ...]

    @property
    def is_empty(self) -> bool:
        """Whether the card holds nothing at all."""
        return self.preferred_name is None and self.address_form is None and not self.tastes


def _clean(value: str) -> str:
    """Return *value* as one short line of plain data, or an empty string.

    Whitespace collapses to single spaces, control characters go, a double quote becomes a single
    one (so the renderer's quotes stay balanced) and the result is cut at ``MAX_VALUE_CHARS``.
    """
    spaced = "".join(" " if char.isspace() else char for char in value)
    kept = "".join(
        char
        for char in spaced
        if char == _ZERO_WIDTH_JOINER or unicodedata.category(char) not in _DROPPED_CATEGORIES
    )
    return " ".join(kept.replace('"', "'").split())[:MAX_VALUE_CHARS].rstrip()


def _is_card_row(row: LiteralFactV4) -> bool:
    """Defensive filter: the reader already filters, a wrong row must still never get in."""
    return (
        row.predicate in CARD_PREDICATES
        and row.lifecycle is AssertionLifecycle.ACTIVE
        and row.visibility == DataVisibility.PERSONAL
        and row.sensitivity == DataSensitivity.NORMAL
    )


def build_card(rows: Sequence[LiteralFactV4]) -> ProfileCard:
    """Build the card from the person's own rows, newest first.

    Args:
        rows: Literal facts the caller already authorized, newest first (``id`` descending).
            A row outside the allow-list, not active, not ``personal`` or not ``normal`` is
            ignored even if handed in.

    Returns:
        The card: for a single-valued predicate the newest value wins; the tastes keep their
        order and stop at ``MAX_CARD_TASTES``.
    """
    name: str | None = None
    form: Literal["tu", "usted"] | None = None
    tastes: list[CardTaste] = []
    for row in filter(_is_card_row, rows):
        value = _clean(row.value_text)
        if not value:
            continue
        match row.predicate:
            case "preferred_name":
                name = name or value
            case "address_form":
                if form is None and value in _ADDRESS_FORMS:
                    form = "usted" if value == "usted" else "tu"
            case "likes" | "dislikes" | "prefers" as predicate:
                tastes.append(CardTaste(predicate, value))
    if len(tastes) > MAX_CARD_TASTES:
        logger.debug("Profile card: %d tastes over the cap left out", len(tastes) - MAX_CARD_TASTES)
    return ProfileCard(name, form, tuple(tastes[:MAX_CARD_TASTES]))


def _render_prompt(card: ProfileCard, tastes: Sequence[CardTaste]) -> str:
    lines = [CARD_HEADER]
    identity: list[str] = []
    if card.preferred_name is not None:
        identity.append(f'Nombre: "{card.preferred_name}".')
    if card.address_form is not None:
        identity.append(f"Trato: {_ADDRESS_FORMS[card.address_form]}.")
    if identity:
        lines.append("- " + " ".join(identity))
    for predicate in _TASTE_PREDICATES:
        quoted = ", ".join(f'"{taste.value}"' for taste in tastes if taste.predicate == predicate)
        if quoted:
            lines.append(f"- {_PROMPT_LABELS[predicate]}: {quoted}.")
    lines.append(_CARD_FOOTER)
    return "\n".join(lines)


def render_prompt_card(card: ProfileCard) -> str | None:
    """Render the card as the block that enters the system prompt.

    Args:
        card: The card to render.

    Returns:
        The block, at most ``MAX_CARD_CHARS`` long (the oldest tastes are dropped until it
        fits), or ``None`` when the card is empty.
    """
    if card.is_empty:
        return None
    tastes = list(card.tastes)
    rendered = _render_prompt(card, tastes)
    while len(rendered) > MAX_CARD_CHARS and tastes:
        tastes.pop()
        rendered = _render_prompt(card, tastes)
    if len(tastes) < len(card.tastes):
        logger.debug(
            "Profile card: %d tastes left out by the size cap", len(card.tastes) - len(tastes)
        )
    return rendered


def render_summary(card: ProfileCard) -> str:
    """Render what the card holds as the sentence the robot speaks.

    Args:
        card: The card to read back.

    Returns:
        The fixed-wording summary, or the fixed «nothing yet» phrase for an empty card.
    """
    if card.is_empty:
        return _EMPTY_SUMMARY
    sentences = [_SUMMARY_OPENING]
    if card.preferred_name is not None:
        sentences.append(f"Te llamo {card.preferred_name}.")
    if card.address_form is not None:
        sentences.append(f"Te trato de {_ADDRESS_FORMS[card.address_form]}.")
    for predicate in _TASTE_PREDICATES:
        values = ", ".join(taste.value for taste in card.tastes if taste.predicate == predicate)
        if values:
            sentences.append(f"{_SPOKEN_PREFIXES[predicate]}: {values}.")
    return " ".join(sentences)
