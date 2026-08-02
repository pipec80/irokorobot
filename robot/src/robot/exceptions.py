"""Custom exceptions for the robot package."""


class AudioCaptureError(Exception):
    """Raised when microphone capture or VAD fails."""


class AudioPlaybackError(Exception):
    """Raised when speaker playback fails."""


class ServerError(Exception):
    """Raised when the server returns an unexpected response."""


class NoSpeechError(Exception):
    """Raised when the server found no speech in the audio (HTTP 422).

    Not a failure: ambient noise triggered the VAD but Whisper heard
    nothing. The caller should simply resume listening.
    """


class CameraError(Exception):
    """Raised when the webcam cannot be opened, read, or encoded."""
