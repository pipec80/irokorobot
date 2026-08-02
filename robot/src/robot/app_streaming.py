"""Streaming (R3) FSM states for robot/app.py's THINKING and SPEAKING.

Split out of app.py to stay under the 200-line file limit. Only used when
``settings.robot_streaming`` is True; the classic THINKING/SPEAKING path in
app.py (the default) is untouched.
"""

import base64
from collections.abc import AsyncIterator
import logging

from robot.audio_playback import play_wav_stream
from robot.exceptions import AudioPlaybackError, NoSpeechError, ServerError
from robot.fsm_types import LoopContext, RobotState
from robot.server_client import transcribe_stream
from robot.stream_events import AudioEvent, DoneEvent, EmotionEvent, StreamEvent, TextHeardEvent

logger = logging.getLogger(__name__)


async def on_thinking_stream(ctx: LoopContext) -> RobotState:
    """Streaming variant of THINKING: start the stream, log the transcript.

    Only the first event (text_heard) is consumed here — the same failure
    modes as classic ``transcribe()`` surface on it, since this is when the
    server would otherwise have raised NoSpeechError/ServerError. The rest
    of the stream is handed to SPEAKING via ``ctx.stream_events``.
    """
    events = transcribe_stream(ctx.audio)
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


async def _audio_chunks(events: AsyncIterator[StreamEvent]) -> AsyncIterator[bytes]:
    """Adapt the remaining stream events into WAV chunks for play_wav_stream.

    Args:
        events: Remaining stream events after THINKING already consumed the
            text_heard event — audio chunks are WAV at 16kHz mono int16 per
            the audio contract, base64-decoded here.

    Yields:
        Decoded WAV bytes, one per audio event (i.e. one per sentence).
    """
    async for event in events:
        if isinstance(event, EmotionEvent):
            logger.info("Robot emotion: %s", event.value)
        elif isinstance(event, AudioEvent):
            yield base64.b64decode(event.audio_base64)
        elif isinstance(event, DoneEvent):
            logger.info(
                "Pipeline (stream): stt=%dms llm=%dms tts=%dms total=%dms",
                event.stt_ms,
                event.llm_ms,
                event.tts_ms,
                event.total_ms,
            )


async def on_speaking_stream(ctx: LoopContext) -> RobotState:
    """Streaming variant of SPEAKING: drain the queued sentence audio.

    No LOOKING transition here — vision-intent turns are not part of the
    streaming protocol (see server/streaming.py), so a streaming turn always
    returns to IDLE once every sentence has played.
    """
    if ctx.stream_events is None:
        return RobotState.IDLE
    events, ctx.stream_events = ctx.stream_events, None
    try:
        await play_wav_stream(_audio_chunks(events))
    except (AudioPlaybackError, ValueError) as exc:
        logger.error("Streaming playback failed: %s", exc)
        return RobotState.ERROR
    except (ServerError, NoSpeechError) as exc:
        logger.error("Server stream failed mid-turn: %s", exc)
        return RobotState.ERROR
    return RobotState.IDLE
