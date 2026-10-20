"""mic_test.py - capture auditor for the robot's microphone (Plan 0069 Task 4).

Lists the input devices, records one take the way the robot opens the
microphone (``--api mme``: the default device at 16 kHz, mono, int16, no ``device=``) or
through WASAPI at the device's native rate (``--api wasapi``: one channel, resampled to
16 kHz with ``soxr``), and reports its levels against Plan 0069's targets. Before the take
it shows the phrase to read; the stream settles, a countdown runs and the visual cue
``>>> HABLA <<<`` opens the window (the same sequence as the corpus tool). Optionally
transcribes it with the server's production decode options, through
``server.stt.run_whisper``. Run it with the server stopped when transcribing.

A saved take goes to ``project-history/calibration/stt/mic/`` (ignored by git), never
elsewhere; a name already there is refused before the microphone opens, unless
``--replace`` asks to record it again. Nothing here is played back.

Usage:
    just mic-test devices
    just mic-test devices --save
    just mic-test record --seconds 6 --api mme --save lv-c60-mme
    just mic-test record --seconds 6 --api mme --save lv-c60-mme --replace
    just mic-test record --phrase Hola Iroko
    just mic-test record --seconds 6 --api wasapi --transcribe
    just mic-test record --transcribe --model medium --beam-size 1 --prompt Conversación con Iroko

Audio contract of every saved take: WAV, 16 000 Hz, mono, int16.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution puts ``scripts/`` on ``sys.path[0]``; the ``from scripts.…`` imports
# below need the repo root (pytest already has it through pyproject ``pythonpath``).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import io
import json
import logging
import re
from typing import TYPE_CHECKING
import wave

from faster_whisper import WhisperModel
import numpy as np
from robot.audio_capture import CHUNK_FRAMES
from server.settings import settings
import sounddevice as sd

from scripts.speaker_calibration_corpus import resolve_corpus_path, write_new_file_atomic
from scripts.stt_audio_levels import (
    CONTRACT_RATE,
    LevelReport,
    level_report,
    level_verdicts,
    to_contract,
)
from scripts.stt_corpus_models import STT_CORPUS_ROOT
from server import stt

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

logger = logging.getLogger(__name__)

LEVEL_PHRASE = "Me gusta el helado de chocolate."

_TAKE_NAME = re.compile(r"[A-Za-z0-9_-]+")
_MIC_DIR = "mic"
_SETTLE_S = 0.5
_COUNTDOWN = (3, 2, 1)


@dataclass(frozen=True)
class InputDevice:
    """One capture device as PortAudio lists it."""

    index: int
    name: str
    host_api: str
    channels: int
    default_rate: int
    is_default: bool


def list_inputs() -> list[InputDevice]:
    """List every device that can capture, with its host API and native rate.

    Returns:
        The inputs in PortAudio order; ``is_default`` marks the device the robot opens.
    """
    default_input = sd.default.device[0]
    return [
        InputDevice(
            index=index,
            name=str(device["name"]),
            host_api=str(sd.query_hostapis(device["hostapi"])["name"]),
            channels=int(device["max_input_channels"]),
            default_rate=int(device["default_samplerate"]),
            is_default=index == default_input,
        )
        for index, device in enumerate(sd.query_devices())
        if int(device["max_input_channels"]) > 0
    ]


def _wasapi_input() -> InputDevice:
    """Return the WASAPI host API's default input device."""
    for host in sd.query_hostapis():
        if "WASAPI" in str(host["name"]):
            device_index = int(host["default_input_device"])
            for device in list_inputs():
                if device.index == device_index:
                    return device
            break
    raise SystemExit("no WASAPI input device found")


@contextmanager
def open_input(api: str) -> Generator[tuple[sd.InputStream, int]]:
    """Open the microphone one way or the other and yield the stream and its opened rate.

    Args:
        api: ``mme`` (the robot's way: default device, 16 kHz, mono, int16) or ``wasapi``
            (the WASAPI default input at its native rate, one float32 channel).

    Yields:
        The started stream and the rate it actually opened at.
    """
    if api == "mme":
        stream = sd.InputStream(
            samplerate=CONTRACT_RATE, channels=1, dtype="int16", blocksize=CHUNK_FRAMES
        )
    else:
        device = _wasapi_input()
        logger.info(
            "WASAPI input: [%d] %s at %d Hz", device.index, device.name, device.default_rate
        )
        stream = sd.InputStream(
            device=device.index,
            samplerate=device.default_rate,
            channels=1,
            dtype="float32",
            extra_settings=sd.WasapiSettings(auto_convert=True),  # only for the mixdown
        )
    with stream:
        yield stream, int(stream.samplerate)


def as_contract(data: np.ndarray, api: str, opened_rate: int) -> np.ndarray:
    """Turn what ``open_input`` read into int16, 16 000 Hz, mono samples.

    Args:
        data: The samples read from the stream.
        api: The API the stream was opened with.
        opened_rate: The rate it opened at.

    Returns:
        Int16 samples, 16 000 Hz, mono.
    """
    if api == "mme":
        return np.asarray(data, dtype=np.int16).reshape(-1)
    return to_contract(np.asarray(data), opened_rate, channels=1)


def record(api: str, seconds: float) -> tuple[np.ndarray, int]:
    """Record one take: settle, count down, cue, then the window.

    The stream is open and running before anything is shown, and samples are kept from
    the start of the countdown, so opening the device never costs an onset (D-3). The
    cue is visual only. Hardware path: Pipec runs it, never an agent.

    Args:
        api: ``mme`` or ``wasapi`` (see ``open_input``).
        seconds: Seconds recorded after the cue.

    Returns:
        Int16 samples, 16 000 Hz, mono, from the countdown on, and the rate the stream
        actually opened at.
    """
    with open_input(api) as (stream, rate):
        stream.read(int(_SETTLE_S * rate))  # discarded: the device settles
        parts = []
        for count in _COUNTDOWN:
            logger.info("   %d ...", count)
            parts.append(stream.read(rate)[0])
        logger.info("   >>> HABLA <<<")
        parts.append(stream.read(int(seconds * rate))[0])
    logger.info("   listo")
    return as_contract(np.concatenate(parts), api, rate), rate


def _wav(samples: np.ndarray) -> bytes:
    """Encode int16 samples as WAV bytes — 16 kHz, mono, int16."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(CONTRACT_RATE)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


def _take_path(name: str) -> Path:
    """Return the saved take's path; a name that is not plain is refused."""
    if not _TAKE_NAME.fullmatch(name):
        raise SystemExit(f"--save takes a plain name (letters, digits, _ and -), not {name!r}")
    return resolve_corpus_path(STT_CORPUS_ROOT, Path(_MIC_DIR) / f"{name}.wav")


def whisper_options(
    args: argparse.Namespace, base: stt.WhisperDecodeOptions
) -> stt.WhisperDecodeOptions:
    """Apply the command line's overrides to the production decode options.

    Args:
        args: Parsed ``record`` arguments.
        base: ``stt.decode_options(settings)``.

    Returns:
        *base* with only the beam size and the prompt that were given replaced.
    """
    options = base
    if args.beam_size is not None:
        options = replace(options, beam_size=args.beam_size)
    if args.prompt:
        options = replace(options, initial_prompt=" ".join(args.prompt))
    return options


def _format_db(value: float | None) -> str:
    return "silence" if value is None else f"{value:.1f}"


def _print_report(report: LevelReport, opened_rate: int, seconds: float) -> None:
    verdicts = level_verdicts(report)
    lines = [
        f"take: {seconds:.1f} s, stream opened at {opened_rate} Hz",
        f"peak:   {_format_db(report.peak_dbfs)} dBFS  [{verdicts['peak']}]",
        f"speech: {_format_db(report.speech_rms_dbfs)} dBFS  [{verdicts['speech']}]",
        f"floor:  {_format_db(report.floor_dbfs)} dBFS  [{verdicts['floor']}]",
        f"snr:    {_format_db(report.snr_db)} dB",
        f"clipped samples: {report.clipped_fraction:.4%}  [{verdicts['clipping']}]",
    ]
    print("\n".join(lines))  # noqa: T201 -- the operator's report table


def _transcribe(samples: np.ndarray, args: argparse.Namespace) -> None:
    model = WhisperModel(
        args.model or settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    options = whisper_options(args, stt.decode_options(settings))
    hotwords = " ".join(args.hotwords) if args.hotwords else None
    transcript = stt.run_whisper(model, _wav(samples), options, hotwords)
    confidence = transcript.confidence
    logprob = "none" if confidence is None else f"{confidence.avg_logprob:.3f}"
    print(f"heard: {transcript.text or '(nothing)'}")  # noqa: T201 -- the operator's own take
    print(f"logprob: {logprob}  after Whisper's VAD: {transcript.after_vad_s:.1f} s")  # noqa: T201


def _devices(save: bool) -> int:
    inputs = list_inputs()
    for device in inputs:
        marker = "->" if device.is_default else "  "
        print(  # noqa: T201 -- the operator's device table
            f"{marker} [{device.index}] {device.name} | {device.host_api} | "
            f"in {device.channels} | {device.default_rate} Hz"
        )
    if save:
        target = resolve_corpus_path(STT_CORPUS_ROOT, Path(_MIC_DIR) / "devices.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps([asdict(d) for d in inputs], indent=2), encoding="utf-8")
        logger.info("device list saved under the private corpus root")
    return 0


def _record_take(args: argparse.Namespace) -> int:
    target = _take_path(args.save) if args.save else None
    if target is not None and target.exists() and not args.replace:
        raise SystemExit(f"{target.name} already exists; add --replace to record it again")
    phrase = " ".join(args.phrase) if args.phrase else LEVEL_PHRASE
    logger.info("Lee en voz alta cuando aparezca >>> HABLA <<<: %s", phrase)
    samples, opened_rate = record(args.api, args.seconds)
    _print_report(level_report(samples), opened_rate, len(samples) / CONTRACT_RATE)
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if args.replace:
            target.unlink(missing_ok=True)
        write_new_file_atomic(target, _wav(samples))
        logger.info("take saved under the private corpus root")
    if args.transcribe:
        _transcribe(samples, args)
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the ``devices`` and ``record`` commands.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        The parsed namespace.
    """
    parser = argparse.ArgumentParser(description="Capture auditor for the robot microphone")
    commands = parser.add_subparsers(dest="command", required=True)
    devices = commands.add_parser("devices", help="list the capture devices")
    devices.add_argument("--save", action="store_true", help="save the list as JSON")
    take = commands.add_parser("record", help="record one take and report its levels")
    take.add_argument("--seconds", type=float, default=6.0, help="window after the cue")
    take.add_argument("--api", choices=("mme", "wasapi"), default="mme")
    take.add_argument("--save", default=None, help="plain name of the take to keep")
    take.add_argument("--replace", action="store_true", help="record a saved name again")
    take.add_argument("--phrase", nargs="+", default=None, help="what to read aloud")
    take.add_argument("--transcribe", action="store_true")
    take.add_argument("--model", default=None, help="Whisper model (default: the server's)")
    take.add_argument("--beam-size", type=int, default=None)
    take.add_argument("--prompt", nargs="+", default=None)
    take.add_argument("--hotwords", nargs="+", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one auditor command.

    Args:
        argv: Arguments without the program name.

    Returns:
        The process exit code.
    """
    args = parse_args(argv)
    if args.command == "devices":
        return _devices(args.save)
    return _record_take(args)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    raise SystemExit(main())
