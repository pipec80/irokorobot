"""The two heavy identity models expose a warm-up that loads them off the event loop (Plan 0055)."""

import threading

import pytest
from server.vision import faces
from server.voice import speaker_embedding
from server.voice.speaker_embedding import SpeakerBackendError


async def test_face_warm_up_loads_the_analyzer_once_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threads: list[int] = []
    monkeypatch.setattr(faces, "_get_analyzer", lambda: threads.append(threading.get_ident()))

    await faces.warm_up()

    assert len(threads) == 1
    assert threads[0] != threading.get_ident()


async def test_speaker_warm_up_loads_the_encoder_once_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threads: list[int] = []
    monkeypatch.setattr(
        speaker_embedding, "_load_encoder", lambda: threads.append(threading.get_ident())
    )

    await speaker_embedding.warm_up()

    assert len(threads) == 1
    assert threads[0] != threading.get_ident()


async def test_speaker_warm_up_retypes_any_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> None:
        raise RuntimeError("yaml parse error")

    monkeypatch.setattr(speaker_embedding, "_load_encoder", _boom)

    with pytest.raises(SpeakerBackendError):
        await speaker_embedding.warm_up()


async def test_speaker_warm_up_keeps_a_typed_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _cooling_down() -> None:
        raise SpeakerBackendError("Speaker model load failed recently; not retrying yet")

    monkeypatch.setattr(speaker_embedding, "_load_encoder", _cooling_down)

    with pytest.raises(SpeakerBackendError, match="not retrying yet"):
        await speaker_embedding.warm_up()
