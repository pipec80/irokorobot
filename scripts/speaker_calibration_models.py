"""Frozen types and vocabulary for the Plan 0047 speaker-calibration harness.

Types, constants and report-invariant checks only — no I/O, no numeric math and
no embedding backend. The pure numeric layer lives in
``scripts.speaker_calibration``; manifest, corpus and report behaviour lives in
``scripts.speaker_calibration_corpus``. The concrete SpeechBrain backend that
satisfies :class:`SpeakerEmbeddingBackend` is added in Task 3.

This study never enrols a production voiceprint and never makes ``VOICE``
trusted identity evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import TYPE_CHECKING, Final, Literal, Protocol, get_args

if TYPE_CHECKING:
    import numpy as np

SampleClass = Literal["reference", "genuine", "impostor", "replay"]
SAMPLE_CLASSES: Final[tuple[SampleClass, ...]] = get_args(SampleClass)

SCHEMA_VERSION: Final = 1
CONDITIONS: Final = ("quiet-near", "quiet-far", "background-near", "background-far")
PHRASE_IDS: Final = ("phrase-01", "phrase-02", "phrase-03")
# The three frozen neutral Spanish phrases (Plan 0047 block 4). Single source of
# truth: the capture CLI shows these so the operator needs no second terminal.
PHRASE_TEXT: Final[dict[str, str]] = {
    "phrase-01": "La lluvia cae despacio sobre el tejado de la casa",
    "phrase-02": "Guardé cinco libros nuevos en el estante de madera",
    "phrase-03": "Prefiero caminar por el parque cuando termina la tarde",
}
OWNER_SUBJECT_ID: Final = "owner"
IMPOSTOR_ID_PATTERN: Final = re.compile(r"^impostor_[a-z]+$")
EMBEDDING_DIM: Final = 192

MINIMUM_SAMPLES: Final[dict[SampleClass, int]] = {
    "reference": 6,
    "genuine": 24,
    "impostor": 18,
    "replay": 6,
}
MIN_GENUINE_SESSIONS: Final = 2
MIN_IMPOSTOR_SUBJECTS: Final = 3

DEFAULT_CORPUS_ROOT: Final = Path("project-history/calibration/speaker")
MANIFEST_NAME: Final = "manifest.json"
EMBEDDINGS_NAME: Final = "embeddings.npz"
REPORT_NAME: Final = "aggregate-report.md"

CliAction = Literal["model-contract", "capture", "validate", "embed", "analyze", "cleanup"]
CLI_ACTIONS: Final[tuple[CliAction, ...]] = get_args(CliAction)
CAPTURE_FLAGS: Final = ("sample_class", "subject_id", "session_id", "phrase_id", "condition")

ReportOutcome = Literal[
    "provisional_pass",
    "fail_distance_overlap",
    "fail_backend_latency",
    "invalid_procedure",
]

_RATE_FIELDS: Final = (
    "live_false_accepts",
    "live_far",
    "genuine_false_rejects",
    "genuine_frr",
    "replay_accepts",
    "replay_accept_rate",
)
_METRIC_FIELDS: Final = (*_RATE_FIELDS, "latency_p50_ms", "latency_p95_ms")


@dataclass(frozen=True)
class SpeakerSample:
    """One captured calibration sample's metadata — never the audio itself."""

    sample_id: str
    subject_id: str
    sample_class: SampleClass
    session_id: str
    phrase_id: str
    condition: str
    wav_path: Path
    sha256: str


@dataclass(frozen=True)
class EmbeddedSample:
    """A sample paired with its finite 192-d embedding and embed latency."""

    sample: SpeakerSample
    embedding: np.ndarray
    latency_ms: float


@dataclass(frozen=True)
class SpeakerManifest:
    """The full validated set of samples for one calibration corpus."""

    schema_version: Literal[1]
    samples: tuple[SpeakerSample, ...]


@dataclass(frozen=True)
class ConditionSummary:
    """Accept/reject counts and distance range for one class + condition cell."""

    sample_class: SampleClass
    condition: str
    total: int
    accepted: int
    rejected: int
    distance_min: float
    distance_max: float
    distance_mean: float


@dataclass(frozen=True)
class SpeakerCliOptions:
    """One fully parsed and cross-checked speaker-calibration invocation."""

    action: CliAction
    corpus_root: Path
    manifest_path: Path
    output_path: Path | None
    sample_class: SampleClass | None
    subject_id: str | None
    session_id: str | None
    phrase_id: str | None
    condition: str | None


@dataclass(frozen=True)
class AggregateSpeakerReport:
    """Privacy-reviewed aggregate result — no ids, hashes, transcripts or paths.

    ``__post_init__`` rejects any field combination inconsistent with
    ``outcome`` rather than filling a missing value with zero.
    """

    model_id: str
    package_version: str
    sample_counts: dict[SampleClass, int]
    selected_threshold: float | None
    live_false_accepts: int | None
    live_far: float | None
    genuine_false_rejects: int | None
    genuine_frr: float | None
    replay_accepts: int | None
    replay_accept_rate: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    by_condition: dict[str, ConditionSummary]
    outcome: ReportOutcome
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate the report against its ``outcome``.

        Raises:
            ValueError: If a mandatory field is missing or a field is set that
                the outcome forbids.
        """
        if not self.model_id or not self.package_version:
            raise ValueError("model_id and package_version are always mandatory")
        if not self.limitations:
            raise ValueError("limitations must always name the small-corpus confidence limit")
        match self.outcome:
            case "fail_backend_latency":
                self._reject_corpus_and_rates()
            case "provisional_pass":
                self._require_full_measurement()
                self._require_threshold(present=True)
                if self.live_false_accepts != 0:
                    raise ValueError("provisional_pass requires zero live false accepts")
            case "fail_distance_overlap":
                self._require_full_measurement()
                self._require_threshold(present=False)
            case "invalid_procedure":
                pass  # renders only what was observed; limitations already required

    def _reject_corpus_and_rates(self) -> None:
        for name in ("selected_threshold", *_RATE_FIELDS):
            if getattr(self, name) is not None:
                raise ValueError(f"fail_backend_latency requires {name} to be None")
        if self.sample_counts or self.by_condition:
            raise ValueError("fail_backend_latency permits no corpus")

    def _require_full_measurement(self) -> None:
        for name in _METRIC_FIELDS:
            if getattr(self, name) is None:
                raise ValueError(f"a measurement outcome requires {name}")
        missing = set(SAMPLE_CLASSES) - set(self.sample_counts)
        if missing:
            raise ValueError(f"sample_counts is missing classes: {sorted(missing)}")
        if not self.by_condition:
            raise ValueError("a measurement outcome requires per-condition summaries")

    def _require_threshold(self, *, present: bool) -> None:
        if (self.selected_threshold is not None) != present:
            state = "a selected threshold" if present else "no selected threshold"
            raise ValueError(f"outcome {self.outcome} requires {state}")


class SpeakerEmbeddingBackend(Protocol):
    """One replaceable local embedding backend (concrete impl added in Task 3)."""

    @property
    def model_id(self) -> str:
        """Return the frozen model identifier and revision."""
        ...

    def embed_wav(self, wav_bytes: bytes) -> np.ndarray:
        """Embed WAV audio at 16 kHz, mono, signed int16 into a finite 192-d vector."""
        ...
