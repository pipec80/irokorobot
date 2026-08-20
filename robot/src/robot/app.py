"""Robot main loop — FSM: IDLE → LISTENING → THINKING → SPEAKING (→ LOOKING).

The loop never dies on errors: any failure routes through ERROR, which
logs, waits, and returns to IDLE. Capture only runs in LISTENING and
playback completes before leaving SPEAKING (half-duplex), so the
microphone can never transcribe the robot's own voice.

LOOKING (V0.5): when the server answers with ``vision_requested=True``
(the user asked a visual question), the robot captures ONE webcam frame,
sends it with the question to ``/vision/respond``, and speaks the answer.
The mic stays closed the whole time — half-duplex is preserved.

R3 (settings.robot_streaming): THINKING/SPEAKING delegate to
app_streaming.py instead, which consumes POST /transcribe/stream and plays
audio sentence-by-sentence. See app_streaming.py's module docstring.
Streaming does not support visual questions — at startup, `_run()` refuses
to start if streaming is on and the server reports vision enabled (F-08).
"""

import asyncio
import base64
import logging

from robot import app_streaming
from robot.audio_capture import capture_utterance
from robot.audio_playback import play_wav
from robot.camera_capture import capture_frame
from robot.exceptions import (
    AudioCaptureError,
    AudioPlaybackError,
    CameraError,
    NoSpeechError,
    ServerError,
)
from robot.fsm_types import LoopContext, RobotState
from robot.logging_setup import build_file_handler
from robot.server_client import check_vision_enabled, close_client, respond_vision, transcribe
from robot.settings import settings

logger = logging.getLogger(__name__)

_ERROR_RECOVERY_S = 2.0


async def _on_idle(ctx: LoopContext) -> RobotState:
    """Reset the interaction context and start listening."""
    ctx.audio = b""
    ctx.result = None
    ctx.stream_events = None
    ctx.stream_request_start = None
    return RobotState.LISTENING


async def _on_listening(ctx: LoopContext) -> RobotState:
    """Capture one utterance; empty capture (onset timeout) cycles to IDLE."""
    try:
        ctx.audio = await capture_utterance()
    except AudioCaptureError as exc:
        logger.error("Microphone capture failed: %s", exc)
        return RobotState.ERROR
    return RobotState.THINKING if ctx.audio else RobotState.IDLE


async def _on_thinking(ctx: LoopContext) -> RobotState:
    """Send the utterance to the server and hold the result for playback."""
    if settings.robot_streaming:
        return await app_streaming.on_thinking_stream(ctx)
    try:
        ctx.result = await transcribe(ctx.audio)
    except NoSpeechError:
        # Ambient noise tripped the local VAD but Whisper heard nothing —
        # not an error, just resume listening.
        logger.info("No speech understood — listening again")
        return RobotState.IDLE
    except (ServerError, ValueError) as exc:
        logger.error("Server request failed: %s", exc)
        return RobotState.ERROR
    logger.info("Heard: %s", ctx.result.text_heard)
    logger.info("Robot: %s", ctx.result.llm_response)
    return RobotState.SPEAKING


async def _on_speaking(ctx: LoopContext) -> RobotState:
    """Play the response; finishes before LISTENING can run again (half-duplex)."""
    if settings.robot_streaming:
        return await app_streaming.on_speaking_stream(ctx)
    if ctx.result is None:
        return RobotState.IDLE
    try:
        await play_wav(base64.b64decode(ctx.result.audio_base64))
    except (AudioPlaybackError, ValueError) as exc:
        logger.error("Playback failed: %s", exc)
        return RobotState.ERROR
    # Server asked for a frame — look AFTER speaking the cue phrase. The
    # vision result comes back with vision_requested=False, so LOOKING
    # cannot loop.
    if ctx.result.vision_requested:
        return RobotState.LOOKING
    return RobotState.IDLE


async def _on_looking(ctx: LoopContext) -> RobotState:
    """Capture one webcam frame and ask the server to answer with it (V0.5).

    Camera or server failure is not fatal: the robot logs and returns to
    IDLE — it already spoke the cue phrase, and staying alive beats
    retrying with the mic closed.
    """
    if ctx.result is None:
        return RobotState.IDLE
    loop = asyncio.get_running_loop()
    try:
        # cv2 capture is blocking I/O — keep it off the event loop.
        frame = await loop.run_in_executor(None, capture_frame)
        ctx.result = await respond_vision(ctx.result.text_heard, frame)
    except (CameraError, ServerError, ValueError) as exc:
        logger.error("Vision turn failed — returning to listen: %s", exc)
        return RobotState.IDLE
    logger.info("Robot (vision): %s", ctx.result.llm_response)
    return RobotState.SPEAKING


async def _on_error(_ctx: LoopContext) -> RobotState:
    """Wait a beat and recover — the robot never stays down."""
    await asyncio.sleep(_ERROR_RECOVERY_S)
    logger.info("Recovered from error — listening again")
    return RobotState.IDLE


async def tick(state: RobotState, ctx: LoopContext) -> RobotState:
    """Execute one FSM state and return the next state.

    Args:
        state: Current state to execute.
        ctx: Shared context mutated across states (audio in, result out).

    Returns:
        The next state of the loop.
    """
    match state:
        case RobotState.IDLE:
            return await _on_idle(ctx)
        case RobotState.LISTENING:
            return await _on_listening(ctx)
        case RobotState.THINKING:
            return await _on_thinking(ctx)
        case RobotState.SPEAKING:
            return await _on_speaking(ctx)
        case RobotState.LOOKING:
            return await _on_looking(ctx)
        case RobotState.ERROR:
            return await _on_error(ctx)


async def _guard_streaming_vision_compat() -> None:
    """Refuse to start with ROBOT_STREAMING and server vision both enabled.

    /transcribe/stream never detects visual questions (see
    transcribe_stream's docstring in server_client.py) and app_streaming.py
    has no LOOKING transition, so this combination would silently drop
    "what do you see?" turns instead of failing loudly — F-08 in
    docs/c-audit/auditoria-forense-codigo-2026-07-21.md. Only checked when
    streaming is on: a non-streaming robot has no reason to pay this extra
    network round trip at startup.

    Raises:
        SystemExit: If ROBOT_STREAMING is True and the server reports
            vision_enabled True.
    """
    if not settings.robot_streaming:
        return
    if await check_vision_enabled():
        logger.error(
            "ROBOT_STREAMING=true is incompatible with the server's "
            "VISION_ENABLED=true — streaming does not support visual "
            "questions yet (F-08, docs/c-audit/"
            "auditoria-forense-codigo-2026-07-21.md). Disable one of the "
            "two before starting the robot."
        )
        raise SystemExit(1)


async def _run() -> None:
    """Run the FSM forever, surviving any unexpected exception."""
    logger.info("OMNiBot robot client starting — state machine online")
    state = RobotState.IDLE
    ctx = LoopContext()
    try:
        await _guard_streaming_vision_compat()
        while True:
            try:
                state = await tick(state, ctx)
            except Exception as exc:
                # The loop must never die: anything tick() did not anticipate
                # is logged and recovered through the ERROR state.
                logger.error("Unexpected error in state %s: %s", state.name, exc, exc_info=True)
                state = RobotState.ERROR
    finally:
        await close_client()


def main() -> None:
    """Entry point for the robot script."""
    log_format = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    log_datefmt = "%Y-%m-%d %H:%M:%S"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if settings.log_to_file:
        # JSON Lines on disk for analysis tools; the console stays human-readable.
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            build_file_handler(settings.log_dir / "robot.log", settings.log_retention_days)
        )
    logging.basicConfig(
        level=settings.log_level.upper(),
        format=log_format,
        datefmt=log_datefmt,
        handlers=handlers,
    )
    asyncio.run(_run())
