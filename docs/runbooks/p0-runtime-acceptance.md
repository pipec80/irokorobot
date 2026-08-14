# P0 Runtime Acceptance Runbook

> **Status:** Draft acceptance contract — this runbook becomes executable only
> after the implementation plan derived from
> [Plan 0012](../plans/0012-p0-runtime-acceptance-design.md) is merged.

## Purpose

Validate P0 through the real local server and robot. A green pytest run is
necessary but insufficient: an incorrect response in this runbook is a failed
P0 acceptance, even if automated checks pass.

## Safety boundary

- Use a disposable local acceptance database only. Do not run this against a
  household database with real data.
- Keep the server loopback-bound and `ROBOT_STREAMING=false`.
- Do not use a voice phrase, name, face, or HTTP field as identity proof.
- The manual acceptance session is temporary; clear it after testing.

## Existing commands

These commands already exist. The future implementation adds the documented
acceptance bootstrap/session commands before this runbook is marked Ready.

```powershell
just reset-db
just services
just run-server
just run-robot
```

## Acceptance procedure after implementation

1. Stop all server instances, then run `just reset-db`. Record the backup path
   and confirm the next server startup applies migrations 1 through 5.
2. Start local models with `just services`. Confirm required local models are
   available.
3. Start the acceptance interview mode using the final documented local-only
   bootstrap command. It must refuse non-loopback binding and must identify the
   disposable database in its output.
4. In another terminal run `just run-server`, then `just run-robot`.
5. Complete Iroko's interview with known values. Use this fixed acceptance
   household:

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
