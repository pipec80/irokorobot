# P0 runtime policy hardening design

> **Status:** Open umbrella, partially implemented. P0-C1 through P0-C6 are
> implemented. The 2026-08-17 operator run found three runtime blockers;
> remediation is designed in
> [Plan 0020](0020-p0-operator-qa-remediation-design.md). The silent-streaming
> blocker (C6) is closed and operator-confirmed on 2026-08-20 — see [Plan
> 0022](../completed/0022-p0-reliable-streaming-output.md#execution-evidence).
> Intent (C5) is closed and operator-confirmed on 2026-08-21 — see [Plan
> 0021](../completed/0021-p0-typed-intent-resolution.md#execution-evidence).
> Visual-grounding (C7) remains open.

## Current slice disposition

| Slice | State | Do not rebuild | Still required |
|---|---|---|---|
| C1 | Implemented by Plan 0016 | Streaming/controller parity | Preserve as regression coverage |
| C2 | Implemented by Plan 0017 | Vision/controller parity | Preserve while grounding C7 |
| C3 | Implemented by Plan 0018 | Client-test WAV normalization | Preserve audio contract |
| C4 | Implemented by Plan 0019 | Bounded protected-request wording | Extend through C5; do not replace policy |
| C5 | Complete in Plan 0021 | Typed resolver, reviewed corpus, controller injection | Revalidate only |
| C6 | Complete in Plan 0022 | Audible fallback and terminal stream rules | Revalidate only |
| C7 | Not implemented as Plan 0023 | Scene/VLM transport and vision parity already exist | Ground the response and remove duplicate trigger authority |

The umbrella remains under `open/` because C7 and the final combined
operator run are still required. Its completed slices are historical evidence,
not work to repeat.

## Objective

Close the remaining gap between P0's tested controller/policy foundation and
the actual public local runtime. Every enabled public conversation route must
enforce the same fail-closed boundary before P0 can be operator-accepted.

## Inputs

- [P0 runtime policy audit](../../architecture/p0-runtime-policy-audit.md)
- [P0 runtime acceptance design](../completed/0012-p0-runtime-acceptance-design.md)
- [Voice controller bridge](0013-p0-voice-controller-bridge.md)
- [Implementation guardrails](../../architecture/implementation-guardrails.md)

## Invariants

- Preserve WAV, JSON, NDJSON, image, server/robot, and local-first contracts.
- Do not infer identity from text, a name, a face, or a voice.
- Do not retrieve protected v4 or legacy data, create a memory write, or call a
  provider before policy permits it.
- Do not turn an LLM into an authorization classifier.
- Do not implement R2 trusted sessions, biometrics, family onboarding, a UI,
  or P1 while closing P0.

## Required bounded slices

### P0-C1 — Streaming policy parity

Revalidate the streaming contract and introduce the smallest adapter that
applies controller decisions to `/transcribe/stream`. Deterministic and denied
outcomes must stream without legacy generation; generic allowed text must
preserve NDJSON event order and TTS behaviour. Tests must prove date routing,
protected denial, audit output, and no v4 reader call.

The revalidated slice is [Plan 0016](../completed/0016-p0-streaming-controller-parity.md).

### P0-C2 — Visual dialogue policy parity

Keep scene perception local and ephemeral, but place the subsequent visual
question behind an equivalent controller/policy boundary. A scene description
is not identity evidence, authorization, or durable memory. Until the boundary
exists, the P0 runbook must require `VISION_ENABLED=false`.

The revalidated slice is [Plan 0017](../completed/0017-p0-vision-controller-parity.md).

### P0-C3 — Audio QA contract

Make `scripts/client_test.py --text` inspect and normalize its generated WAV
to the existing 16 kHz, mono, int16 contract before POSTing it. A
nonconforming Piper voice must produce a deterministic local error or a valid
converted WAV; never a misleading server 422. Add focused script-level tests
without changing the robot client contract.

The revalidated slice is [Plan 0018](../completed/0018-p0-client-test-audio-contract.md).

### P0-C4 — Bounded protected-request recognition

Document a limited Spanish protected-request vocabulary and explicit ambiguity
behaviour. Add realistic STT variants for relationship, birth-date, child, and
spouse questions. When text plausibly requests protected data but cannot be
classified safely, ask for clarification rather than silently use a date prompt
or family retrieval. Ordinary unrelated conversation remains available.

The revalidated slice is [Plan 0019](../completed/0019-p0-protected-request-recognition.md).

## Verification required for the final Ready plans

1. Observed RED/GREEN coverage for each changed adapter.
2. HTTP integration tests for classic audio, streaming audio, and enabled visual
   dialogue.
3. Disposable-DB assertions that denied requests create safe audit metadata but
   never retrieve protected values or persist them.
4. `just lint`, `just typecheck`, `just test`, `just audit`, `just check`
   on a feature branch, and `git diff --check`.
5. A recorded operator run using `just services`, `just run-server`, and
   `just run-robot`; record literal STT text, response text, audible output,
   route, and pass/fail.

## Stop conditions

Stop for an ADR or explicit approval if parity requires changing a public
contract, a new global identity mechanism, a schema migration, cloud
processing, or a general agent/orchestration framework.
