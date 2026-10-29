"""Parse a character profile from a Markdown file with YAML frontmatter.

Format (industry-standard frontmatter):

    ---
    curiosity: 0.8
    verbosity: 0.35
    ...
    ---
    # BASE PROMPT
    <identity, backstory and limits>

A ``# ONBOARDING PROMPT`` section is refused: the first-run interview went away with the legacy
memory path (Plan 0076), and silently keeping its text would merge it into the base prompt.

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


def _base_prompt(body: str) -> str:
    """Return the trimmed base prompt of the markdown body.

    Args:
        body: Everything after the frontmatter.

    Returns:
        The base prompt.

    Raises:
        ValueError: If the body still has an onboarding section, or the base prompt is empty.
    """
    if _ONBOARDING_HEADER in body:
        raise ValueError("Character profiles no longer take an onboarding section")
    base_prompt = body.replace(_BASE_HEADER, "", 1).strip()
    if not base_prompt:
        raise ValueError("Character base prompt is empty")
    return base_prompt


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
        ValueError: If the frontmatter is missing, not a mapping, the body has an
            onboarding section, the base prompt is empty, the base prompt embeds a legacy output-format
            contract (see ``CharacterProfile.__post_init__``), or a
            personality value is invalid.
        yaml.YAMLError: If the frontmatter is not valid YAML.
    """
    meta, body = _parse_frontmatter(content, name)

    return CharacterProfile(
        name=name.lower(),
        base_prompt=_base_prompt(body),
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
