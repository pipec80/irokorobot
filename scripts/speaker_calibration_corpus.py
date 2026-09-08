"""Private-corpus layer for the Plan 0047 speaker-calibration harness.

WAV-contract validation, strict manifest I/O, safe path resolution, corpus-rule
enforcement and aggregate-report rendering. No numeric math (that is
``scripts.speaker_calibration``), no embedding backend (Task 3) and no
microphone. Every real WAV, manifest and embedding stays under the gitignored
``project-history/calibration/speaker/`` root; nothing here writes outside it.

Audio contract, enforced by :func:`validate_wav_bytes`: WAV, 16 000 Hz, mono,
signed int16.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

# `server` is a workspace package with no py.typed marker; the real
# `just typecheck` checks it by path. `validate_wav_contract` is the single
# source of truth for the 16 kHz / mono / int16 rule (Plan 0047 reuse note).
from server.audio_contract import validate_wav_contract  # type: ignore[import-untyped]
from server.exceptions import AudioContractError  # type: ignore[import-untyped]

from scripts.speaker_calibration_models import (
    CONDITIONS,
    IMPOSTOR_ID_PATTERN,
    MIN_GENUINE_SESSIONS,
    MIN_IMPOSTOR_SUBJECTS,
    MINIMUM_SAMPLES,
    OWNER_SUBJECT_ID,
    PHRASE_IDS,
    SAMPLE_CLASSES,
    SCHEMA_VERSION,
    AggregateSpeakerReport,
    ConditionSummary,
    SpeakerManifest,
    SpeakerSample,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

# Generous ceiling: a fixed neutral phrase read and the 3-second latency WAV are
# both far below this. It bounds only accidental oversized captures, not format.
_MAX_WAV_SECONDS = 30.0

_SAMPLE_FIELDS = frozenset(
    {
        "sample_id",
        "subject_id",
        "sample_class",
        "session_id",
        "phrase_id",
        "condition",
        "wav_path",
        "sha256",
    }
)


def validate_wav_bytes(wav_bytes: bytes) -> None:
    """Validate WAV audio against the mandatory contract.

    Args:
        wav_bytes: Raw bytes, expected to be WAV — 16 000 Hz, mono, signed
            int16.

    Raises:
        ValueError: If the bytes are not a contract-conforming WAV container.
    """
    try:
        validate_wav_contract(wav_bytes, max_duration_s=_MAX_WAV_SECONDS)
    except AudioContractError as exc:
        raise ValueError(f"WAV does not meet the audio contract: {exc}") from exc


def sha256_of_file(path: Path) -> str:
    """Return the hex SHA-256 of the file at *path*, read in fixed-size chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_corpus_path(corpus_root: Path, wav_path: Path | str) -> Path:
    """Resolve *wav_path* against *corpus_root* and prove it stays inside it.

    Args:
        corpus_root: The calibration corpus root directory.
        wav_path: A path relative to the root, or an absolute path.

    Returns:
        The fully resolved WAV path.

    Raises:
        ValueError: If the resolved path escapes the root or is a symlink.
    """
    from pathlib import Path as _Path  # noqa: PLC0415 -- keep Path out of the annotation import

    root = _Path(corpus_root).resolve()
    candidate = _Path(wav_path)
    raw = candidate if candidate.is_absolute() else root / candidate
    resolved = raw.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"WAV path {wav_path!r} escapes the corpus root {root}")
    if raw.is_symlink():
        raise ValueError(f"WAV path {wav_path!r} is a symlink; corpus files must be real")
    return resolved


def load_manifest(path: Path, corpus_root: Path) -> SpeakerManifest:
    """Load a strict manifest and prove every WAV stays under *corpus_root*.

    Raises:
        ValueError: On a bad schema version, unknown fields, duplicate sample
            ids, a path escape or a SHA-256 mismatch against an existing file.
    """
    if not path.exists():
        raise ValueError(f"no manifest at {path} - capture at least one sample first")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest must be a JSON object")
    unknown = set(raw) - {"schema_version", "samples"}
    if unknown:
        raise ValueError(f"manifest has unknown fields: {sorted(unknown)}")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"manifest schema_version must be {SCHEMA_VERSION}, got {raw.get('schema_version')!r}"
        )
    rows = raw.get("samples")
    if not isinstance(rows, list):
        raise ValueError("manifest 'samples' must be a list")
    samples = tuple(_parse_row(row, corpus_root) for row in rows)
    ids = [s.sample_id for s in samples]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"manifest has duplicate sample_id values: {duplicates}")
    return SpeakerManifest(schema_version=SCHEMA_VERSION, samples=samples)


def _parse_row(row: object, corpus_root: Path) -> SpeakerSample:
    if not isinstance(row, dict):
        raise ValueError("each manifest sample must be a JSON object")
    if set(row) != _SAMPLE_FIELDS:
        unknown = sorted(set(row) - _SAMPLE_FIELDS)
        missing = sorted(_SAMPLE_FIELDS - set(row))
        raise ValueError(f"manifest sample off contract: unknown={unknown} missing={missing}")
    resolved = resolve_corpus_path(corpus_root, str(row["wav_path"]))
    _verify_sha256(resolved, str(row["sha256"]))
    return SpeakerSample(
        sample_id=str(row["sample_id"]),
        subject_id=str(row["subject_id"]),
        sample_class=row["sample_class"],
        session_id=str(row["session_id"]),
        phrase_id=str(row["phrase_id"]),
        condition=str(row["condition"]),
        wav_path=resolved,
        sha256=str(row["sha256"]),
    )


def _verify_sha256(path: Path, expected: str) -> None:
    if path.exists() and sha256_of_file(path) != expected:
        raise ValueError(f"sha256 mismatch for {path.name}: manifest says {expected}")


def append_sample_atomic(manifest_path: Path, corpus_root: Path, sample: SpeakerSample) -> None:
    """Append one validated sample, never exposing a partial manifest.

    Writes the whole manifest to a sibling ``.tmp`` file and swaps it into
    place with a single atomic rename.
    """
    rows: list[dict[str, str]] = list(_existing_rows(manifest_path))
    rows.append(_row_from_sample(sample, corpus_root))
    payload = {"schema_version": SCHEMA_VERSION, "samples": rows}
    tmp = manifest_path.with_name(manifest_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        tmp.replace(manifest_path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _existing_rows(manifest_path: Path) -> Iterable[dict[str, str]]:
    if not manifest_path.exists():
        return []
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("samples"), list):
        raise ValueError("existing manifest is malformed")
    return list(raw["samples"])


def _row_from_sample(sample: SpeakerSample, corpus_root: Path) -> dict[str, str]:
    from pathlib import Path as _Path  # noqa: PLC0415 -- keep Path out of the annotation import

    root = _Path(corpus_root).resolve()
    wav = _Path(sample.wav_path).resolve()
    rel = wav.relative_to(root) if wav.is_relative_to(root) else _Path(sample.wav_path)
    return {
        "sample_id": sample.sample_id,
        "subject_id": sample.subject_id,
        "sample_class": sample.sample_class,
        "session_id": sample.session_id,
        "phrase_id": sample.phrase_id,
        "condition": sample.condition,
        "wav_path": rel.as_posix(),
        "sha256": sample.sha256,
    }


def validate_corpus(manifest: SpeakerManifest) -> None:
    """Enforce subject, class, session, phrase, condition and matrix rules.

    Raises:
        ValueError: On the first rule a sample or the corpus as a whole breaks.
    """
    samples = manifest.samples
    if not samples:
        raise ValueError("corpus is empty")
    for sample in samples:
        _check_vocabulary(sample)
        _check_subject(sample)
    _check_distinct_wav_paths(samples)
    _check_reference_session(samples)
    _check_session_separation(samples)
    _check_minimum_matrix(samples)
    _check_genuine_coverage(samples)
    _check_impostor_diversity(samples)


def _check_vocabulary(sample: SpeakerSample) -> None:
    if sample.sample_class not in SAMPLE_CLASSES:
        raise ValueError(f"{sample.sample_id}: unknown sample_class {sample.sample_class!r}")
    if sample.condition not in CONDITIONS:
        raise ValueError(f"{sample.sample_id}: unknown condition {sample.condition!r}")
    if sample.phrase_id not in PHRASE_IDS:
        raise ValueError(f"{sample.sample_id}: unknown phrase_id {sample.phrase_id!r}")


def _check_subject(sample: SpeakerSample) -> None:
    if sample.sample_class == "impostor":
        if not IMPOSTOR_ID_PATTERN.match(sample.subject_id):
            raise ValueError(f"{sample.sample_id}: impostor subject_id must match impostor_[a-z]+")
    elif sample.subject_id != OWNER_SUBJECT_ID:
        raise ValueError(
            f"{sample.sample_id}: {sample.sample_class} subject_id must be {OWNER_SUBJECT_ID!r}"
        )


def _check_distinct_wav_paths(samples: Sequence[SpeakerSample]) -> None:
    paths = [str(s.wav_path) for s in samples]
    if len(paths) != len(set(paths)):
        raise ValueError("every sample must reference a distinct WAV file")


def _check_reference_session(samples: Sequence[SpeakerSample]) -> None:
    references = [s for s in samples if s.sample_class == "reference"]
    if not references:
        return
    sessions = {s.session_id for s in references}
    if len(sessions) != 1:
        raise ValueError(
            f"reference samples must share one dedicated session, got {sorted(sessions)}"
        )
    if {s.condition for s in references} != {"quiet-near"}:
        raise ValueError("reference samples must all be captured at quiet-near")


def _check_session_separation(samples: Sequence[SpeakerSample]) -> None:
    reference_sessions = {s.session_id for s in samples if s.sample_class == "reference"}
    probe_sessions = {s.session_id for s in samples if s.sample_class != "reference"}
    leaked = reference_sessions & probe_sessions
    if leaked:
        raise ValueError(f"reference and probe sessions must be distinct; shared: {sorted(leaked)}")


def _check_minimum_matrix(samples: Sequence[SpeakerSample]) -> None:
    for sample_class, minimum in MINIMUM_SAMPLES.items():
        count = sum(1 for s in samples if s.sample_class == sample_class)
        if count < minimum:
            raise ValueError(f"{sample_class} needs at least {minimum} samples, got {count}")


def _check_genuine_coverage(samples: Sequence[SpeakerSample]) -> None:
    genuine = [s for s in samples if s.sample_class == "genuine"]
    if len({s.session_id for s in genuine}) < MIN_GENUINE_SESSIONS:
        raise ValueError(f"genuine samples need at least {MIN_GENUINE_SESSIONS} distinct sessions")
    if {s.condition for s in genuine} != set(CONDITIONS):
        raise ValueError("genuine samples must span all four frozen conditions")


def _check_impostor_diversity(samples: Sequence[SpeakerSample]) -> None:
    subjects = {s.subject_id for s in samples if s.sample_class == "impostor"}
    if len(subjects) < MIN_IMPOSTOR_SUBJECTS:
        raise ValueError(
            f"impostor samples need at least {MIN_IMPOSTOR_SUBJECTS} consenting adults, got {len(subjects)}"
        )


def render_aggregate_report(report: AggregateSpeakerReport) -> str:
    """Render a local aggregate report with no biometric, id or path data."""
    lines = [
        "# Speaker calibration aggregate report (Plan 0047, PC-3A)",
        "",
        f"- Outcome: `{report.outcome}`",
        f"- Model: {report.model_id}",
        f"- Package: {report.package_version}",
        f"- Selected threshold: {_fmt(report.selected_threshold)}",
        f"- Live impostor false accepts: {_fmt(report.live_false_accepts)}",
        f"- Live impostor FAR: {_fmt(report.live_far)}",
        f"- Genuine false rejects: {_fmt(report.genuine_false_rejects)}",
        f"- Genuine FRR: {_fmt(report.genuine_frr)}",
        f"- Replay accepts: {_fmt(report.replay_accepts)}",
        f"- Replay accept rate: {_fmt(report.replay_accept_rate)}",
        f"- Latency p50 ms: {_fmt(report.latency_p50_ms)}",
        f"- Latency p95 ms: {_fmt(report.latency_p95_ms)}",
        "",
        "## Sample counts",
        "",
        *(f"- {cls}: {count}" for cls, count in sorted(report.sample_counts.items())),
        "",
        "## By condition",
        "",
        "| class | condition | total | accepted | rejected | dmin | dmax | dmean |",
        "|---|---|---|---|---|---|---|---|",
        *(_condition_row(report.by_condition[key]) for key in sorted(report.by_condition)),
        "",
        "## Limitations",
        "",
        *(f"- {item}" for item in report.limitations),
    ]
    return "\n".join(lines) + "\n"


def _condition_row(summary: ConditionSummary) -> str:
    return (
        f"| {summary.sample_class} | {summary.condition} | {summary.total} | {summary.accepted} "
        f"| {summary.rejected} | {summary.distance_min:.4f} | {summary.distance_max:.4f} "
        f"| {summary.distance_mean:.4f} |"
    )


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value}"


def condition_key(sample_class: str, condition: str) -> str:
    """Return the deterministic ``by_condition`` dict key for one cell."""
    return f"{sample_class}/{condition}"
