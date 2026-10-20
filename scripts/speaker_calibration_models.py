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

SampleClass = Literal[
    "reference",
    "genuine",
    "impostor",
    "replay",
    "reference-short",
    "genuine-short",
    "impostor-short",
    "replay-short",
]
SAMPLE_CLASSES: Final[tuple[SampleClass, ...]] = get_args(SampleClass)
# Plan 0047 classes (3-5 s fixed phrases) and Plan 0068 classes (1-2.5 s spoken
# answers). A short class never counts toward a long-class minimum, or the reverse.
LONG_CLASSES: Final[tuple[SampleClass, ...]] = ("reference", "genuine", "impostor", "replay")
SHORT_CLASSES: Final[tuple[SampleClass, ...]] = (
    "reference-short",
    "genuine-short",
    "impostor-short",
    "replay-short",
)
SHORT_SUFFIX: Final = "-short"

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
# Plan 0068 D-5: the short spoken answers. Same words for the owner and the
# impostors, so the comparison is about the voice and not the vocabulary.
SHORT_PHRASE_IDS: Final = ("short-01", "short-02", "short-03")
SHORT_PHRASE_TEXT: Final[dict[str, str]] = {
    "short-01": "Sí",
    "short-02": "Acepto",
    "short-03": "Sí, autorizo",
}
# Everything the capture prompt may show, long and short.
ALL_PHRASE_IDS: Final = (*PHRASE_IDS, *SHORT_PHRASE_IDS)
ALL_PHRASE_TEXT: Final[dict[str, str]] = {**PHRASE_TEXT, **SHORT_PHRASE_TEXT}
OWNER_SUBJECT_ID: Final = "owner"
IMPOSTOR_ID_PATTERN: Final = re.compile(r"^impostor_[a-z]+$")
# Session ids become part of a WAV file name: lowercase words only, so no path
# separator, drive colon (an NTFS alternate data stream) or empty value gets in.
SESSION_ID_PATTERN: Final = re.compile(r"^[a-z0-9-]{1,40}$")
EMBEDDING_DIM: Final = 192
# Capture lower bound in seconds (Plan 0047 block 4 for long takes; Plan 0068 D-5
# for short answers, which are a single word or two).
LONG_MIN_CAPTURE_SECONDS: Final = 2.5
SHORT_MIN_CAPTURE_SECONDS: Final = 1.0

MINIMUM_SAMPLES: Final[dict[SampleClass, int]] = {
    "reference": 6,
    "genuine": 24,
    "impostor": 18,
    "replay": 6,
}
# Plan 0068 D-5 matrix, applied when the corpus holds any short sample: the long
# reference and long genuine classes are then only the control (6 each); the short
# classes carry the study. Impostor and replay exist only as short classes.
SHORT_STUDY_MINIMUMS: Final[dict[SampleClass, int]] = {
    "reference": 6,
    "genuine": 6,
    "reference-short": 6,
    "genuine-short": 24,
    "impostor-short": 18,
    "replay-short": 6,
}
MIN_GENUINE_SESSIONS: Final = 2
# Plan 0047 matrix: the reference and every live impostor read each frozen
# phrase at least this many times.
MIN_PHRASE_REPETITIONS: Final = 2
REPLAY_CONDITIONS: Final = ("quiet-near", "quiet-far")
MIN_IMPOSTOR_SUBJECTS: Final = 3

DEFAULT_CORPUS_ROOT: Final = Path("project-history/calibration/speaker")
MANIFEST_NAME: Final = "manifest.json"
EMBEDDINGS_NAME: Final = "embeddings.npz"
REPORT_NAME: Final = "aggregate-report.md"
MODEL_CACHE_DIRNAME: Final = "model-cache"
# ``embeddings.npz`` holds one vector per sample_id plus, in reserved namespaces,
# that sample's embedding latency in ms (``LATENCY_KEY_PREFIX + sample_id``), the
# WAV sha256 it was computed from (``SHA_KEY_PREFIX + sample_id``) and the model
# id that produced every vector (``MODEL_KEY``), so ``analyze`` can refuse stale
# or foreign vectors.
LATENCY_KEY_PREFIX: Final = "__lat__"
SHA_KEY_PREFIX: Final = "__sha__"
MODEL_KEY: Final = "__model__"

CliAction = Literal[
    "model-contract", "capture", "validate", "embed", "analyze", "cleanup", "discard"
]
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


def is_short_class(sample_class: str) -> bool:
    """Return ``True`` for the Plan 0068 short-answer classes."""
    return sample_class.endswith(SHORT_SUFFIX)


def base_class(sample_class: str) -> str:
    """Return the long class a class belongs to (``genuine-short`` -> ``genuine``)."""
    return sample_class.removesuffix(SHORT_SUFFIX)


def phrase_ids_for(sample_class: str) -> tuple[str, ...]:
    """Return the frozen phrase ids a class may use: short ids only for short classes."""
    return SHORT_PHRASE_IDS if is_short_class(sample_class) else PHRASE_IDS


def min_capture_seconds(sample_class: str) -> float:
    """Return the shortest live take, in seconds, ``capture`` accepts for a class."""
    return SHORT_MIN_CAPTURE_SECONDS if is_short_class(sample_class) else LONG_MIN_CAPTURE_SECONDS


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
    sample_id: str | None = None  # only for ``discard --sample``
    purge_model_cache: bool = False  # only for ``cleanup --purge-model-cache``


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
        missing = set(LONG_CLASSES) - set(self.sample_counts)
        if missing:
            raise ValueError(f"sample_counts is missing classes: {sorted(missing)}")
        if not self.by_condition:
            raise ValueError("a measurement outcome requires per-condition summaries")

    def _require_threshold(self, *, present: bool) -> None:
        if (self.selected_threshold is not None) != present:
            state = "a selected threshold" if present else "no selected threshold"
            raise ValueError(f"outcome {self.outcome} requires {state}")


# --- Plan 0068 short-answer study -------------------------------------------

# The speaker threshold the server runs today (Plan 0047, settings default). The
# short-answer study judges every variant AT this value and never retunes it.
SPEAKER_STUDY_THRESHOLD: Final = 0.4834
# The one speech-level floor of the study: a 20 ms frame is speech when its RMS
# (full scale = 1.0) is at least this. ``capture`` refuses a take whose 95th
# percentile frame is under it and ``trim_silence`` keeps only frames at or above
# it. It sits just under the quietest legitimate far-field take of the real corpus
# (p95 ~0.0065, -44 dBFS) and above empty-room noise (~0.002).
SPEECH_FRAME_RMS: Final = 0.004
# Reserved ``embeddings.npz`` namespaces added for a short-answer corpus: the
# embedding of the silence-trimmed clip and ``[raw_samples, trimmed_samples]``.
TRIM_KEY_PREFIX: Final = "__trim__"
CLIP_KEY_PREFIX: Final = "__clip__"

# A cell smaller than this reports no distance range or mean: the range would
# expose a single sample's raw score (Plan 0047 privacy rule - counts and ranges
# only). Shared by the long-study and short-study renderers.
MIN_CELL_FOR_RANGE: Final = 3

ClipVariant = Literal["raw", "trimmed"]
ReferenceSet = Literal["long-only", "long+short"]
CLIP_VARIANTS: Final[tuple[ClipVariant, ...]] = get_args(ClipVariant)
REFERENCE_SETS: Final[tuple[ReferenceSet, ...]] = get_args(ReferenceSet)
# Classes scored against the reference centroids: the long genuine control and
# the three short probe classes.
SHORT_STUDY_PROBES: Final[tuple[SampleClass, ...]] = (
    "genuine",
    "genuine-short",
    "impostor-short",
    "replay-short",
)


@dataclass(frozen=True)
class ClipInfo:
    """Length of one clip before and after silence trimming, in samples at 16 kHz."""

    raw_samples: int
    trimmed_samples: int


@dataclass(frozen=True)
class VariantCell:
    """One class scored in one variant. A silent-after-trim clip is rejected, with no distance.

    ``distance_*`` are ``None`` for fewer than three scored clips: a range over one
    or two clips would expose a raw per-sample score.
    """

    sample_class: SampleClass
    total: int
    accepted: int
    silent: int
    distance_min: float | None
    distance_mean: float | None
    distance_max: float | None


@dataclass(frozen=True)
class LengthBucketCell:
    """Accepts of one class among the clips whose raw length falls in one bucket."""

    sample_class: SampleClass
    bucket: str
    total: int
    accepted: int


@dataclass(frozen=True)
class VariantResult:
    """Every cell of one (clip variant, reference set) pair."""

    clip: ClipVariant
    references: ReferenceSet
    cells: dict[str, VariantCell]
    buckets: tuple[LengthBucketCell, ...]

    @property
    def impostor_accepts(self) -> int:
        """Return how many short impostor clips this variant accepts."""
        return self.cells["impostor-short"].accepted

    @property
    def eligible(self) -> bool:
        """Return ``True`` only with 0 observed accepts on the short impostor class."""
        return self.impostor_accepts == 0


@dataclass(frozen=True)
class SilenceShare:
    """How much of the raw clips of one class the silence trim removes."""

    sample_class: SampleClass
    total: int
    silent_clips: int
    mean_share: float | None  # None for fewer than three clips


@dataclass(frozen=True)
class ShortStudyReport:
    """Aggregate result of the Plan 0068 short-answer comparison - no ids, hashes or paths."""

    model_id: str
    package_version: str
    threshold: float
    sample_counts: dict[SampleClass, int]
    variants: tuple[VariantResult, ...]
    silence: tuple[SilenceShare, ...]
    limitations: tuple[str, ...]

    def variant(self, clip: str, references: str) -> VariantResult:
        """Return the result of one (clip variant, reference set) pair.

        Raises:
            KeyError: If the pair is not one of the four compared variants.
        """
        for result in self.variants:
            if (result.clip, result.references) == (clip, references):
                return result
        raise KeyError((clip, references))


class SpeakerEmbeddingBackend(Protocol):
    """One replaceable local embedding backend (concrete impl added in Task 3)."""

    @property
    def model_id(self) -> str:
        """Return the frozen model identifier and revision."""
        ...

    def embed_wav(self, wav_bytes: bytes) -> np.ndarray:
        """Embed WAV audio at 16 kHz, mono, signed int16 into a finite 192-d vector."""
        ...
