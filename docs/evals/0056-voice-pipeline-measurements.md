# Voice-pipeline measurements (Plan 0056, Task 7)

> **Status:** Historical measurement, recorded 2026-10-02. Numbers only: no
> transcript, no model output and no name appear here. The decision rules were
> written in [Plan 0056](../plans/completed/0056-voice-pipeline-reliability-and-diagnostics.md#decisions)
> (D-5, D-6) **before** the runs.

## Conditions

| Item | Value |
|---|---|
| Date | 2026-10-02 |
| Commit | streaming measurement at `1b4707a`; STT probes at `76a4ae3` (the code the probes use did not change between them) |
| Machine | non-dedicated development laptop, Whisper `small`, chat model `qwen2.5:3b`; Ollama running, server stopped |
| Who ran it | Pipec, locally; the executor recorded only the printed numbers |

## 1. Streaming protocol fallback (0049 O-04)

Command: `just eval-chat --mode stream --runs 5 --output docs/evals/0056-stream-protocol-run1.md`
(raw report: [0056-stream-protocol-run1.md](0056-stream-protocol-run1.md)).

| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate |
|---|---:|---:|---:|---:|---:|
| all (120 observations) | 85 | 35 | 0 | 0 | **29.17 %** |
| context turns (60) | 26 | 34 | 0 | 0 | 56.67 % |
| public turns (60) | 59 | 1 | 0 | 0 | 1.67 % |

Rule D-5: a fallback rate above 5 % opens a follow-up plan; 3 % to 8 % would be
repeated with `--runs 10`. **29.17 % is above 5 % and outside the repeat band, so
the follow-up is opened and no second run is needed.** Nothing was repaired in this
plan (the fallback code is read-only here).

What the split does and does not say: the fallback is concentrated in the turns that
carry golden memory context (56.67 %) and almost absent in context-free chit-chat
(1.67 %). The measurement does not say why. The follow-up plan should start from that
split, not from a guess.

## 2. Prompt echo and hallucination on synthetic noise

Command: `just probe-stt noise --clips 100` (the probe reads the raw transcript,
before the echo guard).

| Clips | Empty | Echo | Other | Other rate | Follow-up |
|---:|---:|---:|---:|---:|---|
| 100 | 100 | 0 | 0 | 0.000 | no |

Rule D-6: more than 5 % of clips with a non-empty, non-echo transcript opens a
hallucination-filter plan. **0 % is not above 5 %: closed with measured rate 0 %.**
The synthetic noise did not reproduce the prompt echo Pipec heard four times, so this
run says nothing about the guard's hit rate; it only shows Whisper stays silent on this
kind of noise.

## 3. First utterance after a restart

Command: `just probe-stt first-turn --processes 5 --rounds 3` (five fresh processes,
three Piper-synthesized phrases, three rounds in rotated order).

| First-call mean WER | Same phrase later, mean WER | Paired difference | Mean WER over every call | Follow-up | Accuracy flag |
|---:|---:|---:|---:|---|---|
| 0.150 | 0.150 | 0.000 | 0.200 | no | no |

Rule D-6: a paired difference above 0.15 opens a Whisper warm-up plan; the accuracy
flag (mean above 0.25) never opens one by itself. **0.000 is not above 0.15: closed
with a measured difference of 0.000, and the accuracy flag is not raised (0.200).**

## Decisions

| Rule | Measured | Outcome |
|---|---|---|
| D-5 streaming fallback | 29.17 % (35 of 120) | **Follow-up plan opened** (roadmap row, no number yet) |
| D-6 hallucination filter | 0 % of 100 noise clips | Closed |
| D-6 Whisper warm-up | paired difference 0.000 | Closed |

## Limitations

- Synthetic noise is a proxy for the robot's room; it did not reproduce the echo.
- The first-turn probe isolates STT from the server's other start-up work and uses
  Piper speech, not Pipec's voice. The roadmap's criterion (the first utterance after a
  restart is transcribed correctly) is judged in the real acceptance session.
- 120 observations give a wide interval, and the context turns are 60 golden cases
  repeated five times, not 60 independent conversations.
- The thresholds are decision rules agreed in advance, not proof of general
  reliability.
