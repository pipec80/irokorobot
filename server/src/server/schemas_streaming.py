"""NDJSON event schemas for POST /transcribe/stream (R3).

Kept separate from schemas.py (which was already near the 200-line file
limit) rather than growing that file — same split rationale as the
routers/pipeline.py split in bitácora 011. TranscribeResponse in schemas.py
is untouched; these events are a distinct wire format for the streaming
endpoint only.
"""

from typing import Literal

from pydantic import BaseModel, Field


class StreamTextHeardEvent(BaseModel):
    """First NDJSON event on POST /transcribe/stream — the STT transcript."""

    type: Literal["text_heard"] = "text_heard"
    value: str = Field(description="Transcribed user speech")


class StreamEmotionEvent(BaseModel):
    """NDJSON event carrying the detected emotion, emitted before any audio."""

    type: Literal["emotion"] = "emotion"
    value: str = Field(description="Detected user emotion")


class StreamAudioEvent(BaseModel):
    """NDJSON event carrying one synthesized sentence's audio."""

    type: Literal["audio"] = "audio"
    text: str = Field(description="The sentence this audio chunk speaks")
    audio_base64: str = Field(description="WAV audio encoded as base64 — 16kHz mono int16")
    duration_ms: int = Field(ge=0, description="TTS synthesis time in milliseconds")


class StreamDoneEvent(BaseModel):
    """Final NDJSON event on POST /transcribe/stream — per-stage latency."""

    type: Literal["done"] = "done"
    stt_ms: int = Field(default=0, ge=0, description="Speech-to-text time in milliseconds")
    llm_ms: int = Field(default=0, ge=0, description="LLM response generation time in milliseconds")
    tts_ms: int = Field(default=0, ge=0, description="Total text-to-speech time in milliseconds")
    total_ms: int = Field(default=0, ge=0, description="Full request time in milliseconds")
