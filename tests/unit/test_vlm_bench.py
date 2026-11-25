"""Plan 0089 D-8: the vision bench records numbers and closed checks, never a text."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx
import pytest

from scripts.vlm_bench import (
    CELLS,
    BenchImage,
    Meters,
    quality,
    render_summary,
    run_cell,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit

_TEXT_CANARY = "qqcanarioqq"


def _ollama(reply: str) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True})
        body = {"message": {"content": reply}, "load_duration": 5_000_000, "eval_count": 9}
        return httpx.Response(200, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _meters(ram: int = 6000) -> Meters:
    return Meters(ram=lambda: ram, vram=lambda: 1500)


def _images() -> list[BenchImage]:
    return [
        BenchImage(name="card", data=b"\xff\xd8card"),
        BenchImage(name="ball", data=b"\xff\xd8ball"),
    ]


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_one_cell_writes_its_numbers_and_no_text(tmp_path: Path) -> None:
    out = tmp_path / "bench.jsonl"
    reply = f"Lista {_TEXT_CANARY}: pan, té, fósforos"
    async with _ollama(reply) as client:
        calls = await run_cell(
            client,
            _images(),
            CELLS["today"],
            mode="warm",
            consolidation="unloaded",
            meters=_meters(),
            out=out,
        )

    assert calls == 2
    card, cup = _lines(out)
    assert (card["cell"], card["capability"], card["image"]) == ("today", "reading", "card")
    assert cup["capability"] == "scene"
    assert card["canary_ok"] is True
    assert cup["object_named"] is False
    for key in (
        "latency_ms",
        "load_ms",
        "eval_count",
        "ram_before_mb",
        "ram_after_mb",
        "vram_mb",
        "probe_ms",
        "mode",
        "consolidation",
    ):
        assert key in card
    assert card["load_ms"] == 5
    assert _TEXT_CANARY not in out.read_text(encoding="utf-8")


async def test_low_memory_stops_the_run_before_the_next_call(tmp_path: Path) -> None:
    out = tmp_path / "bench.jsonl"
    async with _ollama("Una taza.") as client:
        calls = await run_cell(
            client,
            _images(),
            CELLS["today"],
            mode="warm",
            consolidation="unloaded",
            meters=_meters(ram=900),
            out=out,
        )

    assert calls == 0
    (stop,) = _lines(out)
    assert stop["stopped"] == "low_ram"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Lista qqcanarioqq:\npan, té, fósforos", True),
        ("LISTA QQCANARIOQQ: PAN, TE, FOSFOROS.", True),
        ("Lista qqcanarioqq: pan, té", False),
        ("Lista qqcanarioqq: pan, café, fósforos", False),
    ],
)
def test_the_canary_comparison_is_closed(text: str, expected: bool) -> None:
    assert quality("card", text)["canary_ok"] is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Boleta qqluzqq. Total $12.345. Vence 15-12-2026.", True),
        ("Total $12.346, vence 15-12-2026", False),
        ("Total $12.345, vence 15-12-2025", False),
    ],
)
def test_the_bill_needs_its_total_and_due_date_exactly(text: str, expected: bool) -> None:
    assert quality("bill", text)["bill_ok"] is expected


def test_an_object_is_named_only_by_its_closed_synonyms() -> None:
    assert quality("ball", "Una persona sostiene una pelota roja.")["object_named"] is True
    assert quality("cube", "Sostiene un rompecabezas de colores.")["object_named"] is True
    assert quality("band", "Lleva una pulsera negra en la muñeca.")["object_named"] is True
    assert quality("band", "Hay un objeto negro en su brazo.")["object_named"] is False
    assert quality("codes", "Una hoja con un código QR.")["code_named"] is True


def test_the_bic_handwriting_is_a_canary_reading() -> None:
    assert quality("hand_bic", "LISTA QQCANARIOQQ: PAN, TÉ, FÓSFOROS")["canary_ok"] is True


def test_the_summary_is_one_markdown_row_per_cell(tmp_path: Path) -> None:
    out = tmp_path / "bench.jsonl"
    rows = [
        {
            "cell": "today",
            "mode": "cold",
            "capability": "reading",
            "image": "card",
            "latency_ms": 9000,
            "load_ms": 6000,
            "ram_after_mb": 2100,
            "cause": None,
            "canary_ok": True,
        },
        {
            "cell": "today",
            "mode": "cold",
            "capability": "reading",
            "image": "screen",
            "latency_ms": 7000,
            "load_ms": 10,
            "ram_after_mb": 2000,
            "cause": "ReadTimeout",
            "canary_ok": False,
        },
    ]
    out.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    table = render_summary(out)

    assert table.splitlines()[0].startswith("| cell |")
    (row,) = [line for line in table.splitlines() if line.startswith("| today |")]
    assert "| 2 |" in row  # calls
    assert "| 1/2 |" in row  # quality ok
    assert "| 1 |" in row  # failures


async def test_metrics_are_kept_even_when_the_loggers_are_at_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain script logs at WARNING: the bench must still see vision.metrics (INFO)."""
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    previous = root.level
    root.setLevel(logging.WARNING)  # what a script without logging config has
    out = tmp_path / "bench.jsonl"
    try:
        async with _ollama("Una pelota roja.") as client:
            await run_cell(
                client,
                [BenchImage(name="ball", data=b"\xff\xd8ball")],
                CELLS["today"],
                mode="warm",
                consolidation="unloaded",
                meters=_meters(),
                out=out,
            )
    finally:
        root.setLevel(previous)

    (row,) = _lines(out)
    assert row["load_ms"] == 5
    assert row["eval_count"] == 9
