"""Streaming (R3) FSM states for robot/app.py's THINKING and SPEAKING.

Split out of app.py to stay under the 200-line file limit. Only used when
``settings.robot_streaming`` is True; the classic THINKING/SPEAKING path in
app.py (the default) is untouched.

Defense in depth: the server (P0-C6 tasks 1-3) no longer emits an invalid
event ordering, but this module still validates every event through
``StreamValidationState`` instead of trusting the server unconditionally.
"""

import asyncio
import base64
from collections.abc import AsyncIterator
import logging
import time

from robot.audio_playback import play_wav_stream
from robot.camera_capture import capture_frame
from robot.exceptions import AudioPlaybackError, CameraError, NoSpeechError, ServerError
from robot.fsm_types import LoopContext, RobotState
from robot.server_client import transcribe_stream
from robot.settings import settings
from robot.stream_events import (
    AudioEvent,
    DoneEvent,
    EmotionEvent,
    ErrorEvent,
    StreamEvent,
    TextHeardEvent,
)
from robot.stream_validation import StreamValidationState

logger = logging.getLogger(__name__)


def _elapsed_ms(start: float | None) -> float | None:
    """Return milliseconds elapsed since a ``time.perf_counter()`` reading."""
    return None if start is None else (time.perf_counter() - start) * 1000


async def capture_face_frame_if_enabled() -> bytes | None:
    """Capture one webcam frame for face authentication, if opted in.

    Shared by classic THINKING (app.py) and streaming THINKING (this
    module) — defined here rather than in app.py because app.py already
    imports this module at load time, and the reverse import would be
    circular.

    Gated by ``settings.robot_face_auth_enabled`` (Plan 0029); off by
    default, so the webcam is never opened. Because the robot cannot know
    in advance whether an upcoming utterance will turn out to be a
    protected question, enabling this opens the webcam on EVERY turn —
    OpenCV capture costs low-hundreds of milliseconds. Measuring or
    mitigating that latency (e.g. keeping the camera open across turns) is
    out of scope for this plan; see Plan 0030 (real-camera acceptance).

    A camera failure degrades to sending the turn without a frame — it
    never raises and never blocks the turn, exactly as if the setting were
    disabled.

    Returns:
        JPEG frame bytes, or None when disabled or the capture failed.
    """
    if not settings.robot_face_auth_enabled:
        return None
    try:
        # cv2 capture is blocking I/O — keep it off the event loop.
        return await asyncio.to_thread(capture_frame)
    except CameraError as exc:
        logger.warning("Face-auth frame capture failed — sending turn without a frame: %s", exc)
        return None


async def on_thinking_stream(ctx: LoopContext) -> RobotState:
    """Streaming variant of THINKING: start the stream, log the transcript.

    Only the first event (text_heard) is consumed here — the same failure
    modes as classic ``transcribe()`` surface on it, since this is when the
    server would otherwise have raised NoSpeechError/ServerError. The rest
    of the stream is handed to SPEAKING via ``ctx.stream_events``.
    """
    frame = await capture_face_frame_if_enabled()
    events = transcribe_stream(ctx.audio, identity_token=ctx.identity_token, frame=frame)
    ctx.stream_request_start = time.perf_counter()
    try:
        first = await anext(events)
    except NoSpeechError:
        logger.info("No speech understood — listening again")
        return RobotState.IDLE
    except (ServerError, ValueError) as exc:
        logger.error("Server stream request failed: %s", exc)
        return RobotState.ERROR
    if not isinstance(first, TextHeardEvent):
        logger.error("Unexpected first stream event: %s", type(first).__name__)
        return RobotState.ERROR
    logger.info("Heard: %d chars", len(first.value))
    ctx.stream_events = events
    return RobotState.SPEAKING


async def _audio_chunks(
    events: AsyncIterator[StreamEvent],
    state: StreamValidationState,
    ctx: LoopContext,
) -> AsyncIterator[bytes]:
    """Validate and adapt remaining stream events into WAV chunks.

    Consumption continues through EOF even after ``done`` arrives, so a
    duplicate or later event is still detected by ``state.accept()`` rather
    than silently accepted. The pipeline summary is logged only once
    ``state.finish()`` has validated a clean EOF.

    Args:
        events: Remaining stream events after THINKING already consumed the
            text_heard event — audio chunks are WAV at 16kHz mono int16 per
            the audio contract, base64-decoded here.
        state: Ordering validator; ``finish()`` is called once ``events``
            is exhausted.
        ctx: Loop context providing THINKING's ``time.perf_counter()``
            reading (for first-chunk latency) and holding the one-use owner
            token — cleared here only when the terminal DoneEvent reports
            ``authentication_consumed=True`` (Plan 0027). An EOF without
            ``done`` leaves the token untouched; a replay is safely denied
            server-side.

    Yields:
        Decoded WAV bytes, one per audio event (i.e. one per sentence).

    Raises:
        ServerError: If any event violates the expected ordering, the
            stream ends without a valid audio+done sequence, or the server
            emitted a terminal `error` event (Plan 0041, ADR 0012) — mapped
            to the same failure path as any other server/transport error.
    """
    done: DoneEvent | None = None
    error: ErrorEvent | None = None
    first_chunk_logged = False
    async for event in events:
        state.accept(event)
        if isinstance(event, EmotionEvent):
            logger.info("Robot emotion: %s", event.value)
        elif isinstance(event, AudioEvent):
            if not first_chunk_logged:
                elapsed = _elapsed_ms(ctx.stream_request_start)
                if elapsed is not None:
                    logger.debug("First chunk received: %.1fms", elapsed)
                first_chunk_logged = True
            if event.text:
                logger.info("Speaking: %d chars", len(event.text))
            yield base64.b64decode(event.audio_base64)
        elif isinstance(event, DoneEvent):
            done = event
        elif isinstance(event, ErrorEvent):
            error = event
    state.finish()
    if error is not None:
        # `error.detail` is fixed, client-safe text chosen by the server —
        # safe to log, never spoken aloud (no TTS call happens here).
        logger.error("Stream ended in error: code=%s retryable=%s", error.code, error.retryable)
        raise ServerError(f"Stream error: {error.code}")
    if done is not None:
        if done.authentication_consumed:
            ctx.identity_token = None
        logger.info(
            "Pipeline (stream): stt=%dms llm=%dms tts=%dms total=%dms chunks=%d",
            done.stt_ms,
            done.llm_ms,
            done.tts_ms,
            done.total_ms,
            state.audio_chunks,
        )


async def on_speaking_stream(ctx: LoopContext) -> RobotState:
    """Streaming variant of SPEAKING: validate and drain the queued audio.

    No LOOKING transition here — vision-intent turns are not part of the
    streaming protocol (see server/streaming.py), so a streaming turn always
    returns to IDLE once every sentence has played and the stream validated.
    """
    if ctx.stream_events is None:
        return RobotState.IDLE
    events, ctx.stream_events = ctx.stream_events, None
    request_start = ctx.stream_request_start
    state = StreamValidationState()

    def _on_chunk_start(index: int) -> None:
        if index != 1:
            return
        elapsed = _elapsed_ms(request_start)
        if elapsed is not None:
            logger.debug("First playback start: %.1fms", elapsed)

    try:
        await play_wav_stream(_audio_chunks(events, state, ctx), on_chunk_start=_on_chunk_start)
    except (AudioPlaybackError, ValueError) as exc:
        logger.error("Streaming playback failed: %s", exc)
        return RobotState.ERROR
    except (ServerError, NoSpeechError) as exc:
        logger.error("Server stream failed mid-turn: %s", exc)
        return RobotState.ERROR
    return RobotState.IDLE
