# Streaming protocol measurement

- model: qwen2.5:3b
- runs per turn: 3
- graded observations: 108
- fallback rate (invalid protocol + empty stream, over graded): 0.00 %
- replies not in Spanish (word-list heuristic, replies it could judge): 0 of 98

| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate | Not in Spanish |
|---|---:|---:|---:|---:|---:|---:|
| all | 108 | 0 | 0 | 0 | 0.00 % | 0 of 98 |
| context | 36 | 0 | 0 | 0 | 0.00 % | 0 of 30 |
| history | 36 | 0 | 0 | 0 | 0.00 % | 0 of 33 |
| public | 36 | 0 | 0 | 0 | 0.00 % | 0 of 35 |
