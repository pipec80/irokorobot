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
import os
from pathlib import Path
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
    MIN_PHRASE_REPETITIONS,
    MINIMUM_SAMPLES,
    OWNER_SUBJECT_ID,
    PHRASE_IDS,
    REPLAY_CONDITIONS,
    SAMPLE_CLASSES,
    SCHEMA_VERSION,
    AggregateSpeakerReport,
    ConditionSummary,
    SpeakerManifest,
    SpeakerSample,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence

# Generous ceiling: a fixed neutral phrase read and the 3-second latency WAV are
# both far below this. It bounds only accidental oversized captures, not format.
_MAX_WAV_SECONDS = 30.0
# A cell smaller than this reports no distance range: the range would expose a
# single sample's raw score (Plan 0047 privacy rule - counts and ranges only).
_MIN_CELL_FOR_RANGE = 3

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
    root = Path(corpus_root).resolve()
    candidate = Path(wav_path)
    raw = candidate if candidate.is_absolute() else root / candidate
    resolved = raw.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"WAV path {wav_path!r} escapes the corpus root {root}")
    if raw.is_symlink():
        raise ValueError(f"WAV path {wav_path!r} is a symlink; corpus files must be real")
    return resolved


def load_manifest(path: Path, corpus_root: Path, *, verify_files: bool = True) -> SpeakerManifest:
    """Load a strict manifest and prove every WAV stays under *corpus_root*.

    Args:
        path: The manifest file.
        corpus_root: The calibration corpus root directory.
        verify_files: ``True`` (default) also requires every WAV to exist and to
            match its recorded SHA-256. ``discard`` passes ``False`` so a
            participant's withdrawal is honoured even when a file is already gone
            or damaged.

    Raises:
        ValueError: On a bad schema version, unknown fields, duplicate sample
            ids, a path escape, a non-``.wav`` path and - when *verify_files* -
            a missing WAV or a SHA-256 mismatch.
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
    samples = tuple(
        _parse_row(row, corpus_root, index, verify_files=verify_files)
        for index, row in enumerate(rows, start=1)
    )
    ids = [s.sample_id for s in samples]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"manifest has duplicate sample_id values: {duplicates}")
    return SpeakerManifest(schema_version=SCHEMA_VERSION, samples=samples)


def _parse_row(row: object, corpus_root: Path, index: int, *, verify_files: bool) -> SpeakerSample:
    if not isinstance(row, dict):
        raise ValueError(f"manifest row {index} must be a JSON object")
    if set(row) != _SAMPLE_FIELDS:
        unknown = sorted(set(row) - _SAMPLE_FIELDS)
        missing = sorted(_SAMPLE_FIELDS - set(row))
        raise ValueError(f"manifest row {index} off contract: unknown={unknown} missing={missing}")
    resolved = resolve_corpus_path(corpus_root, str(row["wav_path"]))
    if resolved.suffix != ".wav":
        raise ValueError(f"manifest row {index} does not name a .wav file")
    if verify_files:
        _verify_sha256(resolved, str(row["sha256"]), index)
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


def _verify_sha256(path: Path, expected: str, index: int) -> None:
    if not path.is_file():
        raise ValueError(f"manifest row {index} names a WAV that is missing from the corpus")
    if sha256_of_file(path) != expected:
        raise ValueError(f"manifest row {index}: the WAV does not match its recorded sha256")


def append_sample_atomic(manifest_path: Path, corpus_root: Path, sample: SpeakerSample) -> None:
    """Append one validated sample, never exposing a partial manifest.

    Writes the whole manifest to a sibling ``.tmp`` file and swaps it into
    place with a single atomic rename.
    """
    rows: list[dict[str, str]] = list(_existing_rows(manifest_path))
    rows.append(_row_from_sample(sample, corpus_root))
    _write_manifest_atomic(manifest_path, rows)


def remove_samples_atomic(manifest_path: Path, sample_ids: Collection[str]) -> None:
    """Drop the rows named in *sample_ids*, never exposing a partial manifest.

    Other rows are kept exactly as stored. Ids that are not present are ignored,
    so an interrupted removal can simply be run again.
    """
    rows = [row for row in _existing_rows(manifest_path) if row["sample_id"] not in sample_ids]
    _write_manifest_atomic(manifest_path, rows)


def _write_manifest_atomic(manifest_path: Path, rows: list[dict[str, str]]) -> None:
    payload = {"schema_version": SCHEMA_VERSION, "samples": rows}
    write_text_atomic(manifest_path, json.dumps(payload, indent=2))


def write_text_atomic(target: Path, text: str) -> None:
    """Write UTF-8 text so a reader never sees a half-written file.

    Args:
        target: Final path; a sibling ``<name>.tmp`` holds the bytes first.
        text: Full file contents.

    Raises:
        OSError: If the write or the final replace fails; the temporary file is
            removed.
    """
    tmp = target.with_name(target.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    swap_into_place(tmp, target)


def write_new_file_atomic(target: Path, data: bytes) -> None:
    """Create *target* with *data*, never exposing a partial file or overwriting.

    Args:
        target: Final path; it must not exist yet.
        data: Full file contents (a WAV - 16 000 Hz, mono, signed int16).

    Raises:
        FileExistsError: If *target* already exists.
        OSError: If the write fails; the temporary file is removed.
    """
    if target.exists():
        raise FileExistsError(f"refusing to overwrite an existing corpus file: {target.name}")
    tmp = target.with_name(target.name + ".tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    swap_into_place(tmp, target)


def swap_into_place(tmp: Path, target: Path) -> None:
    """Atomically replace ``target`` with the already-written ``tmp``.

    Raises:
        OSError: If the replace fails; ``tmp`` is removed before re-raising.
    """
    try:
        tmp.replace(target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def select_samples(
    manifest: SpeakerManifest, *, subject_id: str | None = None, sample_id: str | None = None
) -> tuple[SpeakerSample, ...]:
    """Return one participant's samples, or the one sample with an exact id.

    Raises:
        ValueError: Unless exactly one of *subject_id* and *sample_id* is given.
    """
    if (subject_id is None) == (sample_id is None):
        raise ValueError("select by exactly one of subject_id or sample_id")
    if subject_id is not None:
        return tuple(s for s in manifest.samples if s.subject_id == subject_id)
    return tuple(s for s in manifest.samples if s.sample_id == sample_id)


def _existing_rows(manifest_path: Path) -> Iterable[dict[str, str]]:
    if not manifest_path.exists():
        return []
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("samples"), list):
        raise ValueError("existing manifest is malformed")
    if not all(isinstance(row, dict) and "sample_id" in row for row in raw["samples"]):
        raise ValueError("existing manifest has a row that is not a sample object")
    return list(raw["samples"])


def _row_from_sample(sample: SpeakerSample, corpus_root: Path) -> dict[str, str]:
    root = Path(corpus_root).resolve()
    wav = Path(sample.wav_path).resolve()
    rel = wav.relative_to(root) if wav.is_relative_to(root) else Path(sample.wav_path)
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
    _check_distinct_audio(samples)
    _check_reference_session(samples)
    _check_session_separation(samples)
    _check_minimum_matrix(samples)
    _check_genuine_coverage(samples)
    _check_impostor_diversity(samples)
    _check_phrase_repetitions(samples)
    _check_replay_conditions(samples)


def find_orphan_wavs(manifest: SpeakerManifest, corpus_root: Path) -> list[Path]:
    """List ``*.wav`` files under *corpus_root* that no manifest row references.

    A crash between writing a WAV and appending its row, or a withdrawn
    participant's leftover file, would otherwise sit in the private corpus unseen.

    Args:
        manifest: The loaded manifest.
        corpus_root: The calibration corpus root directory.

    Returns:
        The unreferenced WAV paths, sorted; callers report a count, never names.
    """
    root = Path(corpus_root).resolve()
    known = {Path(s.wav_path).resolve() for s in manifest.samples}
    return sorted(p for p in root.rglob("*.wav") if p.resolve() not in known)


def _check_vocabulary(sample: SpeakerSample) -> None:
    if sample.sample_class not in SAMPLE_CLASSES:
        raise ValueError(f"{sample.sample_id}: unknown sample_class {sample.sample_class!r}")
    if sample.condition not in CONDITIONS:
        raise ValueError(f"{sample.sample_id}: unknown condition {sample.condition!r}")
    if sample.phrase_id not in PHRASE_IDS:
        raise ValueError(f"{sample.sample_id}: unknown phrase_id {sample.phrase_id!r}")


def subject_id_problem(sample_class: str, subject_id: str) -> str | None:
    """Explain why *subject_id* is invalid for *sample_class*, or ``None`` if valid.

    The one home of the pseudonym rule, shared by manifest validation and the
    capture CLI so a change is made once.

    Args:
        sample_class: One of the frozen sample classes.
        subject_id: The owner id or an ``impostor_<letters>`` pseudonym.

    Returns:
        A short reason without a sample id, or ``None`` when the id is allowed.
    """
    if sample_class == "impostor":
        if not IMPOSTOR_ID_PATTERN.match(subject_id):
            return "impostor subject_id must match impostor_[a-z]+"
    elif subject_id != OWNER_SUBJECT_ID:
        return f"{sample_class} subject_id must be {OWNER_SUBJECT_ID!r}"
    return None


def _check_subject(sample: SpeakerSample) -> None:
    problem = subject_id_problem(sample.sample_class, sample.subject_id)
    if problem is not None:
        raise ValueError(f"{sample.sample_id}: {problem}")


def _check_distinct_wav_paths(samples: Sequence[SpeakerSample]) -> None:
    paths = [str(s.wav_path) for s in samples]
    if len(paths) != len(set(paths)):
        raise ValueError("every sample must reference a distinct WAV file")


def _check_distinct_audio(samples: Sequence[SpeakerSample]) -> None:
    digests = [s.sha256 for s in samples]
    if len(digests) != len(set(digests)):
        raise ValueError("two samples carry byte-identical audio; a copy is not a new sample")


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
    genuine_sessions = {s.session_id for s in samples if s.sample_class == "genuine"}
    impostor_sessions = {s.session_id for s in samples if s.sample_class == "impostor"}
    if genuine_sessions & impostor_sessions:
        raise ValueError("owner genuine sessions and impostor sessions must be distinct")


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


def _check_phrase_repetitions(samples: Sequence[SpeakerSample]) -> None:
    """Require each frozen phrase twice from the reference and from every impostor."""
    groups: dict[tuple[str, str], list[str]] = {}
    for s in samples:
        if s.sample_class == "reference":
            groups.setdefault(("reference", ""), []).append(s.phrase_id)
        elif s.sample_class == "impostor":
            groups.setdefault(("impostor", s.subject_id), []).append(s.phrase_id)
    for (sample_class, _), phrases in sorted(groups.items()):
        for phrase in PHRASE_IDS:
            if phrases.count(phrase) < MIN_PHRASE_REPETITIONS:
                raise ValueError(
                    f"every {sample_class} participant needs each frozen phrase at least "
                    f"{MIN_PHRASE_REPETITIONS} times; {phrase} is short"
                )
    if {s.phrase_id for s in samples if s.sample_class == "genuine"} != set(PHRASE_IDS):
        raise ValueError("genuine samples must cover all three frozen phrases")


def _check_replay_conditions(samples: Sequence[SpeakerSample]) -> None:
    bad = {s.condition for s in samples if s.sample_class == "replay"} - set(REPLAY_CONDITIONS)
    if bad:
        raise ValueError(f"replay conditions must be one of {REPLAY_CONDITIONS}, got {sorted(bad)}")


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
    head = (
        f"| {summary.sample_class} | {summary.condition} | {summary.total} | {summary.accepted} "
        f"| {summary.rejected} |"
    )
    if summary.total < _MIN_CELL_FOR_RANGE:
        # With one or two samples a min/max/mean IS a raw per-sample distance.
        return f"{head} n/a | n/a | n/a |"
    return (
        f"{head} {summary.distance_min:.4f} | {summary.distance_max:.4f} "
        f"| {summary.distance_mean:.4f} |"
    )


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value}"


def condition_key(sample_class: str, condition: str) -> str:
    """Return the deterministic ``by_condition`` dict key for one cell."""
    return f"{sample_class}/{condition}"
