"""Fetch a Piper TTS voice model into the local models directory.

Wraps the official ``piper.download_voices`` module — bundled with the
``piper-tts`` package this project already depends on, no separate tool or
guessed URL. Source: huggingface.co/rhasspy/piper-voices (see
``piper.download_voices.URL_FORMAT``).

Not vendored in git — see .gitignore (``models/``) — run this once per
machine per voice.

Usage:
    uv run python scripts/fetch_piper_voice.py
    uv run python scripts/fetch_piper_voice.py --voice es_ES-sharvard-medium
    uv run python scripts/fetch_piper_voice.py --voice es_MX-ald-medium --force
"""

import argparse
import logging

from piper.download_voices import download_voice
from server.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """Download one Piper voice's `.onnx`/`.onnx.json` pair.

    Raises:
        SystemExit: If the voice name does not match Piper's
            `<language>-<name>-<quality>` pattern.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--voice",
        default=settings.piper_voice,
        help="Voice name like 'es_MX-ald-medium' (default: PIPER_VOICE from .env)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if the files already exist"
    )
    args = parser.parse_args()

    dest_dir = settings.models_dir / "piper"
    dest_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Fetching Piper voice %r into %s ...", args.voice, dest_dir)
    try:
        download_voice(args.voice, dest_dir, force_redownload=args.force)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    logger.info("Done: %s.onnx (+ .onnx.json) in %s", args.voice, dest_dir)


if __name__ == "__main__":
    main()
