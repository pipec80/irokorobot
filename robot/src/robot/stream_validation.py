"""Protocol/ordering policy for the robot's NDJSON stream events (R3).

Enforced independently of the server (defense in depth): the server side
(P0-C6, tasks 1-3) no longer emits an invalid ordering, but the robot must
never treat a truncated, malformed, or out-of-order stream as a successful
turn just because the server is trusted.

Valid order: a required-once EmotionEvent that must precede any audio, then
one or more AudioEvent, then exactly one terminal DoneEvent. TextHeardEvent
is not expected here — ``on_thinking_stream`` already consumed it as the
first stream event before handing the rest of the stream to this validator.
"""

from dataclasses import dataclass

from robot.exceptions import ServerError
from robot.stream_events import (
    AudioEvent,
    DoneEvent,
    EmotionEvent,
    ErrorEvent,
    StreamEvent,
    TextHeardEvent,
)


@dataclass
class StreamValidationState:
    """Tracks stream progress and enforces valid event order."""

    emotion_seen: bool = False
    audio_chunks: int = 0
    done_seen: bool = False
    # Plan 0041 (ADR 0012): a terminal `error` may arrive with zero audio
    # chunks (e.g. TTS failed on the very first sentence) — it does not
    # share `done`'s "at least one audio chunk" requirement.
    error_seen: bool = False

    def accept(self, event: StreamEvent) -> None:
        """Advance valid order or raise ServerError.

        Args:
            event: The next decoded stream event.

        Raises:
            ServerError: If the event violates the expected ordering — a
                duplicate text_heard, a duplicate emotion, audio before
                emotion, done before any audio, a duplicate terminal, or
                any event received after either terminal (done or error).
        """
        if self.done_seen or self.error_seen:
            raise ServerError(f"Stream event received after terminal: {type(event).__name__}")
        match event:
            case TextHeardEvent():
                raise ServerError("Duplicate text_heard event in stream")
            case EmotionEvent():
                self._accept_emotion()
            case AudioEvent():
                self._accept_audio()
            case DoneEvent():
                self._accept_done()
            case ErrorEvent():
                self._accept_error()

    def _accept_emotion(self) -> None:
        if self.emotion_seen:
            raise ServerError("Duplicate emotion event in stream")
        self.emotion_seen = True

    def _accept_audio(self) -> None:
        if not self.emotion_seen:
            raise ServerError("Audio event received before emotion in stream")
        self.audio_chunks += 1

    def _accept_done(self) -> None:
        if self.audio_chunks == 0:
            raise ServerError("Done event received before any audio in stream")
        self.done_seen = True

    def _accept_error(self) -> None:
        self.error_seen = True

    def finish(self) -> None:
        """Require a valid terminal: one audio event plus done, or an error.

        Raises:
            ServerError: If the stream ended (EOF) without at least one
                audio event and a terminal done event, and no error
                terminal was seen either.
        """
        if self.error_seen:
            return
        if self.audio_chunks == 0 or not self.done_seen:
            raise ServerError(
                f"Stream ended incomplete: audio_chunks={self.audio_chunks} "
                f"done_seen={self.done_seen}"
            )
