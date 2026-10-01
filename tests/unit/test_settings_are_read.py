"""Every server setting is read somewhere (Plan 0050): a dead knob misleads whoever tunes it."""

from pathlib import Path
import re

import pytest
from server.settings import Settings

_ROOT = Path(__file__).resolve().parents[2]
_SOURCES = [
    *(_ROOT / "server" / "src").rglob("*.py"),
    *(_ROOT / "robot" / "src").rglob("*.py"),
    *(_ROOT / "scripts").rglob("*.py"),
]


def _unread_settings() -> list[str]:
    """Return the setting names that no source file reads as an attribute."""
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in _SOURCES)
    return sorted(name for name in Settings.model_fields if not re.search(rf"\.{name}\b", corpus))


@pytest.mark.unit
def test_every_setting_is_read_by_the_code() -> None:
    """A setting nothing reads is removed, not left as a knob that does nothing."""
    assert _unread_settings() == []
