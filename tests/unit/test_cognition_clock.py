"""The cognition layer has one production clock (Plan 0055)."""

from datetime import UTC

from server.cognition import (
    clock,
    face_authentication,
    identity_fusion,
    owner_authentication,
    speaker_authentication,
)


def test_utc_now_is_aware_and_utc() -> None:
    assert clock.utc_now().utcoffset() == UTC.utcoffset(None)


def test_no_module_keeps_its_own_copy() -> None:
    for module in (
        face_authentication,
        identity_fusion,
        owner_authentication,
        speaker_authentication,
    ):
        assert not hasattr(module, "_utc_now")
