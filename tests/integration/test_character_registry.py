"""Integration tests for character resolution: markdown override, safe-name
guard, the hot-reload dev gate, and fail-safe fallback (touches the FS)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from server.characters import get_character
from server.characters.iroko import IROKO
from server.settings import settings

from server import characters

_PROFILE = """\
---
curiosity: 0.9
verbosity: 0.6
empathy: 0.9
humor: 0.8
social_energy: "extrovert"
---
# BASE PROMPT
Sos {who}.

FORMATO — JSON: {{"response": "<t>", "emotion": "<e>"}}

# ONBOARDING PROMPT
Saludá.
"""


@pytest.fixture
def profiles_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the registry at a temp profiles dir with an empty cache."""
    monkeypatch.setattr(characters, "_PROFILES_DIR", tmp_path)
    monkeypatch.setattr(characters, "_CACHE", {})
    monkeypatch.setattr(settings, "character_hot_reload", False)
    return tmp_path


def _write(dir_: Path, name: str, who: str = "un vendedor") -> Path:
    path = dir_ / f"{name}.md"
    path.write_text(_PROFILE.format(who=who), encoding="utf-8")
    return path


@pytest.mark.integration
def test_unknown_name_falls_back_to_iroko(profiles_dir: Path) -> None:
    assert get_character("inexistente") is IROKO


@pytest.mark.integration
def test_builtin_without_override_uses_registry(profiles_dir: Path) -> None:
    """With no iroko.md present, the built-in Python profile is returned."""
    assert get_character("iroko") is IROKO


@pytest.mark.integration
@pytest.mark.parametrize("evil", ["../secret", "..\\secret", "foo/bar", "a.b", "iroko;rm"])
def test_unsafe_names_never_read_outside_and_fall_back(profiles_dir: Path, evil: str) -> None:
    """A crafted name must be rejected before any path is built."""
    assert get_character(evil) is IROKO


@pytest.mark.integration
def test_markdown_profile_is_loaded(profiles_dir: Path) -> None:
    _write(profiles_dir, "vendedor")

    profile = get_character("vendedor")

    assert profile.name == "vendedor"
    assert profile.personality.social_energy == "extrovert"
    assert "un vendedor" in profile.base_prompt


@pytest.mark.integration
def test_markdown_overrides_builtin(profiles_dir: Path) -> None:
    """A profiles/iroko.md wins over the built-in Iroko."""
    _write(profiles_dir, "iroko", who="Iroko recargado")

    profile = get_character("iroko")

    assert profile is not IROKO
    assert "Iroko recargado" in profile.base_prompt


@pytest.mark.integration
def test_broken_profile_no_cache_falls_back(profiles_dir: Path) -> None:
    """An invalid override with nothing cached degrades to the built-in."""
    (profiles_dir / "iroko.md").write_text("garbage, no frontmatter", encoding="utf-8")

    assert get_character("iroko") is IROKO


@pytest.mark.integration
def test_broken_profile_reuses_last_good_cache(
    profiles_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A good load then a broken edit keeps serving the last good version."""
    monkeypatch.setattr(settings, "character_hot_reload", True)
    path = _write(profiles_dir, "vendedor", who="bueno")
    assert "bueno" in get_character("vendedor").base_prompt

    path.write_text("roto sin frontmatter", encoding="utf-8")
    _touch_newer(path)

    assert "bueno" in get_character("vendedor").base_prompt


@pytest.mark.integration
def test_hot_reload_off_serves_cache_after_edit(profiles_dir: Path) -> None:
    """Hot-reload OFF: a changed file is NOT re-read — cache wins."""
    path = _write(profiles_dir, "vendedor", who="original")
    assert "original" in get_character("vendedor").base_prompt

    path.write_text(_PROFILE.format(who="editado"), encoding="utf-8")
    _touch_newer(path)

    assert "original" in get_character("vendedor").base_prompt


@pytest.mark.integration
def test_hot_reload_on_picks_up_edit(profiles_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hot-reload ON: a newer mtime triggers a fresh parse."""
    monkeypatch.setattr(settings, "character_hot_reload", True)
    path = _write(profiles_dir, "vendedor", who="original")
    assert "original" in get_character("vendedor").base_prompt

    path.write_text(_PROFILE.format(who="editado"), encoding="utf-8")
    _touch_newer(path)

    assert "editado" in get_character("vendedor").base_prompt


def _touch_newer(path: Path) -> None:
    """Bump the file mtime 10s forward — deterministic across filesystems."""
    future = os.path.getmtime(path) + 10
    os.utime(path, (future, future))
