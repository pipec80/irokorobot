# Personal companion delivery map

> **Status:** Canonical cross-plan traceability map.
>
> **Observed:** 2026-08-20 on branch `docs/personal-family-profiles` at
> `9b699de`, plus the current documentation-only worktree.
>
> **Execution authority:** None. This map explains what exists, what is
> missing, and which bounded plan owns each gap. Only the single `NOW` item in
> the [plan router](../plans/README.md) may be considered for execution, and
> only after explicit user approval.

## North-star outcome

The first personal-companion proof is complete only when the real local path
can demonstrate both sides of the same privacy boundary:

```text
fresh authenticated Pipec
  -> “¿Quiénes son mis hijos?”
  -> authorized structured retrieval
  -> “Tus hijos son Máximo y Dominga.”
  -> audible Piper output

no fresh authentication
  -> the same question
  -> non-disclosing denial before protected retrieval
  -> no names, count, hint, or confirmation that the data exists
```

This result is not documentary RAG. The answer comes from the existing typed
v4 relationship/tool path after identity, authentication, and authorization
have succeeded. RAG remains a later memory-retrieval capability.

## Locked-posture invariant

Without fresh authentication, Iroko remains able to perceive, transcribe,
converse generally, and speak, but the actor is `unknown`: protected memory is
not read or mutated, unknown statements are not attached to Pipec, and
protected tools do not execute. A denial explains that the speaker cannot be
confirmed without revealing whether the requested fact exists.

Authentication is capability-scoped rather than a global unlock. Plans
0025–0028 create and accept only one consume-once
`personal_protected_read`/`child_data` grant. Home control, PC restart,
biometric administration, memory mutation, and actuators require future,
separately authorized capabilities and are not implied by this delivery chain.
See [ADR 0009](../adr/0009-locked-posture-and-scoped-capabilities.md).

## How the open reference documents fit

These documents describe the program but are not independent implementation
batches:

| Reference | Role | Implemented content it preserves | Open outcome it governs |
|---|---|---|---|
| [0014](../plans/open/0014-p0-runtime-policy-hardening-design.md) | P0 runtime-policy umbrella | C1–C4 and C6 | C5, C7, and combined P0 acceptance |
| [0015](../plans/open/0015-personal-companion-design.md) | Product direction | Reuse of the existing local cognitive/audio/memory foundations | Personal-companion stages PC-1 through PC-6 |
| [0020](../plans/open/0020-p0-operator-qa-remediation-design.md) | Operator-QA defect umbrella | C6 via completed Plan 0022 | C5 via 0021 and C7 via 0023 |
| [0024](../plans/open/0024-owner-authenticated-memory-mvp-design.md) | PC-1 integration design | Existing identity, policy, child-memory, and channel seams | Executable delivery through 0025–0028 |

Do not execute these four documents from top to bottom. Their job is to retain
decisions and acceptance boundaries while the smaller plans deliver the gaps.

## Code-to-outcome traceability

Evidence priority is executable code, tests, configuration, then
documentation. “Implemented” below means the named foundation exists; it does
not mean the north-star path is connected or accepted.

| Stage | Verified existing foundation | Existing tests | Verified gap | Accountable plan |
|---|---|---|---|---|
| Audio ingress and STT | [`routers/transcribe.py`](../../server/src/server/routers/transcribe.py) creates the classic typed event and preserves the WAV contract | [`test_transcribe_pipeline.py`](../../tests/integration/test_transcribe_pipeline.py), [`test_transcribe_validation.py`](../../tests/integration/test_transcribe_validation.py) | Real STT accuracy remains operator evidence, not a component-test claim | [0028](../plans/open/0028-owner-authenticated-memory-runtime-acceptance.md) |
| Owner and household setup | Owner bootstrap and v4 relationship repositories exist; legacy [`onboarding.py`](../../server/src/server/onboarding.py) separately exposes the v3 eight-slot checklist | [`test_household_authorization_schema.py`](../../tests/integration/test_household_authorization_schema.py), [`test_onboarding_checklist.py`](../../tests/integration/test_onboarding_checklist.py) | No minimal owner/children/PIN setup flow; migrations stop at 005; v3 onboarding cannot verify v4 setup | [0025](../plans/open/0025-personal-owner-bootstrap-and-pin-setup.md) |
| Typed identity evidence | [`cognition/identity.py`](../../server/src/server/cognition/identity.py) defines evidence/context/resolution; [`identity_sessions.py`](../../server/src/server/cognition/identity_sessions.py) provides expiring manual evidence | [`test_active_person_identity.py`](../../tests/unit/test_active_person_identity.py), [`test_identity_sessions.py`](../../tests/unit/test_identity_sessions.py) | Current registry is process-local manual selection, not authenticated, request-bound, consume-once evidence | [0026](../plans/open/0026-one-use-owner-authenticated-classic-turn.md) |
| Channel actor resolution | Chat, classic audio, and vision already inject typed `ActivePersonContext` resolver seams in their routers | [`test_chat_endpoint.py`](../../tests/integration/test_chat_endpoint.py), [`test_transcribe_memory.py`](../../tests/integration/test_transcribe_memory.py), [`test_vision_dialog.py`](../../tests/integration/test_vision_dialog.py) | Public resolvers still return `unknown`; no PIN/token propagation exists in server or robot | [0026](../plans/open/0026-one-use-owner-authenticated-classic-turn.md), then [0027](../plans/open/0027-one-use-owner-streaming-parity.md) |
| Intent resolution | [`cognition/controller.py`](../../server/src/server/cognition/controller.py) owns the current inline information-need classifier and normalization | [`test_cognitive_controller.py`](../../tests/unit/test_cognitive_controller.py) plus route integration suites | No extracted typed resolver, supervised Spanish corpus, or C5 operator proof | [0021](../plans/open/0021-p0-typed-intent-resolution.md), after PC-1 |
| Authorization and audit | [`cognition/authorization.py`](../../server/src/server/cognition/authorization.py) evaluates deterministic policy; [`memory/household_authorization.py`](../../server/src/server/memory/household_authorization.py) writes safe audit metadata | [`test_household_authorization_policy.py`](../../tests/unit/test_household_authorization_policy.py), [`test_household_authorization_runtime.py`](../../tests/integration/test_household_authorization_runtime.py) | Public turns cannot yet supply fresh authenticated owner evidence | [0026](../plans/open/0026-one-use-owner-authenticated-classic-turn.md) |
| Structured child retrieval | [`household_tools.py`](../../server/src/server/cognition/household_tools.py) implements authorized `get_children` and `count_children`; [`policy_gated_v4_reader.py`](../../server/src/server/memory/policy_gated_v4_reader.py) authorizes before storage | [`test_household_knowledge_tools.py`](../../tests/unit/test_household_knowledge_tools.py), [`test_p05b2_household_acceptance.py`](../../tests/integration/test_p05b2_household_acceptance.py) | The working internal tool seam is unreachable from a fresh authenticated public owner turn | [0026](../plans/open/0026-one-use-owner-authenticated-classic-turn.md) |
| Audible response and streaming | Piper TTS is integrated; [`streaming_render.py`](../../server/src/server/streaming_render.py) owns C6 audible fallback and audio-before-`done` behavior | [`test_transcribe_stream.py`](../../tests/integration/test_transcribe_stream.py), [`test_transcribe_stream_resilience.py`](../../tests/integration/test_transcribe_stream_resilience.py) | Authenticated streaming parity and the full physical proof remain absent | [0027](../plans/open/0027-one-use-owner-streaming-parity.md), then [0028](../plans/open/0028-owner-authenticated-memory-runtime-acceptance.md) |
| Current visual dialogue | [`routers/vision.py`](../../server/src/server/routers/vision.py) has controller parity; [`vision/perception.py`](../../server/src/server/vision/perception.py) has scene and face adapters | [`test_vision_dialog.py`](../../tests/integration/test_vision_dialog.py), [`test_vision_endpoint.py`](../../tests/integration/test_vision_endpoint.py) | Typed visual preflight, direct grounded VLM-to-TTS, trigger migration, and physical acceptance remain open | [0023](../plans/open/0023-p0-grounded-visual-dialogue.md), after 0021 |

## Verified absent PC-1 artifacts

The 2026-08-20 audit found only migrations 002–005 and no production or test
symbol for the planned PIN hash, owner-unlock prompt, request authentication
header, or `authentication_consumed` result. These are genuine implementation
gaps owned by Plans 0025–0027, not hidden existing features.

Face recognition functions exist, but no consented runtime adapter converts a
face match into fresh authenticated request evidence. Speaker recognition is
absent; STT and VAD do not identify a speaker. Neither biometric path blocks
PC-1.

## One delivery chain

```text
NOW
0025 minimal owner/children/PIN security bootstrap
  -> 0026 one-use authenticated classic turn
  -> 0027 authenticated streaming parity
  -> 0028 physical allowed/denied/replay/expiry acceptance
       `-> execute and independently close 0013 R1 acceptance debt
  -> 0021 typed intent resolution
  -> 0023 grounded visual dialogue
```

Plans 0014, 0015, 0020, and 0024 remain open as reference until their governed
outcomes close. They do not create parallel work.

## Status transition protocol

After each executable plan:

1. Verify the merged code and tests rather than trusting the plan checklist.
2. Record exact commands, counts, commit SHA, and real-runtime evidence required
   by that plan.
3. Update [`current-state.md`](../architecture/current-state.md), this map, and
   the [operational board](../plans/README.md) in the same documentation change.
4. Move only the completed executable plan to `completed/`; never rewrite its
   evidence to describe later work.
5. Revalidate only the next plan's assumptions and interfaces.
6. Keep product, umbrella, and implementation status separate.

This protocol makes the repository—not chat history—the durable handoff for
humans and agents.
