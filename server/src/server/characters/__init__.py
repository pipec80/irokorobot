"""Character registry — load and build system prompts for robot personas."""

from datetime import date
import logging
from pathlib import Path
import re
import unicodedata

import yaml

from server.characters.base import CharacterProfile, PersonalityProfile
from server.characters.iroko import IROKO
from server.characters.nova import NOVA
from server.characters.parser import load_character_from_file
from server.cognition.identity import ActivePersonContext, ActivePersonStatus
from server.onboarding import OnboardingSlot
from server.schemas import MemoryContext
from server.settings import settings

logger = logging.getLogger(__name__)

# A character name is a file stem — restrict it to a safe alphabet so a
# crafted name (e.g. "../../secret") can never escape the profiles dir.
_SAFE_NAME = re.compile(r"^[a-z0-9_-]+$")

_DAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

# Observed live 2026-07-14: with no date in the prompt, the model announced
# "tu cumpleaños es justo hoy" out of thin air. The LLM cannot know the
# date — the code must tell it.
_TODAY_TEMPLATE = """
FECHA ACTUAL: hoy es {date_es}. Toda referencia a "hoy", cumpleaños o \
aniversarios debe salir de ESTA fecha — nunca la inventes."""


def current_date_es(today: date | None = None) -> str:
    """Return *today* in Spanish prose, e.g. ``"martes 14 de julio de 2026"``.

    Args:
        today: Date to format; defaults to the system date.
    """
    today = today or date.today()
    return (
        f"{_DAYS_ES[today.weekday()]} {today.day} de {_MONTHS_ES[today.month - 1]} de {today.year}"
    )


_REGISTRY: dict[str, CharacterProfile] = {
    "iroko": IROKO,
    "nova": NOVA,
}

# Cache for dynamic markdown profiles. Maps character name to (mtime, profile)
_CACHE: dict[str, tuple[float, CharacterProfile]] = {}

_PROFILES_DIR = Path(__file__).parent / "profiles"

# Anti-confabulation: small models fill memory gaps with invented names said
# with full confidence, which then get re-consolidated as facts (observed live
# 2026-07-06). This block is always present, with or without active memory.
_MEMORY_DISCIPLINE = """
MEMORY DISCIPLINE — non-negotiable:
- The memory block appended below (when present) is your ONLY source of \
truth about the owner's life: names, family, pets, dates, preferences.
- If asked about something NOT present in that memory, admit you don't \
remember it yet and ask them to tell you — NEVER invent or guess names, \
ages, or facts. A wrong confident answer poisons your own memory."""

_PRESENTATION_GUIDANCE_TEMPLATE = """
PRESENTATION GUIDANCE:
- The display name supplied for this turn is {display_name}.
- You may use it as an optional form of address, or use second-person phrasing,
  only when natural.
- Do not state that the name identifies the speaker.
- Do not infer relationships, personal facts, or authorization from it."""

_MAX_PRESENTATION_DISPLAY_NAME_LENGTH = 80

# D2/D3: the checklist decides WHAT to ask; the character decides HOW.
# The echo provokes correction — if the robot repeats a garbled name, the
# user fixes it next turn and fact versioning does the rest.
_ONBOARDING_GOAL_TEMPLATE = """
PRÓXIMO OBJETIVO de la entrevista: preguntale {question_hint}. UNA sola \
pregunta. Cuando el usuario te dé un dato importante (nombre, fecha, \
lugar), repetilo naturalmente en tu respuesta para confirmar que lo \
entendiste bien."""

# V0.5: what the camera sees THIS turn enters the prompt like memory does —
# the VLM provides the raw description, the character reacts in its own voice.
_PERCEPTION_TEMPLATE = """
--- Percepción visual (lo que ves AHORA MISMO por tu cámara) ---
{description}
Respondé a lo que el usuario preguntó usando lo que ves, en tu propia voz \
y en español. No repitas la descripción literal — reaccioná a ella."""

_EMOTION_ADAPTATIONS: dict[str, str] = {
    "joy": "- The user seems happy — match with warmth; you may be slightly more playful than usual.",
    "anger": "- The user seems frustrated — stay calm and measured; do NOT mirror the anger; validate briefly.",
    "sadness": "- The user seems sad — lead with empathy before answering; keep a gentle, unhurried tone.",
    "surprise": "- The user seems surprised — acknowledge it briefly and offer a short reassuring response.",
}

# Threshold tables: (min_value, directive). First match wins (highest threshold first).
_CURIOSITY_RULES: list[tuple[float, str]] = [
    (0.6, "- Ask one follow-up question each turn to learn more about the user."),
    (0.3, "- Ask a follow-up question every 2-3 turns when naturally curious."),
    (0.0, "- Do not ask follow-up questions unless strictly necessary."),
]
_VERBOSITY_RULES: list[tuple[float, str]] = [
    (0.6, "- Responses can reach up to 5 sentences when the topic warrants it."),
    (0.3, "- Keep responses to 2-3 sentences maximum."),
    (0.0, "- Limit responses to 1 sentence."),
]
_EMPATHY_RULES: list[tuple[float, str]] = [
    (0.7, "- Lead with empathy: acknowledge the user's emotional state before answering."),
    (0.4, "- Briefly acknowledge the user's emotional state when noticeable."),
    (0.0, "- Stay analytical and neutral in tone regardless of the user's mood."),
]
_HUMOR_RULES: list[tuple[float, str]] = [
    (0.5, "- Include humor or wit regularly — it is expected and welcomed."),
    (0.2, "- Add an occasional dry observation when it fits naturally — do not force it."),
    (0.0, "- Keep humor out of responses — stay serious and direct."),
]
_SOCIAL_ENERGY_DIRECTIVES: dict[str, str] = {
    "extrovert": "- Be expansive and enthusiastic; welcome small talk and tangents.",
    "introvert": "- Be terse; reserve warmth for topics you find genuinely interesting.",
    "moderate": "- Balance directness with warmth — neither cold nor over-eager.",
}


def _load_md_profile(name: str) -> CharacterProfile | None:
    """Return the markdown profile for *name*, or ``None`` to fall back.

    A ``profiles/<name>.md`` overrides the built-in Python character. The
    parsed profile is cached; it is re-read only when
    ``settings.character_hot_reload`` is on and the file's mtime advanced —
    so production stat's the file once and never blocks the request path
    afterwards, staying reproducible from the committed file.

    A malformed override never crashes the robot: the last good cached
    version is reused, or (if none) ``None`` sends the caller to the
    built-in registry.

    Args:
        name: Already-sanitized character name.

    Returns:
        The profile, or ``None`` when no usable override exists.
    """
    md_path = _PROFILES_DIR / f"{name}.md"
    if not md_path.exists():
        return None

    cached = _CACHE.get(name)
    if cached is not None and not settings.character_hot_reload:
        return cached[1]

    try:
        mtime = md_path.stat().st_mtime
        if cached is None or cached[0] < mtime:
            logger.info("Loading character profile from %s", md_path)
            profile = load_character_from_file(md_path)
            _CACHE[name] = (mtime, profile)
            return profile
    except (ValueError, yaml.YAMLError, OSError) as exc:
        logger.error("Invalid character profile %s — using fallback: %s", md_path, exc)
        return cached[1] if cached is not None else None
    return cached[1]


def get_character(name: str) -> CharacterProfile:
    """Return a character profile by name, falling back to Iroko if unknown.

    Resolution order: a validated ``profiles/<name>.md`` override, then the
    built-in Python registry, then Iroko. Names are restricted to a safe
    alphabet so a crafted name cannot read files outside ``profiles/``.

    Args:
        name: Character identifier (matches ROBOT_CHARACTER env var).

    Returns:
        The requested ``CharacterProfile``, or Iroko as default.
    """
    name = name.lower()
    if not _SAFE_NAME.match(name):
        logger.warning("Rejected unsafe character name %r — falling back to iroko", name)
        return IROKO

    override = _load_md_profile(name)
    if override is not None:
        return override

    builtin = _REGISTRY.get(name)
    if builtin is not None:
        return builtin

    logger.warning("Unknown character %r — falling back to iroko", name)
    return IROKO


def _safe_presentation_display_name(
    active_person: ActivePersonContext | None,
) -> str | None:
    """Return bounded, single-line display guidance safe for prompt interpolation."""
    if (
        active_person is None
        or active_person.status is not ActivePersonStatus.IDENTIFIED
        or not active_person.display_name
    ):
        return None
    display_name = active_person.display_name
    has_unsafe_control = any(
        unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"} for character in display_name
    )
    if (
        not display_name.strip()
        or len(display_name) > _MAX_PRESENTATION_DISPLAY_NAME_LENGTH
        or has_unsafe_control
    ):
        return None
    return display_name


def build_system_prompt(
    profile: CharacterProfile,
    context: MemoryContext | None,
    *,
    onboarding: bool = False,
    onboarding_slot: OnboardingSlot | None = None,
    user_emotion: str | None = None,
    active_person: ActivePersonContext | None = None,
    perception: str | None = None,
) -> str:
    """Assemble the full system prompt for a character.

    Args:
        profile: The active character profile.
        context: Memory context with entities and semantic memories, or None.
        onboarding: If True, appends first-run meeting instructions.
        onboarding_slot: Next missing checklist slot. When provided during
            onboarding, the prompt names the ONE datum to ask for this turn.
        user_emotion: Most frequent non-neutral emotion detected in recent turns.
            When provided, appends a behavioral adaptation directive.
        active_person: Internally resolved person context for this turn. An
            identified context with a display name contributes optional neutral
            presentation guidance; it never asserts identity or authorization.
        perception: What the camera sees this turn (VLM description). When
            provided, appended as a visual-perception block so the
            character reacts to it in its own voice.

    Returns:
        Complete system prompt string ready for the LLM.
    """
    parts = [
        profile.base_prompt,
        _personality_instructions(profile.personality),
        _MEMORY_DISCIPLINE,
        _TODAY_TEMPLATE.format(date_es=current_date_es()),
    ]
    display_name = _safe_presentation_display_name(active_person)
    if display_name is not None:
        parts.append(_PRESENTATION_GUIDANCE_TEMPLATE.format(display_name=display_name))
    if onboarding:
        parts.append(profile.onboarding_prompt)
        if onboarding_slot is not None:
            parts.append(
                _ONBOARDING_GOAL_TEMPLATE.format(question_hint=onboarding_slot.question_hint)
            )
    if user_emotion:
        adaptation = _emotion_adaptation(user_emotion)
        if adaptation:
            parts.append(adaptation)
    if context and (context.entities or context.memories):
        parts.append(_format_memory_block(context))
    if perception:
        parts.append(_PERCEPTION_TEMPLATE.format(description=perception))
    return "\n".join(parts)


def _pick(value: float, rules: list[tuple[float, str]]) -> str:
    """Return the directive for the first rule whose threshold the value meets.

    Args:
        value: Personality axis value in [0.0, 1.0].
        rules: Ordered list of (min_threshold, directive) pairs, highest first.

    Returns:
        Matching directive string.
    """
    for threshold, directive in rules:
        if value >= threshold:
            return directive
    return rules[-1][1]


def _personality_instructions(p: PersonalityProfile) -> str:
    """Convert numeric personality axes to concrete behavioral directives.

    Args:
        p: The personality profile to translate.

    Returns:
        A block of directives to append to the system prompt.
    """
    social = _SOCIAL_ENERGY_DIRECTIVES.get(p.social_energy, _SOCIAL_ENERGY_DIRECTIVES["moderate"])
    return "\n".join(
        [
            "\nBEHAVIOR DIRECTIVES — apply to every response:",
            _pick(p.curiosity, _CURIOSITY_RULES),
            _pick(p.verbosity, _VERBOSITY_RULES),
            _pick(p.empathy, _EMPATHY_RULES),
            _pick(p.humor, _HUMOR_RULES),
            social,
        ]
    )


def _emotion_adaptation(emotion: str) -> str:
    """Return a behavioral directive for the user's current emotional state.

    Args:
        emotion: Dominant non-neutral emotion from the last N turns.

    Returns:
        Directive block to append, or empty string for neutral/unknown.
    """
    directive = _EMOTION_ADAPTATIONS.get(emotion, "")
    if not directive:
        return ""
    return f"\nEMOTION ADAPTATION — user's current mood:\n{directive}"


def _format_memory_block(ctx: MemoryContext) -> str:
    """Format active memory as a block appended to the system prompt."""
    lines = ["\n--- Memoria activa sobre tu dueño ---"]
    for entity in ctx.entities:
        facts = ", ".join(f"{f.predicate}: {f.object_value}" for f in entity.facts)
        label = f"- {entity.name} ({entity.type})"
        lines.append(f"{label}: {facts}" if facts else label)
    for mem in ctx.memories:
        summary = mem.summary or mem.content[:120]
        lines.append(f"- [recuerdo] {summary}")
    return "\n".join(lines)
