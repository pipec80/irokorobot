"""Task 4 (Plan 0075): does the embedding model separate Spanish paraphrases?

Embeds an invented, tracked fixture of Chilean-neutral Spanish phrases through
Ollama (``llm_transport.ollama_embed`` directly, so a non-768-d model is measured
and not rejected), then reports, per model, how much closer within-group
paraphrase pairs sit than across-group unrelated pairs: the within/across means,
their difference, and the ROC-AUC of within against across. It changes no runtime
setting and adopts nothing — it only measures (Plan 0075 D-5, ADR 0027 decision 11).

Usage:
    just cm4-embed report --model nomic-embed-text --model embeddinggemma:300m

The phrases are invented canaries (no household data); run it with Ollama up.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution (just cm4-embed) puts scripts/ on sys.path[0]; the from-scripts
# imports below need the repo root (pytest adds it via pyproject).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
import itertools
import json
import logging

import httpx
import numpy as np
from server.exceptions import LLMError
from server.llm_transport import ollama_embed
from server.settings import settings
import yaml

logger = logging.getLogger(__name__)

__all__ = [
    "PhraseGroup",
    "SeparationReport",
    "cosine",
    "embed_fixture",
    "load_phrases",
    "main",
    "separation",
    "within_across",
]

_DEFAULT_FIXTURE = Path("tests/evals/cm4_embedding_phrases.yaml")
_MIN_GROUPS = 6
_MIN_PARAPHRASES = 2

type PhraseEmbedder = Callable[[str], Awaitable[list[float]]]


@dataclass(frozen=True)
class PhraseGroup:
    """One meaning: an anchor and its paraphrases (all invented canaries)."""

    id: str
    anchor: str
    paraphrases: tuple[str, ...]


@dataclass(frozen=True)
class SeparationReport:
    """How well a model separates within-group pairs from across-group pairs.

    Attributes:
        mean_within: Mean cosine similarity of within-group paraphrase pairs.
        mean_across: Mean cosine similarity of across-group unrelated pairs.
        difference: ``mean_within - mean_across`` (higher is better separation).
        roc_auc: Probability a random within pair scores above a random across
            pair (ties count a half); 1.0 is a perfect split, 0.5 is no signal.
        n_within: Number of within-group pairs.
        n_across: Number of across-group pairs.
    """

    mean_within: float
    mean_across: float
    difference: float
    roc_auc: float
    n_within: int
    n_across: int


def load_phrases(path: Path) -> tuple[PhraseGroup, ...]:
    """Load and validate the invented Spanish fixture.

    Args:
        path: The fixture YAML.

    Returns:
        The groups.

    Raises:
        ValueError: On a malformed fixture, a duplicate id, a group with fewer
            than two paraphrases, or fewer than six groups.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw_groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(raw_groups, list) or not raw_groups:
        raise ValueError("fixture must have a non-empty 'groups' list")
    groups: list[PhraseGroup] = []
    seen: set[str] = set()
    for entry in raw_groups:
        group_id = str(entry["id"])
        if group_id in seen:
            raise ValueError(f"duplicate group id {group_id!r}")
        seen.add(group_id)
        paraphrases = tuple(str(item) for item in entry["paraphrases"])
        if len(paraphrases) < _MIN_PARAPHRASES:
            raise ValueError(f"group {group_id!r} needs at least {_MIN_PARAPHRASES} paraphrases")
        groups.append(
            PhraseGroup(id=group_id, anchor=str(entry["anchor"]), paraphrases=paraphrases)
        )
    if len(groups) < _MIN_GROUPS:
        raise ValueError(f"fixture needs at least {_MIN_GROUPS} groups")
    return tuple(groups)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the cosine similarity of two vectors, or ``0.0`` if either is zero."""
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def _roc_auc(within: Sequence[float], across: Sequence[float]) -> float:
    """Return the probability a within pair scores above an across pair (ties half)."""
    if not within or not across:
        return 0.0
    wins = 0.0
    for high in within:
        for low in across:
            if high > low:
                wins += 1.0
            elif high == low:
                wins += 0.5
    return wins / (len(within) * len(across))


def separation(within: Sequence[float], across: Sequence[float]) -> SeparationReport:
    """Summarize within-group versus across-group similarity.

    Args:
        within: Cosine similarities of within-group paraphrase pairs.
        across: Cosine similarities of across-group unrelated pairs.

    Returns:
        The :class:`SeparationReport`.
    """
    mean_within = sum(within) / len(within) if within else 0.0
    mean_across = sum(across) / len(across) if across else 0.0
    return SeparationReport(
        mean_within=mean_within,
        mean_across=mean_across,
        difference=mean_within - mean_across,
        roc_auc=_roc_auc(within, across),
        n_within=len(within),
        n_across=len(across),
    )


def _keys_of(group: PhraseGroup) -> list[str]:
    """Return the embedding keys for a group's anchor and paraphrases."""
    return [f"{group.id}:{index}" for index in range(1 + len(group.paraphrases))]


def within_across(
    embeddings: Mapping[str, list[float]], groups: Sequence[PhraseGroup]
) -> tuple[list[float], list[float]]:
    """Split every phrase pair into within-group and across-group cosine lists.

    Args:
        embeddings: Phrase key (``<group>:<index>``) to its vector.
        groups: The fixture groups.

    Returns:
        ``(within, across)`` cosine-similarity lists.
    """
    keys = {group.id: _keys_of(group) for group in groups}
    within: list[float] = []
    for group in groups:
        for first, second in itertools.combinations(keys[group.id], 2):
            within.append(cosine(embeddings[first], embeddings[second]))
    across: list[float] = []
    for left, right in itertools.combinations([group.id for group in groups], 2):
        for key_left in keys[left]:
            for key_right in keys[right]:
                across.append(cosine(embeddings[key_left], embeddings[key_right]))
    return within, across


async def embed_fixture(
    groups: Sequence[PhraseGroup], *, embed: PhraseEmbedder
) -> dict[str, list[float]]:
    """Embed every phrase of every group through the *embed* seam.

    Args:
        groups: The fixture groups.
        embed: Seam that embeds one phrase; the CLI wires ``ollama_embed``, tests
            inject a fake.

    Returns:
        Phrase key (``<group>:<index>``) to its embedding vector.
    """
    embeddings: dict[str, list[float]] = {}
    for group in groups:
        for index, text in enumerate([group.anchor, *group.paraphrases]):
            embeddings[f"{group.id}:{index}"] = await embed(text)
    return embeddings


async def _run(groups: Sequence[PhraseGroup], models: Sequence[str]) -> list[dict[str, object]]:
    """Measure each pulled model; skip (with a log line) one that is not pulled."""
    results: list[dict[str, object]] = []
    async with httpx.AsyncClient() as client:
        for model in models:

            def embed(text: str, name: str = model) -> Awaitable[list[float]]:
                return ollama_embed(client, text, model=name, timeout=settings.ollama_timeout_s)

            try:
                embeddings = await embed_fixture(groups, embed=embed)
            except (httpx.HTTPError, LLMError) as exc:
                logger.warning(
                    "Skipping model %s (not pulled or unreachable): %s", model, type(exc).__name__
                )
                continue
            within, across = within_across(embeddings, groups)
            report = separation(within, across)
            dimension = len(next(iter(embeddings.values())))
            results.append(
                {
                    "model": model,
                    "dimension": dimension,
                    "mean_within": round(report.mean_within, 4),
                    "mean_across": round(report.mean_across, 4),
                    "difference": round(report.difference, 4),
                    "roc_auc": round(report.roc_auc, 4),
                    "n_within": report.n_within,
                    "n_across": report.n_across,
                }
            )
    return results


def _cmd_report(args: argparse.Namespace) -> None:
    groups = load_phrases(args.fixture)
    results = _run_sync(groups, args.model)
    print(json.dumps({"models": results}, indent=2))  # noqa: T201 -- the operator pastes this


def _run_sync(groups: Sequence[PhraseGroup], models: Sequence[str]) -> list[dict[str, object]]:
    return asyncio.run(_run(groups, models))


def main(argv: list[str] | None = None) -> None:
    """Run the embedding-separation CLI."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="CM-4 Spanish embedding separation (Plan 0075).")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    report = subparsers.add_parser("report")
    report.add_argument("--model", action="append", required=True)
    report.add_argument("--fixture", type=Path, default=_DEFAULT_FIXTURE)
    report.set_defaults(handler=_cmd_report)
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
