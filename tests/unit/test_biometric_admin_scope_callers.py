"""Every caller of biometric administration unlocks for that operation (Plan 0051)."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_ADMIN_ROUTES = ("/auth/owner/face/", "/auth/owner/voice/")
_ADMIN_CALLERS = {"face_auth_demo.py", "onboard.py", "speaker_auth_demo.py"}
_SCOPE_FIELD = '"scope": "biometric_admin"'


def _scripts_calling_the_admin_routes() -> dict[str, str]:
    sources = {
        path.name: path.read_text(encoding="utf-8") for path in (_ROOT / "scripts").glob("*.py")
    }
    return {
        name: text
        for name, text in sources.items()
        if any(route in text for route in _ADMIN_ROUTES)
    }


@pytest.mark.unit
def test_the_scripts_that_administer_biometrics_are_exactly_the_known_ones() -> None:
    assert set(_scripts_calling_the_admin_routes()) == _ADMIN_CALLERS


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(_ADMIN_CALLERS))
def test_a_biometric_admin_script_unlocks_with_the_admin_scope(name: str) -> None:
    """A read grant is refused by the admin routes, so these scripts must ask for the other."""
    assert _SCOPE_FIELD in _scripts_calling_the_admin_routes()[name]


@pytest.mark.unit
def test_the_robot_never_asks_for_the_administration_scope() -> None:
    """The robot keeps only read grants: it is a generic client of the audio API."""
    sources = (_ROOT / "robot" / "src" / "robot").rglob("*.py")

    assert not [path.name for path in sources if "biometric_admin" in path.read_text("utf-8")]
