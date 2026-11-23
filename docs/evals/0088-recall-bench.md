# Plan 0088 Part A — the recall bench and the gate it chose

> **Status:** run on 2026-11-23, Task A3 of [Plan 0088](../plans/open/0088-close-the-rag-gate-and-documents.md),
> twice. **First run (D-3 as written): no rule met D-3, none adopted.** Pipec then amended D-3
> («separa los problemas»): *direct by meaning* is measured and reported, no longer required,
> because the meaning threshold is a problem apart from the gate. **Second run (D-3 as amended):
> D-3 chooses G3 with `T_w` = 0.464**, shown to Pipec at Task A3 Step 5. Counts and rates only;
> every unit and question is an invented canary of
> [`tests/evals/recall_bench_v1.yaml`](../../tests/evals/recall_bench_v1.yaml).

## What was run

- `just recall-bench --gates G0` (Step 2), then `just recall-bench --gates G0,G1,G2,G3` (Step 3),
  each against a fresh temporary database through the production `search_recall`, whose gate is a
  parameter (D-5). Real `granite-embedding:278m` (Ollama digest `1a37926bf842`; `bert`, 277.45M
  parameters, context 512, embedding 768, F16). `T_v` = `RECALL_MAX_DISTANCE` = 0.43 (ADR 0028
  amendment A5). The occurred time is off in the bench (the windows of ADR 0028 decision 7).
- The bench: 57 units (53 turns, 4 episodes) of one invented owner and 48 questions in the ten
  classes of D-4, split into `tune` (25) and `check` (23). Seven are asked with the embedding
  model unreachable (`lexical_only`, `lexical_only_no_name`), through the search's own
  degradation path. It holds more than the «about 30» units of D-4 because the `window` class
  needs 25 older units of one topic, so that they fill the KNN's 20 neighbours.
- `T_w` was swept on `tune` only, over the midpoints between consecutive word-hit distances
  observed in `[0.43, 0.70]` (the range's ends count as points): 8 midpoints. D-3 ranks the rules
  on `tune`; `check` only has to hold the hard constraints.
- It is a regression bench of invented questions, not a calibration of the robot's real speech
  (D-3); the hardware acceptance of D-7 is the real check.

## The first run: why no rule met D-3 as written

1. **G0 already failed *direct by meaning*** (Recall@3 0.25 on `tune`, 0.50 on `check`). It also
   failed the negative classes, as Step 2 expected (Z 0.00 on both common-word classes, 0.67 on
   *named, never told*).
2. **G1, G2 and G3 only refuse more than G0.** A unit found by its meaning alone qualifies under
   every rule only with `d < T_v`, so no candidate can recover what G0 misses: the constraint on
   *direct by meaning* was out of reach of the whole family D-2 fixed.
3. **The distances of the expected stories.** The cosine distance of each meaning question's
   expected unit, from the question's embedded query (a diagnostic of the same run, by question id):

   | Question | Half | Expected unit's distance | Its rank among the 57 |
   |---|---|---|---|
   | m1 | tune | 0.532 | 1 |
   | m2 (capitalized common noun) | tune | 0.487 | 1 |
   | m3 | tune | 0.453 | 1 |
   | m4 (capitalized common noun) | tune | 0.530 | 3 (found by one shared word) |
   | m5 | check | 0.406 | 2 |
   | m6 | check | 0.442 | 1 |
   | m7 (capitalized common noun) | check | 0.522 | 12 |
   | m8 | check | 0.413 | 2 |

   Only m5 and m8 fall under 0.43. The nearest unit of the six *named, never told* questions lies
   at 0.407, 0.421, 0.463, 0.479, 0.496 and 0.507: true meaning hits (0.406 to 0.532) and the
   nearest wrong story overlap, so on this bench no vector threshold separates them. That is the
   meaning threshold's problem (`T_v` was calibrated on two real hits, ADR 0028 A5), not the gate's.

Every metric of the first run equals the second's below, except G1 and G3, which the first run
measured at the sweep's closest point to constraints none could meet.

## The second run: the result per class, half and rule

R = Recall@3, P = Precision@3 (— with no hit), MRR; Z = correct-zero rate (classes whose right
answer is none). G1 and G3 at the `T_w` the sweep chose, 0.464.

**tune**

| Class | n | G0 | G1 | G2 | G3 |
|---|---|---|---|---|---|
| direct_words | 3 | R 1.00 · P 0.83 · MRR 1.00 | R 1.00 · P 0.83 · MRR 1.00 | R 1.00 · P 0.83 · MRR 1.00 | R 1.00 · P 0.83 · MRR 1.00 |
| direct_meaning | 4 | R 0.25 · P 0.50 · MRR 0.25 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 |
| named_never_told | 3 | Z 0.67 | Z 0.67 | Z 1.00 | Z 1.00 |
| common_no_name | 3 | Z 0.00 | Z 0.67 | Z 0.00 | Z 0.67 |
| common_with_name | 2 | Z 0.00 | Z 1.00 | Z 1.00 | Z 1.00 |
| lexical_only | 2 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 |
| lexical_only_no_name | 2 | R 1.00 · P 1.00 · MRR 1.00 | R 0.00 · P — · MRR 0.00 | R 1.00 · P 1.00 · MRR 1.00 | R 0.00 · P — · MRR 0.00 |
| window | 2 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 |
| plural_variant | 2 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 |
| name_misheard | 2 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 0.50 · P 1.00 · MRR 0.50 | R 0.50 · P 1.00 · MRR 0.50 |

**check**

| Class | n | G0 | G1 | G2 | G3 |
|---|---|---|---|---|---|
| direct_words | 3 | R 1.00 · P 0.78 · MRR 1.00 | R 1.00 · P 0.78 · MRR 1.00 | R 1.00 · P 0.78 · MRR 1.00 | R 1.00 · P 0.78 · MRR 1.00 |
| direct_meaning | 4 | R 0.50 · P 0.42 · MRR 0.25 | R 0.50 · P 0.42 · MRR 0.25 | R 0.50 · P 0.42 · MRR 0.25 | R 0.50 · P 0.42 · MRR 0.25 |
| named_never_told | 3 | Z 0.67 | Z 0.67 | Z 1.00 | Z 1.00 |
| common_no_name | 3 | Z 0.00 | Z 0.00 | Z 0.00 | Z 0.00 |
| common_with_name | 2 | Z 0.00 | Z 0.00 | Z 1.00 | Z 1.00 |
| lexical_only | 2 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 |
| lexical_only_no_name | 1 | R 1.00 · P 1.00 · MRR 1.00 | R 0.00 · P — · MRR 0.00 | R 1.00 · P 1.00 · MRR 1.00 | R 0.00 · P — · MRR 0.00 |
| window | 2 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 | R 1.00 · P 1.00 · MRR 1.00 |
| plural_variant | 2 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 |
| name_misheard | 1 | R 0.00 · P 0.00 · MRR 0.00 | R 0.00 · P 0.00 · MRR 0.00 | R 0.00 · P — · MRR 0.00 | R 0.00 · P — · MRR 0.00 |

What D-3 reads (the lowest Recall@3 of the three hard classes; Z pooled over the three negative
classes; Z of `common_no_name`):

| Rule | `T_w` (margin) | tune: hard · Z · common | check: hard · Z · common | `search_recall` p50 / p95 |
|---|---|---|---|---|
| G0 | — | 1.00 · 0.25 · 0.00 | 1.00 · 0.25 · 0.00 | 31.0 / 33.0 ms |
| G1 | 0.464 (0.016) | 1.00 · 0.75 · 0.67 | 1.00 · 0.25 · 0.00 | 37.6 / 51.8 ms |
| G2 | — | 1.00 · 0.62 · 0.00 | 1.00 · 0.62 · 0.00 | 36.0 / 43.4 ms |
| **G3** | **0.464 (0.016)** | **1.00 · 0.88 · 0.67** | **1.00 · 0.62 · 0.00** | **33.7 / 40.7 ms** |

The `T_w` sweep on `tune` (hard · Z · common):

| `T_w` | margin | G1 | G3 |
|---|---|---|---|
| 0.443 | 0.026 | 0.50 · 0.75 · 0.67 | 0.50 · 0.88 · 0.67 |
| **0.464** | **0.016** | **1.00 · 0.75 · 0.67** | **1.00 · 0.88 · 0.67** |
| 0.476 | 0.007 | 1.00 · 0.62 · 0.33 | 1.00 · 0.75 · 0.33 |
| 0.483 | 0.007 | 1.00 · 0.50 · 0.33 | 1.00 · 0.75 · 0.33 |
| 0.492 | 0.011 | 1.00 · 0.38 · 0.33 | 1.00 · 0.75 · 0.33 |
| 0.502 | 0.008 | 1.00 · 0.38 · 0.33 | 1.00 · 0.75 · 0.33 |
| 0.518 | 0.024 | 1.00 · 0.25 · 0.00 | 1.00 · 0.62 · 0.00 |
| 0.615 | 0.170 | 1.00 · 0.25 · 0.00 | 1.00 · 0.62 · 0.00 |

## D-3's choice, and what it does not prove

**G3 with `T_w` = 0.464**: it meets the hard constraints on both halves, has the highest
correct-zero rate on `tune` (0.88 against G0's 0.25) and improves on G0 in *common word, no name*
on `tune` (0.67 against 0.00). Read with it:

1. **The names hold on both halves.** *Named, never told* and *common word with a name* go to Z
   1.00 on `tune` and `check` (G0: 0.67 and 0.00): the defect seen on hardware.
2. **The single common word improves on `tune` only.** On `check`, *common word, no name* stays at
   Z 0.00 under every rule; on the held-out half G3 and G2 are equal everywhere except *lexical
   only, no name*, where G2 finds the story and G3 does not. The gain of the second gate is not
   replicated on held-out questions.
3. **The margin is narrow.** `T_w` = 0.464 sits between two observed word-hit distances 0.016
   apart; 0.443 already loses a window question, and from 0.476 the common-word gain halves.
4. **What G3 refuses by design.** With the embedding model down, a story asked by one common word
   and no name is not found (*lexical only, no name*, R 0.00; D-2: with no distance, a word hit
   needs covered specific words). A misheard name written with a capital («Leokadia» for a told
   «Leocadia») is refused, where G0 found it (*name misheard* 0.50 against 1.00 on `tune`), and a
   capitalized common noun the story does not hold («Año Nuevo» against «el último día del
   año») is refused (m4).
5. ***Direct by meaning*** is 0.25 or less on `tune` and 0.50 on `check` under every rule: the
   meaning threshold, apart from the gate (D-3 as amended).

## Inputs to the record

- **Task A0 Step 4** (2026-11-23, a copy of the real database opened with `immutable=1` under
  `data/rehearsal-0088a/`, deleted the same session): 234 turns of one owner; 8 name tokens of the
  alta's people and pets; 4 turns hold a name; of the 6 occurrences, 2 are capitalized mid-sentence,
  2 capitalized opening a sentence, 2 in lower case; 3 tokens are one edit away from a name. The
  sample is small; half the mid-sentence names are in lower case, so `S` misses them and the rule
  falls back to its no-`S` path (Review focus 1).
- ***The audit* item 2, recounted** (deduplicated `recall.read` lines of `logs/server*.log`): 46
  reads, 32 `found`, 2 of them with `best_distance ≥ 0.43` (1 `lexical_only`). These counts need the
  logs through 2026-11-18; between 2026-10-28 and 2026-11-12 they are 40, 26 and 1.
- Task A0 Step 3 baseline: the CI selection, 8470 passed.
