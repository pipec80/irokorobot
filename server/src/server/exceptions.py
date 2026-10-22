"""Custom exceptions for the server package."""


class TranscriptionError(Exception):
    """Raised when faster-whisper cannot process the audio."""


class UnclearSpeechError(Exception):
    """Raised when Whisper's confidence in a non-empty transcript is below the threshold.

    Not a ``TranscriptionError``: the audio was processed, but the text is too doubtful to act
    on (Plan 0069 D-11). The message is fixed; the doubtful text travels only in ``text``.
    """

    def __init__(self, text: str) -> None:
        """Keep the doubtful transcript out of the message.

        Args:
            text: What Whisper heard, for the reply's ``text_heard`` only.
        """
        super().__init__("Transcript below the confidence threshold")
        self.text = text


class AudioContractError(Exception):
    """Raised when uploaded audio violates the WAV 16kHz/mono/int16 contract."""


class LLMError(Exception):
    """Raised when a local LLM operation fails."""


class TTSError(Exception):
    """Raised when Piper TTS synthesis fails."""


class BrainMemoryError(Exception):
    """Raised when the brain memory layer fails (DB, embeddings, etc)."""


class SecurityStorageUndecidedError(Exception):
    """Raised when a SECURITY value would be stored before storage at rest is decided.

    The message is fixed and never carries the value, the subject or the predicate's content
    (ADR 0022 decision 9): a refused value leaves no trace.
    """


class SensorError(Exception):
    """Raised when sensor ingestion or processing fails."""


class VisionError(Exception):
    """Raised when the VLM backend fails to describe an image."""


class UploadTooLargeError(Exception):
    """Raised when an upload exceeds its configured per-file byte limit."""

    def __init__(self, limit: int) -> None:
        """Record the limit that was exceeded — never the oversized payload.

        Args:
            limit: The byte budget the upload exceeded.
        """
        super().__init__(f"Upload exceeds the {limit}-byte limit")
        self.limit = limit


class ImageContractError(Exception):
    """Raised when an uploaded image violates the vision image contract.

    Unlike ``VisionError`` (always a 503 — a backend failure), this is a
    422: the client sent bytes in an unknown/unsupported format, bytes
    that fail to decode as an image, or an image whose dimensions exceed
    the contract limit.
    """


class EnrollmentRejectedError(VisionError):
    """Raised when a frame fails the face-enrollment business rules.

    Attributes:
        code: Machine-readable reason — ``no_face``, ``multiple_faces``,
            ``low_quality`` or ``face_too_small``. Lets the API map to a
            422 detail and the conversational flow pick a friendly phrase.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AmbiguousEntityError(Exception):
    """Raised when a third party's folded name and type already exist and are not re-claimed."""
