"""Pydantic schemas shared across the brain subsystem."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EntityType = Literal[
    "person",
    "place",
    "object",
    "event",
    "preference",
    "schedule",
    "concept",
    "other",
]


class ConversationTurn(BaseModel):
    """A single turn in the conversation history.

    Attributes:
        role: Speaker role — either ``"user"`` or ``"assistant"``.
        content: Text of the turn.
        timestamp: UTC timestamp of the turn.
    """

    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FactRecord(BaseModel):
    """A single active fact about an entity.

    Attributes:
        predicate: Relation name in snake_case (e.g. ``"vive_en"``).
        object_value: Value of the relation.
        confidence: Confidence score in ``[0, 1]``.
    """

    predicate: str
    object_value: str
    confidence: float = Field(ge=0, le=1, default=1.0)


class EntityWithFacts(BaseModel):
    """An entity together with its active facts.

    Attributes:
        id: Database row id.
        name: Canonical name of the entity.
        type: Entity category.
        facts: Active (non-superseded) fact records.
    """

    id: int
    name: str
    type: EntityType
    facts: list[FactRecord] = Field(default_factory=list)


class MemoryHit(BaseModel):
    """A single result from a semantic memory search.

    Attributes:
        id: Database row id.
        kind: Memory kind: episodic, semantic, or reflection.
        content: Full content of the memory.
        summary: Short summary used for embedding (optional).
        importance: Importance score in ``[0, 1]``.
        distance: Vector distance from query (lower = more similar).
    """

    id: int
    kind: Literal["episodic", "semantic", "reflection"]
    content: str
    summary: str | None
    importance: float
    distance: float


class MemoryContext(BaseModel):
    """Assembled context injected into the LLM prompt.

    Attributes:
        entities: Relevant entities with their active facts.
        memories: Top-K semantic memory hits for the current query.
    """

    entities: list[EntityWithFacts] = Field(default_factory=list)
    memories: list[MemoryHit] = Field(default_factory=list)


class ExtractedEntity(BaseModel):
    """An entity extracted from a conversation turn by the consolidation LLM.

    Attributes:
        name: Canonical entity name.
        type: Entity category.
        attributes: Key-value attributes (free-form JSON).
        aliases: Alternative names for the entity.
    """

    name: str
    type: EntityType
    attributes: dict[str, Any] = Field(default_factory=dict)  # Any: open schema from LLM
    aliases: list[str] = Field(default_factory=list)


class ExtractedFact(BaseModel):
    """A fact triple extracted from a conversation turn.

    Attributes:
        subject: Subject entity name.
        predicate: Relation name in snake_case.
        object: Value of the relation.
        confidence: Confidence score in ``[0, 1]``.
    """

    subject: str
    predicate: str
    object: str
    confidence: float = Field(ge=0, le=1, default=0.9)


class TurnExtraction(BaseModel):
    """Result of consolidation LLM extraction for one conversation turn.

    Attributes:
        entities: Entities mentioned or implied in the turn.
        facts: Persistent facts inferred from the turn.
        episodic_summary: Short summary if the turn is worth remembering; ``None`` otherwise.
        importance: Overall importance score in ``[0, 1]``.
    """

    entities: list[ExtractedEntity] = Field(default_factory=list)
    facts: list[ExtractedFact] = Field(default_factory=list)
    episodic_summary: str | None = None
    importance: float = Field(ge=0, le=1, default=0.5)


class HealthResponse(BaseModel):
    """Response from GET /health."""

    status: str = Field(default="ok")
    # Additive field: lets the robot ask "does this server have vision on?"
    # via the API it already calls, instead of reading server config across
    # the hard client/server boundary (F-08 streaming/vision incompatibility
    # guard — see docs/c-audit/auditoria-forense-codigo-2026-07-21.md).
    vision_enabled: bool = Field(
        default=False, description="Whether the server has vision (VLM) enabled"
    )


class TranscribeResponse(BaseModel):
    """Response from POST /transcribe."""

    text_heard: str = Field(description="Transcribed user speech")
    llm_response: str = Field(description="Robot text response")
    audio_base64: str = Field(description="WAV audio encoded as base64 — 16kHz mono int16")
    duration_ms: int = Field(ge=0, description="TTS synthesis time in milliseconds")
    emotion: str = Field(default="neutral", description="Detected user emotion")
    # Additive field (contract allows adding): the server wants ONE camera
    # frame — the client should capture and POST /vision/respond (V0.5).
    vision_requested: bool = Field(
        default=False, description="Client should send a camera frame to /vision/respond"
    )
    # Additive fields (R2): per-stage latency, measured in the endpoint so
    # R3's sentence-streaming win can be demonstrated against a real baseline.
    stt_ms: int = Field(default=0, ge=0, description="Speech-to-text time in milliseconds")
    llm_ms: int = Field(default=0, ge=0, description="LLM response generation time in milliseconds")
    tts_ms: int = Field(
        default=0, ge=0, description="Text-to-speech synthesis time in milliseconds"
    )
    total_ms: int = Field(
        default=0, ge=0, description="Full /transcribe request time in milliseconds"
    )
    # Additive field: whether this turn consumed a fresh one-use owner unlock
    # grant (X-Iroko-Identity-Token). Absent/expired/replayed tokens leave
    # this False without disclosing which case occurred.
    authentication_consumed: bool = Field(
        default=False, description="Whether this turn consumed a fresh owner unlock grant"
    )


class VisionDescribeResponse(BaseModel):
    """Response from POST /vision/describe."""

    description: str = Field(description="Scene description in Spanish")
    duration_ms: int = Field(ge=0, description="VLM inference time in milliseconds")


class VisionEnrollResponse(BaseModel):
    """Response from POST /vision/enroll."""

    name: str = Field(description="Person name as stored (title-cased)")
    entity_id: int = Field(description="Memory entity the face links to")
    profile_id: int = Field(description="New face profile id")


class SensorReading(BaseModel):
    """A raw sensor measurement.

    Attributes:
        sensor_id: Unique identifier for the sensor.
        sensor_type: Sensor category (e.g. ``"temperature"``, ``"gas"``).
        value: Numeric measurement.
        unit: Physical unit (e.g. ``"celsius"``, ``"ppm"``).
        location: Optional physical location (e.g. ``"kitchen"``).
        metadata: Arbitrary extra fields (free-form JSON).
        created_at: UTC timestamp of the reading.
    """

    sensor_id: str
    sensor_type: str
    value: float
    unit: str
    location: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)  # Any: open schema from sensors
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
