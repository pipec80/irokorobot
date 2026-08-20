"""Streaming (R3) FSM states for robot/app.py's THINKING and SPEAKING.

Split out of app.py to stay under the 200-line file limit. Only used when
``settings.robot_streaming`` is True; the classic THINKING/SPEAKING path in
app.py (the default) is untouched.

Defense in depth: the server (P0-C6 tasks 1-3) no longer emits an invalid
event ordering, but this module still validates every event through
``StreamValidationState`` instead of trusting the server unconditionally.
"""

import base64
from collections.abc import AsyncIterator
import logging
import time

from robot.audio_playback import play_wav_stream
from robot.exceptions import AudioPlaybackError, NoSpeechError, ServerError
from robot.fsm_types import LoopContext, RobotState
from robot.server_client import transcribe_stream
from robot.stream_events import AudioEvent, DoneEvent, EmotionEvent, StreamEvent, TextHeardEvent
from robot.stream_validation import StreamValidationState

logger = logging.getLogger(__name__)


def _elapsed_ms(start: float | None) -> float | None:
    """Return milliseconds elapsed since a ``time.perf_counter()`` reading."""
    return None if start is None else (time.perf_counter() - start) * 1000


async def on_thinking_stream(ctx: LoopContext) -> RobotState:
    """Streaming variant of THINKING: start the stream, log the transcript.

    Only the first event (text_heard) is consumed here — the same failure
    modes as classic ``transcribe()`` surface on it, since this is when the
    server would otherwise have raised NoSpeechError/ServerError. The rest
    of the stream is handed to SPEAKING via ``ctx.stream_events``.
    """
    events = transcribe_stream(ctx.audio)
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
        logger.error("Unexpected first stream event: %r", first)
        return RobotState.ERROR
    logger.info("Heard: %s", first.value)
    ctx.stream_events = events
    return RobotState.SPEAKING


async def _audio_chunks(
    events: AsyncIterator[StreamEvent],
    state: StreamValidationState,
    request_start: float | None,
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
        request_start: ``time.perf_counter()`` reading from THINKING, used
            to log first-chunk receive latency.

    Yields:
        Decoded WAV bytes, one per audio event (i.e. one per sentence).

    Raises:
        ServerError: If any event violates the expected ordering, or the
            stream ends without a valid audio+done sequence.
    """
    done: DoneEvent | None = None
    first_chunk_logged = False
    async for event in events:
        state.accept(event)
        if isinstance(event, EmotionEvent):
            logger.info("Robot emotion: %s", event.value)
        elif isinstance(event, AudioEvent):
            if not first_chunk_logged:
                elapsed = _elapsed_ms(request_start)
                if elapsed is not None:
                    logger.debug("First chunk received: %.1fms", elapsed)
                first_chunk_logged = True
            if event.text:
                logger.info("Speaking: %s", event.text)
            yield base64.b64decode(event.audio_base64)
        elif isinstance(event, DoneEvent):
            done = event
    state.finish()
    if done is not None:
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
        await play_wav_stream(
            _audio_chunks(events, state, request_start), on_chunk_start=_on_chunk_start
        )
    except (AudioPlaybackError, ValueError) as exc:
        logger.error("Streaming playback failed: %s", exc)
        return RobotState.ERROR
    except (ServerError, NoSpeechError) as exc:
        logger.error("Server stream failed mid-turn: %s", exc)
        return RobotState.ERROR
    return RobotState.IDLE
