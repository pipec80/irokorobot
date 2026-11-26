"""Plan 0090 Task 3 (ADR 0041 decision 1): the OCR reader behind the reading seam."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

import cv2
import httpx
import numpy as np
from pydantic import ValidationError
import pytest
from server.exceptions import VisionError
from server.settings import Settings, settings
from server.vision import ocr_reader
from server.vision.read_text import read_text

pytestmark = pytest.mark.unit

_CANARY = ["Boleta qqluzqq", "Total a pagar: $12.345", "Vence: 15-12-2026"]


@dataclass
class _Result:
    txts: tuple[str, ...] | None


@dataclass
class _FakeEngine:
    lines: list[str]
    seen: list[np.ndarray] = field(default_factory=list)
    error: Exception | None = None

    def __call__(self, image: np.ndarray) -> _Result:
        self.seen.append(image)
        if self.error is not None:
            raise self.error
        return _Result(txts=tuple(self.lines))


def _jpeg() -> bytes:
    ok, encoded = cv2.imencode(".jpg", np.full((48, 96, 3), 180, dtype=np.uint8))
    assert ok
    return bytes(encoded)


def _no_ollama() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"the vision model was called: {request.url}")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> _FakeEngine:
    fake = _FakeEngine(lines=list(_CANARY))
    monkeypatch.setattr(settings, "reading_engine", "rapidocr")
    monkeypatch.setattr(ocr_reader, "_load_engine", lambda: fake)
    monkeypatch.setattr(ocr_reader, "_engine", None)
    return fake


def test_the_reader_is_rapidocr_by_default_and_vlm_remains() -> None:
    assert Settings.model_fields["reading_engine"].default == "rapidocr"
    Settings(reading_engine="vlm")
    with pytest.raises(ValidationError):
        Settings(reading_engine="tesseract")  # type: ignore[arg-type]  # the refused value is the test


async def test_the_ocr_reads_the_frame_and_never_calls_the_vision_model(
    engine: _FakeEngine,
) -> None:
    async with _no_ollama() as client:
        text = await read_text(client, _jpeg())

    assert text == "\n".join(_CANARY)
    (image,) = engine.seen
    # Decision 9 as amended: the frame as taken, in colour; a contrast step misread a real figure.
    assert image.shape == (48, 96, 3)
    assert int(image.min()) >= 170


async def test_an_engine_failure_is_a_vision_error_not_a_fallback(engine: _FakeEngine) -> None:
    engine.error = RuntimeError("model broken")
    async with _no_ollama() as client:
        with pytest.raises(VisionError):
            await read_text(client, _jpeg())


@pytest.mark.parametrize("lines", [[], ["   "], ["单车"]])
async def test_nothing_readable_is_a_vision_error(engine: _FakeEngine, lines: list[str]) -> None:
    engine.lines = lines
    async with _no_ollama() as client:
        with pytest.raises(VisionError):
            await read_text(client, _jpeg())


async def test_characters_of_another_script_are_dropped(engine: _FakeEngine) -> None:
    engine.lines = ["CANARIO单车", "PAN, TÉ, FÓSFOROS"]
    async with _no_ollama() as client:
        assert await read_text(client, _jpeg()) == "CANARIO\nPAN, TÉ, FÓSFOROS"


async def test_an_undecodable_frame_is_a_vision_error(engine: _FakeEngine) -> None:
    async with _no_ollama() as client:
        with pytest.raises(VisionError):
            await read_text(client, b"not an image")
    assert engine.seen == []


async def test_a_reading_logs_counts_never_the_text(
    engine: _FakeEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    async with _no_ollama() as client:
        await read_text(client, _jpeg())
    engine.error = RuntimeError("qqluzqq")
    async with _no_ollama() as client:
        with pytest.raises(VisionError):
            await read_text(client, _jpeg())

    assert "qqluzqq" not in caplog.text
    assert "12.345" not in caplog.text
    assert any(getattr(r, "event", None) == "vision.ocr_read" for r in caplog.records)
