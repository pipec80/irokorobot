"""Plan 0090 Task 1: the isolated OCR probe records numbers and closed checks, never a text."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pytest

from scripts.ocr_probe import (
    PHOTOGRAPHS,
    canary_words_read,
    checks,
    raise_contrast,
    read_one,
    run,
    summary,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.unit

_BILL_TEXT = [
    "Boleta qqluzqq",
    "Consumo del período",
    "Total a pagar: $12.345",
    "Vence: 15-12-2026",
]
_NOTE_TEXT = ["Lista qqcanarioqq:", "pan, té, fósforos"]


def _png(width: int = 64, height: int = 32) -> bytes:
    ok, encoded = cv2.imencode(".png", np.full((height, width, 3), 200, dtype=np.uint8))
    assert ok
    return bytes(encoded)


def _ticks() -> Callable[[], float]:
    values = iter((10.0, 10.25))
    return lambda: next(values)


def test_the_bill_check_needs_the_total_and_the_due_date() -> None:
    assert checks("bill", " ".join(_BILL_TEXT)) == (True, None)
    assert checks("bill", "Total a pagar: $12.345") == (False, None)


def test_a_note_counts_its_canary_words_with_accents_folded() -> None:
    assert canary_words_read(" ".join(_NOTE_TEXT)) == 5
    assert checks("hand_bic", "lista pan") == (None, 2)
    assert checks("hand_graphite", "") == (None, 0)


def test_a_read_is_measured_and_scored() -> None:
    line = read_one(
        lambda _image: _BILL_TEXT,
        engine="fake",
        photograph="bill",
        variant="as_taken",
        image=b"x",
        clock=_ticks(),
        free_ram=lambda: 4000,
    )
    assert (line.latency_ms, line.lines_read, line.bill_ok, line.cause) == (250, 4, True, None)
    assert line.ram_before_mb == line.ram_after_mb == 4000


def test_an_engine_failure_is_a_line_with_its_cause() -> None:
    def broken(_image: bytes) -> list[str]:
        raise RuntimeError("model missing")

    line = read_one(broken, engine="fake", photograph="hand_bic", variant="contrast", image=b"x")
    assert (line.cause, line.lines_read, line.bill_ok, line.canary_words) == (
        "RuntimeError",
        0,
        None,
        None,
    )


def test_the_contrast_step_gives_a_grayscale_png() -> None:
    result = cv2.imdecode(np.frombuffer(raise_contrast(_png()), np.uint8), cv2.IMREAD_UNCHANGED)
    assert result is not None
    assert result.ndim == 2  # one channel: grayscale


def test_an_undecodable_photograph_is_refused() -> None:
    with pytest.raises(ValueError, match="decoded"):
        raise_contrast(b"not an image")


def test_no_line_and_no_summary_holds_the_read_text(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    for name in PHOTOGRAPHS:
        (images / f"{name}.png").write_bytes(_png())
    out = tmp_path / "probe.jsonl"

    written = run("fake", lambda _image: _BILL_TEXT + _NOTE_TEXT, images, out)

    assert written == len(PHOTOGRAPHS) * 2
    raw = out.read_text(encoding="utf-8")
    table = summary(out)
    for secret in ("qqluzqq", "qqcanarioqq", "12.345", "fósforos"):
        assert secret not in raw
        assert secret not in table
    first = json.loads(raw.splitlines()[0])
    assert first["photograph"] == "bill"
    assert first["bill_ok"] is True


def test_a_missing_photograph_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "bill.png").write_bytes(_png())
    out = tmp_path / "probe.jsonl"
    assert run("fake", lambda _image: [], tmp_path, out) == 2
