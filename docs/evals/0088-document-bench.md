# 0088 — The document bench

> Plan [0088](../plans/open/0088-close-the-rag-gate-and-documents.md) Part B, D-10, D-9 and D-13.
> Counts and rates only: no section, title or question of a real document appears here.

## The corpus

[`tests/evals/document_bench_v1.yaml`](../../tests/evals/document_bench_v1.yaml) over three
invented documents in [`tests/fixtures/documents/`](../../tests/fixtures/documents/): a washing
machine manual (`.md`, `normal`), a bread recipe (`.txt`, `normal`) and a knee care guide (a
text-layer PDF of three pages, `sensitive`, written by `make_care_guide_pdf.py`). 36 questions in
seven classes, each split into `tune` and `check` halves; 8 of them ask about a section that holds
a planted instruction, 3 of those in the `sensitive` guide.

## The section cap (Task B0 Step 4, 2026-11-23)

Characters per token of `granite-embedding:278m` (Ollama 0.40.16, `prompt_eval_count`, special
tokens included), on paragraphs of at least 80 characters:

| Corpus | Paragraphs | Minimum | 5th percentile | Median |
|---|---|---|---|---|
| Bench manual (`.md`) | 13 | 3.31 | 3.31 | 3.69 |
| Bench recipe (`.txt`) | 6 | 3.26 | 3.26 | 3.49 |
| Bench guide (PDF) | 3 | 3.71 | 3.71 | 3.76 |
| One long PDF of Pipec's own (local, never copied) | 94 | 2.77 | 2.77 | 3.04 |

**The cap: 1,200 characters per section.** At the lowest ratio observed (2.77) that is 433 tokens,
under the 512-token window with a margin; the load counts each section's tokens when Ollama answers
and cuts again a section over the window before inserting it. `/api/embed` with `truncate: false`
refuses an over-long input (HTTP 400), so a section is never cut silently.

## The extraction caps (Task B0 Step 4, 2026-11-23)

Four PDFs of Pipec's own, measured locally in a child process with `pypdf` 7.1.1 (counts only):

| Document | Size | Pages | Characters | Pages without text | Extraction | Peak memory |
|---|---|---|---|---|---|---|
| 1 | 21.8 MB | 7 | 0 | 7 | 0.08 s | 44 MB |
| 2 | 18.9 MB | 4 | 0 | 4 | 0.07 s | 38 MB |
| 3 | 134.0 MB | 750 | 0 | 750 | 2.2 s | 259 MB |
| 4 | 3.5 MB | 99 | 93,504 | 0 | 10.1 s | 14 MB |

Three are scanned (no text layer: R4). The long text-layer document fits the caps of D-9 as
proposed, so they are kept: 10 MB, 200 pages, 30 s, 2,000 sections.

## The document gate (Task B7)

Not run yet.
