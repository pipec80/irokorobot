# P0 Runtime Acceptance Runbook

> **Status:** P0-C public-route hardening is implemented in the current feature
> branch and automated gates are green. The first operator run on 2026-08-17
> confirmed policy denial and media paths but found intent, silent-streaming,
> and visual-grounding blockers documented in
> [Plan 0020](../plans/open/0020-p0-operator-qa-remediation-design.md). The
> silent-streaming blocker is closed: [Plan
> 0022](../plans/completed/0022-p0-reliable-streaming-output.md) passed a 2026-08-20
> real operator rerun (case C1-S below) with zero silent successes across 4
> live turns, including a live reproduction of the original hybrid-output
> failure ending in an audible fallback. Intent (C5, Plan 0021) and
> visual-grounding (C7, Plan 0023) remain open; P0 acceptance still requires
> their remediation and a combined clean rerun. Personal identity/session acceptance is P1 work under
> [Plan 0015](../plans/open/0015-personal-companion-design.md), not an unfinished
> P0 requirement.

## Purpose

Validate P0 through the real local server and robot. A green pytest run is
necessary but insufficient: an incorrect response in this runbook is a failed
P0 acceptance, even if automated checks pass.

## Safety boundary

- Use a disposable local acceptance database only. Do not run this against a
  household database with real data.
- Keep the server loopback-bound. For the first audio checkpoint use
  `ROBOT_STREAMING=false` and `VISION_ENABLED=false` to isolate the classic
  route. Controller/policy parity now also exists for streaming and visual
  dialogue; those settings are no longer a security workaround.
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
Those records remain protected until a future P1 personal-companion flow creates
and validates a separate trusted local session.

## P0-C supplementary route checks

After the R1 audio checkpoint, use the same disposable database and loopback
server. These checks complete public-route and QA-tool evidence; they do not
create a trusted identity or household data.

| ID | Setup | Action | Required result |
|---|---|---|---|
| C1-S | `ROBOT_STREAMING=true`, `VISION_ENABLED=false` | Speak “¿Qué día es hoy?”, “¿Cómo se llaman mis hijos?”, then “Hola, Iroko.” through `just run-robot`. | Deterministic date, non-disclosing denial, then normal streamed generic audio; record literal STT and output. **PASS 2026-08-20** (commit `1927912`, 4 live turns): non-disclosing denial confirmed with `llm_ms=0`; a generic turn and a live hybrid-protocol failure both ended audibly (`outcome=ok` and `outcome=protocol_fallback` respectively, never silent); the date question fell through to the LLM instead of the deterministic tool — expected, C5 intent resolution (Plan 0021) is not yet implemented on this branch. Full transcripts kept in a local untracked operator note per this runbook's own instruction, not in this tracked file. |
| C2-V | `ROBOT_STREAMING=false`, `VISION_ENABLED=true` | Ask “Iroko, ¿qué ves?” through `just run-robot` with the PC webcam available. | Cue then an audible scene description of the current frame; it must not identify a person, disclose family data, or enroll a face. |
| C3-Q | Server running, no microphone required | Run `just test-client --text "Hola Iroko" --no-play`. | Request reaches `/transcribe` and does not fail with `422 ... got 22050 Hz`; record actual STT and response. |
| C4-A | Any public audio route | If STT shows “¿Qué día soy?”, record the literal text and response. | Fixed clarification; no fabricated date and no family information. |

For every case record the command, effective non-secret settings, literal STT
text, response, audible output, route, and pass/fail. Stop and file a defect
on any mismatch; do not reinterpret a near miss as a pass.

## Separate P1.1 personal acceptance (not implemented)

P1.1 is not a P0 closure step. Its old illustrative session procedure has been
superseded by the owner-approved design in
[Plan 0024](../plans/open/0024-owner-authenticated-memory-mvp-design.md) and the
bounded executable sequence:

1. [Plan 0025](../plans/open/0025-personal-owner-bootstrap-and-pin-setup.md) creates
   Pipec, confirms Máximo and Dominga, and stores only a PIN verifier;
2. [Plan 0026](../plans/open/0026-one-use-owner-authenticated-classic-turn.md) proves
   the one-use classic `/chat` and `/transcribe` paths;
3. [Plan 0027](../plans/open/0027-one-use-owner-streaming-parity.md) adds equivalent
   streaming behavior;
4. [Plan 0028](../plans/open/0028-owner-authenticated-memory-runtime-acceptance.md)
   defines the recoverable database setup, commands, repeated spoken cases,
   audit checks, and evidence record.

Until those plans are implemented and Plan 0028 passes, no active owner
session or personal runtime acceptance may be claimed. The fixed future
product cases are:

| ID | Preconditions | Spoken phrase | Required result |
|---|---|---|---|
| P1-PUBLIC | No fresh one-use grant | “¿Quiénes son mis hijos?” | Non-disclosing denial; no names, count, existence hint, or protected read. |
| P1-ALLOW | Fresh Pipec grant | “¿Quiénes son mis hijos?” | Exactly “Tus hijos son Máximo y Dominga.” through Piper. |
| P1-REPLAY | Already consumed grant | Same protected question | Non-disclosing denial; no protected read. |
| P1-EXPIRED | Expired unused grant | Same protected question | Non-disclosing denial; no protected read. |
| P1-GENERIC | Fresh grant, then generic question | “¿Qué día es hoy?” followed by the protected question | Generic turn does not consume the grant; the next protected turn consumes it once. |

Permitted family reads must preserve the documented policy/tool audit order.
Denied cases must not produce `read_household_data`, and audit metadata must
not contain names, PIN material, tokens, birth dates, preferences, or derived
family values.

## Completion record

For each run, record in a local, untracked operator note:

- date/time, commit SHA, Windows machine, Python version, and model names;
- database reset backup path, without copying household data;
- each case ID, exact STT transcript, response text, audible result, and pass/fail;
- session expiry/clear result and audit action order;
- latency observations for STT, controller, LLM, TTS, and total turn;
- deviations, failures, and the issue/PR that resolves them.

Do not mark P0 runtime-accepted until the P0-C public-route slices and their
R1/C1-S/C2-V/C3-Q operator cases pass on a clean database with matching
automated/CI gates.
The deferred P1 cases are a separate personal-companion acceptance gate.
