"""Models and manifest of the private speech-to-text corpus (Plan 0069, D-2 and D-5).

Every WAV, manifest and per-clip result of the study lives under ``STT_CORPUS_ROOT``,
inside ``project-history/`` (ignored by git). The reading script is tracked and
invented (``tests/evals/stt_reading_script.yaml``). Audio contract of every WAV in the
corpus: WAV, 16 000 Hz, mono, int16.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Final

import yaml

from scripts.speaker_calibration_corpus import resolve_corpus_path, swap_into_place

STT_CORPUS_ROOT: Final = Path("project-history/calibration/stt")
SCRIPT_PATH: Final = Path("tests/evals/stt_reading_script.yaml")
MANIFEST_NAME: Final = "manifest.jsonl"
LAYERS: Final = frozenset("ABCDEFGH")
_EXPECT_KEYS: Final = frozenset({"need", "taste", "answer"})
_MIN_WINDOW_S: Final = 4.0


@dataclass(frozen=True)
class ScriptItem:
    """One sentence of the reading script (Appendix A of Plan 0069)."""

    id: str
    text: str
    layer: str
    kind: str
    reps: int
    window_s: float
    also: tuple[str, ...] = ()
    pair: str | None = None
    target: str | None = None
    competitor: str | None = None
    relaxed: int = 0
    block: bool = False
    chat: bool = False
    expect: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Clip:
    """One clip the robot's segmentation cut from a take (WAV 16 kHz, mono, int16)."""

    path: str
    sha256: str
    reference: str | None = None
    continued: bool = False
    inaudible: bool = False


@dataclass(frozen=True)
class Take:
    """One continuous raw take and the clips derived from it (D-2, D-3, D-4)."""

    take_id: str
    session: str
    condition: str
    style: str
    mode: str
    item_id: str | None
    raw_path: str
    raw_sha256: str
    clips: tuple[Clip, ...]
    reference: str | None
    deviated: bool = False
    block: bool = False  # a condition-block take (D-6), never one of the main reps (D-5)


def _item(raw: dict[str, object]) -> ScriptItem:
    values = dict(raw)
    values["also"] = tuple(values.get("also") or ())  # type: ignore[arg-type]  # YAML list
    return ScriptItem(**values)  # type: ignore[arg-type]  # validated in load_script


def load_script(path: Path = SCRIPT_PATH) -> tuple[ScriptItem, ...]:
    """Load and validate the reading script.

    Args:
        path: The YAML script.

    Returns:
        Its items, in file order.

    Raises:
        ValueError: On a duplicate id, an unknown layer, a pair without exactly two
            members, a D item without target and competitor, a window under 4 s, a
            non-positive repetition count or an unknown expectation key.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = tuple(_item(raw) for raw in document["items"])
    ids = [item.id for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate item id in the reading script")
    pairs: dict[str, int] = {}
    for item in items:
        if item.layer not in LAYERS:
            raise ValueError(f"{item.id}: unknown layer {item.layer!r}")
        if item.layer == "D" and not (item.target and item.competitor):
            raise ValueError(f"{item.id}: a D item needs a target and a competitor")
        if item.window_s < _MIN_WINDOW_S or item.reps < 1 or not 0 <= item.relaxed <= item.reps:
            raise ValueError(f"{item.id}: window, reps or relaxed out of range")
        if not set(item.expect) <= _EXPECT_KEYS:
            raise ValueError(f"{item.id}: unknown expectation key")
        if item.pair:
            pairs[item.pair] = pairs.get(item.pair, 0) + 1
    if any(count != 2 for count in pairs.values()):  # noqa: PLR2004 -- a pair has two members
        raise ValueError("every pair needs exactly two members")
    return items


def _check_inside(root: Path, take: Take) -> None:
    for relative in (take.raw_path, *(clip.path for clip in take.clips)):
        resolve_corpus_path(root, relative)


def _take_from_json(raw: dict[str, object]) -> Take:
    values = dict(raw)
    values["clips"] = tuple(Clip(**clip) for clip in values["clips"])  # type: ignore[union-attr, arg-type]  # JSON list of dicts
    return Take(**values)  # type: ignore[arg-type]  # manifest written by append_take


def append_take(manifest: Path, root: Path, take: Take) -> None:
    """Append one take to the manifest, after proving every path stays inside *root*.

    Args:
        manifest: The JSONL manifest.
        root: The corpus root.
        take: The take to record.

    Raises:
        ValueError: If a WAV path escapes the root.
    """
    _check_inside(root, take)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(asdict(take), ensure_ascii=False) + "\n")


def load_takes(manifest: Path, root: Path) -> list[Take]:
    """Read every take of the manifest; paths must stay inside *root*.

    Args:
        manifest: The JSONL manifest (absent means no take yet).
        root: The corpus root.

    Returns:
        The takes in recording order.
    """
    if not manifest.exists():
        return []
    takes = [
        _take_from_json(json.loads(line))
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for take in takes:
        _check_inside(root, take)
    return takes


def replace_takes(manifest: Path, root: Path, takes: list[Take]) -> None:
    """Rewrite the whole manifest atomically (annotation changes clips in place).

    Args:
        manifest: The JSONL manifest.
        root: The corpus root.
        takes: Every take, in order.
    """
    for take in takes:
        _check_inside(root, take)
    tmp = manifest.with_name(manifest.name + ".tmp")
    lines = "".join(json.dumps(asdict(take), ensure_ascii=False) + "\n" for take in takes)
    tmp.write_text(lines, encoding="utf-8", newline="\n")
    swap_into_place(tmp, manifest)
