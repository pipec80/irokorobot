# Personal companion delivery map

> **Status:** Canonical cross-plan traceability map.
>
> **Observed:** 2026-08-21 on `main` after PR #56 (Plan 0025), PR #57
> (Plan 0026), and PR #64 (Plan 0027) merged, and Plan 0028's real-hardware
> runtime acceptance executed with a PASS verdict for the PC-1 slice.
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
| [0024](../plans/open/0024-owner-authenticated-memory-mvp-design.md) | PC-1 integration design | Existing identity, policy, child-memory, and channel seams; Plans 0025–0028 merged/executed | Delivery complete — PC-1 accepted |

Do not execute these four documents from top to bottom. Their job is to retain
decisions and acceptance boundaries while the smaller plans deliver the gaps.

## Code-to-outcome traceability

Evidence priority is executable code, tests, configuration, then
documentation. “Implemented” below means the named foundation exists; it does
not mean the north-star path is connected or accepted.

| Stage | Verified existing foundation | Existing tests | Verified gap | Accountable plan |
|---|---|---|---|---|
| Audio ingress and STT | [`routers/transcribe.py`](../../server/src/server/routers/transcribe.py) creates the classic typed event and preserves the WAV contract, and the streaming route now propagates identity too (Plan 0027) | [`test_transcribe_pipeline.py`](../../tests/integration/test_transcribe_pipeline.py), [`test_transcribe_validation.py`](../../tests/integration/test_transcribe_validation.py) | Real STT accuracy is confirmed with 3x recorded classic and 3x streaming hardware evidence (Plan 0028, 2026-08-21); a repeatable Whisper "small" mis-transcription of the proper noun "Iroko" and of the first utterance after each robot restart were found and are open follow-up items, not blockers | — |
| Owner and household setup | **Closed by [0025](../plans/completed/0025-personal-owner-bootstrap-and-pin-setup.md).** `just setup-personal` bootstraps the sole owner, confirms `child_of` v4 relations, and stores a scrypt-hashed PIN (migration 006, [`personal_setup.py`](../../server/src/server/personal_setup.py)) | [`test_personal_setup.py`](../../tests/integration/test_personal_setup.py), [`test_owner_credentials_schema.py`](../../tests/integration/test_owner_credentials_schema.py), [`test_pin_credentials.py`](../../tests/unit/test_pin_credentials.py) | None remaining for this stage | — |
| Typed identity evidence | **Closed by [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) and [0027](../plans/completed/0027-one-use-owner-streaming-parity.md).** `IdentityEvidenceSource.LOCAL_UNLOCK` and `IdentitySessionRegistry.issue_for_person`/`consume_evidence` give request-bound, authenticated, consume-once evidence in both classic and streaming modes ([`identity.py`](../../server/src/server/cognition/identity.py), [`identity_sessions.py`](../../server/src/server/cognition/identity_sessions.py)) | [`test_active_person_identity.py`](../../tests/unit/test_active_person_identity.py), [`test_identity_sessions.py`](../../tests/unit/test_identity_sessions.py) | None remaining | — |
| Channel actor resolution | **Closed for classic and streaming modes by [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) and [0027](../plans/completed/0027-one-use-owner-streaming-parity.md).** `X-Iroko-Identity-Token` is accepted by `/chat`, classic `/transcribe`, and `/transcribe/stream`; `OwnerRequestResolver` resolves the actor only for protected branches in every channel | [`test_owner_authenticated_turn.py`](../../tests/integration/test_owner_authenticated_turn.py), [`test_owner_unlock_endpoint.py`](../../tests/integration/test_owner_unlock_endpoint.py), [`test_owner_authenticated_stream.py`](../../tests/integration/test_owner_authenticated_stream.py) | None remaining | — |
| Intent resolution | [`cognition/controller.py`](../../server/src/server/cognition/controller.py) owns the current inline information-need classifier and normalization; Plan 0026 extended the `OWN_CHILDREN_LIST` trigger phrases to match the accepted north-star wording | [`test_cognitive_controller.py`](../../tests/unit/test_cognitive_controller.py) plus route integration suites | No extracted typed resolver, supervised Spanish corpus, or C5 operator proof; Plan 0028's acceptance also surfaced that a garbled STT phrase can match the broader `protected_household` pattern and consume a fresh grant without disclosing or denying cleanly (stub response) — worth folding into 0021's classifier work | [0021](../plans/open/0021-p0-typed-intent-resolution.md), now executable |
| Authorization and audit | **Closed by [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md).** Classic public turns can now supply fresh authenticated owner evidence before policy evaluation | [`test_household_authorization_policy.py`](../../tests/unit/test_household_authorization_policy.py), [`test_household_authorization_runtime.py`](../../tests/integration/test_household_authorization_runtime.py), [`test_owner_authenticated_turn.py`](../../tests/integration/test_owner_authenticated_turn.py) | None remaining for classic mode | — |
| Structured child retrieval | **Closed by [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) and [0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md).** The `household_tools.py` seam is reachable from a fresh authenticated owner turn end to end in both classic and streaming modes, with 3x repeated real-hardware evidence and a direct SQLite audit-trail inspection confirming `execute_household_tool → read_household_data` ordering on every allowed disclosure | [`test_household_knowledge_tools.py`](../../tests/unit/test_household_knowledge_tools.py), [`test_p05b2_household_acceptance.py`](../../tests/integration/test_p05b2_household_acceptance.py), [`test_owner_authenticated_turn.py`](../../tests/integration/test_owner_authenticated_turn.py), [`test_owner_authenticated_stream.py`](../../tests/integration/test_owner_authenticated_stream.py) | None remaining | — |
| Audible response and streaming | Piper TTS is integrated; [`streaming_render.py`](../../server/src/server/streaming_render.py) owns C6 audible fallback and audio-before-`done` behavior; Plan 0027 added the `authentication_consumed` terminal field | [`test_transcribe_stream.py`](../../tests/integration/test_transcribe_stream.py), [`test_transcribe_stream_resilience.py`](../../tests/integration/test_transcribe_stream_resilience.py) | None remaining — Plan 0028 measured streaming as consistently faster than classic for the same answer (~1.9s vs ~2.0s total) since audio starts on the first NDJSON chunk instead of waiting for the full response body | — |
| Current visual dialogue | [`routers/vision.py`](../../server/src/server/routers/vision.py) has controller parity; [`vision/perception.py`](../../server/src/server/vision/perception.py) has scene and face adapters | [`test_vision_dialog.py`](../../tests/integration/test_vision_dialog.py), [`test_vision_endpoint.py`](../../tests/integration/test_vision_endpoint.py) | Typed visual preflight, direct grounded VLM-to-TTS, trigger migration, and physical acceptance remain open | [0023](../plans/open/0023-p0-grounded-visual-dialogue.md), after 0021 |

## PC-1 artifacts delivered by Plans 0025–0028

The 2026-08-20 audit found only migrations 002–005 and no production or test
symbol for the planned PIN hash, owner-unlock prompt, request authentication
header, or `authentication_consumed` result. Plans 0025–0027 (merged) closed
every one of those gaps, and Plan 0028 proved them on real hardware:

- PIN hash: migration 006 (`owner_pin_credentials`), `cognition/pin_credentials.py`.
- Owner-unlock prompt: `server/personal_setup.py` (local CLI wizard) and
  `robot/app.py::_prompt_owner_unlock` (opt-in robot startup prompt, now
  usable with `ROBOT_STREAMING` too since Plan 0027 removed the earlier
  `SystemExit` guard).
- Request authentication header: `X-Iroko-Identity-Token`, read by `/chat`,
  classic `/transcribe`, and `/transcribe/stream`.
- `authentication_consumed` result: additive field on `ChatResponse`,
  `TranscribeResponse`, and the streaming NDJSON terminal `done` event.
- Real-hardware proof: Plan 0028 (2026-08-21) — 3x classic + 3x streaming
  allowed/replay cycles, expiry, and generic non-consumption, all audibly
  confirmed and cross-checked against the `authorization_audit_events`
  table directly.

Face recognition functions exist, but no consented runtime adapter converts a
face match into fresh authenticated request evidence. Speaker recognition is
absent; STT and VAD do not identify a speaker. Neither biometric path blocks
PC-1.

## One delivery chain

```text
0025 minimal owner/children/PIN security bootstrap — merged (PR #56)
  -> 0026 one-use authenticated classic turn — merged (PR #57)
  -> 0027 authenticated streaming parity — merged (PR #64)
  -> 0028 physical allowed/denied/replay/expiry acceptance — executed, PASS (2026-08-21)
       `-> 0013 R1 independently closed: R1-01/R1-02 PASS, R1-03 FAIL
          (STT accuracy on "Iroko") — Plan 0013 stays open on this finding
PC-1 accepted
NOW
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
