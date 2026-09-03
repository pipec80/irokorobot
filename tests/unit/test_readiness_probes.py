"""Unit tests for the side-effect-free readiness probes (Plan 0040 Task 4).

`is_loaded()`/`is_open()` must reflect the module's real loaded/open state
without ever triggering a load or an open themselves — that guarantee is
exactly what `GET /ready` relies on.
"""

import pytest

from server import db, stt, tts


@pytest.mark.unit
def test_stt_is_loaded_reflects_the_model_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt, "_model", None)
    assert stt.is_loaded() is False

    monkeypatch.setattr(stt, "_model", object())
    assert stt.is_loaded() is True


@pytest.mark.unit
def test_tts_is_loaded_reflects_the_voice_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tts, "_voice", None)
    assert tts.is_loaded() is False

    monkeypatch.setattr(tts, "_voice", object())
    assert tts.is_loaded() is True


@pytest.mark.unit
def test_db_is_open_reflects_the_connection_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "_conn", None)
    assert db.is_open() is False

    monkeypatch.setattr(db, "_conn", object())
    assert db.is_open() is True
