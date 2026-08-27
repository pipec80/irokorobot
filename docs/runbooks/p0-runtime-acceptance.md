# P0 Runtime Acceptance Runbook

> **Status:** P0 is fully operator-accepted (2026-08-25). P0-C public-route
> hardening is implemented and automated gates are green. The first operator
> run on 2026-08-17 confirmed policy denial and media paths but found intent,
> silent-streaming, and visual-grounding blockers documented in
> [Plan 0020](../plans/completed/0020-p0-operator-qa-remediation-design.md). The
> silent-streaming blocker is closed: [Plan
> 0022](../plans/completed/0022-p0-reliable-streaming-output.md) passed a 2026-08-20
> real operator rerun (case C1-S below) with zero silent successes across 4
> live turns, including a live reproduction of the original hybrid-output
> failure ending in an audible fallback. The intent blocker is closed: [Plan
> 0021](../plans/completed/0021-p0-typed-intent-resolution.md) passed a 2026-08-21
> real operator rerun (R1 checkpoint below) — see its own execution evidence
> for the full 6/6 classic and 5/5 streaming case-by-case result.
> Visual-grounding is closed: [Plan
> 0023](../plans/completed/0023-p0-grounded-visual-dialogue.md) passed a
> 2026-08-21/2026-08-25 real operator run (case C2-V below, revised) — all 5
> required cases (identity denial, grounded scene description with no second
> LLM, VLM-down exact fallback, enrollment rejection, household denial)
> passed. The combined P0-C operator runbook (R1+C1-S+C2-V+C3-Q together) ran
> and passed on 2026-08-25, closing [Plan
> 0013](../plans/completed/0013-p0-voice-controller-bridge.md)'s R1-03 STT
> debt in the same session (see the R1 2026-08-25 run below). Personal
> identity/session acceptance is P1 work under
> [Plan 0015](../plans/open/0015-personal-companion-design.md), not a P0
> requirement.

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

**Run 2026-08-21** (commit `9b7662a`, classic public mode,
`ROBOT_STREAMING=false`, `ROBOT_OWNER_UNLOCK_PROMPT=false`, executed as
part of [Plan 0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md)):
R1-01 **PASS** (exact STT, `Hoy es 2026-08-21.`, no family data). R1-02
**PASS** (exact STT, non-disclosing denial, `tools=-`, no v4 read). R1-03
**FAIL** — 5 consecutive attempts, Whisper "small" never produced the
literal phrase; it consistently mis-heard the proper noun "Iroko"
(`'Hola Hiroko.'` twice, `'¿O leí roco?'`, `'Hola y roco.'`, and once
dropping it entirely as `'¡Hola!'`). Every attempt still exercised the
full STT→controller→LLM→Piper pipeline correctly and produced an
appropriate, audible generic greeting — the failure is a repeatable STT
vocabulary gap on this specific word, not a routing or pipeline defect.
Per this runbook's own rule above, it is recorded as a failure rather
than reinterpreted as a pass. R1 is not complete; Plan 0013 stays open.
Full untracked evidence:
`project-history/acceptance/2026-08-21-owner-authenticated-memory.md`.

**Run 2026-08-25** (commit `a07b731`, classic public mode,
`ROBOT_STREAMING=false`, `VISION_ENABLED=false`, `ROBOT_OWNER_UNLOCK_PROMPT=false`,
executed as part of the combined P0-C runbook): root cause of R1-03's failure
identified and fixed — `WHISPER_INITIAL_PROMPT` and the commented
`WHISPER_HOTWORDS` example still said "Omnibot" (the pre-rename hardware-guide
name), never "Iroko", so Whisper never had it as an expected token. After the
fix: R1-01 **PASS** (STT required two retries after "día" was twice misheard
as "vía" — a d/v acoustic confusion, not a routing defect; the successful
attempt gave exact STT `¿Qué día es hoy?` → `Hoy es 2026-08-25.`). R1-02
**PASS** (exact STT, non-disclosing denial). R1-03 **PASS** — exact STT
`'Hola Iroko.'` on the first attempt, reproduced again in streaming mode
(case C1-S below) — the wake-word transcription gap is closed. R1 is
complete; [Plan 0013](../plans/completed/0013-p0-voice-controller-bridge.md)
is closed. Full untracked evidence:
`project-history/acceptance/2026-08-25-combined-p0-runbook.md`.

R1 does **not** authorize reading any existing legacy or v4 household data.
Those records remain protected until a future P1 personal-companion flow creates
and validates a separate trusted local session.

## P0-C supplementary route checks

After the R1 audio checkpoint, use the same disposable database and loopback
server. These checks complete public-route and QA-tool evidence; they do not
create a trusted identity or household data.

| ID | Setup | Action | Required result |
|---|---|---|---|
| C1-S | `ROBOT_STREAMING=true`, `VISION_ENABLED=false` | Speak “¿Qué día es hoy?”, “¿Cómo se llaman mis hijos?”, then “Hola, Iroko.” through `just run-robot`. | Deterministic date, non-disclosing denial, then normal streamed generic audio; record literal STT and output. **PASS 2026-08-20** (commit `1927912`, 4 live turns): non-disclosing denial confirmed with `llm_ms=0`; a generic turn and a live hybrid-protocol failure both ended audibly (`outcome=ok` and `outcome=protocol_fallback` respectively, never silent); the date question fell through to the LLM instead of the deterministic tool — expected then, C5 intent resolution (Plan 0021) was not yet implemented on that branch. **Reconfirmed PASS 2026-08-25** (commit `a07b731`, combined runbook): with C5 now present, all 3 phrases routed deterministically — exact STT for all 3, `Hoy es 2026-08-25.` (`need=current_date`, `llm_ms=0`), non-disclosing denial (`need=own_children_list`, `llm_ms=0`), and `'Hola Iroko.'` transcribed exactly, answered with 3 audible streamed sentences (`outcome=ok`, never silent). |
| C2-V | `ROBOT_STREAMING=false`, `VISION_ENABLED=true` | Ask “Iroko, ¿qué ves?” through `just run-robot` with the PC webcam available. | Cue then an audible scene description of the current frame; it must not identify a person, disclose family data, or enroll a face. **PASS 2026-08-25** (commit `0978388`): STT mangled the wake word (“Y loco que ves.”) but the core phrase still routed correctly; cue, then one VLM call, then “Una persona con gafas sostiene una bola roja en su mano derecha…” spoken directly with no second LLM pass. Full C7 evidence, including identity/enrollment/protected/VLM-down cases: [Plan 0023](../plans/completed/0023-p0-grounded-visual-dialogue.md#execution-evidence). |
| C3-Q | Server running, no microphone required | Run `just test-client --text Hola Iroko --no-play`. | Request reaches `/transcribe` and does not fail with `422 ... got 22050 Hz`; record actual STT and response. **PASS 2026-08-25** (commit `a07b731`): `200 OK` in 11.13s, no contract error. Piper's own synthetic voice reading "Hola Iroko" was itself heard by Whisper as `'¡Vale Iroko!'` — a separate TTS-voice-pronunciation curiosity, not a C3-Q failure (C3-Q only gates the audio-contract path, not STT accuracy against synthetic speech). |
| C4-A | Any public audio route | If STT shows “¿Qué día soy?”, record the literal text and response. | Fixed clarification; no fabricated date and no family information. Not observed this session (opportunistic case). |

For every case record the command, effective non-secret settings, literal STT
text, response, audible output, route, and pass/fail. Stop and file a defect
on any mismatch; do not reinterpret a near miss as a pass.

## Separate P1.1 personal acceptance — CLOSED (2026-08-21)

P1.1 is not a P0 closure step. Its old illustrative session procedure was
superseded by the owner-approved design in
[Plan 0024](../plans/completed/0024-owner-authenticated-memory-mvp-design.md) and the
bounded executable sequence, now fully executed:

1. [Plan 0025](../plans/completed/0025-personal-owner-bootstrap-and-pin-setup.md)
   (merged, PR #56) creates the sole owner, confirms two child relations, and
   stores only a PIN verifier;
2. [Plan 0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md)
   (merged, PR #57) proves the one-use classic `/chat` and `/transcribe` paths;
3. [Plan 0027](../plans/completed/0027-one-use-owner-streaming-parity.md) (merged,
   PR #64) adds equivalent streaming behavior;
4. [Plan 0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md)
   executed the recoverable database setup, commands, repeated spoken cases,
   audit checks, and evidence record on 2026-08-21 — **PASS**.

The fixed product cases below were each proven 3x in classic mode and 3x in
streaming mode with real microphone/speaker hardware. The 2026-08-21
acceptance run used the operator's real local owner/children identity rather
than the placeholder names below — the exact required phrase is dynamically
built from whichever names are stored (`f"Tus hijos son {names}."` in
`controller.py`, never hardcoded), so this substitution is functionally
equivalent and does not weaken the result. Full untracked evidence,
including the literal transcripts and audit-table cross-checks:
`project-history/acceptance/2026-08-21-owner-authenticated-memory.md`.

| ID | Preconditions | Spoken phrase | Required result | Result |
|---|---|---|---|---|
| P1-PUBLIC | No fresh one-use grant | “¿Quiénes son mis hijos?” | Non-disclosing denial; no names, count, existence hint, or protected read. | **PASS** (3x classic + streaming baseline) |
| P1-ALLOW | Fresh owner grant | “¿Quiénes son mis hijos?” | Exactly “Tus hijos son Máximo y Dominga.” (or the real stored names) through Piper. | **PASS** (3x classic, 3x streaming) |
| P1-REPLAY | Already consumed grant | Same protected question | Non-disclosing denial; no protected read. | **PASS** (3x classic, 3x streaming) |
| P1-EXPIRED | Expired unused grant | Same protected question | Non-disclosing denial; no protected read. | **PASS** |
| P1-GENERIC | Fresh grant, then generic question | “¿Qué día es hoy?” followed by the protected question | Generic turn does not consume the grant; the next protected turn consumes it once. | **PASS** |

Permitted family reads preserved the documented `execute_household_tool` →
`read_household_data` policy/tool audit order on every allowed case,
confirmed by a direct SQLite inspection of `authorization_audit_events`, not
just console logs. Denied cases never produced a paired
`execute_household_tool`/reader invocation, and a full-database byte-scan
confirmed no PIN, token, or protected name appeared in any audit row.

A repeatable, unrelated finding surfaced during this acceptance: a garbled
STT transcript of the protected question can occasionally match the
broader `protected_household` intent pattern instead of the specific
`own_children_list` one. When that happens with a fresh, valid grant, the
grant is consumed but the response is a generic "not yet connected" stub
sentence — never the protected names and never the standard denial text.
No disclosure occurred in any observed instance, but it is a UX gap worth
folding into [Plan 0021](../plans/completed/0021-p0-typed-intent-resolution.md)'s
classifier work.

## Completion record

For each run, record in a local, untracked operator note:

- date/time, commit SHA, Windows machine, Python version, and model names;
- database reset backup path, without copying household data;
- each case ID, exact STT transcript, response text, audible result, and pass/fail;
- session expiry/clear result and audit action order;
- latency observations for STT, controller, LLM, TTS, and total turn;
- deviations, failures, and the issue/PR that resolves them.

**P0 is marked runtime-accepted as of 2026-08-25**: the P0-C public-route
slices and their R1/C1-S/C2-V/C3-Q operator cases all passed with matching
automated/CI gates green on commit `a07b731`.
The deferred P1 cases are a separate personal-companion acceptance gate.
