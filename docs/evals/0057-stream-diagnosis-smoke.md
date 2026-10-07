# Streaming protocol diagnosis (Plan 0057)

- model: qwen2.5:3b (digest `357c53fb659c`)
- ollama version: 0.34.4
- generation options: server defaults (production passes none)
- runs per turn and variant: 1; shuffle seed: 57
- observations (all variants): 48 (graded 48, provider errors 0)
- baseline (`full`) fallback rate: context 58.33 %, public 0.00 %
- replies spoken that the whole text rejects (all variants): 0

## Variants

| Variant | What it changes |
|---|---|
| full | the turn exactly as `just eval-chat --mode stream` sends it (the baseline) |
| full_repeat | `full` again, interleaved: the noise of repeating one condition |
| no_context | the memory block removed; person and history kept |
| no_person | the active person removed; memory and history kept |
| no_history | the history removed; memory and person kept |
| question_only | memory, person and history all removed (several factors at once) |
| contract_first | the output contract moved to the start of the system prompt |
| public_with_context | a public question with a golden memory block borrowed in rotation |

## 1. Fallback by variant and source

| Variant | Source | Valid | Invalid | Empty | Errors | Fallback rate | Undue accept | Split-dependent |
|---|---|---|---|---|---|---|---|---|
| full | context | 5 | 7 | 0 | 0 | 58.33 % | 0 | 0 |
| full | public | 12 | 0 | 0 | 0 | 0.00 % | 0 | 0 |
| full_repeat | context | 7 | 5 | 0 | 0 | 41.67 % | 0 | 0 |
| full_repeat | public | 12 | 0 | 0 | 0 | 0.00 % | 0 | 0 |

## 2. Interventions against `full` (exploratory)

Each row compares one intervention with `full` on the turns where `full`, the variant and the `full_repeat` control all have the 1 expected runs graded; a turn missing any of them is excluded, never compared on a different sample, and a row with no complete control is `incomplete`, never a signal. The noise of a row is the mean absolute difference, turn by turn, between `full` and `full_repeat` on that row's own turns (opposite swings never cancel). A signal is a change of at least 15 points that also exceeds that noise. It is an exploratory signal, not a cause: confirm with another seed before attributing one.

| Variant | Paired | Excluded | `full` | Variant | Change (pp) | Noise (pp) | Reading |
|---|---|---|---|---|---|---|---|
| full_repeat | 24 | 0 | 7/24 (29.17 %) | 5/24 (20.83 %) | +8.3 | n/a | control |

`question_only` runs only on turns that have a person or a history; elsewhere it sends what `no_context` sends and is not repeated.

## 3. Failure shapes

| Shape in `full` (context) | Count | Share |
|---|---|---|
| tag_same_line | 7 | 100.00 % |

Dominant shape in `full` (context): `tag_same_line`.

| Shape in `full` (public) | Count | Share |
|---|---|---|

No fallbacks in `full` (public).

Shapes of each intervention, apart (never merged into the baseline):

| Variant | Source | Shape | Count |
|---|---|---|---|
| full_repeat | context | tag_same_line | 4 |
| full_repeat | context | no_tag | 1 |

## 4. Turns under `full`

| Turn | Fallbacks | Provider errors | Graded | Expected |
|---|---|---|---|---|
| absent_address | 0 | 0 | 1 | 1 |
| absent_pet | 1 | 0 | 1 | 1 |
| corrected_age_active_fact | 1 | 0 | 1 | 1 |
| corrected_species_active_fact | 1 | 0 | 1 | 1 |
| identified_person_second_person | 1 | 0 | 1 | 1 |
| multiple_active_facts | 1 | 0 | 1 | 1 |
| old_history_vs_active_fact | 1 | 0 | 1 | 1 |
| persisted_context_after_restart | 0 | 0 | 1 | 1 |
| public_1 | 0 | 0 | 1 | 1 |
| public_10 | 0 | 0 | 1 | 1 |
| public_11 | 0 | 0 | 1 | 1 |
| public_12 | 0 | 0 | 1 | 1 |
| public_2 | 0 | 0 | 1 | 1 |
| public_3 | 0 | 0 | 1 | 1 |
| public_4 | 0 | 0 | 1 | 1 |
| public_5 | 0 | 0 | 1 | 1 |
| public_6 | 0 | 0 | 1 | 1 |
| public_7 | 0 | 0 | 1 | 1 |
| public_8 | 0 | 0 | 1 | 1 |
| public_9 | 0 | 0 | 1 | 1 |
| resolved_face_enrollment | 0 | 0 | 1 | 1 |
| resolved_face_recognition | 1 | 0 | 1 | 1 |
| semantic_distractor_ignored | 0 | 0 | 1 | 1 |
| two_children_names | 0 | 0 | 1 | 1 |

Turns with at least one fallback: 7 of 24; that fell back in every expected run: 7; incomplete turns: 0.

## 5. Timing (ms)

| Variant | Outcome | n | First delta | Speech start | End |
|---|---|---|---|---|---|
| full | valid | 17 | 1120 / 2146 | 3493 / 5896 | 4963 / 13615 |
| full | fallback | 7 | 1254 / 1545 | 3364 / 5935 | 3364 / 5935 |
| full_repeat | valid | 19 | 1149 / 2123 | 3293 / 9149 | 5210 / 13739 |
| full_repeat | fallback | 5 | 1189 / 1427 | 3926 / 5680 | 3926 / 5680 |

p50 / p95 by the nearest-rank method. Speech start is when production would hand its first sentence, or the fallback, to TTS (TTS time excluded).

## 6. Execution order

Quarters of the shuffled execution order, all variants together: it describes the experiment, not the baseline.

| Quarter | Fallback rate |
|---|---|
| Q1 | 25.00 % |
| Q2 | 25.00 % |
| Q3 | 25.00 % |
| Q4 | 25.00 % |

No order effect above the rule.

## 7. Prompt size (characters sent)

| Variant | Min | Mean | Max |
|---|---|---|---|
| full | 2822 | 2884 | 3173 |
| full_repeat | 2822 | 2884 | 3173 |

## 8. Stream arrival probe

The probe sees the chunks as this client received them. It cannot tell a reply that Ollama withheld from fast generation, from buffering or from the client's own reading, so a burst never proves the `llm_streaming.py` header; only a spread-out arrival of the schema-constrained reply is evidence against it.

### Schema-constrained

| Run | Status | Chunks | Paced gaps / gaps | Pattern |
|---|---|---|---|---|
| 1 | complete | 113 | 112/112 | incremental |
| 2 | complete | 70 | 69/69 | incremental |
| 3 | complete | 96 | 95/95 | incremental |

Complete runs: 3 of 3; provider errors: 0; incomplete: 0; off schema: 0. Verdict: incremental.

### Plain-text control

| Run | Status | Chunks | Paced gaps / gaps | Pattern |
|---|---|---|---|---|
| 1 | complete | 128 | 127/127 | incremental |
| 2 | complete | 119 | 118/118 | incremental |
| 3 | complete | 83 | 82/82 | incremental |

Complete runs: 3 of 3; provider errors: 0; incomplete: 0; off schema: 0. Verdict: incremental.

Reading: The schema-constrained reply reached this client spread over time, which is compatible with incremental generation: streaming with a JSON schema is a candidate protocol and this is evidence against the `llm_streaming.py` claim that Ollama withholds it, though a client cannot see when generation ended.
