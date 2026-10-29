"""Task 4 (Plan 0075): the Spanish embedding-separation instrument.

A fake embedder (deterministic vectors), the pure separation math, and a
structure + reserved-terms check on the tracked fixture. No Ollama, no network.
"""

import asyncio
from pathlib import Path

import pytest

from scripts import check_reserved_terms, cm4_embed_separation
from scripts.cm4_embed_separation import PhraseGroup

_FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "cm4_embedding_phrases.yaml"


def test_cosine_of_known_vectors() -> None:
    assert cm4_embed_separation.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cm4_embed_separation.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cm4_embed_separation.cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_separation_perfect_split() -> None:
    report = cm4_embed_separation.separation(within=[0.9, 0.85, 0.88], across=[0.2, 0.1, 0.25])
    assert report.mean_within > report.mean_across
    assert report.difference == pytest.approx(report.mean_within - report.mean_across)
    assert report.roc_auc == 1.0


def test_separation_full_overlap_is_half() -> None:
    report = cm4_embed_separation.separation(within=[0.5, 0.5], across=[0.5, 0.5])
    assert report.roc_auc == 0.5


def test_load_phrases_structure_and_reserved_terms() -> None:
    groups = cm4_embed_separation.load_phrases(_FIXTURE)
    assert len(groups) >= 6
    ids = [group.id for group in groups]
    assert len(set(ids)) == len(ids)
    for group in groups:
        assert len(group.paraphrases) >= 2
    matcher = check_reserved_terms.build_matcher(check_reserved_terms.load_reserved_terms())
    if matcher is not None:
        assert (
            check_reserved_terms.offending_lines(_FIXTURE.read_text(encoding="utf-8"), matcher)
            == []
        )


def test_embed_fixture_and_within_across_scoring() -> None:
    groups = (
        PhraseGroup(id="a", anchor="a1", paraphrases=("a2", "a3")),
        PhraseGroup(id="b", anchor="b1", paraphrases=("b2", "b3")),
    )

    async def fake_embed(text: str) -> list[float]:
        return [1.0, 0.0] if text.startswith("a") else [0.0, 1.0]

    embeddings = asyncio.run(cm4_embed_separation.embed_fixture(groups, embed=fake_embed))
    assert len(embeddings) == 6  # two groups x three phrases
    within, across = cm4_embed_separation.within_across(embeddings, groups)
    report = cm4_embed_separation.separation(within, across)
    assert report.roc_auc == 1.0
    assert report.mean_within == pytest.approx(1.0)
    assert report.mean_across == pytest.approx(0.0)
