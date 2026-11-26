"""Plan 0090 Task 3: the real OCR reads a canary card drawn in memory (slow: loads its models)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from server.vision import ocr_reader

pytestmark = pytest.mark.slow

_LINES = ("BOLETA QQLUZQQ", "TOTAL A PAGAR 12345")


def _card() -> bytes:
    canvas = np.full((480, 640, 3), 255, dtype=np.uint8)
    for index, line in enumerate(_LINES):
        cv2.putText(
            canvas, line, (30, 120 + index * 90), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 0), 3
        )
    ok, encoded = cv2.imencode(".jpg", canvas)
    assert ok
    return bytes(encoded)


async def test_the_real_ocr_reads_a_canary_card() -> None:
    pytest.importorskip("rapidocr")
    text = await ocr_reader.ocr_read_text(_card())
    folded = " ".join(text.upper().split())
    assert "QQLUZQQ" in folded
    assert "12345" in folded
