"""face_calibration.py — Plan 0030: measure the real-camera face threshold.

Two layers: pure FAR/FRR math (this module, no I/O) and a capture/corpus CLI
(added in Task 2) that reads Pipec's already-enrolled reference profiles
read-only from `omnibot.db` and appends probe embeddings to an untracked
corpus under `project-history/calibration/`. No frame is ever persisted; no
impostor is ever enrolled.

The distance formula below is deliberately identical to
`server.vision.faces.match_face`'s `L2² / 2` on L2-normalized embeddings,
which is algebraically `1 - dot(a, b)` — this module reproduces the exact
number sqlite-vec's KNN would produce in production, not an approximation.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
from robot.camera_capture import capture_frame
from server.settings import settings
from server.vision.faces import detect_faces

from server import db


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Return the cosine distance between two L2-normalized embeddings.

    Args:
        a: A 512-d L2-normalized face embedding.
        b: A 512-d L2-normalized face embedding.

    Returns:
        `1 - dot(a, b)`, identical to `server.vision.faces.match_face`'s
        `L2² / 2` formula on L2-normalized inputs. `0.0` for identical
        vectors, `1.0` for orthogonal ones.
    """
    return float(1.0 - np.dot(a, b))


def closest_profile_distance(probe: np.ndarray, profiles: list[np.ndarray]) -> float:
    """Return the minimum distance from *probe* to any enrolled profile.

    Mirrors `k = 1` in the real sqlite-vec KNN query — a multi-profile match
    is the closest of the enrolled profiles, never an average.

    Args:
        probe: The embedding being evaluated.
        profiles: One or more enrolled reference embeddings for one person.

    Returns:
        The smallest `cosine_distance` between *probe* and any profile.

    Raises:
        ValueError: If `profiles` is empty.
    """
    if not profiles:
        raise ValueError("profiles must contain at least one enrolled embedding")
    return min(cosine_distance(probe, profile) for profile in profiles)


@dataclass(frozen=True)
class ThresholdResult:
    """False-accept/false-reject counts for one candidate threshold.

    Attributes:
        threshold: The candidate cosine-distance threshold evaluated.
        false_accepts: Impostor samples with distance <= threshold.
        false_rejects: Genuine samples with distance > threshold.
        total_genuine: Total genuine samples evaluated.
        total_impostor: Total impostor samples evaluated.
    """

    threshold: float
    false_accepts: int
    false_rejects: int
    total_genuine: int
    total_impostor: int


def sweep_thresholds(
    genuine_distances: list[float],
    impostor_distances: list[float],
    candidates: list[float],
) -> list[ThresholdResult]:
    """Count false accepts/rejects for each candidate threshold.

    A sample is accepted when its distance is `<= threshold` — the same
    accept/reject boundary `server.vision.faces.match_face` applies (it
    rejects only when `cosine_distance > threshold`).

    Args:
        genuine_distances: Measured distances for Pipec's own probe samples.
        impostor_distances: Measured distances for impostor probe samples.
        candidates: Threshold values to evaluate.

    Returns:
        One `ThresholdResult` per candidate, in the given order.
    """
    return [
        ThresholdResult(
            threshold=candidate,
            false_accepts=sum(1 for d in impostor_distances if d <= candidate),
            false_rejects=sum(1 for d in genuine_distances if d > candidate),
            total_genuine=len(genuine_distances),
            total_impostor=len(impostor_distances),
        )
        for candidate in candidates
    ]


def zero_far_threshold(
    genuine_distances: list[float], impostor_distances: list[float]
) -> tuple[float, float] | None:
    """Return the midpoint threshold and margin at zero false accepts.

    A threshold that admits every genuine sample and rejects every impostor
    sample exists only when the largest genuine distance is strictly smaller
    than the smallest impostor distance. When it exists, this returns the
    midpoint of that gap — not the boundary itself — so the chosen threshold
    keeps a symmetric safety margin against future measurement noise on
    either side, rather than sitting exactly against one edge.

    Args:
        genuine_distances: Measured distances for Pipec's own probe samples.
        impostor_distances: Measured distances for impostor probe samples.

    Returns:
        `(threshold, margin)` where `margin` is the full gap between the
        largest genuine and smallest impostor distance, or `None` when no
        such threshold exists (the two distributions overlap or touch).
    """
    if not genuine_distances or not impostor_distances:
        return None
    largest_genuine = max(genuine_distances)
    smallest_impostor = min(impostor_distances)
    if largest_genuine >= smallest_impostor:
        return None
    margin = smallest_impostor - largest_genuine
    threshold = (largest_genuine + smallest_impostor) / 2
    return threshold, margin


# --- Task 2: capture/corpus CLI ---

_CORPUS_PATH = Path("project-history/calibration/face-corpus.jsonl")

type PhotoLoader = Callable[[str], bytes]
type WebcamCapture = Callable[[int], bytes]
type EmbeddingExtractor = Callable[[bytes], Awaitable[np.ndarray]]


@dataclass(frozen=True)
class CorpusRecord:
    """One untracked calibration sample — an embedding, never a frame.

    Attributes:
        embedding: 512-d L2-normalized face embedding, as a plain list so it
            serializes to JSON without a numpy dependency at read time.
        subject: `"owner"` for a genuine probe, `"impostor:<label>"` for an
            impostor probe, or `"owner-reference"` for an enrolled reference
            profile pulled from `omnibot.db`.
        condition: Free-text capture condition, e.g. `"light=day,distance=near"`.
        source: Where the probe frame came from.
        profile_index: Position among the owner's enrolled reference
            profiles (`0` = first enrolled). `None` for probe samples.
    """

    embedding: list[float]
    subject: str
    condition: str
    source: Literal["webcam", "photo"]
    profile_index: int | None = field(default=None)


def _resolve_photo(path: str) -> Path:
    """Resolve a photo argument against the drop-folder (`settings.images_dir`).

    Args:
        path: File name inside `IMAGES_DIR`, or a full path.

    Returns:
        The existing photo path.

    Raises:
        FileNotFoundError: If the file exists in neither location.
    """
    direct = Path(path)
    if direct.exists():
        return direct
    dropped = settings.images_dir / path
    if dropped.exists():
        return dropped
    raise FileNotFoundError(f"Photo not found: {path} (looked in {settings.images_dir} too)")


def _load_photo(path: str) -> bytes:
    """Read raw bytes from a photo resolved against the drop-folder."""
    return _resolve_photo(path).read_bytes()


async def _extract_single_embedding(image: bytes) -> np.ndarray:
    """Detect exactly one face in *image* and return its embedding.

    Args:
        image: Frame bytes per the image contract — decoded in memory and
            discarded by `detect_faces`; never persisted here or by the caller.

    Returns:
        The detected face's 512-d embedding.

    Raises:
        ValueError: If zero or 2+ faces are detected — a calibration sample
            must isolate exactly one person.
    """
    faces = await detect_faces(image)
    if len(faces) == 0:
        raise ValueError("No face detected in the captured frame")
    if len(faces) > 1:
        raise ValueError(f"Found {len(faces)} faces — capture needs exactly one person in frame")
    return faces[0].embedding


async def capture_probe(
    *,
    subject: str,
    condition: str,
    image: str | None,
    device: int,
    load_photo: PhotoLoader = _load_photo,
    capture_webcam: WebcamCapture = capture_frame,
    extract_embedding: EmbeddingExtractor = _extract_single_embedding,
) -> CorpusRecord:
    """Capture one probe frame, extract its embedding, and discard the frame.

    Args:
        subject: `"owner"` or `"impostor:<label>"`.
        condition: Free-text capture condition for this sample.
        image: A photo file name/path, or `None` to use the webcam.
        device: OpenCV camera index, used only when `image` is `None`.
        load_photo: Boundary that reads photo bytes from disk.
        capture_webcam: Boundary that captures one webcam frame.
        extract_embedding: Boundary that detects and embeds exactly one face.

    Returns:
        A `CorpusRecord` holding only the embedding — the raw frame bytes
        are never attached to it and go out of scope once this returns.

    Raises:
        ValueError: If zero or 2+ faces were detected in the frame.
    """
    if image is not None:
        raw = load_photo(image)
        source: Literal["webcam", "photo"] = "photo"
    else:
        raw = capture_webcam(device)
        source = "webcam"
    embedding = await extract_embedding(raw)
    return CorpusRecord(
        embedding=embedding.tolist(), subject=subject, condition=condition, source=source
    )


def append_records(records: list[CorpusRecord], *, corpus_path: Path = _CORPUS_PATH) -> None:
    """Append records to the untracked calibration corpus, one JSON line each.

    Args:
        records: Records to append.
        corpus_path: Corpus file path — defaults to the untracked
            `project-history/calibration/` location.
    """
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    with corpus_path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record)) + "\n")


def load_corpus(corpus_path: Path = _CORPUS_PATH) -> list[CorpusRecord]:
    """Load every record from the untracked calibration corpus.

    Args:
        corpus_path: Corpus file path.

    Returns:
        Every stored `CorpusRecord`, in append order. An empty list when no
        capture session has run yet.
    """
    if not corpus_path.exists():
        return []
    records = []
    for line in corpus_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(CorpusRecord(**json.loads(line)))
    return records


async def _resolve_owner_entity_id(conn: Any) -> int:  # noqa: ANN401 -- duck-typed: real conn or test fake
    """Read-only: the currently active owner's entity id.

    Args:
        conn: Database connection boundary.

    Returns:
        The owner's `entities.id`.

    Raises:
        ValueError: If no active owner role assignment exists.
    """
    cursor = await conn.execute(
        "SELECT person_entity_id FROM household_role_assignments "
        "WHERE role = 'owner' AND revoked_at IS NULL "
        "ORDER BY granted_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        raise ValueError("No active owner found — run `just onboard` first")
    return int(row[0])


async def _read_reference_embeddings(conn: Any, entity_id: int) -> list[np.ndarray]:  # noqa: ANN401 -- duck-typed: real conn or test fake
    """Read-only: every enrolled face embedding for *entity_id*, oldest first.

    Args:
        conn: Database connection boundary.
        entity_id: The owner's entity id.

    Returns:
        Enrolled embeddings in enrollment order (oldest profile first).
    """
    cursor = await conn.execute(
        "SELECT v.embedding FROM vec_faces AS v "
        "JOIN face_profiles AS p ON p.id = v.rowid "
        "WHERE p.entity_id = ? ORDER BY p.id ASC",
        (entity_id,),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [np.frombuffer(row[0], dtype=np.float32) for row in rows]


async def load_reference_profiles(conn: Any) -> list[CorpusRecord]:  # noqa: ANN401 -- duck-typed: real conn or test fake
    """Read-only: pull every enrolled owner embedding into corpus records.

    Issues only `SELECT` statements — it never calls `enroll_face()` and
    never inserts into `face_profiles` or `vec_faces`. Enrolling reference
    profiles is done through the existing, unmodified `just face-auth-demo
    --enroll` flow before this is called.

    Args:
        conn: Database connection boundary (real `db.get_conn()` in
            production; a fake in tests).

    Returns:
        One `CorpusRecord` per enrolled profile, tagged `owner-reference`
        with its `profile_index` in enrollment order.
    """
    entity_id = await _resolve_owner_entity_id(conn)
    embeddings = await _read_reference_embeddings(conn, entity_id)
    return [
        CorpusRecord(
            embedding=embedding.tolist(),
            subject="owner-reference",
            condition="enrolled",
            source="webcam",
            profile_index=index,
        )
        for index, embedding in enumerate(embeddings)
    ]


@dataclass(frozen=True)
class AnalysisReport:
    """Genuine and impostor distances measured against the chosen reference set.

    Attributes:
        genuine_distances: One distance per `"owner"` probe sample.
        impostor_distances: One distance per `"impostor:*"` probe sample.
    """

    genuine_distances: list[float]
    impostor_distances: list[float]


def analyze_corpus(records: list[CorpusRecord], *, profile_count: int) -> AnalysisReport:
    """Compute genuine/impostor distances against a chosen reference-profile policy.

    Args:
        records: The full loaded corpus.
        profile_count: `1` to use only the first enrolled reference profile,
            or the number of profiles to use starting from the oldest — the
            two policies Task 5 compares.

    Returns:
        Distances ready for `sweep_thresholds`/`zero_far_threshold`.
    """
    references = sorted(
        (r for r in records if r.subject == "owner-reference"),
        key=lambda r: r.profile_index if r.profile_index is not None else 0,
    )[:profile_count]
    reference_embeddings = [np.array(r.embedding, dtype=np.float32) for r in references]

    def _distance(record: CorpusRecord) -> float:
        return closest_profile_distance(
            np.array(record.embedding, dtype=np.float32), reference_embeddings
        )

    genuine_distances = [_distance(r) for r in records if r.subject == "owner"]
    impostor_distances = [_distance(r) for r in records if r.subject.startswith("impostor:")]
    return AnalysisReport(
        genuine_distances=genuine_distances, impostor_distances=impostor_distances
    )


async def _run_capture(args: argparse.Namespace) -> None:
    """Capture one probe frame and append it to the corpus.

    Warns before opening the webcam, mirroring `scripts/onboard.py` and
    `scripts/face_auth_demo.py` (PR #80) — capturing instantly with no
    countdown produces blinking/off-camera frames across a capture matrix
    this size. Photo-file captures (`--image`) skip the warning; no camera
    opens for those.
    """
    if args.image is None:
        print("Mira a la camara. Capturando en 3 segundos...")  # noqa: T201
        await asyncio.sleep(3)
    record = await capture_probe(
        subject=args.subject, condition=args.condition, image=args.image, device=args.device
    )
    append_records([record])
    print(f"Capturado: subject={record.subject} condition={record.condition}")  # noqa: T201


async def _run_load_reference_profiles() -> None:
    """Pull the owner's enrolled reference embeddings into the corpus."""
    await db.open_db()
    try:
        await db.run_migrations()
        records = await load_reference_profiles(db.get_conn())
    finally:
        await db.close_db()
    append_records(records)
    print(f"{len(records)} perfil(es) de referencia cargados al corpus.")  # noqa: T201


def _run_analyze(profile_count: int) -> None:
    """Sweep candidate thresholds and print the FAR/FRR table plus verdict."""
    records = load_corpus()
    report = analyze_corpus(records, profile_count=profile_count)
    print(  # noqa: T201
        f"Muestras: {len(report.genuine_distances)} genuinas, "
        f"{len(report.impostor_distances)} impostoras (profiles={profile_count})"
    )
    if report.genuine_distances:
        candidates = sorted(
            {round(d, 3) for d in report.genuine_distances + report.impostor_distances}
        )
        for result in sweep_thresholds(
            report.genuine_distances, report.impostor_distances, candidates
        ):
            print(  # noqa: T201
                f"  umbral={result.threshold:.3f} FA={result.false_accepts}/{result.total_impostor} "
                f"FR={result.false_rejects}/{result.total_genuine}"
            )
    verdict = zero_far_threshold(report.genuine_distances, report.impostor_distances)
    if verdict is None:
        print("VEREDICTO: FAIL — genuinas e impostoras se solapan, ningun umbral separa ambas.")  # noqa: T201
    else:
        threshold, margin = verdict
        print(f"VEREDICTO: umbral={threshold:.4f} margen={margin:.4f}")  # noqa: T201


def main() -> None:
    """CLI entrypoint for the Plan 0030 calibration harness."""
    parser = argparse.ArgumentParser(description="Plan 0030: real-camera face calibration")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--capture", action="store_true", help="Capture one probe sample")
    action.add_argument(
        "--load-reference-profiles",
        action="store_true",
        help="Pull the owner's enrolled embeddings from omnibot.db (read-only)",
    )
    action.add_argument("--analyze", action="store_true", help="Sweep thresholds over the corpus")
    parser.add_argument("--subject", default=None, help="owner, or impostor:<label>")
    parser.add_argument("--condition", default="", help="e.g. light=day,distance=near,glasses=off")
    parser.add_argument("--image", default=None, help="Photo file instead of the webcam")
    parser.add_argument("--live", action="store_true", help="Explicit webcam capture (default)")
    parser.add_argument("--device", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument(
        "--profiles",
        type=int,
        choices=(1, 3),
        default=1,
        help="Reference-profile policy to analyze",
    )
    args = parser.parse_args()

    if args.capture:
        if not args.subject:
            parser.error("--capture requires --subject")
        asyncio.run(_run_capture(args))
    elif args.load_reference_profiles:
        asyncio.run(_run_load_reference_profiles())
    else:
        _run_analyze(args.profiles)


if __name__ == "__main__":
    main()
