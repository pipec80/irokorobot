"""One-off fetch of the Silero VAD ONNX model for R1.

Copies silero_vad.onnx out of the official ``silero-vad`` PyPI package (which
bundles the file but pulls in torch as a dependency) into the robot's model
directory, so the robot itself never depends on torch at runtime. Not
vendored in git — see .gitignore (*.onnx) — run this once per machine.

Usage (ephemeral install, never added to any pyproject.toml):
    uv run --with silero-vad python scripts/fetch_silero_vad_model.py
    uv run --with silero-vad python scripts/fetch_silero_vad_model.py --dest models/silero_vad.onnx
"""

import argparse
import logging
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)

_DEFAULT_DEST = Path("models/silero_vad.onnx")


def main() -> None:
    """Copy the bundled Silero ONNX model to the robot's model directory."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=_DEFAULT_DEST)
    args = parser.parse_args()

    try:
        import silero_vad  # noqa: PLC0415 — ephemeral dep, only present via `uv run --with`
    except ImportError as exc:
        raise SystemExit(
            "silero-vad not installed for this run. Use:\n"
            "  uv run --with silero-vad python scripts/fetch_silero_vad_model.py"
        ) from exc

    source = Path(silero_vad.__file__).parent / "data" / "silero_vad.onnx"
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, args.dest)
    logger.info("Copied %s -> %s (%d bytes)", source, args.dest, args.dest.stat().st_size)
    logger.info("Resolved absolute path: %s", args.dest.resolve())


if __name__ == "__main__":
    main()
