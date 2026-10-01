"""`scripts/onboard.py` reports a rejected setup without a traceback (Plan 0050)."""

import sys

import pytest

from scripts import onboard


@pytest.mark.unit
def test_a_rejected_setup_exits_with_its_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ValueError from the setup service is a message and exit code 1."""

    async def rejected(*, skip_face: bool, device: int) -> None:
        del skip_face, device
        raise ValueError("owner_name must not be blank")

    monkeypatch.setattr(onboard, "_run", rejected)
    monkeypatch.setattr(sys, "argv", ["onboard"])

    with pytest.raises(SystemExit) as caught:
        onboard.main()

    assert caught.value.code == 1
    assert "owner_name must not be blank" in capsys.readouterr().out
