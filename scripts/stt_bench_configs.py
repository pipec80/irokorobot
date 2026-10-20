"""The bench configurations of Plan 0069 (Appendix B, D-8 and D-10).

``P0`` is production today, built from the server's own ``decode_options``; every other
configuration changes exactly what Appendix B names and nothing else, so a difference
against ``P0`` has one cause. The segmentation policies are replayed offline on the raw
takes (D-17).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import random
from typing import TYPE_CHECKING, Final

from robot.audio_capture import SegmentationPolicy
from server.stt import SHORT_REPLY_HOTWORDS, WhisperDecodeOptions

if TYPE_CHECKING:
    from collections.abc import Sequence

#: D-10: vocabulary and «¿?» style, fixed before measuring; it names no scripted value.
PR_VOCAB_PROMPT: Final = (
    "Conversación en español de Chile con Iroko, un robot doméstico: gustos, comidas, la hora "
    "y la casa. ¿Lo guardo? Sí, autorizo que lo guardes."
)
_CPU_THREADS_TODAY: Final = 0  # CTranslate2's own default (four threads)
_GPU_COMPUTE: Final = "int8_float16"
_PEAK_DBFS: Final = -3.0


@dataclass(frozen=True)
class BenchConfig:
    """One way to run Whisper over the corpus.

    Attributes:
        name: The Appendix B name.
        model: The faster-whisper model name.
        device: ``cpu`` or ``cuda``.
        compute_type: The CTranslate2 compute type.
        cpu_threads: Threads on CPU (0 is CTranslate2's default).
        options: The decode options.
        hotwords: Hotwords passed on every clip (``HW``); ``None`` otherwise.
    """

    name: str
    model: str
    device: str
    compute_type: str
    cpu_threads: int
    options: WhisperDecodeOptions
    hotwords: str | None = None


def configs(base: WhisperDecodeOptions) -> dict[str, BenchConfig]:
    """Build every configuration of Appendix B from the production options.

    Args:
        base: ``stt.decode_options(settings)`` — production today.

    Returns:
        The configurations by name, ``P0`` first.
    """
    p0 = BenchConfig("P0", "small", "cpu", "int8", _CPU_THREADS_TODAY, base)

    def with_options(name: str, **changes: object) -> BenchConfig:
        return replace(p0, name=name, options=replace(base, **changes))  # type: ignore[arg-type]  # dataclass fields

    table = [
        p0,
        with_options("T0", temperatures=(0.0,)),
        with_options("NS-off", no_speech_threshold=None),
        with_options("V-off", vad_filter=False),
        with_options(
            "V-soft",
            vad_threshold=0.35,
            vad_speech_pad_ms=500,
            vad_min_speech_ms=150,
            vad_min_silence_ms=2000,
        ),
        with_options("PR-none", initial_prompt=None),
        with_options("PR-vocab", initial_prompt=PR_VOCAB_PROMPT),
        replace(p0, name="HW", hotwords=" ".join(SHORT_REPLY_HOTWORDS)),
        with_options("WT", word_timestamps=True),
        with_options("B1", beam_size=1),
        replace(p0, name="TH8", cpu_threads=8),
        replace(p0, name="F32", compute_type="float32"),
        with_options("NORM", input_peak_dbfs=_PEAK_DBFS),
        replace(p0, name="M-medium", model="medium"),
        replace(p0, name="M-turbo", model="large-v3-turbo"),
        replace(p0, name="G-small", device="cuda", compute_type=_GPU_COMPUTE),
        replace(
            p0, name="G-turbo", model="large-v3-turbo", device="cuda", compute_type=_GPU_COMPUTE
        ),
    ]
    return {config.name: config for config in table}


def split_items(item_ids: Sequence[str], seed: int = 69) -> tuple[frozenset[str], frozenset[str]]:
    """Split the script items into a dev half and a test half (D-8), by item.

    Args:
        item_ids: Every item id (order does not matter).
        seed: The split's seed.

    Returns:
        (dev, test): disjoint, together every item; every take of an item stays on its side.
    """
    ordered = sorted(set(item_ids))
    random.Random(seed).shuffle(ordered)  # noqa: S311 -- a reproducible split, not security
    half = (len(ordered) + 1) // 2
    return frozenset(ordered[:half]), frozenset(ordered[half:])


def _policy(preroll_ms: int, close_ms: int, tail_ms: int) -> SegmentationPolicy:
    return SegmentationPolicy(
        preroll_ms=preroll_ms, close_silence_ms=close_ms, upload_tail_ms=tail_ms
    )


#: D-17: today's segmentation and the variants replayed offline on the raw takes.
SEGMENTATION_POLICIES: Final = {
    "close800-tail800-pre400": _policy(400, 800, 800),
    "close800-tail300": _policy(400, 800, 300),
    "close800-tail500": _policy(400, 800, 500),
    "close1200-tail300": _policy(400, 1200, 300),
    "close1600-tail300": _policy(400, 1600, 300),
    "close1200-tail300-pre600": _policy(600, 1200, 300),
}
