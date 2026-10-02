"""The PIN format rule is defined in exactly one place (Plan 0050)."""

from pathlib import Path

import pytest

import server

_SERVER_ROOT = Path(server.__file__).resolve().parent
_PIN_RULE = "[0-9]{6,12}"


@pytest.mark.unit
def test_the_pin_format_is_defined_once() -> None:
    """Unlock requests and stored credentials cannot drift onto different rules."""
    definitions = [
        path.relative_to(_SERVER_ROOT).as_posix()
        for path in sorted(_SERVER_ROOT.rglob("*.py"))
        if _PIN_RULE in path.read_text(encoding="utf-8")
    ]

    assert definitions == ["cognition/pin_credentials.py"]
