# P0 Runtime Acceptance Runbook

> **Status:** Classic R1 bridge is implemented, but P0 operator acceptance is
> blocked by the public-route gaps in
> [Plan 0014](../plans/0014-p0-runtime-policy-hardening-design.md). R2
> personal-data acceptance remains a draft.

## Purpose

Validate P0 through the real local server and robot. A green pytest run is
necessary but insufficient: an incorrect response in this runbook is a failed
P0 acceptance, even if automated checks pass.

## Safety boundary

- Use a disposable local acceptance database only. Do not run this against a
  household database with real data.
- Keep the server loopback-bound, `ROBOT_STREAMING=false`, and
  `VISION_ENABLED=false` until Plan 0014 supplies controller/policy parity for
  streaming and visual dialogue.
- Do not use a voice phrase, name, face, or HTTP field as identity proof.
- The manual acceptance session is temporary; clear it after testing.

## Existing commands

These commands already exist. R2 will add bounded local-only interview and
session commands; do not invent or use them during R1.

```powershell
just reset-db
just services
just run-server
just run-robot
```

## R1 manual checkpoint: controller bridge without identity

Do this only after the R1 branch or its merged commit has passed the automated
gates. No reset database, owner data, enrollment, name, face, or session is
needed for this checkpoint.

1. Confirm `ROBOT_STREAMING=false` and `VISION_ENABLED=false`, then run
   `just services`.
2. In one terminal run `just run-server`.
3. In another terminal run `just run-robot`.
4. Speak each phrase once and record the displayed STT transcript, the returned
   response text, whether Piper audibly said the same result, and pass/fail:

   | ID | Spoken phrase | Required result |
   |---|---|---|
   | R1-01 | “¿Qué día es hoy?” | `Hoy es YYYY-MM-DD.` for the local date; no age, child count, or family data. |
   | R1-02 | “¿Cómo se llaman mis hijos?” | The non-disclosing authorization denial; no child name or other household value. |
   | R1-03 | “Hola, Iroko.” | A normal generic response through STT, controller delegation, and Piper. |

5. Stop both processes. If STT hears a materially different phrase, record the
   actual transcript as a runtime acceptance failure; do not reinterpret it as
   a pass. If any answer is routed to the wrong capability, R1 is not complete
   even when pytest is green.

R1 does **not** authorize reading any existing legacy or v4 household data.
Those records remain protected until R2 creates a separate trusted local
session and its acceptance cases pass.

## R2 personal acceptance procedure (not implemented)

1. Stop all server instances, then run `just reset-db`. Record the backup path
   and confirm the next server startup applies migrations 1 through 5.
2. Start local models with `just services`. Confirm required local models are
   available.
3. Start the acceptance interview mode using the final documented local-only
   bootstrap command. It must refuse non-loopback binding and must identify the
   disposable database in its output.
4. In another terminal run `just run-server`, then `just run-robot`.
5. Complete Iroko's interview with disposable known values. This is a personal
   acceptance profile, not family onboarding:

   | Field | Value |
   |---|---|
   | Owner | Felipe |
   | Children | Máximo, Sofía |
   | Máximo birth date | 2017-12-29 |
   | Sofía birth date | 2019-06-15 |
   | Owner preferences | café, robótica |

6. Listen to Iroko's summary. It must describe pending candidates rather than
   claim durable confirmation.
7. Perform the final local operator confirmation with the final documented
   command. Record the generated session expiry time, but never copy the
   opaque token into this runbook, source control, or logs.
8. Start the robot with that temporary local session and speak each case below.
   Record the STT transcript, returned response text, audible result, and audit
   action sequence.

## Required cases

| ID | Preconditions | Spoken phrase | Pass condition |
|---|---|---|---|
| R1-01 | No session | “¿Qué día es hoy?” | A date response; no age/family claim. |
| R1-02 | No session | “¿Cómo se llaman mis hijos?” | No protected value; no v4 read audit. |
| R2-01 | Confirmed active session | “¿Cómo se llaman mis hijos?” | “Máximo” and “Sofía” only if both were confirmed. |
| R2-02 | Confirmed active session | “¿Cuántos hijos tengo?” | `2`, derived from active v4 relations. |
| R2-03 | Confirmed active session | “¿Qué día es hoy?” | Date response; never child count or age. |
| R2-04 | Confirmed active session | “¿Qué hora es?” | Safe unavailable/unknown response until a time tool exists. |
| R2-05 | Session cleared or expired | “¿Cuántos hijos tengo?” | No protected value; no v4 read audit. |

For permitted family reads, audit actions must appear in this order:

```text
execute_household_tool
read_household_data
```

Denied cases must not produce `read_household_data`, and audit metadata must
not contain names, birth dates, preference values, or calculated ages.

## Completion record

For each run, record in a local, untracked operator note:

- date/time, commit SHA, Windows machine, Python version, and model names;
- database reset backup path, without copying household data;
- each case ID, exact STT transcript, response text, audible result, and pass/fail;
- session expiry/clear result and audit action order;
- latency observations for STT, controller, LLM, TTS, and total turn;
- deviations, failures, and the issue/PR that resolves them.

Do not mark P0 runtime-accepted until every required case passes on a clean
database and the matching automated/CI gates are green.
