"""Unit tests for scripts.fetch_silero_vad_model: default download path parity.

Regression test for F-03 (docs/c-audit/auditoria-forense-codigo-2026-07-21.md):
the downloader script and the robot runtime must agree on where the Silero
ONNX model lives, otherwise `just fetch-vad-model` silently writes to a path
`create_vad("silero")` never reads.
"""

import pytest
from robot.settings import Settings

from scripts import fetch_silero_vad_model


@pytest.mark.unit
def test_default_dest_matches_robot_vad_model_path() -> None:
    """The script's default destination must equal Settings().vad_model_path."""
    assert Settings().vad_model_path == fetch_silero_vad_model._DEFAULT_DEST
