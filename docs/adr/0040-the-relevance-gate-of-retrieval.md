# 0040 — The relevance gate of retrieval: a near meaning, or the question's named words

- **Status:** **Proposed (2026-11-23)**, until Task A7 of
  [Plan 0088](../plans/open/0088-close-the-rag-gate-and-documents.md) accepts it on real hardware.
  The rule was chosen by the plan's bench ([record](../evals/0088-recall-bench.md)) under D-3 as
  amended by Pipec on 2026-11-23, and **Pipec adopted it the same day** («Sí, adopta G3»).
- **Date:** 2026-11-23
- **Builds on:** [ADR 0028](0028-recall-what-the-owner-told.md) (decision 6 and amendments A4,
  A5), [ADR 0031](0031-the-memory-engine-boundary.md) (decision 1: reading a sentence is the
  cognition side's job).
- **Supersedes:** ADR 0028 decision 6.3 (*a unit qualifies if its vector distance is under
  `RECALL_MAX_DISTANCE` **or** it shares a content word with the question*). **Narrows:** ADR 0028
  decision 6.7 (*without the embedding model the search is lexical only*): it still is, but a word
  hit then needs the question's named words (decision 3).
- **Used by:** [ADR 0034](0034-documents-and-reading-through-the-camera.md) decision 4: documents
  reuse this rule with their own thresholds, calibrated on their own corpus (Plan 0088 D-13).

## Context

Read on `main` at `c7469c4` (schema version 22) and on the installed packages (SQLite 3.49.1,
`sqlite-vec` 0.1.9, `granite-embedding:278m`), 2026-11-23:

1. **The gate is an «or».** `recall_search` kept a unit when its cosine distance to the question
   was under 0.43 **or** when FTS5 found it by any one content word (`MATCH "a" OR "b" …`).
2. **It failed both ways, on real evidence.** On Plan 0086's hardware sitting (2026-11-18),
   «¿qué te conté de X?», with no unit holding X, answered an unrelated story at distances 0.368
   and 0.372. Of the 32 `found` recall reads in the server logs (2026-11-03 to 2026-11-18), 2 had
   no vector hit under 0.43: their answer came from words alone.
3. **No second net.** The recall prompt has no «no me acuerdo» exit (ADR 0028 A4), so every unit
   that passes the gate becomes an answer.
4. **The signals a better gate needs were there or cost one query**: the distance of a word hit
   the KNN did not rank (`vec_distance_cosine` on named rows), and the capitalization and digits of
   the raw transcript before it is folded.

## Decision

### 1. One gate step, shared by every source

`memory/retrieval.py`, pure (no I/O, no settings, no model), holds what every source shares: the
signals of a candidate, the gate rules, Reciprocal Rank Fusion, the cap by group and the FTS5 match
expression. A search runs: the two rankings → the bodies of every candidate through the delivery
filter → the distance of every candidate the KNN did not rank → the gate on each candidate → RRF
over what qualified → the cap. A candidate scores on the vector ranking only when it qualifies
without its word hit. The gate is a parameter of the search, so a bench measures the production
pipeline.

### 2. The signals

- `d`: the candidate's cosine distance to the question; absent when the embedding model is down or
  the unit has no vector yet.
- `W`: whether the word index found it.
- `S`, the question's **specific words** (`recall_cues.specific_words`, carried on the cue): the
  words of the raw transcript written with a capital letter that do not open a sentence (after
  «¿», «¡», «.», «?», «!» or the start), and every token holding a digit; folded, without the stop
  words and «Iroko». A unit *covers* `S` when its folded body holds each word of `S`, with or
  without one final «s» (Plan 0086's rule for names, words of four letters or more).

### 3. The rule (G3 of Plan 0088)

A candidate qualifies when:

1. **if `S` is not empty, the unit covers `S`** — named things must be there; and
2. **with a distance:** `d < T_v`, or `W` and `d < T_w`; **without a distance:** `W`, and only when
   `S` is not empty (so the unit covers it).

| Threshold | Setting | Value | Where it comes from |
|---|---|---|---|
| `T_v` | `RECALL_MAX_DISTANCE` | 0.43 | ADR 0028 A5 (Pipec's questions), unchanged |
| `T_w` | `RECALL_WORD_MAX_DISTANCE` | 0.464 | Plan 0088's bench: the midpoint of two observed word-hit distances, swept on its `tune` half |

What a search by words alone (decision 6.7) returns now: a story asked by an exact name or code
the story holds («¿qué te dije del repuesto ZX-41?»). A question that names nothing specific finds
nothing by words alone: a strong cue says «No me acuerdo de eso.», a weak one converses.

The log line `recall.read` adds `rejected` (candidates the gate refused), `specific` (how many
specific words the question had) and `gate` (`G3`); never a text.

## The bench, and its limits

[Plan 0088's bench](../evals/0088-recall-bench.md): 57 invented units, 48 invented questions in ten
classes, two halves (`tune`, `check`), the production search, real `granite-embedding:278m`. Under
D-3 as amended, G3 meets Recall@3 = 100 % on *direct by words*, *lexical only* and *window* on both
halves, and has the highest correct-zero rate on `tune` (0.88; today's rule 0.25):

| | Today's rule (G0) | This rule (G3) |
|---|---|---|
| *Named, never told* (`tune` / `check`) | Z 0.67 / 0.67 | Z 1.00 / 1.00 |
| *Common word with a name* | Z 0.00 / 0.00 | Z 1.00 / 1.00 |
| *Common word, no name* | Z 0.00 / 0.00 | Z 0.67 / 0.00 |
| *Direct by meaning* (measured, not required) | R 0.25 / 0.50 | R 0.00 / 0.50 |

Its limits, said plainly:

- It is a regression bench of invented questions, not a calibration of the robot's real speech;
  the hardware acceptance of Plan 0088 D-7 is the real check.
- The gain on a single common word does not replicate on the held-out half (Z 0.00 on `check`);
  there G3 equals G2 (the named-words rule alone) everywhere except one class, where G2 is better.
- `T_w` = 0.464 sits in a narrow gap (0.016 between the two observed distances it bisects).
- The names are measured on one owner's 234 real turns only for how they are written: 6 name
  occurrences, half of the mid-sentence ones in lower case (Plan 0088 Task A0 Step 4).

## Alternatives considered

- **G0, today's rule** — rejected: it fails the negative classes (above) and the defect seen on
  hardware.
- **G1, the second gate alone** — rejected by D-3: lower correct-zero rate on `tune` (0.75), and on
  `check` it is no better than G0 on any negative class.
- **G2, the named words alone** — rejected by D-3: it does not improve on G0 in *common word, no
  name* on `tune`. On `check` it equals G3 and finds one more story (*lexical only, no name*); it is
  the simpler fallback if this rule's second gate fails on hardware.
- **A reranker, an LLM grader of relevance, HyDE** — not measured, rejected without measurement:
  they add a model call to a turn of a 3B model on a laptop, and the defect is solved without them.

## Consequences

### Positive

- A person or a thing never told no longer brings back somebody else's story when the question
  names it; one common word no longer qualifies a story far in meaning.
- Documents reuse the same step and the same rule, with their own thresholds (ADR 0034 decision 4).

### Negative

- **A misheard name is refused** when the speech-to-text writes it capitalized but differently
  («Leokadia» for a told «Leocadia»); a lower-case name is not specific, and the question falls
  back to the rule without `S`.
- **A capitalized common noun the story does not hold is refused** («¿qué hicimos en Año Nuevo?»
  against «el último día del año»).
- **With the embedding model down, or before a fresh unit has its vector** (the conversation job
  embeds it in the background), a story asked by common words alone is not found until the vector
  exists.
- One more query per recall: the distances of the word hits the KNN did not rank (the bench's
  p50 31 → 34 ms, p95 33 → 41 ms).

### The meaning threshold, a separate problem (Pipec, 2026-11-23)

The bench showed that a story asked by its meaning alone rarely lies under `T_v` = 0.43: 2 of 8
expected stories did (0.406 and 0.413; the others 0.442 to 0.532), and the nearest wrong stories of
the *named, never told* questions overlap them (0.407 to 0.507). No gate of this family can fix
that; it is the threshold's calibration (two real hits, ADR 0028 A5), not the gate's. **Not decided
here.** Trigger: the hardware acceptance or normal use shows a story asked by its meaning not
found, or a real corpus of Pipec's recall questions exists to recalibrate `T_v`.

## Test consequences

- `test_every_lexical_hit_qualifies` and `test_a_far_vector_hit_found_by_words_still_qualifies`
  (`tests/unit/test_recall_fusion.py`), which pinned decision 6.3, are replaced by
  `test_one_common_word_far_away_does_not_qualify`.
- Named tests pin the rule: a named person never told finds nothing even near; a story asked by its
  meaning still qualifies; an exact code qualifies with the vector side off; a common word with the
  vector side off does not; a lower-case name falls back to the rule without specific words; a unit
  without a vector yet follows the no-distance rule; the log counts `rejected` and `specific`.
- `just recall-bench --gates production` reproduces the bench's numbers for G3.
