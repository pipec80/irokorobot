"""Unit tests for the perception composer (V1) — all pipelines mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from server.exceptions import VisionError
from server.vision.describe import PERCEPTION_FAILED
from server.vision.faces import FaceMatch
from server.vision.perception import perceive

_FELIPE = FaceMatch(entity_id=1, name="Felipe", distance=0.1)
_FRAME = b"\xff\xd8fake"


def _recognize(result: object) -> AsyncMock:
    """AsyncMock for recognize — pass an Exception to make it raise."""
    if isinstance(result, Exception):
        return AsyncMock(side_effect=result)
    return AsyncMock(return_value=result)


@pytest.mark.unit
async def test_recognized_face_enters_perception() -> None:
    """A matched face adds the greeting line before the description."""
    with (
        patch("server.vision.perception.recognize", _recognize(([_FELIPE], 0))),
        patch(
            "server.vision.perception.describe_image",
            AsyncMock(return_value=("Una sala con un sofá.", 900)),
        ),
    ):
        perception = await perceive(_FRAME)

    assert "Felipe" in perception
    assert "Una sala con un sofá." in perception


@pytest.mark.unit
async def test_unknown_face_adds_gentle_line() -> None:
    """An unmatched face adds the no-alarm unknown line."""
    with (
        patch("server.vision.perception.recognize", _recognize(([], 1))),
        patch(
            "server.vision.perception.describe_image",
            AsyncMock(return_value=("Una sala.", 900)),
        ),
        patch("server.vision.perception._record_unknown_face", AsyncMock()),
    ):
        perception = await perceive(_FRAME)

    assert "NO reconocés" in perception


@pytest.mark.unit
async def test_face_failure_never_blinds_description() -> None:
    """Face model down → the scene description still comes through."""
    with (
        patch("server.vision.perception.recognize", _recognize(VisionError("model missing"))),
        patch(
            "server.vision.perception.describe_image",
            AsyncMock(return_value=("Una sala.", 900)),
        ),
    ):
        perception = await perceive(_FRAME)

    assert perception == "Una sala."


@pytest.mark.unit
async def test_description_failure_keeps_face_lines() -> None:
    """VLM down but a face matched → the robot still greets by name."""
    with (
        patch("server.vision.perception.recognize", _recognize(([_FELIPE], 0))),
        patch(
            "server.vision.perception.describe_image",
            AsyncMock(side_effect=VisionError("vlm down")),
        ),
    ):
        perception = await perceive(_FRAME)

    assert "Felipe" in perception


@pytest.mark.unit
async def test_both_pipelines_down_falls_back() -> None:
    """Nothing seen at all → the canned excuse, never an exception."""
    with (
        patch("server.vision.perception.recognize", _recognize(VisionError("down"))),
        patch(
            "server.vision.perception.describe_image",
            AsyncMock(side_effect=VisionError("down")),
        ),
    ):
        perception = await perceive(_FRAME)

    assert perception == PERCEPTION_FAILED
