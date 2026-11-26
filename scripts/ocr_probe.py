"""Prove one OCR engine alone on three canary photographs (Plan 0090 Task 1, D-1): numbers only.

The server stays off and no model of Ollama is loaded: the reader is proved by itself, as each
piece of the pipeline was. Every photograph is read as taken and with its contrast raised
(grayscale and a local contrast step with OpenCV), and one JSON line per read is appended:
latency, the free memory before and after, closed checks with no judge model, and the failure
cause. No line holds the read text. RapidOCR is a server dependency since Plan 0090 Task 3; the
reserve, Tesseract, runs from an ephemeral layer (``uv run --with pytesseract``).

The photographs are invented canaries (Plan 0089's printable sheet): ``bill`` is the invented
bill (total $12.345, due 15-12-2026); ``hand_bic`` and ``hand_graphite`` are the canary list
written by hand in blue ballpoint and in graphite.

Usage:
    uv run python scripts/ocr_probe.py --images .superpowers/sdd/0090/images --engine rapidocr --out .superpowers/sdd/0090/probe.jsonl
    uv run python scripts/ocr_probe.py --summary .superpowers/sdd/0090/probe.jsonl
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution puts ``scripts/`` on ``sys.path[0]``; the ``from scripts.…`` import below needs
# the repo root (pytest already has it through pyproject ``pythonpath``), as in ``cm4_corpus.py``.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
from dataclasses import asdict, dataclass
import json
import logging
import time
from typing import TYPE_CHECKING, Final, Literal

from server.system_memory import available_ram_mb
from server.text_keys import normalize_spanish

from scripts.vlm_bench import quality

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

type Variant = Literal["as_taken", "contrast"]
type Reader = Callable[[bytes], list[str]]

#: The three photographs of the amended Task 1, by file stem.
PHOTOGRAPHS: Final = ("bill", "hand_bic", "hand_graphite")
VARIANTS: Final[tuple[Variant, ...]] = ("as_taken", "contrast")
ENGINES: Final = ("rapidocr", "tesseract")
#: The handwritten canary list of Plan 0089's sheet, folded: «Lista qqcanarioqq: pan, té, fósforos».
_CANARY_WORDS: Final = ("lista", "qqcanarioqq", "pan", "te", "fosforos")
_CLAHE_CLIP: Final = 2.0
_CLAHE_TILE: Final = 8
_BLANK_SIDE: Final = 64
_WHITE: Final = 255


def blank_png() -> bytes:
    """A small white PNG for the warm-up read (no text, so nothing to score)."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    ok, encoded = cv2.imencode(".png", np.full((_BLANK_SIDE, _BLANK_SIDE), _WHITE, dtype=np.uint8))
    if not ok:
        raise ValueError("the warm-up image could not be encoded")
    return bytes(encoded)


@dataclass(frozen=True)
class ProbeLine:
    """One read of one photograph: numbers and booleans, never the text.

    Attributes:
        engine: The OCR engine's name.
        photograph: The photograph's stem.
        variant: ``as_taken`` or ``contrast``.
        latency_ms: The read's wall time.
        ram_before_mb: Free memory before the read (``None`` when the OS does not say).
        ram_after_mb: Free memory after the read.
        lines_read: How many text lines the engine returned.
        bill_ok: The bill's total and due date read exactly (``None`` for a note).
        canary_words: How many of the five canary words were read (``None`` for the bill).
        cause: The exception's class name when the read failed, else ``None``.
    """

    engine: str
    photograph: str
    variant: Variant
    latency_ms: int
    ram_before_mb: int | None
    ram_after_mb: int | None
    lines_read: int
    bill_ok: bool | None
    canary_words: int | None
    cause: str | None


def canary_words_read(text: str) -> int:
    """Count the canary words of the handwritten list found in *text* (accents folded)."""
    words = set(normalize_spanish(text).replace(",", " ").replace(":", " ").split())
    return sum(1 for word in _CANARY_WORDS if word in words)


def checks(photograph: str, text: str) -> tuple[bool | None, int | None]:
    """Score one read with closed checks only; only a boolean and a count leave this function.

    Args:
        photograph: The photograph's stem.
        text: Every line the engine read, joined.

    Returns:
        ``(bill_ok, canary_words)``: the first for the bill, the second for a note.
    """
    if photograph == "bill":
        return bool(quality("bill", text)["bill_ok"]), None
    return None, canary_words_read(text)


def raise_contrast(image: bytes) -> bytes:
    """Return *image* in grayscale with its local contrast raised (CLAHE), as a PNG.

    A probe variant only: the server reads the frame as taken (Plan 0090 decision 9 as amended).

    Args:
        image: A JPEG or PNG photograph.

    Raises:
        ValueError: If OpenCV cannot decode or encode the image.
    """
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    decoded = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if decoded is None:
        raise ValueError("the photograph could not be decoded")
    clahe = cv2.createCLAHE(clipLimit=_CLAHE_CLIP, tileGridSize=(_CLAHE_TILE, _CLAHE_TILE))
    ok, encoded = cv2.imencode(".png", clahe.apply(decoded))
    if not ok:
        raise ValueError("the photograph could not be encoded")
    return bytes(encoded)


def read_one(
    reader: Reader,
    *,
    engine: str,
    photograph: str,
    variant: Variant,
    image: bytes,
    clock: Callable[[], float] = time.perf_counter,
    free_ram: Callable[[], int | None] = available_ram_mb,
) -> ProbeLine:
    """Read one photograph once with *reader* and measure it; a failure is a line, not a crash.

    Args:
        reader: Returns the text lines the engine reads in one image.
        engine: The engine's name, for the line.
        photograph: The photograph's stem.
        variant: Whether the contrast step ran.
        image: The photograph's bytes, already in *variant*.
        clock: Seconds, monotonic; injectable for tests.
        free_ram: Free megabytes; injectable for tests.
    """
    before = free_ram()
    start = clock()
    cause: str | None = None
    lines: list[str] = []
    try:
        lines = reader(image)
    except Exception as exc:  # the probe's boundary: any engine failure is recorded by class
        cause = type(exc).__name__
    latency_ms = int((clock() - start) * 1000)
    bill_ok, canary = checks(photograph, " ".join(lines)) if cause is None else (None, None)
    return ProbeLine(
        engine=engine,
        photograph=photograph,
        variant=variant,
        latency_ms=latency_ms,
        ram_before_mb=before,
        ram_after_mb=free_ram(),
        lines_read=len(lines),
        bill_ok=bill_ok,
        canary_words=canary,
        cause=cause,
    )


def rapidocr_reader() -> Reader:
    """Build RapidOCR's reader with its default models (PP-OCRv6 small, which covers Spanish)."""
    from rapidocr import RapidOCR  # noqa: PLC0415 - heavy import, only when probing

    engine = RapidOCR()

    def read(image: bytes) -> list[str]:
        result = engine(image)
        return [str(text) for text in (result.txts or ())]

    return read


def tesseract_reader() -> Reader:
    """Build Tesseract's reader (the reserve; needs the native binary and its Spanish model)."""
    # Present only in the probe's ephemeral layer (`uv run --with pytesseract`), never in the lock.
    from PIL import Image  # noqa: PLC0415
    import pytesseract  # noqa: PLC0415  # pyright: ignore[reportMissingImports]

    def read(image: bytes) -> list[str]:
        from io import BytesIO  # noqa: PLC0415

        text = pytesseract.image_to_string(Image.open(BytesIO(image)), lang="spa")
        return [line for line in text.splitlines() if line.strip()]

    return read


def run(engine: str, reader: Reader, images: Path, out: Path) -> int:
    """Read every photograph in both variants once and append one line each to *out*.

    Returns:
        The number of lines written.
    """
    written = 0
    with out.open("a", encoding="utf-8") as sink:
        for photograph in PHOTOGRAPHS:
            source = next(iter(sorted(images.glob(f"{photograph}.*"))), None)
            if source is None:
                logger.warning("Photograph missing: %s", photograph)
                continue
            taken = source.read_bytes()
            for variant in VARIANTS:
                image = raise_contrast(taken) if variant == "contrast" else taken
                line = read_one(
                    reader, engine=engine, photograph=photograph, variant=variant, image=image
                )
                sink.write(json.dumps(asdict(line), ensure_ascii=False) + "\n")
                written += 1
    return written


def summary(path: Path) -> str:
    """Render the probe's lines as a Markdown table (numbers and outcomes only)."""
    rows = [
        "| engine | photograph | variant | ms | free MB before | free MB after | lines | bill_ok "
        "| canary words | cause |",
        "|---|---|---|---:|---:|---:|---:|---|---:|---|",
    ]
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        item = json.loads(raw)
        cells = [
            item["engine"],
            item["photograph"],
            item["variant"],
            str(item["latency_ms"]),
            str(item["ram_before_mb"]),
            str(item["ram_after_mb"]),
            str(item["lines_read"]),
            "-" if item["bill_ok"] is None else str(item["bill_ok"]).lower(),
            "-" if item["canary_words"] is None else f"{item['canary_words']}/5",
            item["cause"] or "-",
        ]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the probe, or print the summary of an earlier run."""
    parser = argparse.ArgumentParser(description="Prove one OCR engine alone (Plan 0090).")
    parser.add_argument("--images", type=Path)
    parser.add_argument("--engine", choices=ENGINES, default="rapidocr")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.summary is not None:
        sys.stdout.write(summary(args.summary))
        return 0
    if args.images is None or args.out is None:
        parser.error("--images and --out are required to run the probe")
    loaded_before = available_ram_mb()
    start = time.perf_counter()
    reader = rapidocr_reader() if args.engine == "rapidocr" else tesseract_reader()
    # RapidOCR loads its models on the first call: one blank read keeps the load out of the reads.
    reader(blank_png())
    load_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "Engine %s loaded in %d ms (free MB %s -> %s)",
        args.engine,
        load_ms,
        loaded_before,
        available_ram_mb(),
    )
    written = run(args.engine, reader, args.images, args.out)
    logger.info("Probe wrote %d lines to %s", written, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
