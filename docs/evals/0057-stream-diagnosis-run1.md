# Streaming protocol diagnosis (Plan 0057)

- model: qwen2.5:3b (digest `357c53fb659c`)
- ollama version: 0.34.4
- generation options: server defaults (production passes none)
- runs per turn and variant: 5; shuffle seed: 57
- observations (all variants): 500 (graded 500, provider errors 0)
- baseline (`full`) fallback rate: context 51.67 %, public 1.67 %
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
| full | context | 29 | 31 | 0 | 0 | 51.67 % | 0 | 0 |
| full | public | 59 | 1 | 0 | 0 | 1.67 % | 0 | 0 |
| full_repeat | context | 29 | 31 | 0 | 0 | 51.67 % | 0 | 0 |
| full_repeat | public | 58 | 2 | 0 | 0 | 3.33 % | 0 | 0 |
| no_context | context | 50 | 10 | 0 | 0 | 16.67 % | 0 | 0 |
| no_person | context | 2 | 3 | 0 | 0 | 60.00 % | 0 | 0 |
| no_history | context | 2 | 3 | 0 | 0 | 60.00 % | 0 | 0 |
| question_only | context | 10 | 0 | 0 | 0 | 0.00 % | 0 | 0 |
| contract_first | context | 0 | 60 | 0 | 0 | 100.00 % | 0 | 0 |
| contract_first | public | 0 | 60 | 0 | 0 | 100.00 % | 0 | 0 |
| public_with_context | public | 54 | 6 | 0 | 0 | 10.00 % | 0 | 0 |

## 2. Interventions against `full` (exploratory)

Each row compares one intervention with `full` on the turns where `full`, the variant and the `full_repeat` control all have the 5 expected runs graded; a turn missing any of them is excluded, never compared on a different sample, and a row with no complete control is `incomplete`, never a signal. The noise of a row is the mean absolute difference, turn by turn, between `full` and `full_repeat` on that row's own turns (opposite swings never cancel). A signal is a change of at least 15 points that also exceeds that noise. It is an exploratory signal, not a cause: confirm with another seed before attributing one.

| Variant | Paired | Excluded | `full` | Variant | Change (pp) | Noise (pp) | Reading |
|---|---|---|---|---|---|---|---|
| full_repeat | 24 | 0 | 32/120 (26.67 %) | 33/120 (27.50 %) | -0.8 | n/a | control |
| no_context | 12 | 0 | 31/60 (51.67 %) | 10/60 (16.67 %) | +35.0 | 16.7 | exploratory signal |
| no_person | 1 | 0 | 4/5 (80.00 %) | 3/5 (60.00 %) | +20.0 | 0.0 | exploratory signal |
| no_history | 1 | 0 | 5/5 (100.00 %) | 3/5 (60.00 %) | +40.0 | 20.0 | exploratory signal |
| question_only | 2 | 0 | 9/10 (90.00 %) | 0/10 (0.00 %) | +90.0 | 10.0 | exploratory signal |
| contract_first | 24 | 0 | 32/120 (26.67 %) | 120/120 (100.00 %) | -73.3 | 9.2 | no signal |
| public_with_context | 12 | 0 | 1/60 (1.67 %) | 6/60 (10.00 %) | +8.3 | 1.7 | no signal |

`question_only` runs only on turns that have a person or a history; elsewhere it sends what `no_context` sends and is not repeated.

## 3. Failure shapes

| Shape in `full` (context) | Count | Share |
|---|---|---|
| tag_same_line | 30 | 96.77 % |
| no_tag | 1 | 3.23 % |

Dominant shape in `full` (context): `tag_same_line`.

| Shape in `full` (public) | Count | Share |
|---|---|---|
| tag_same_line | 1 | 100.00 % |

Dominant shape in `full` (public): `tag_same_line`.

Shapes of each intervention, apart (never merged into the baseline):

| Variant | Source | Shape | Count |
|---|---|---|---|
| full_repeat | context | tag_same_line | 29 |
| full_repeat | context | no_tag | 1 |
| full_repeat | context | text_before_tag | 1 |
| full_repeat | public | tag_same_line | 2 |
| no_context | context | no_tag | 5 |
| no_context | context | tag_same_line | 5 |
| no_person | context | tag_same_line | 3 |
| no_history | context | tag_same_line | 3 |
| contract_first | context | no_tag | 60 |
| contract_first | public | no_tag | 60 |
| public_with_context | public | tag_same_line | 6 |

## 4. Turns under `full`

| Turn | Fallbacks | Provider errors | Graded | Expected |
|---|---|---|---|---|
| absent_address | 0 | 0 | 5 | 5 |
| absent_pet | 4 | 0 | 5 | 5 |
| corrected_age_active_fact | 5 | 0 | 5 | 5 |
| corrected_species_active_fact | 0 | 0 | 5 | 5 |
| identified_person_second_person | 4 | 0 | 5 | 5 |
| multiple_active_facts | 4 | 0 | 5 | 5 |
| old_history_vs_active_fact | 5 | 0 | 5 | 5 |
| persisted_context_after_restart | 0 | 0 | 5 | 5 |
| public_1 | 0 | 0 | 5 | 5 |
| public_10 | 0 | 0 | 5 | 5 |
| public_11 | 0 | 0 | 5 | 5 |
| public_12 | 0 | 0 | 5 | 5 |
| public_2 | 0 | 0 | 5 | 5 |
| public_3 | 0 | 0 | 5 | 5 |
| public_4 | 1 | 0 | 5 | 5 |
| public_5 | 0 | 0 | 5 | 5 |
| public_6 | 0 | 0 | 5 | 5 |
| public_7 | 0 | 0 | 5 | 5 |
| public_8 | 0 | 0 | 5 | 5 |
| public_9 | 0 | 0 | 5 | 5 |
| resolved_face_enrollment | 4 | 0 | 5 | 5 |
| resolved_face_recognition | 4 | 0 | 5 | 5 |
| semantic_distractor_ignored | 1 | 0 | 5 | 5 |
| two_children_names | 0 | 0 | 5 | 5 |

Turns with at least one fallback: 9 of 24; that fell back in every expected run: 2; incomplete turns: 0.

## 5. Timing (ms)

| Variant | Outcome | n | First delta | Speech start | End |
|---|---|---|---|---|---|
| full | valid | 88 | 1205 / 2121 | 4157 / 8452 | 5288 / 13123 |
| full | fallback | 32 | 1268 / 1643 | 4315 / 15049 | 4315 / 15049 |
| full_repeat | valid | 87 | 1104 / 1658 | 3269 / 7601 | 4888 / 10874 |
| full_repeat | fallback | 33 | 1245 / 1648 | 4323 / 10365 | 4323 / 10365 |
| no_context | valid | 50 | 1211 / 3324 | 3898 / 8978 | 6555 / 11113 |
| no_context | fallback | 10 | 1104 / 3627 | 3799 / 11671 | 3799 / 11671 |
| no_person | valid | 2 | 532 / 1220 | 1427 / 2552 | 1502 / 3718 |
| no_person | fallback | 3 | 1147 / 1226 | 3788 / 4733 | 3788 / 4733 |
| no_history | valid | 2 | 1154 / 1195 | 2412 / 2779 | 2550 / 2972 |
| no_history | fallback | 3 | 1227 / 1254 | 4074 / 4587 | 4074 / 4587 |
| question_only | valid | 10 | 1031 / 1506 | 2469 / 5336 | 3419 / 7170 |
| contract_first | fallback | 120 | 1212 / 2979 | 5346 / 15157 | 5346 / 15157 |
| public_with_context | valid | 54 | 1216 / 1494 | 3706 / 7283 | 5790 / 12442 |
| public_with_context | fallback | 6 | 1148 / 1205 | 6515 / 10529 | 6515 / 10529 |

p50 / p95 by the nearest-rank method. Speech start is when production would hand its first sentence, or the fallback, to TTS (TTS time excluded).

## 6. Execution order

Quarters of the shuffled execution order, all variants together: it describes the experiment, not the baseline.

| Quarter | Fallback rate |
|---|---|
| Q1 | 41.60 % |
| Q2 | 42.40 % |
| Q3 | 44.00 % |
| Q4 | 37.60 % |

No order effect above the rule.

## 7. Prompt size (characters sent)

| Variant | Min | Mean | Max |
|---|---|---|---|
| full | 2822 | 2884 | 3173 |
| full_repeat | 2822 | 2884 | 3173 |
| no_context | 2819 | 2863 | 3100 |
| no_person | 2890 | 2890 | 2890 |
| no_history | 2895 | 2895 | 2895 |
| question_only | 2817 | 2826 | 2835 |
| contract_first | 2822 | 2884 | 3173 |
| public_with_context | 2877 | 2905 | 2960 |

## 8. Stream arrival probe

The probe sees the chunks as this client received them. It cannot tell a reply that Ollama withheld from fast generation, from buffering or from the client's own reading, so a burst never proves the `llm_streaming.py` header; only a spread-out arrival of the schema-constrained reply is evidence against it.

### Schema-constrained

| Run | Status | Chunks | Paced gaps / gaps | Pattern |
|---|---|---|---|---|
| 1 | complete | 97 | 96/96 | incremental |
| 2 | complete | 125 | 124/124 | incremental |
| 3 | complete | 99 | 98/98 | incremental |
| 4 | complete | 115 | 114/114 | incremental |
| 5 | complete | 97 | 96/96 | incremental |

Complete runs: 5 of 5; provider errors: 0; incomplete: 0; off schema: 0. Verdict: incremental.

### Plain-text control

| Run | Status | Chunks | Paced gaps / gaps | Pattern |
|---|---|---|---|---|
| 1 | complete | 98 | 97/97 | incremental |
| 2 | complete | 102 | 101/101 | incremental |
| 3 | complete | 111 | 110/110 | incremental |
| 4 | complete | 100 | 99/99 | incremental |
| 5 | complete | 100 | 99/99 | incremental |

Complete runs: 5 of 5; provider errors: 0; incomplete: 0; off schema: 0. Verdict: incremental.

Reading: The schema-constrained reply reached this client spread over time, which is compatible with incremental generation: streaming with a JSON schema is a candidate protocol and this is evidence against the `llm_streaming.py` claim that Ollama withholds it, though a client cannot see when generation ended.
