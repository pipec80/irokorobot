"""Debug script: Piper TTS → WAV synthesis + optional playback.

Standalone — no .env, no server, no Whisper required.
Tests only the TTS pipeline: text → WAV bytes → speaker.

Audio contract: WAV · 16000 Hz · mono · int16.

Usage:
    uv run python scripts/piper_test.py --list-voices
    uv run python scripts/piper_test.py --text Hola soy Omnibot
    uv run python scripts/piper_test.py --voice es_AR-daniela-high --save output.wav
    uv run python scripts/piper_test.py --no-play
"""

import argparse
import io
import logging
from pathlib import Path
import time
import wave

import numpy as np
from piper import PiperVoice, SynthesisConfig
import sounddevice as sd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_MODELS_DIR = Path("models") / "piper"
_DEFAULT_TEXT = "Hola, soy Omnibot dos mil. ¿En qué puedo ayudarte?"


def list_voices() -> None:
    """Print available .onnx voice models found in models/piper/."""
    print("\n=== Voces disponibles en models/piper/ ===")  # noqa: T201
    if not _MODELS_DIR.exists():
        print(f"  (directorio no encontrado: {_MODELS_DIR})")  # noqa: T201
        return
    voices = sorted(_MODELS_DIR.glob("*.onnx"))
    if not voices:
        print("  (ningún modelo .onnx encontrado)")  # noqa: T201
    for v in voices:
        print(f"  · {v.stem}")  # noqa: T201
    print()  # noqa: T201


def load_voice(voice_name: str) -> PiperVoice:
    """Load a PiperVoice model by name.

    Args:
        voice_name: Stem of the .onnx file inside models/piper/.

    Returns:
        Loaded PiperVoice instance.

    Raises:
        FileNotFoundError: If the .onnx model is not found.
    """
    model_path = _MODELS_DIR / f"{voice_name}.onnx"
    if not model_path.exists():
        raise FileNotFoundError(
            f"Modelo no encontrado: {model_path}\nEjecuta --list-voices para ver los disponibles."
        )
    logger.info("Cargando modelo: %s", model_path)
    return PiperVoice.load(str(model_path))


def synthesize(
    voice: PiperVoice,
    text: str,
    speed: float = 1.0,
    noise: float | None = None,
    noise_w: float | None = None,
) -> tuple[bytes, int]:
    """Synthesize text to WAV bytes.

    Args:
        voice: Loaded PiperVoice instance.
        text: Text to synthesize.
        speed: Speed multiplier — >1.0 faster, <1.0 slower (default: 1.0).
        noise: noise_scale — higher = more audio variation/naturalness.
        noise_w: noise_w_scale — higher = more phoneme duration variation.

    Returns:
        Tuple of (wav_bytes, duration_ms).
    """
    logger.info("Sintetizando: %r  (speed=%.2f noise=%s noise_w=%s)", text, speed, noise, noise_w)
    config = SynthesisConfig(length_scale=1.0 / speed, noise_scale=noise, noise_w_scale=noise_w)
    start = time.monotonic()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=config)
    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info("Síntesis completada en %d ms", duration_ms)
    return buf.getvalue(), duration_ms


def inspect_wav(wav_bytes: bytes) -> None:
    """Log WAV header metadata to verify audio contract."""
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        logger.info(
            "WAV info → rate: %d Hz · channels: %d · width: %d bytes · frames: %d",
            wf.getframerate(),
            wf.getnchannels(),
            wf.getsampwidth(),
            wf.getnframes(),
        )


def play(wav_bytes: bytes) -> None:
    """Play WAV bytes through the default audio output device.

    Args:
        wav_bytes: WAV at 16kHz mono int16.
    """
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16)
    logger.info("Reproduciendo audio (%d muestras @ %d Hz)...", len(audio), sample_rate)
    sd.play(audio, samplerate=sample_rate)
    sd.wait()
    logger.info("Reproducción completa.")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Piper TTS debug script")
    parser.add_argument(
        "--voice", default="es_MX-ald-medium", help="Nombre de la voz (default: es_MX-ald-medium)"
    )
    parser.add_argument("--text", default=_DEFAULT_TEXT, help="Texto a sintetizar")
    parser.add_argument(
        "--save", type=str, default=None, help="Guardar WAV en esta ruta (opcional)"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Velocidad: 1.2=20%% más rápido, 0.8=20%% más lento (default: 1.0)",
    )
    parser.add_argument(
        "--noise",
        type=float,
        default=None,
        help="noise_scale: variación de audio, más natural (ej: 0.667)",
    )
    parser.add_argument(
        "--noise-w",
        type=float,
        default=None,
        help="noise_w_scale: variación de duración de fonemas (ej: 0.8)",
    )
    parser.add_argument("--no-play", action="store_true", help="No reproducir audio por speaker")
    parser.add_argument(
        "--list-voices", action="store_true", help="Listar modelos disponibles y salir"
    )
    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return

    voice = load_voice(args.voice)
    wav_bytes, duration_ms = synthesize(
        voice, args.text, speed=args.speed, noise=args.noise, noise_w=args.noise_w
    )
    inspect_wav(wav_bytes)

    if args.save:
        Path(args.save).write_bytes(wav_bytes)
        logger.info("WAV guardado → %s", args.save)

    if not args.no_play:
        play(wav_bytes)

    print(f"\n{'=' * 40}")  # noqa: T201
    print(f"  Texto   : {args.text}")  # noqa: T201
    print(f"  Voz     : {args.voice}")  # noqa: T201
    print(f"  Speed   : {args.speed}")  # noqa: T201
    print(f"  Noise   : {args.noise}  |  Noise-W: {args.noise_w}")  # noqa: T201
    print(f"  Tiempo  : {duration_ms} ms")  # noqa: T201
    print(f"{'=' * 40}\n")  # noqa: T201


if __name__ == "__main__":
    main()
