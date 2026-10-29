# 0075 — CM-4 pre-measurement record

> **Aggregates only.** No transcript, no phrase text, no per-clip distance and no household datum. The
> private corpus (Pipec's real voice) lived only under `project-history/calibration/cm4/` and was
> deleted at the close of [Plan 0075](../plans/completed/0075-cm4-pre-measurement.md). Measured by Pipec on
> 2026-10-29; the instruments are deterministic and reusable.

## What was measured, and why

Before CM-4 is built, [ADR 0027](../adr/0027-conversation-record-and-the-diary.md) requires two numbers
(decisions 2, 3, 6 and 11): how often the owner's voice verifies on real conversation clips, and whether
the embedding model separates Spanish. This record holds both, with the eligibility rule left for Pipec
to decide from the numbers.

## Machine and setup

- Shared development laptop (i7-11390H, 15.7 GB RAM; NVIDIA MX450, 2 GB). Only project processes open.
- Owner entity id **1**, **3** enrolled voiceprints, model
  `speechbrain/spkrec-ecapa-voxceleb@0f99f2d0…`, fixed threshold **0.4834** (in-sample, Plan 0047).
- Voice rate: server **stopped**, scored offline against a **read-only copy** of the database placed
  under the corpus root; the live database was never opened. Embeddings: Ollama up, each model measured
  in isolation.
- Corpus: two spontaneous conversations (`s1` ≈ 5 min free speech; `s2` ≈ 2 min reading a script that
  covers the five phrase types). **62 clips** total, segmented with the robot's adopted policy
  (pre-roll 400 ms, closing silence 1200 ms, upload tail 300 ms).

## 1. Owner-voice verification rate

Overall: **22 of 62 turns verified = 35.5 %** (95 % Wilson interval 24.7 – 47.9 %).

### By clip duration

| Bucket | verified / assessed | rate |
|---|---|---|
| `> 3 s` | 18 / 31 (1 not assessable) | 58 % |
| `1.5 – 3 s` | 4 / 19 | 21 % |
| `< 1.5 s` | 0 / 12 | 0 % (rejected by the 1.5 s floor) |

### By phrase type

| Type | verified / total | rate |
|---|---|---|
| `command` | 2 / 3 | 67 % |
| `taste_statement` | 8 / 16 (1 not assessable) | 50 % |
| `other` | 11 / 22 | 50 % |
| `short_answer` | 1 / 14 | 7 % |
| `question` | 0 / 7 | 0 % |

### Per conversation

| Conversation | verified / total | rate |
|---|---|---|
| `s1` (free speech) | 17 / 34 | 50 % |
| `s2` (scripted, short/varied) | 5 / 28 | 18 % |

Conversations with at least one verified turn: 2 of 2. By-conversation bootstrap 95 % interval of the
pooled rate: 17.9 – 50.0 % (n = 2 conversations, wide).

### Sub-1.5 s no-floor diagnostic (not a proposal)

Of the 12 clips under 1.5 s, **0 would have matched** the owner even if the duration floor were removed.
Lowering `speaker_min_verification_s` would recover nothing here.

### One not-assessable clip

One `> 3 s` clip was 30.5 s (a long continuous utterance) and exceeded the 30 s audio-contract cap, so
the backend could not embed it; it is counted `unavailable`, exactly as the robot's own voice check would
degrade it. (The instrument was fixed mid-run to degrade such a clip instead of crashing.)

## 2. Embedding separation in Spanish

Seven invented Chilean-neutral Spanish groups (anchor + 2 paraphrases each); within-group paraphrase
pairs should sit closer than across-group unrelated pairs. n_within = 21, n_across = 189.

| Model | dim | mean within | mean across | difference | ROC-AUC | footprint (`ollama ps`) |
|---|---|---|---|---|---|---|
| `nomic-embed-text` (current) | 768 | 0.816 | 0.584 | 0.231 | 0.980 | 335 MB (GPU) |
| `embeddinggemma:300m` | 768 | 0.761 | 0.345 | 0.416 | 1.000 | 1.1 GB (CPU/GPU) |
| `granite-embedding:278m` | 768 | 0.839 | 0.569 | 0.270 | 1.000 | 185 MB (GPU) |

The current `nomic-embed-text` does separate Spanish (ROC-AUC 0.98), but unrelated phrases still sit
fairly close (mean across 0.58). Both 768-d multilingual models separate better (ROC-AUC 1.00): a swap
would be a drop-in by dimension. `embeddinggemma` has the widest gap but the largest footprint (1.1 GB,
spilling to CPU); `granite-embedding:278m` reaches ROC-AUC 1.00 at the smallest footprint (185 MB, fully
on the GPU).

## What Pipec decides

1. **Eligibility rule (ADR 0027 decisions 2–3).** The verified rate is driven by clip duration:
   substantive turns (statements and longer turns) verify at ~50–58 %, while **short answers verify at
   7 % and questions at 0 %**. A **per-turn** rule would keep the owner's substantive statements for the
   diary and drop almost all short confirmations and questions — acceptable if CM-4's episodes summarize
   what the owner states, not one-word replies. A **per-conversation "majority verified"** rule is
   fragile here (s1 50 %, s2 18 %); "at least one verified turn" is only the record-retention flag
   (decision 2), not what feeds memory. **Recommendation: per turn**, noting that voice confirmation of
   short answers is unreliable (a standing CM-3 finding). **Confirmed by Pipec (2026-10-29): per turn;**
   the CM-4 implementation plan cements it.
2. **The 1.5 s floor.** 0 of 12 sub-1.5 s clips would match even without the floor → lowering it is not
   worth a plan. Closed.
3. **The embedding model.** `nomic-embed-text` is adequate (ROC-AUC 0.98). If a future plan wants better
   Spanish separation, `granite-embedding:278m` is the strongest drop-in (ROC-AUC 1.00, 768-d, 185 MB);
   `embeddinggemma:300m` separates most but is heavier. A swap means re-embedding the index and is its
   own plan. Pipec decides whether to open it.

## Method limitations

- Two conversations, one enrolled owner, one laptop; the by-conversation interval is wide (n = 2).
- `s1` was free speech (no `question`/`command`); the five types are balanced only because `s2` used a
  script. A future run can use the capture guide now built into `cm4-corpus capture-conversation`.
- The 0.4834 threshold is in-sample (Plan 0047), so genuine rates are optimistic.
- The embedding fixture is invented canaries approximating Pipec's style, not his real phrases, so the
  separation figures rank candidates rather than certify production behaviour.

## Next plan

The CM-4 implementation — the conversation record, the episode and candidate jobs and migration 013 — is
the next plan; it is out of scope here and flips [ADR 0027](../adr/0027-conversation-record-and-the-diary.md)
to `Accepted` when it closes.
