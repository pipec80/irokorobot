"""memory_test.py — inspect the public voice channel and local memory DB.

Public voice turns have unknown public turns by default: they do not prove
private persistent recall or durable consolidation. Use this script to inspect
the channel response and, separately, the local SQLite state. Trusted household
memory flows require the future authorization and onboarding paths.

Modes:
  --session        Live mic conversation loop. Grabs N seconds, plays response,
                   repeats until you type 'q'. Shows DB at the end.
  --show-db        Read current DB state without sending anything (no server needed).
  --chat TEXT...   Send a single custom message and show DB after.

Requires the server running (just run-server) for all modes except --show-db.
DB is read directly via sqlite3 (WAL mode allows concurrent reads while server runs).

Audio contract: WAV 16000 Hz mono int16.

Usage:
    just memory-test --session
    just memory-test --session --seconds 8
    just memory-test --show-db
    just memory-test --chat hola me llamo Juan y vivo en Santiago
"""

import argparse
import asyncio
import base64
import io
import logging
from pathlib import Path
import sqlite3
import time
import wave

import httpx
import numpy as np
from piper import PiperVoice, SynthesisConfig
from server.settings import settings
import sounddevice as sd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_SEP = "=" * 60
_SEP2 = "-" * 60
_SAMPLE_RATE = 16_000
_CHANNELS = 1
_DTYPE = "int16"
_RMS_THRESHOLD = 200

# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------


def record(seconds: int, device: int | None) -> bytes:
    """Record audio from the microphone for a fixed duration.

    Args:
        seconds: Duration to record.
        device: Input device index, or None for system default.

    Returns:
        WAV bytes at 16kHz mono int16.
    """
    logger.info("Recording %ds on device %s... SPEAK NOW", seconds, device or "default")
    frames = sd.rec(
        int(seconds * _SAMPLE_RATE),
        samplerate=_SAMPLE_RATE,
        channels=_CHANNELS,
        dtype=_DTYPE,
        device=device,
    )
    sd.wait()
    rms = float(np.sqrt(np.mean(frames.astype(np.float32) ** 2)))
    level = "OK" if rms > _RMS_THRESHOLD else "LOW — check mic"
    logger.info("RMS energy: %.0f  [%s]", rms, level)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(frames.tobytes())
    return buf.getvalue()


def record_ptt(device: int | None) -> bytes:
    """Record audio in push-to-talk mode: Enter to start, Enter to stop.

    Streams from the mic until the user presses Enter again. No time limit.

    Args:
        device: Input device index, or None for system default.

    Returns:
        WAV bytes at 16kHz mono int16. Empty WAV if nothing was captured.
    """
    chunks: list[np.ndarray] = []

    def _callback(
        indata: np.ndarray,
        frames: int,  # noqa: ARG001
        time_info: object,  # noqa: ARG001
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.warning("Audio stream status: %s", status)
        chunks.append(indata.copy())

    print("  ** GRABANDO — Enter para PARAR **", flush=True)  # noqa: T201
    with sd.InputStream(
        samplerate=_SAMPLE_RATE,
        channels=_CHANNELS,
        dtype=_DTYPE,
        device=device,
        callback=_callback,
    ):
        input()  # blocks until Enter

    if not chunks:
        logger.warning("No audio captured")
        return b""

    frames_all = np.concatenate(chunks, axis=0)
    rms = float(np.sqrt(np.mean(frames_all.astype(np.float32) ** 2)))
    level = "OK" if rms > _RMS_THRESHOLD else "LOW — check mic"
    logger.info("RMS energy: %.0f  [%s]  frames=%d", rms, level, len(frames_all))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(frames_all.tobytes())
    return buf.getvalue()


def _voice_model_path() -> Path:
    """Resolve the full path to the configured Piper ONNX model."""
    return settings.models_dir / "piper" / f"{settings.piper_voice}.onnx"


def _synthesize_wav(text: str) -> bytes:
    """Convert text to WAV bytes using the local Piper model.

    Args:
        text: Spanish text to synthesize.

    Returns:
        WAV bytes at 16kHz mono int16.

    Raises:
        FileNotFoundError: If the Piper voice model is missing.
    """
    model_path = _voice_model_path()
    if not model_path.exists():
        raise FileNotFoundError(
            f"Piper model not found: {model_path}\n"
            "Run 'just setup' or download the voice model first."
        )
    voice = PiperVoice.load(str(model_path))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=SynthesisConfig())
    return buf.getvalue()


def _play_wav(wav_bytes: bytes) -> None:
    """Play WAV bytes through the default audio output device.

    Args:
        wav_bytes: WAV at 16kHz mono int16.
    """
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16)
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


async def _post_wav(wav_bytes: bytes, url: str, play: bool) -> None:
    """POST WAV audio to /transcribe, print and optionally play the response.

    Args:
        wav_bytes: WAV at 16kHz mono int16.
        url: Server base URL.
        play: Whether to play the TTS response through speakers.
    """
    endpoint = f"{url}/transcribe"
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            endpoint,
            files={"audio": ("audio.wav", wav_bytes, "audio/wav")},
        )
        if resp.is_error:
            logger.error("Server %s: %s", resp.status_code, resp.text[:300])
            return
    elapsed = time.perf_counter() - t0
    data = resp.json()
    print(f"  STT  : {data['text_heard']}")  # noqa: T201
    print(f"  BOT  : {data['llm_response']}")  # noqa: T201
    print(f"  EMO  : {data['emotion']}  ({elapsed:.1f}s)")  # noqa: T201
    if play:
        _play_wav(base64.b64decode(data["audio_base64"]))


async def _send_text(text: str, url: str, play: bool) -> None:
    """Synthesize text with Piper then POST to server.

    Args:
        text: Spanish text to send.
        url: Server base URL.
        play: Whether to play the TTS response.
    """
    print(f"\n  > {text}")  # noqa: T201
    await _post_wav(_synthesize_wav(text), url, play)


# ---------------------------------------------------------------------------
# DB reader
# ---------------------------------------------------------------------------


def _show_db(db_path: Path) -> None:
    """Print a human-readable summary of the current memory DB.

    Args:
        db_path: Path to the omnibot.db SQLite file.
    """
    if not db_path.exists():
        print(f"\n  [DB not found at {db_path}]")  # noqa: T201
        return

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    print(f"\n{_SEP}")  # noqa: T201
    print(f"  DB: {db_path}")  # noqa: T201
    print(_SEP)  # noqa: T201

    for table in ("entities", "facts", "memories", "embeddings_cache", "outbox"):
        try:
            (n,) = cur.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
            print(f"  {table:<22} {n:>4} rows")  # noqa: T201
        except sqlite3.OperationalError:
            print(f"  {table:<22} (table missing)")  # noqa: T201

    entities = cur.execute(
        "SELECT id, name, type FROM entities ORDER BY updated_at DESC LIMIT 20"
    ).fetchall()
    if entities:
        print(f"\n{_SEP2}")  # noqa: T201
        print("  ENTITIES & FACTS")  # noqa: T201
        print(_SEP2)  # noqa: T201
        for ent in entities:
            facts = cur.execute(
                "SELECT predicate, object_value, confidence FROM facts "
                "WHERE entity_id = ? AND superseded_at IS NULL "
                "ORDER BY asserted_at DESC",
                (ent["id"],),
            ).fetchall()
            fact_str = (
                "  |  ".join(
                    f"{f['predicate']}: {f['object_value']} ({f['confidence']:.2f})" for f in facts
                )
                if facts
                else "(no facts)"
            )
            print(f"  [{ent['type']}] {ent['name']}")  # noqa: T201
            print(f"         {fact_str}")  # noqa: T201

    memories = cur.execute(
        "SELECT kind, content, summary, created_at FROM memories ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    if memories:
        print(f"\n{_SEP2}")  # noqa: T201
        print("  RECENT MEMORIES")  # noqa: T201
        print(_SEP2)  # noqa: T201
        for mem in memories:
            text = mem["summary"] or mem["content"][:120]
            print(f"  [{mem['kind']}] {mem['created_at'][:19]}")  # noqa: T201
            print(f"         {text}")  # noqa: T201

    con.close()
    print(f"\n{_SEP}")  # noqa: T201


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


async def run_session(url: str, seconds: int, device: int | None, play: bool, ptt: bool) -> None:
    """Interactive mic conversation loop. Records, sends, plays, repeats.

    PTT mode (default): Enter to start recording, Enter to stop — no time limit.
    Timed mode (--seconds): records a fixed duration after pressing Enter.

    Args:
        url: Server base URL.
        seconds: Recording duration for timed mode (ignored in PTT mode).
        device: Mic input device index, or None for default.
        play: Whether to play TTS responses.
        ptt: If True, use push-to-talk (Enter start / Enter stop).
    """
    mode_label = "PTT — Enter=start, Enter=stop" if ptt else f"timed {seconds}s"
    print(f"\n{_SEP}")  # noqa: T201
    print(f"  MODE: session  ({mode_label})")  # noqa: T201
    print("  Type 'q' + Enter at the prompt to end the session.")  # noqa: T201
    print(_SEP)  # noqa: T201
    turn = 0
    loop = asyncio.get_event_loop()
    while True:
        turn += 1
        if ptt:
            print(  # noqa: T201
                f"\n  [Turn {turn}] Enter para EMPEZAR a grabar... (q = salir): ",
                end="",
                flush=True,
            )
            cmd = await loop.run_in_executor(None, input)
            if cmd.strip().lower() == "q":
                break
            wav_bytes = await loop.run_in_executor(None, record_ptt, device)
        else:
            print(  # noqa: T201
                f"\n  [Turn {turn}] Enter para grabar {seconds}s... (q = salir): ",
                end="",
                flush=True,
            )
            cmd = await loop.run_in_executor(None, input)
            if cmd.strip().lower() == "q":
                break
            wav_bytes = await loop.run_in_executor(None, record, seconds, device)
        if not wav_bytes:
            logger.warning("Empty recording — skipping turn")
            continue
        await _post_wav(wav_bytes, url, play)
    print(f"\n{_SEP2}")  # noqa: T201
    print(f"  Session ended — {turn - 1} turn(s). Showing memory DB:")  # noqa: T201
    _show_db(settings.brain_db_path)


async def run_chat(texts: list[str], url: str, play: bool) -> None:
    """Send a custom public-channel message and dump the local DB after.

    Args:
        texts: Words forming the message (joined with spaces).
        url: Server base URL.
        play: Whether to play TTS response.
    """
    msg = " ".join(texts)
    print(f"\n{_SEP}")  # noqa: T201
    print(f"  MODE: chat  ({msg!r})")  # noqa: T201
    print(_SEP)  # noqa: T201
    await _send_text(msg, url, play)
    _show_db(settings.brain_db_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Public voice-channel diagnostic and local memory DB inspector"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--session",
        action="store_true",
        help="Live mic conversation loop (shows DB when you quit with 'q')",
    )
    group.add_argument(
        "--show-db",
        action="store_true",
        help="Dump current DB state without sending anything (no server needed)",
    )
    group.add_argument(
        "--chat",
        nargs="+",
        metavar="WORD",
        help="Send a custom message and show DB after",
    )
    parser.add_argument(
        "--ptt",
        action="store_true",
        default=True,
        help="Push-to-talk in --session: Enter=start, Enter=stop (default: on)",
    )
    parser.add_argument(
        "--no-ptt",
        dest="ptt",
        action="store_false",
        help="Use fixed-duration recording instead of PTT (combine with --seconds)",
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=5,
        help="Mic recording duration per turn when --no-ptt is set (default: 5)",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="Mic input device index (default: system default)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit",
    )
    parser.add_argument("--no-play", action="store_true", help="Skip audio playback")
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Delete the memory DB before running (fresh start / re-trigger onboarding)",
    )
    args = parser.parse_args()

    if args.reset_db:
        db = settings.brain_db_path
        if db.exists():
            db.unlink()
            logger.info("DB deleted: %s — fresh start", db)
        else:
            logger.info("DB not found — nothing to delete")

    if args.list_devices:
        print("\n=== Audio Input Devices ===")  # noqa: T201
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:  # type: ignore[index]
                marker = "->" if i == sd.default.device[0] else "  "
                print(f"  {marker} [{i}] {dev['name']}")  # type: ignore[index]  # noqa: T201
        return

    if args.show_db:
        _show_db(settings.brain_db_path)
        return

    play = not args.no_play

    host = "localhost" if settings.server_host == "0.0.0.0" else settings.server_host  # noqa: S104
    url = f"http://{host}:{settings.server_port}"

    if args.session:
        asyncio.run(run_session(url, args.seconds, args.device, play, args.ptt))
    elif args.chat:
        asyncio.run(run_chat(args.chat, url, play))


if __name__ == "__main__":
    main()
