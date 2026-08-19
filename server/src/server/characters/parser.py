"""Parse a character profile from a Markdown file with YAML frontmatter.

Format (industry-standard frontmatter):

    ---
    curiosity: 0.8
    verbosity: 0.35
    ...
    ---
    # BASE PROMPT
    <identity, backstory, limits, and the JSON response contract>
    # ONBOARDING PROMPT
    <first-run interview guidance>

The parser is strict on purpose: a hand-edited profile that drops the base
prompt, embeds a legacy output-format contract, or uses an out-of-range
personality value must fail at load time (and fall back to the built-in
character), never silently ship a broken robot. Output format is not this
parser's concern — ``CharacterProfile.__post_init__`` rejects a base prompt
that embeds one; each LLM adapter owns appending its own contract.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import yaml

from server.characters.base import CharacterProfile, PersonalityProfile

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Frontmatter: leading `---`, YAML block, closing `---`, then the body.
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)
_BASE_HEADER = "# BASE PROMPT"
_ONBOARDING_HEADER = "# ONBOARDING PROMPT"

# Only these keys feed the personality; anything else in the frontmatter is
# ignored (no arbitrary attribute injection).
_PERSONALITY_KEYS = ("curiosity", "verbosity", "empathy", "humor", "social_energy")


def _split_body(body: str) -> tuple[str, str]:
    """Split the markdown body into (base_prompt, onboarding_prompt).

    Args:
        body: Everything after the frontmatter.

    Returns:
        The base prompt and onboarding prompt, both trimmed. Onboarding is
        empty when its header is absent.

    Raises:
        ValueError: If the base prompt is empty after parsing.
    """
    if _ONBOARDING_HEADER in body:
        base_part, onboarding_part = body.split(_ONBOARDING_HEADER, 1)
    else:
        base_part, onboarding_part = body, ""
    base_prompt = base_part.replace(_BASE_HEADER, "", 1).strip()
    if not base_prompt:
        raise ValueError("Character base prompt is empty")
    return base_prompt, onboarding_part.strip()


def _build_personality(meta: dict[str, Any]) -> PersonalityProfile:
    """Build a validated PersonalityProfile from frontmatter keys.

    Args:
        meta: Parsed YAML frontmatter.

    Returns:
        The personality profile (defaults fill any missing axis).

    Raises:
        ValueError: If any provided axis is out of range or the wrong type
            (validated by ``PersonalityProfile.__post_init__``).
    """
    kwargs = {key: meta[key] for key in _PERSONALITY_KEYS if key in meta}
    return PersonalityProfile(**kwargs)


def _parse_frontmatter(content: str, name: str) -> tuple[dict[str, object], str]:
    """Split raw markdown text into parsed YAML frontmatter and the raw body.

    Args:
        content: Full markdown text (frontmatter + body).
        name: Character name, used only to phrase error messages.

    Returns:
        Tuple of (frontmatter mapping, raw body text after the closing
        ``---``).

    Raises:
        ValueError: If the frontmatter delimiters are missing or the parsed
            YAML is not a mapping.
        yaml.YAMLError: If the frontmatter is not valid YAML.
    """
    match = _FRONTMATTER.match(content.strip() + "\n")
    if match is None:
        raise ValueError(f"No YAML frontmatter found in profile {name!r}")

    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise ValueError(f"Frontmatter in profile {name!r} is not a YAML mapping")
    return meta, match.group(2)


def parse_character(content: str, name: str) -> CharacterProfile:
    """Parse and validate a CharacterProfile from raw markdown text.

    Pure function (no I/O) so every validation path is unit-testable.

    Args:
        content: Full markdown text (frontmatter + body).
        name: Character name (normally the file stem), lowercased here.

    Returns:
        A parsed, validated ``CharacterProfile``.

    Raises:
        ValueError: If the frontmatter is missing, not a mapping, the base
            prompt is empty, the base prompt embeds a legacy output-format
            contract (see ``CharacterProfile.__post_init__``), or a
            personality value is invalid.
        yaml.YAMLError: If the frontmatter is not valid YAML.
    """
    meta, body = _parse_frontmatter(content, name)
    base_prompt, onboarding_prompt = _split_body(body)

    return CharacterProfile(
        name=name.lower(),
        base_prompt=base_prompt,
        onboarding_prompt=onboarding_prompt,
        personality=_build_personality(meta),
    )


def load_character_from_file(filepath: Path) -> CharacterProfile:
    """Load and validate a CharacterProfile from a markdown file.

    Args:
        filepath: Path to the ``.md`` profile.

    Returns:
        A parsed, validated ``CharacterProfile`` named after the file stem.

    Raises:
        ValueError: If the profile is malformed (see ``parse_character``).
        yaml.YAMLError: If the frontmatter is not valid YAML.
        OSError: If the file cannot be read.
    """
    return parse_character(filepath.read_text(encoding="utf-8"), filepath.stem)
