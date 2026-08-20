# P0 runtime policy audit and disposition

> **Observed:** 2026-08-14
>
> **Code baseline:** `8e6d23f` on `main` at the start of review.
>
> **Disposition update:** On 2026-08-14, P0-C1 through P0-C4 were implemented
> in `docs/personal-family-profiles` with automated gates green. They remain
> unmerged and require the runbook's real operator acceptance.
>
> **Purpose:** distinguish current static evidence from reported runtime
> observations. This document does not replace the historical
> [`COGNITIVE_AUDIT.md`](../history/audits/COGNITIVE_AUDIT.md) snapshot.

## Executive verdict

The P0 foundation is implemented, but P0 operator acceptance is not complete.
At the audited `main` baseline, streaming and visual dialogue bypassed the
controller. The current feature worktree routes all enabled public conversation
paths through that boundary, normalizes the QA-script WAV, and expands bounded
protected wording. Real PC acceptance is still the remaining P0 exit gate.

No P1 implementation is authorized by this audit. The next executable work is
bounded P0 runtime-policy hardening, then the approved personal-companion
milestone.

## Evidence classification

| Finding | Classification | Current evidence | Required disposition |
|---|---|---|---|
| `/transcribe/stream` bypasses the controller. | Resolved in feature worktree; operator-confirmed 2026-08-20 | Baseline called `prepare_text_turn()` directly after STT. | C1 routes a typed event through `decide()` and renders safe plans without legacy generation. Plan 0022's real `just run-robot` run confirmed this live: a protected question returned `source=deterministic`, `llm_ms=0`, the non-disclosing denial, over `/transcribe/stream` — see [Plan 0022](../plans/completed/0022-p0-reliable-streaming-output.md#execution-evidence). |
| Narrow protected-intent classification misses ordinary family phrasings. | Resolved in feature worktree | Baseline missed terms such as `esposa` or `nació`. | C4 documents bounded fail-closed forms and the `qué día soy` clarification; real STT evidence remains pending. |
| `/vision/respond` bypasses the controller. | Resolved in feature worktree | Baseline called `process_text_turn()` directly after local scene perception. | C2 gives visual dialogue the controller boundary while preserving scene-only perception; operator camera evidence remains pending. |
| `client_test.py --text` does not enforce the audio contract. | Resolved in feature worktree | Baseline wrote Piper-native WAV without resampling or validating its header. | C3 reuses the local converter and validator; a real disposable-server invocation remains pending. |
| Public voice cannot become an owner. | Confirmed intended boundary | Public chat and classic voice adapters construct an `unknown` actor. | Preserve until the bounded local personal session exists. |
| Persisted roles are not wired into public identity. | Confirmed planned gap | `get_active_role()` and `IdentitySessionRegistry` exist, while public adapters use unknown actors. | Implement only in the approved personal-companion milestone; do not infer identity from text, face, or voice. |
| Prompt and deterministic paths both know the date. | Confirmed technical debt | `characters.current_date_es()` injects a date prompt while the controller has `get_current_date()`. | Remove the duplicate source when a focused compatibility plan proves no regression. |
| Runtime STT/LLM latency and exact spoken outcomes reported by an external audit. | Requires reproduction artifact | The reported harness, request payloads, logs, and model warm/cold state are not versioned. | Reproduce with a disposable DB and preserve a local run record before using numbers as an acceptance baseline. |
| Shared SQLite rollback/concurrency concern. | Requires focused reproduction | A single connection is visible in current code, but no failure interleaving was captured. | Create a narrow concurrency test only if P0-C touches those transactions. |

## Read-only production-data observation

The local `data/omnibot.db` was inspected read-only. It reports
`PRAGMA user_version = 3`; the v4/v5 tables are absent. Legacy predicate
counts include `edad:2`, `fecha_nacimiento:1`, `hijo_de:3`,
`le_gusta:2`, and `vive_en:1`.

This is not a migration authorization. Real-data migration remains a separate,
backup-first, dry-run-first decision. The personal acceptance flow begins on a
disposable database; legacy migration is considered only after it passes.

## P0 acceptance rules

- A green pytest run is necessary but never sufficient.
- A wrong live response through `just run-server` plus `just run-robot`
  fails acceptance even if all automated gates pass.
- An unknown speaker must receive general conversation but no protected
  household retrieval, prompt context, or durable write.
- Controller/policy coverage applies equally to every enabled public text,
  audio, streaming, and visual dialogue route.
- `just check` includes a branch-protection hook. A recorded green result is
  meaningful only from a non-`main` feature branch; it is not a claim that the
  same command should pass on `main`.

## Explicit non-conclusions

This audit does not prove a runtime data leak, a biometric recognition path, a
complete consent system, real-model latency, or readiness for the family UI. It
also does not reopen completed P0 foundation history; it records the work needed
to make that foundation demonstrable through the actual robot path.
