"""Plan 0090 decision 11: the live camera preview saves one contract frame, safely named."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.camera_preview import HD_SIZE, PreviewArgs, parse_args, save_frame

pytestmark = pytest.mark.unit


def test_the_defaults_keep_the_robot_s_size_and_an_ignored_folder() -> None:
    args = parse_args(["bill"])
    assert args == PreviewArgs(name="bill", hd=False, folder=Path(".superpowers/camera"), device=0)


def test_hd_and_the_folder_and_the_device_are_options() -> None:
    args = parse_args(["real_bill", "--hd", "--folder", "out", "--device", "1"])
    assert (args.hd, args.folder, args.device) == (True, Path("out"), 1)
    assert HD_SIZE == (1280, 720)


@pytest.mark.parametrize("name", ["../escape", "a/b", "with space", "", "x" * 65])
def test_a_name_that_is_not_a_plain_stem_is_refused(name: str) -> None:
    with pytest.raises(SystemExit):
        parse_args([name])


def test_a_saved_frame_is_a_contract_jpeg(tmp_path: Path) -> None:
    frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)

    target = save_frame(frame, tmp_path / "shots", "bill")

    assert target == tmp_path / "shots" / "bill.jpg"
    decoded = cv2.imdecode(np.frombuffer(target.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[1] <= 1280
    assert decoded.shape[0] <= 720
