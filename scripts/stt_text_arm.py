"""stt_text_arm.py - did the speech-to-text mishear, or did the rest misread? (Plan 0069 Task 8)

For each read take, the item's own text and what Whisper heard go through the same
deterministic readers the server uses — the intent need, the taste gate and the memory
answer grammar — and are compared with the expectation the script records:

- ``ok``: the text gives the expected outcome and the transcript gives the same;
- ``stt``: the text gives it, the transcript does not (Whisper misheard);
- ``rest``: the text itself does not give it (the reader is wrong, not Whisper);
- ``both``: the text does not give it, and the transcript changes the outcome again.

Only scripted item ids and counts are printed, never a spontaneous sentence. Deviated
takes (Pipec said something else) are skipped: the expectation is about the script text.

Usage:
    just stt-text-arm --run P0-dev-20261021T100000
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution puts ``scripts/`` on ``sys.path[0]``; the ``from scripts.…`` imports
# below need the repo root (pytest already has it through pyproject ``pythonpath``).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
from collections import Counter
from typing import TYPE_CHECKING

from server.cognition.intent_resolution import parse_memory_answer, resolve_information_need
from server.memory.preference_gate import match_preference

from scripts.stt_bench_report import score_run
from scripts.stt_corpus_models import MANIFEST_NAME, STT_CORPUS_ROOT, load_script, load_takes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.stt_corpus_models import ScriptItem

OUTCOMES = ("ok", "stt", "rest", "both")


def _outcome(text: str, keys: Sequence[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    if "need" in keys:
        values["need"] = resolve_information_need(text).need.value
    if "taste" in keys:
        values["taste"] = "yes" if match_preference(text).matches else "no"
    if "answer" in keys:
        answer = parse_memory_answer(text)
        values["answer"] = "none" if answer is None else ("accept" if answer.accept else "reject")
    return values


def attribute(item: ScriptItem, reference: str, hypothesis: str) -> str:
    """Attribute one take's outcome to the speech-to-text or to the readers after it.

    Args:
        item: The script item, with its expectation.
        reference: The item's text as read.
        hypothesis: What Whisper heard (the take's clips joined).

    Returns:
        ``ok``, ``stt``, ``rest`` or ``both`` (see the module docstring).
    """
    keys = sorted(item.expect)
    from_reference = _outcome(reference, keys)
    reference_ok = from_reference == item.expect
    changed = _outcome(hypothesis, keys) != from_reference
    if reference_ok:
        return "stt" if changed else "ok"
    return "both" if changed else "rest"


def render(root: Path, run_id: str) -> str:
    """Count the attributions of one bench run per layer.

    Args:
        root: The corpus root.
        run_id: A bench run file stem.

    Returns:
        A Markdown table of counts.
    """
    items = {item.id: item for item in load_script()}
    deviated = {take.take_id for take in load_takes(root / MANIFEST_NAME, root) if take.deviated}
    counts: Counter[tuple[str, str]] = Counter()
    for score in score_run(root, run_id).takes:
        if score.take_id in deviated:
            continue
        item = items[score.item_id]
        counts[item.layer, attribute(item, item.text, score.marked_hypothesis)] += 1
    lines = [
        f"# Text arm ({run_id})",
        "",
        "| layer | " + " | ".join(OUTCOMES) + " |",
        "|---|" + "---|" * len(OUTCOMES),
    ]
    for layer in sorted({layer for layer, _ in counts}):
        cells = " | ".join(str(counts[layer, outcome]) for outcome in OUTCOMES)
        lines.append(f"| {layer} | {cells} |")
    lines += ["", f"deviated takes skipped: {len(deviated)}"]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the text arm's table for one run.

    Args:
        argv: Arguments without the program name.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description="Attribute STT errors (Plan 0069)")
    parser.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    print(render(STT_CORPUS_ROOT, args.run))  # noqa: T201 -- the count table
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
