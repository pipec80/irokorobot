"""Tests for the Plan 0030 face-calibration math and capture/corpus CLI."""

from collections.abc import Sequence
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.face_calibration import (
    CorpusRecord,
    ThresholdResult,
    analyze_corpus,
    append_records,
    capture_probe,
    closest_profile_distance,
    cosine_distance,
    load_corpus,
    load_reference_profiles,
    sweep_thresholds,
    zero_far_threshold,
)


def _unit_vector(axis: int) -> np.ndarray:
    """Return a 512-d unit vector along *axis* — a synthetic 'face'."""
    vec = np.zeros(512, dtype=np.float32)
    vec[axis] = 1.0
    return vec


def test_cosine_distance_matches_the_production_formula() -> None:
    """1 - dot(a, b) must equal faces.py's L2² / 2 formula on the same inputs."""
    a = _unit_vector(0)
    near = np.zeros(512, dtype=np.float32)
    near[0], near[1] = 0.8, 0.6

    distance = cosine_distance(a, near)

    l2_squared_over_2 = float(np.linalg.norm(a - near) ** 2) / 2
    assert distance == pytest.approx(l2_squared_over_2, abs=1e-6)
    assert distance == pytest.approx(0.2, abs=1e-6)


def test_cosine_distance_is_zero_for_identical_vectors() -> None:
    """The same embedding compared to itself has zero distance."""
    a = _unit_vector(0)

    assert cosine_distance(a, a) == pytest.approx(0.0, abs=1e-6)


def test_cosine_distance_is_one_for_orthogonal_vectors() -> None:
    """Orthogonal unit vectors (cos similarity 0) are distance 1.0 apart."""
    assert cosine_distance(_unit_vector(0), _unit_vector(1)) == pytest.approx(1.0, abs=1e-6)


def test_closest_profile_distance_is_the_minimum_over_profiles() -> None:
    """Multi-profile matching takes the minimum distance, mirroring k=1 KNN."""
    probe = _unit_vector(0)
    near = np.zeros(512, dtype=np.float32)
    near[0], near[1] = 0.8, 0.6
    far = _unit_vector(1)
    profiles = [far, near, _unit_vector(2)]

    distance = closest_profile_distance(probe, profiles)

    assert distance == pytest.approx(cosine_distance(probe, near), abs=1e-6)


def test_closest_profile_distance_with_a_single_profile() -> None:
    """A one-profile policy still uses the same minimum-over-set logic."""
    probe = _unit_vector(0)

    assert closest_profile_distance(probe, [probe]) == pytest.approx(0.0, abs=1e-6)


def test_sweep_thresholds_counts_false_accepts_and_false_rejects() -> None:
    """A threshold accepts distance <= threshold — mirroring faces.py's `> threshold` reject."""
    genuine = [0.1, 0.2, 0.35]
    impostor = [0.3, 0.5, 0.6]

    results = sweep_thresholds(genuine, impostor, candidates=[0.25, 0.4])

    by_threshold = {r.threshold: r for r in results}
    # threshold 0.25: genuine 0.35 rejected (FR=1); impostor none <= 0.25 (FA=0)
    assert by_threshold[0.25] == ThresholdResult(
        threshold=0.25, false_accepts=0, false_rejects=1, total_genuine=3, total_impostor=3
    )
    # threshold 0.4: all genuine accepted (FR=0); impostor 0.3 <= 0.4 accepted (FA=1)
    assert by_threshold[0.4] == ThresholdResult(
        threshold=0.4, false_accepts=1, false_rejects=0, total_genuine=3, total_impostor=3
    )


def test_sweep_thresholds_handles_empty_impostor_set() -> None:
    """No impostor samples yet must not crash the sweep — FAR is simply zero."""
    results = sweep_thresholds([0.1, 0.2], [], candidates=[0.3])

    assert results == [
        ThresholdResult(
            threshold=0.3, false_accepts=0, false_rejects=0, total_genuine=2, total_impostor=0
        )
    ]


def test_zero_far_threshold_returns_none_when_distances_overlap() -> None:
    """A genuine sample farther than an impostor sample means no threshold separates them."""
    genuine = [0.1, 0.5]  # 0.5 overlaps with the impostor below
    impostor = [0.3, 0.6]

    assert zero_far_threshold(genuine, impostor) is None


def test_zero_far_threshold_returns_the_midpoint_and_margin_when_separable() -> None:
    """A clean separation reports the midpoint threshold and the full gap as margin."""
    genuine = [0.1, 0.2, 0.25]
    impostor = [0.45, 0.5, 0.6]

    result = zero_far_threshold(genuine, impostor)

    assert result is not None
    threshold, margin = result
    assert threshold == pytest.approx(0.35, abs=1e-6)  # midpoint of 0.25 and 0.45
    assert margin == pytest.approx(0.2, abs=1e-6)  # 0.45 - 0.25


def test_zero_far_threshold_treats_equal_boundary_as_overlap() -> None:
    """A genuine and impostor distance tied exactly is not a safe separation."""
    assert zero_far_threshold([0.1, 0.3], [0.3, 0.5]) is None


# --- Task 2: capture/corpus CLI ---


async def test_capture_probe_uses_the_webcam_by_default() -> None:
    """No --image means the webcam boundary is called, not the photo loader."""
    captured_bytes = b"\xff\xd8fake-webcam-jpeg"

    async def fake_extract(image: bytes) -> np.ndarray:
        assert image == captured_bytes
        return _unit_vector(0)

    record = await capture_probe(
        subject="owner",
        condition="light=day",
        image=None,
        device=0,
        load_photo=lambda _path: pytest.fail("must not load a photo when no --image is given"),
        capture_webcam=lambda _device: captured_bytes,
        extract_embedding=fake_extract,
    )

    assert record.subject == "owner"
    assert record.condition == "light=day"
    assert record.source == "webcam"
    assert record.profile_index is None
    assert record.embedding == _unit_vector(0).tolist()


async def test_capture_probe_uses_the_photo_loader_when_image_given() -> None:
    """--image means the photo loader is called, not the webcam."""
    photo_bytes = b"\xff\xd8fake-photo-jpeg"

    async def fake_extract(image: bytes) -> np.ndarray:
        assert image == photo_bytes
        return _unit_vector(1)

    record = await capture_probe(
        subject="impostor:stranger1",
        condition="n/a",
        image="foto.jpg",
        device=0,
        load_photo=lambda path: photo_bytes if path == "foto.jpg" else b"",
        capture_webcam=lambda _device: pytest.fail(
            "must not open the webcam when --image is given"
        ),
        extract_embedding=fake_extract,
    )

    assert record.source == "photo"
    assert record.subject == "impostor:stranger1"


async def test_capture_probe_propagates_zero_or_multi_face_rejection() -> None:
    """A capture with zero or 2+ detected faces must not silently become a sample."""

    async def fake_extract_no_face(_image: bytes) -> np.ndarray:
        raise ValueError("No face detected in the captured frame")

    with pytest.raises(ValueError, match="No face detected"):
        await capture_probe(
            subject="owner",
            condition="light=day",
            image=None,
            device=0,
            load_photo=lambda _p: b"",
            capture_webcam=lambda _d: b"\xff\xd8",
            extract_embedding=fake_extract_no_face,
        )


def test_append_records_and_load_corpus_round_trip(tmp_path: Path) -> None:
    """Records written by append_records must read back identically."""
    corpus_path = tmp_path / "face-corpus.jsonl"
    records = [
        CorpusRecord(embedding=[0.1, 0.2], subject="owner", condition="light=day", source="webcam"),
        CorpusRecord(
            embedding=[0.3, 0.4],
            subject="owner-reference",
            condition="enrolled",
            source="webcam",
            profile_index=0,
        ),
    ]

    append_records(records, corpus_path=corpus_path)
    loaded = load_corpus(corpus_path)

    assert loaded == records


def test_append_records_never_writes_raw_image_bytes(tmp_path: Path) -> None:
    """The persisted corpus line must contain only the documented fields."""
    corpus_path = tmp_path / "face-corpus.jsonl"
    record = CorpusRecord(embedding=[0.1], subject="owner", condition="c", source="webcam")

    append_records([record], corpus_path=corpus_path)

    line = corpus_path.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert set(payload.keys()) == {"embedding", "subject", "condition", "source", "profile_index"}


def test_load_corpus_returns_empty_list_when_file_is_absent(tmp_path: Path) -> None:
    """No prior capture session must not crash analysis — just an empty corpus."""
    assert load_corpus(tmp_path / "does-not-exist.jsonl") == []


class _FakeCursor:
    def __init__(self, rows: Sequence[tuple[object, ...]]) -> None:
        self._rows = rows

    async def fetchone(self) -> tuple[object, ...] | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> Sequence[tuple[object, ...]]:
        return self._rows

    async def close(self) -> None:
        return None


class _FakeConnection:
    """Raises on any non-SELECT statement — proves read-only access."""

    def __init__(self, owner_row: tuple[int], profile_rows: Sequence[tuple[bytes]]) -> None:
        self._owner_row = owner_row
        self._profile_rows = profile_rows
        self.executed_statements: list[str] = []

    async def execute(self, sql: str, _params: tuple[object, ...] = ()) -> _FakeCursor:
        self.executed_statements.append(sql)
        if not sql.strip().upper().startswith("SELECT"):
            raise AssertionError(f"non-SELECT statement issued: {sql}")
        if "household_role_assignments" in sql:
            return _FakeCursor([self._owner_row])
        return _FakeCursor(self._profile_rows)


async def test_load_reference_profiles_is_read_only_and_tags_profile_index() -> None:
    """Every enrolled owner embedding is read via SELECT only, tagged by index."""
    embeddings = [_unit_vector(0), _unit_vector(1), _unit_vector(2)]
    conn = _FakeConnection(
        owner_row=(42,),
        profile_rows=[(emb.astype(np.float32).tobytes(),) for emb in embeddings],
    )

    records = await load_reference_profiles(conn)

    assert all(stmt.strip().upper().startswith("SELECT") for stmt in conn.executed_statements)
    assert [r.profile_index for r in records] == [0, 1, 2]
    assert all(r.subject == "owner-reference" for r in records)
    assert records[0].embedding == pytest.approx(embeddings[0].tolist())


async def test_load_reference_profiles_raises_when_no_active_owner() -> None:
    """No enrolled owner means calibration cannot proceed — fail loudly, not silently."""

    class _NoOwnerConnection(_FakeConnection):
        async def execute(self, sql: str, _params: tuple[object, ...] = ()) -> _FakeCursor:
            self.executed_statements.append(sql)
            return _FakeCursor([])

    with pytest.raises(ValueError, match="active owner"):
        await load_reference_profiles(_NoOwnerConnection(owner_row=(0,), profile_rows=[]))


def test_analyze_corpus_uses_only_the_frontal_reference_with_profile_count_one() -> None:
    """--profiles 1 must use only profile_index 0, ignoring the other enrolled profiles."""
    owner_probe = _unit_vector(0)
    records = [
        CorpusRecord(
            embedding=_unit_vector(0).tolist(),
            subject="owner-reference",
            condition="enrolled",
            source="webcam",
            profile_index=0,
        ),
        CorpusRecord(
            embedding=_unit_vector(5).tolist(),
            subject="owner-reference",
            condition="enrolled",
            source="webcam",
            profile_index=1,
        ),
        CorpusRecord(
            embedding=owner_probe.tolist(), subject="owner", condition="c", source="webcam"
        ),
    ]

    report = analyze_corpus(records, profile_count=1)

    assert report.genuine_distances == pytest.approx([0.0], abs=1e-6)


def test_analyze_corpus_uses_all_references_with_profile_count_three() -> None:
    """--profiles 3 takes the minimum distance across every enrolled reference."""
    records = [
        CorpusRecord(
            embedding=_unit_vector(5).tolist(),
            subject="owner-reference",
            condition="enrolled",
            source="webcam",
            profile_index=0,
        ),
        CorpusRecord(
            embedding=_unit_vector(0).tolist(),
            subject="owner-reference",
            condition="enrolled",
            source="webcam",
            profile_index=1,
        ),
        CorpusRecord(
            embedding=_unit_vector(0).tolist(), subject="owner", condition="c", source="webcam"
        ),
        CorpusRecord(
            embedding=_unit_vector(5).tolist(),
            subject="impostor:stranger1",
            condition="c",
            source="photo",
        ),
    ]

    report = analyze_corpus(records, profile_count=3)

    assert report.genuine_distances == pytest.approx([0.0], abs=1e-6)
    assert report.impostor_distances == pytest.approx([0.0], abs=1e-6)
