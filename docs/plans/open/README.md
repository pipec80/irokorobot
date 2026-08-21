# Open plan index

> **Status:** Work not yet closed. A plan can be implemented, partially
> implemented, deferred, or only designed and still belong here. Presence in
> this directory does not grant permission to implement.

## Audited disposition

The following status was checked against the executable code, tests, current
Git ancestry, and recorded runtime evidence on 2026-08-21. Existing components
named under **Reuse** must not be rebuilt by a later plan.

For daily work, do not choose a plan from this inventory. Follow the single-WIP
[operational board](../README.md#operational-board), whose current `NOW` item
is Plan 0027. Use the
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md)
to see the code, tests, verified gap, and accountable plan for each outcome.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0013](0013-p0-voice-controller-bridge.md) | Implemented and merged by PR #51 | Classic `/transcribe` controller bridge, unknown public actor, deterministic/protected routes | Repeat and record real microphone-to-Piper R1 acceptance |
| [0014](0014-p0-runtime-policy-hardening-design.md) | Partial umbrella: C1–C4 and C6 implemented | Plans 0016–0019 and 0022 | C5, C7, and combined P0 operator acceptance |
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 code is merged (Plans 0025–0026), acceptance still owed to Plan 0028 | Controller, policy/audit, v4 child tools, identity-session seam, onboarding primitives, STT/TTS, face engine | Execute 0027–0028; biometrics remain later slices |
| [0020](0020-p0-operator-qa-remediation-design.md) | Partial umbrella: C6 complete; C5/C7 not executed | Reliable streaming output from completed Plan 0022 | Execute 0021 after PC-1, then 0023, then combined acceptance |
| [0021](0021-p0-typed-intent-resolution.md) | Plan-specific implementation not started | Existing inline classifier, normalization, typed needs, policy/tools, channel parity | Extract the typed injected resolver, corpus, precedence/privacy tests, and operator evidence |
| [0023](0023-p0-grounded-visual-dialogue.md) | Plan-specific grounding not started | Existing vision controller parity, scene perception/VLM transport, image validation, Piper, enrollment quarantine | Add typed visual decisions, preflight before frame access, direct grounded VLM-to-TTS, migrate triggers, and accept physically |
| [0024](0024-owner-authenticated-memory-mvp-design.md) | Approved design | Existing identity, authorization, child-memory, and channel seams | Deliver through 0027–0028 |
| [0026](0026-one-use-owner-authenticated-classic-turn.md) | Implemented and merged by PR #57; classic flow informally confirmed once with real mic/speaker on 2026-08-21 | Owner unlock service, `LOCAL_UNLOCK` evidence, `/auth/owner/unlock`, async controller resolvers, robot opt-in prompt | Plan 0028's formal repeated acceptance and independent verdict |
| [0027](0027-one-use-owner-streaming-parity.md) | Not implemented; ready to start | Existing stream controller parity, reliable rendering, and Plan 0026's owner-unlock service/token contract | Propagate the same one-use evidence through streaming |
| [0028](0028-owner-authenticated-memory-runtime-acceptance.md) | Acceptance plan; blocked by 0027 | Real server/robot/STT/Piper path | Prove allowed, unauthenticated, reused-token, and expired-token scenarios in both classic and streaming modes |

Plans 0025 (merged) closed with no acceptance debt — see
[completed/0025](../completed/0025-personal-owner-bootstrap-and-pin-setup.md).

Canonical execution order: **0027 → 0028 → 0021 → 0023**.

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.
