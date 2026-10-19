# Streaming protocol measurement

- model: qwen2.5:3b
- runs per turn: 3
- graded observations: 108
- fallback rate (invalid protocol + empty stream, over graded): 0.00 %
- replies not in Spanish (word-list heuristic, replies it could judge): 1 of 97

| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate | Not in Spanish |
|---|---:|---:|---:|---:|---:|---:|
| all | 108 | 0 | 0 | 0 | 0.00 % | 1 of 97 |
| context | 36 | 0 | 0 | 0 | 0.00 % | 0 of 27 |
| history | 36 | 0 | 0 | 0 | 0.00 % | 0 of 34 |
| public | 36 | 0 | 0 | 0 | 0.00 % | 1 of 36 |
