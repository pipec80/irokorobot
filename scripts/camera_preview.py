"""A live preview of the robot's camera to frame a paper, then one saved frame (Plan 0090). Local.

A window shows the camera live with its frame size in a corner. SPACE saves the frame through the
robot's own encoding path (``fit_to_contract`` and ``encode_jpeg``: JPEG, at most 1280x720,
quality 85) as ``<folder>/<name>.jpg`` and closes; Q or ESC closes without saving. The camera runs
at its default size unless ``--hd`` asks for 1280x720, the image contract's maximum. It is a tool
for camera tests (framing a paper for the OCR probe, a reading round); nothing is sent anywhere,
and the default folder is the ignored ``.superpowers/camera``.

Usage (from the repo root):
    uv run python scripts/camera_preview.py bill
    uv run python scripts/camera_preview.py real_bill --hd --folder .superpowers/sdd/0090/images
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Final

import cv2
from robot.camera_capture import encode_jpeg, fit_to_contract

if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np

logger = logging.getLogger(__name__)

#: The image contract's largest frame, asked for with ``--hd``.
HD_SIZE: Final = (1280, 720)
_WINDOW: Final = "Iroko - camara (ESPACIO = foto, Q = salir)"
_STEM: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SPACE: Final = 32
_ESCAPE: Final = 27
_QUIT_KEYS: Final = frozenset({ord("q"), ord("Q"), _ESCAPE})
_KEY_MASK: Final = 0xFF
_WAIT_MS: Final = 30
_LABEL_ORIGIN: Final = (10, 25)
_LABEL_SCALE: Final = 0.7
_LABEL_COLOUR: Final = (0, 0, 255)
_LABEL_THICKNESS: Final = 2


@dataclass(frozen=True)
class PreviewArgs:
    """What one preview does.

    Attributes:
        name: The saved file's stem: letters, digits, ``_`` and ``-`` only.
        hd: Ask the camera for 1280x720 instead of its default size.
        folder: Where the frame is saved.
        device: The OpenCV camera index (0 is the default webcam, as the robot uses).
    """

    name: str
    hd: bool
    folder: Path
    device: int


def _stem(value: str) -> str:
    if not _STEM.fullmatch(value):
        raise argparse.ArgumentTypeError("use letters, digits, _ or - (at most 64)")
    return value


def parse_args(argv: Sequence[str] | None = None) -> PreviewArgs:
    """Read the command line; a name that is not a plain stem ends the program.

    Args:
        argv: The arguments after the program's name; ``None`` reads ``sys.argv``.
    """
    parser = argparse.ArgumentParser(description="Live camera preview; SPACE saves one frame.")
    parser.add_argument("name", type=_stem)
    parser.add_argument("--hd", action="store_true", help="ask the camera for 1280x720")
    parser.add_argument("--folder", type=Path, default=Path(".superpowers/camera"))
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args(argv)
    return PreviewArgs(name=args.name, hd=args.hd, folder=args.folder, device=args.device)


def save_frame(frame: np.ndarray, folder: Path, name: str) -> Path:
    """Save *frame* as a contract JPEG (at most 1280x720, quality 85) and return its path.

    Args:
        frame: A BGR frame from the camera.
        folder: Created when missing.
        name: The file's stem, already checked by :func:`parse_args`.
    """
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{name}.jpg"
    target.write_bytes(encode_jpeg(fit_to_contract(frame)))
    return target


def _show(frame: np.ndarray) -> int:
    """Show *frame* with its size in a corner; return the key pressed, if any."""
    shown = frame.copy()
    size = f"{frame.shape[1]}x{frame.shape[0]}"
    cv2.putText(
        shown,
        size,
        _LABEL_ORIGIN,
        cv2.FONT_HERSHEY_SIMPLEX,
        _LABEL_SCALE,
        _LABEL_COLOUR,
        _LABEL_THICKNESS,
    )
    cv2.imshow(_WINDOW, shown)
    return int(cv2.waitKey(_WAIT_MS)) & _KEY_MASK


def run(args: PreviewArgs) -> int:
    """Preview until SPACE saves a frame or Q / ESC closes; the camera is always released.

    Returns:
        0 when it saved or closed, 1 when the camera could not be opened or gave no frame.
    """
    cap = cv2.VideoCapture(args.device)
    try:
        if not cap.isOpened():
            logger.error("Cannot open camera %d (close any other app using it)", args.device)
            return 1
        if args.hd:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, HD_SIZE[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HD_SIZE[1])
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                logger.error("Camera %d returned no frame", args.device)
                return 1
            key = _show(frame)
            if key == _SPACE:
                target = save_frame(frame, args.folder, args.name)
                logger.info("Saved %s (%dx%d)", target, frame.shape[1], frame.shape[0])
                return 0
            if key in _QUIT_KEYS:
                return 0
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the preview from the command line."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
