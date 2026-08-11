"""Custom exceptions for the server package."""


class TranscriptionError(Exception):
    """Raised when faster-whisper cannot process the audio."""


class AudioContractError(Exception):
    """Raised when uploaded audio violates the WAV 16kHz/mono/int16 contract."""


class LLMError(Exception):
    """Raised when a local LLM operation fails."""


class TTSError(Exception):
    """Raised when Piper TTS synthesis fails."""


class BrainMemoryError(Exception):
    """Raised when the brain memory layer fails (DB, embeddings, etc)."""


class SensorError(Exception):
    """Raised when sensor ingestion or processing fails."""


class VisionError(Exception):
    """Raised when the VLM backend fails to describe an image."""


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
