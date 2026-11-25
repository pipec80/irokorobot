"""Measure the vision model under a normal day's load (Plan 0089 D-8): numbers, never a text.

It calls the product's own ``describe_image`` and ``read_text`` (no route, no robot) over a small
set of canary photographs kept outside the repository, one cell of the matrix at a time, and
appends one JSON line per call: latency, Ollama's own metrics, free memory and VRAM before and
after, the 3B text model's next latency, the failure cause, and closed quality checks. A safety
stop ends the run when free memory drops under 1 GB or one call passes 120 s.

Usage:
    uv run --env-file .env python scripts/vlm_bench.py --images .superpowers/sdd/0089/images --cell today --mode cold --set all --out .superpowers/sdd/0089/bench.jsonl
    uv run --env-file .env python scripts/vlm_bench.py --cell ctx4096 --override vlm_image_max_side=768 --mode warm --set core --out .superpowers/sdd/0089/bench.jsonl
    uv run python scripts/vlm_bench.py --summary .superpowers/sdd/0089/bench.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
import statistics
import subprocess  # nvidia-smi, a fixed local command with no user input
import sys
import time
from typing import TYPE_CHECKING, Final, Literal

import httpx
from server.exceptions import VisionError
from server.llm_transport import ollama_chat_measured
from server.settings import settings
from server.system_memory import available_ram_mb
from server.text_keys import normalize_spanish
from server.vision.describe import describe_image
from server.vision.read_text import read_text

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

type Mode = Literal["cold", "warm"]
type Consolidation = Literal["loaded", "unloaded"]

_RAM_FLOOR_MB: Final = 1024
_CALL_CEILING_MS: Final = 120_000
_PROBE: Final = "Responde solo con la palabra hola. qqsondaqq"
_CANARY_WORDS: Final = ["lista", "qqcanarioqq", "pan", "te", "fosforos"]
_BILL_TOTAL: Final = re.compile(r"(?<!\d)12[.,\s]?345(?!\d)")
_BILL_DUE: Final = re.compile(r"(?<!\d)15\D{1,3}12\D{1,3}2026(?!\d)")
_CODE_WORDS: Final = ("qr", "codigo de barras", "codigo de barra")
#: The closed synonyms each object may be named by (accents folded, lowercase).
_OBJECT_WORDS: Final = {
    "ball": ("pelota", "balon", "bola"),
    "cube": ("cubo", "rubik", "megaminx", "rompecabezas", "dodecaedro", "puzzle"),
    "band": ("pulsera", "smartband", "smartwatch", "reloj", "brazalete", "banda"),
}
_READING_IMAGES: Final = ("card", "screen", "bill", "hand_neat", "hand_hurried", "hand_bic")
_CANARY_IMAGES: Final = ("card", "screen", "hand_neat", "hand_hurried", "hand_bic")
#: Which photographs each ``--set`` runs.
IMAGE_SETS: Final = {
    "core": ("card", "screen", "ball"),
    "reading": ("bill", "hand_neat", "hand_hurried", "hand_bic", "codes", "cube", "band"),
}
IMAGE_SETS_ALL: Final = (*IMAGE_SETS["core"], *IMAGE_SETS["reading"])


@dataclass(frozen=True)
class Cell:
    """One combination of the matrix: a name and the settings it overrides."""

    name: str
    overrides: dict[str, int | str] = field(default_factory=dict)


#: The cells of D-8. Ollama's own switches are set on Ollama itself, so their cells only label.
CELLS: Final = {
    cell.name: cell
    for cell in (
        Cell("today"),
        Cell("side768", {"vlm_image_max_side": 768}),
        Cell("side512", {"vlm_image_max_side": 512}),
        Cell("side384", {"vlm_image_max_side": 384}),
        Cell("ctx4096", {"vlm_num_ctx": 4096}),
        Cell("ctx2048", {"vlm_num_ctx": 2048}),
        Cell("caps", {"vlm_num_predict_scene": 120, "vlm_num_predict_reading": 400}),
        Cell("keepalive", {"vlm_keep_alive": "10m"}),
        Cell("ollama_flash_attention"),
        Cell("ollama_kv_q8"),
        Cell("ollama_max_loaded"),
        Cell("best"),
    )
}


@dataclass(frozen=True)
class BenchImage:
    """One canary photograph: its name (which says what it shows) and its bytes."""

    name: str
    data: bytes


@dataclass(frozen=True)
class Meters:
    """The readers of free memory and VRAM, in megabytes; tests inject doubles."""

    ram: Callable[[], int | None]
    vram: Callable[[], int | None]


def nvidia_vram_mb() -> int | None:
    """Return the GPU memory in use from ``nvidia-smi``, or ``None`` without a GPU."""
    try:
        done = subprocess.run(  # fixed arguments, no shell
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return int(done.stdout.split()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_spanish(text))


def _contains_run(words: Sequence[str], run: Sequence[str]) -> bool:
    width = len(run)
    return any(list(words[i : i + width]) == list(run) for i in range(len(words) - width + 1))


def quality(image: str, text: str) -> dict[str, bool | None]:
    """Score one answer with closed checks only (no judge model); ``None`` where one does not apply.

    Args:
        image: The photograph's name (``card``, ``bill``, ``cup``, ...).
        text: The model's answer. Only booleans leave this function.
    """
    folded = normalize_spanish(text)
    words = _words(text)
    return {
        "canary_ok": _contains_run(words, _CANARY_WORDS) if image in _CANARY_IMAGES else None,
        "bill_ok": (
            bool(_BILL_TOTAL.search(text) and _BILL_DUE.search(text)) if image == "bill" else None
        ),
        "code_named": (any(word in folded for word in _CODE_WORDS) if image == "codes" else None),
        "object_named": (
            any(word in words for word in _OBJECT_WORDS[image]) if image in _OBJECT_WORDS else None
        ),
    }


class _VisionLog(logging.Handler):
    """Keep the extra fields of the last ``vision.metrics`` and ``vision.*_failed`` records."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.metrics: dict[str, object] = {}
        self.cause: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        event = record.__dict__.get("event")
        if event == "vision.metrics":
            fields = ("load_ms", "prompt_eval_count", "prompt_eval_ms", "eval_count", "eval_ms")
            self.metrics = {key: record.__dict__.get(key) for key in (*fields, "total_ms")}
        elif event in {"vision.describe_failed", "vision.read_failed"}:
            self.cause = str(record.__dict__.get("cause"))


async def _set_loaded(client: httpx.AsyncClient, model: str, *, loaded: bool) -> None:
    """Load a model with an empty generate call, or unload it with ``keep_alive: 0``."""
    body: dict[str, object] = {"model": model} if loaded else {"model": model, "keep_alive": 0}
    response = await client.post(
        f"{settings.ollama_url}/api/generate", json=body, timeout=settings.ollama_timeout_s
    )
    response.raise_for_status()


async def _probe_ms(client: httpx.AsyncClient) -> int | None:
    """Time the 3B model on a fixed canary question, to see whether the VLM evicted it."""
    started = time.perf_counter()
    try:
        await ollama_chat_measured(
            client,
            [{"role": "user", "content": _PROBE}],
            model=settings.ollama_model,
            options={"temperature": 0.0},
            timeout=settings.ollama_timeout_s,
        )
    except (httpx.HTTPError, VisionError, ValueError):
        return None
    return int((time.perf_counter() - started) * 1000)


async def _one_call(
    client: httpx.AsyncClient, image: BenchImage, catcher: _VisionLog
) -> tuple[str, int, str | None, dict[str, bool | None]]:
    """Run one vision call; return its capability, latency, failure cause and quality."""
    capability = "reading" if image.name in _READING_IMAGES else "scene"
    catcher.metrics, catcher.cause = {}, None
    started = time.perf_counter()
    text = ""
    try:
        if capability == "reading":
            text = await read_text(client, image.data)
        else:
            text, _ms = await describe_image(client, image.data)
    except VisionError as exc:
        catcher.cause = catcher.cause or type(exc).__name__
    latency_ms = int((time.perf_counter() - started) * 1000)
    return capability, latency_ms, catcher.cause, quality(image.name, text)


def _append(out: Path, row: dict[str, object]) -> None:
    with out.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


async def run_cell(  # one cell is named by all of these
    client: httpx.AsyncClient,
    images: Sequence[BenchImage],
    cell: Cell,
    *,
    mode: Mode,
    consolidation: Consolidation,
    meters: Meters,
    out: Path,
    probe: bool = True,
) -> int:
    """Run one cell over *images* and append one line per call; return how many calls ran.

    Args:
        client: The one HTTP client of the run.
        images: The photographs of the chosen set.
        cell: The cell (its overrides are applied to the settings for the run).
        mode: ``cold`` unloads the vision model before each call; ``warm`` loads it once first.
        consolidation: Whether the 4B consolidation model is loaded just before each call.
        meters: The free-memory and VRAM readers.
        out: The JSON-lines file appended to.
        probe: Time the 3B model after each call; ``False`` keeps the vision model truly warm
            (nothing else is loaded between its calls).
    """
    for key, value in cell.overrides.items():
        setattr(settings, key, value)
    catcher = _VisionLog()
    vision_logger = logging.getLogger("server.vision")
    # A plain script logs at WARNING; vision.metrics is INFO, so open the level for the run.
    previous_level = vision_logger.level
    vision_logger.setLevel(logging.INFO)
    vision_logger.addHandler(catcher)
    calls = 0
    try:
        if mode == "warm":
            await _set_loaded(client, settings.vlm_model, loaded=True)
        for image in images:
            ram_before = meters.ram()
            if ram_before is not None and ram_before < _RAM_FLOOR_MB:
                _append(out, {"cell": cell.name, "stopped": "low_ram", "ram_mb": ram_before})
                return calls
            if mode == "cold":
                await _set_loaded(client, settings.vlm_model, loaded=False)
            await _set_loaded(
                client,
                settings.consolidation_model or settings.ollama_model,
                loaded=consolidation == "loaded",
            )
            capability, latency_ms, cause, scores = await _one_call(client, image, catcher)
            calls += 1
            _append(
                out,
                {
                    "cell": cell.name,
                    "overrides": cell.overrides,
                    "mode": mode,
                    "consolidation": consolidation,
                    "capability": capability,
                    "image": image.name,
                    "latency_ms": latency_ms,
                    **catcher.metrics,
                    "ram_before_mb": ram_before,
                    "ram_after_mb": meters.ram(),
                    "vram_mb": meters.vram(),
                    "probe_ms": await _probe_ms(client) if probe else None,
                    "cause": cause,
                    **scores,
                },
            )
            if latency_ms > _CALL_CEILING_MS:
                _append(out, {"cell": cell.name, "stopped": "slow_call", "latency_ms": latency_ms})
                return calls
    finally:
        vision_logger.removeHandler(catcher)
        vision_logger.setLevel(previous_level)
    return calls


def _median(values: list[int]) -> int | str:
    return int(statistics.median(values)) if values else "-"


def render_summary(path: Path) -> str:
    """Render the bench file as a Markdown table: one row per cell, mode and capability.

    Args:
        path: The JSON-lines file the runs appended to.
    """
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "stopped" not in row:
            key = (str(row["cell"]), str(row["mode"]), str(row["capability"]))
            groups.setdefault(key, []).append(row)
    lines = [
        "| cell | mode | capability | calls | median ms | max ms | median load ms "
        "| min free MB | quality ok | failures |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for (cell, mode, capability), rows in groups.items():
        latencies = [int(str(r["latency_ms"])) for r in rows]
        loads = [int(str(r["load_ms"])) for r in rows if r.get("load_ms") is not None]
        free = [int(str(r["ram_after_mb"])) for r in rows if r.get("ram_after_mb") is not None]
        checks = [
            r[key]
            for r in rows
            for key in ("canary_ok", "bill_ok", "code_named", "object_named")
            if r.get(key) is not None
        ]
        failures = sum(1 for r in rows if r.get("cause"))
        lines.append(
            f"| {cell} | {mode} | {capability} | {len(rows)} | {_median(latencies)} "
            f"| {max(latencies)} | {_median(loads)} | {min(free) if free else '-'} "
            f"| {sum(1 for c in checks if c)}/{len(checks)} | {failures} |"
        )
    return "\n".join(lines) + "\n"


def _load_images(folder: Path, names: Sequence[str]) -> list[BenchImage]:
    images = []
    for name in names:
        path = next(iter(sorted(folder.glob(f"{name}.*"))), None)
        if path is None:
            sys.stderr.write(f"Missing photograph, skipped: {name}\n")
            continue
        images.append(BenchImage(name=name, data=path.read_bytes()))
    return images


def _override(text: str) -> tuple[str, int | str]:
    key, _, value = text.partition("=")
    return key, int(value) if value.isdigit() else value


async def _main(args: argparse.Namespace) -> int:
    base = CELLS[args.cell]
    cell = Cell(base.name, {**base.overrides, **dict(_override(o) for o in args.override)})
    names = IMAGE_SETS_ALL if args.set == "all" else IMAGE_SETS[args.set]
    images = _load_images(args.images, names)
    meters = Meters(ram=available_ram_mb, vram=nvidia_vram_mb)
    async with httpx.AsyncClient() as client:
        calls = await run_cell(
            client,
            images,
            cell,
            mode=args.mode,
            consolidation=args.consolidation,
            meters=meters,
            out=args.out,
            probe=args.probe,
        )
    sys.stdout.write(f"{cell.name}: {calls} call(s) appended to {args.out}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run one cell, or print the summary table of a bench file."""
    parser = argparse.ArgumentParser(description="Measure the vision model under load.")
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--images", type=Path, default=Path(".superpowers/sdd/0089/images"))
    parser.add_argument("--cell", choices=sorted(CELLS), default="today")
    parser.add_argument("--override", action="append", default=[], metavar="SETTING=VALUE")
    parser.add_argument("--mode", choices=("cold", "warm"), default="cold")
    parser.add_argument("--consolidation", choices=("loaded", "unloaded"), default="unloaded")
    parser.add_argument("--set", choices=("core", "reading", "all"), default="core")
    parser.add_argument("--no-probe", dest="probe", action="store_false")
    parser.add_argument("--out", type=Path, default=Path(".superpowers/sdd/0089/bench.jsonl"))
    args = parser.parse_args(argv)
    if args.summary is not None:
        sys.stdout.write(render_summary(args.summary))
        return 0
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
