"""Base types for robot character profiles."""

from dataclasses import dataclass, field
from typing import NamedTuple

#: Accepted values for the ``social_energy`` axis.
SOCIAL_ENERGY_VALUES = frozenset({"introvert", "moderate", "extrovert"})

#: The numeric personality axes, validated to the [0, 1] range.
_NUMERIC_AXES = ("curiosity", "verbosity", "empathy", "humor")


class _ForbiddenMarkerPair(NamedTuple):
    """A pair of legacy output-contract markers that must never co-occur.

    ``build_system_prompt`` is format-neutral by design (see
    ``server.characters.build_system_prompt``): each LLM adapter owns its
    own output contract. A base prompt carrying both markers below is a
    leftover of the old classic-JSON contract baked into character text —
    the exact structural cause of the hybrid-output bug (mangled
    ``EMOTION: joy {"response": ...}`` lines from Ollama).
    """

    first: str
    second: str


#: Legacy classic-JSON contract markers — rejected together in a base prompt.
_LEGACY_JSON_MARKERS = _ForbiddenMarkerPair('"response"', '"emotion"')


@dataclass(frozen=True)
class PersonalityProfile:
    """Numeric personality axes that drive concrete behavioral instructions.

    All float fields are in [0.0, 1.0]. They are converted to explicit
    prompt directives — not injected as adjectives. Values are validated
    on construction so a malformed markdown profile (e.g. ``curiosity:
    "alto"``) fails loudly at load time instead of at request time.

    Attributes:
        curiosity: How often to ask follow-up questions (0=never, 1=every turn).
        verbosity: Response length (0=1 sentence, 1=up to 5 sentences).
        empathy: Weight given to user's emotional state when shaping tone.
        humor: Frequency of humor — 0 is none, 1 is constant.
        social_energy: Interaction style: "introvert" | "moderate" | "extrovert".
    """

    curiosity: float = 0.6
    verbosity: float = 0.4
    empathy: float = 0.8
    humor: float = 0.3
    social_energy: str = "moderate"

    def __post_init__(self) -> None:
        """Validate axis types and ranges.

        Raises:
            ValueError: If a numeric axis is not a real number in [0, 1],
                or ``social_energy`` is not one of the accepted values.
        """
        for axis in _NUMERIC_AXES:
            value = getattr(self, axis)
            # bool is an int subclass — exclude it so `humor: true` is rejected.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Personality axis '{axis}' must be a number, got {value!r}")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"Personality axis '{axis}' must be in [0, 1], got {value}")
        if self.social_energy not in SOCIAL_ENERGY_VALUES:
            raise ValueError(
                f"social_energy must be one of {sorted(SOCIAL_ENERGY_VALUES)}, "
                f"got {self.social_energy!r}"
            )


@dataclass(frozen=True)
class CharacterProfile:
    """Immutable definition of a robot AI persona.

    Attributes:
        name: Identifier used in ROBOT_CHARACTER env var.
        base_prompt: Core identity, backstory, ethical limits, and response format.
        onboarding_prompt: Appended on first-run to guide introductory questions.
        personality: Numeric profile that generates concrete behavioral instructions.
    """

    name: str
    base_prompt: str
    onboarding_prompt: str
    personality: PersonalityProfile = field(default_factory=PersonalityProfile)

    def __post_init__(self) -> None:
        """Reject a base prompt that embeds an output-format contract.

        Raises:
            ValueError: If ``base_prompt`` contains both legacy JSON contract
                markers — identity/behavior text must stay format-neutral;
                only the LLM adapter (``llm.py`` or ``llm_streaming.py``)
                may append an output contract.
        """
        first, second = _LEGACY_JSON_MARKERS
        if first in self.base_prompt and second in self.base_prompt:
            raise ValueError(
                f"CharacterProfile {self.name!r} base_prompt embeds an output "
                f"format contract ({first}, {second}) — output format belongs "
                "solely to the LLM adapter, never to character text."
            )
