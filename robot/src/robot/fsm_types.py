"""Shared FSM types for the robot main loop — RobotState and LoopContext.

Split out so both app.py (classic FSM) and app_streaming.py (R3 streaming
states) can depend on the same types without an import cycle between them.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum, auto

from robot.server_client import TranscribeResult
from robot.stream_events import StreamEvent


class RobotState(Enum):
    """States of the robot interaction loop."""

    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    LOOKING = auto()
    ERROR = auto()


@dataclass
class LoopContext:
    """Mutable data carried between FSM states within one interaction."""

    audio: bytes = b""
    result: TranscribeResult | None = None
    # R3 (robot_streaming=True): remaining stream events handed from THINKING
    # to SPEAKING once the text_heard event confirms the turn is live.
    stream_events: AsyncIterator[StreamEvent] | None = None
    # R3: time.perf_counter() reading taken before requesting/consuming the
    # first stream event — used to log receive/playback latency in
    # app_streaming.py. IDLE resets it; THINKING sets it.
    stream_request_start: float | None = None
    # Opt-in owner unlock token (classic mode only). Set once at startup by
    # the optional PIN prompt; cleared only when the server reports
    # authentication_consumed=true. IDLE must not reset it — it survives
    # across turns until consumed or the process restarts.
    identity_token: str | None = None
