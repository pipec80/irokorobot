# 0007 — First boot and local-channel default posture

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

[Plan 0007](../plans/0007-household-authorization-foundation.md) (P0.5-A) and
its successors built roles, fail-closed policy, and audit — but no local path
produces an identified owner. `server/cognition/identity_sessions.py`
(`IdentitySessionRegistry`) is the only producer of identity evidence in the
codebase and has zero callers. `memory/household_authorization.py`'s
`bootstrap_initial_owner()` exists, is tested, and has zero callers outside
tests. Every public route's `active_person_resolver` is hard-coded to a
function that always returns `ActivePersonStatus.UNKNOWN`
(`routers/chat.py:_public_unknown_actor`,
`routers/transcribe.py:_public_unknown_voice_actor`,
`routers/vision.py:_public_unknown_vision_actor`). The result: every operator
run — including the combined P0 acceptance run still pending after Plan
0022 — can only ever exercise the unknown-speaker path. No run can prove the
authorized path works, because nothing can reach it.

`onboarding.py`'s eight-slot checklist (`next_missing_slot`) and
`memory/meta.py`'s `set_flag`/`get_flag` (with `onboarding_complete` used as
the example in the module's own docstring, and migration 002 already backing
it) have the same shape: built, tested, zero production callers.

`onboarding.py`'s own docstring records why order matters: on 2026-07-13 the
owner talked about his children before introducing himself, and the robot
anchored a child as its owner. That is not a model failure — it is a missing
sequencing rule enforced nowhere in code.

[ADR 0006](0006-personal-and-family-companion-profiles.md) already commits to
identity never being authorization, to biometrics never being the sole
recovery route, and to explicit local administration as that recovery route.
It stops short of saying what "not yet configured" means for a fresh install,
or what a completed local channel is allowed to presume.

## Decision

Iroko's `personal` profile has an explicit first-boot state, and a completed
first boot changes the default posture of one channel only: the local trusted
channel.

**First boot is a real state, not an inferred one.** `meta.onboarding_complete`
(already defined, already backed by migration 002) is the frontier. Before it
is set, the robot's own answer to any protected or self-referential question
is "I'm not configured yet," not a denial that reads as a permanent policy
outcome.

**Owner bootstrap precedes every other fact.** No household fact (partner,
child, pet, workplace) may be anchored to any entity until
`bootstrap_initial_owner()` has produced exactly one owner. This is the
direct fix for the 2026-07-13 incident: it moves the invariant from
"undocumented conversational hope" to a checked precondition.

**A completed local channel presumes its owner, within the boundary ADR 0006
already drew.** After first boot, a request arriving on the local trusted
channel — loopback bind, the PC's own microphone, no network hop — resolves
`ActivePersonContext` to the bootstrapped owner by default, carrying an
evidence record with a short TTL and an explicit local revoke path, instead of
`ActivePersonStatus.UNKNOWN`. This is a new evidence source alongside
`IdentityEvidenceSource.MANUAL`, not a change to `resolve_active_person`'s
conservative-fusion rules. It answers "who do I greet" — never "what may I
disclose."

**Disclosure keeps every existing boundary.** Biometric enrollment, protected
household data, and anything ADR 0006 already marks as requiring confirmation
or consent are unaffected: they still require the evidence and policy path
already built, not a claimed identity. A resolved local-channel owner may be
greeted and may use the deterministic tools already gated to the owner role;
nothing here widens what those tools may return.

**Recognition stays evidence, never authorization, and stays optional.** Face
and voice (PC-2/PC-3 in [Plan
0015](../plans/0015-personal-companion-design.md)) remain later, faster paths
to the same identified state this ADR defines the entry to — never a
replacement for it, never the only recovery route.

## Alternatives considered

- **Keep every public route permanently unknown until PC-2/PC-3 (face/voice)
  land:** rejected — it is the status quo and it is what makes every operator
  run since 2026-08-17 unable to test the authorized path at all. The gap is
  months, not one slice.
- **Trust a spoken claim ("soy Pipec") as identity:** rejected outright — this
  is exactly the disclosure vector ADR 0006 and Plan 0007's fail-closed policy
  were built to close.
- **No default posture change — require an explicit unlock gesture every
  session:** rejected as the wrong trade for a single-owner home robot on a
  loopback-bound desktop; it reproduces phone-style re-authentication for a
  device that already lives inside the trust boundary of the house. Revisit if
  `family` profile or LAN exposure change that boundary.
- **Skip the onboarding wizard, seed the DB by hand:** rejected — it is what
  the project already does informally in dev, and it is exactly how the
  2026-07-13 mis-anchoring happened. A checked first-boot sequence is cheaper
  than another silent failure.

## Consequences

### Positive

- The two structures already built and already tested —
  `bootstrap_initial_owner()` and `IdentitySessionRegistry` — get their first
  production caller.
- Every remaining P0-C slice, and the combined operator acceptance run, can
  finally exercise both the unknown-speaker path and the identified-owner path
  in the same run.
- The 2026-07-13 failure mode becomes structurally impossible instead of
  informally documented.
- "¿Quién soy?" and similar self-reference questions can answer correctly on
  the local channel without any biometric work.

### Negative

- A completed local channel becomes a security-relevant boundary: whoever
  reaches loopback on that PC is presumed owner. Mitigated by the boundary
  already stated in the decision (TTL, explicit revoke, disclosure unchanged)
  and by the existing loopback-only default from [Plan
  0002c](../plans/0002c-desktop-security-and-drift.md).
- [Plan 0023](../plans/0023-p0-grounded-visual-dialogue.md)'s `ACTIVE_IDENTITY`
  branch (`Todavía no puedo confirmar quién sos.`) must be revised once this
  lands, so a resolved owner is greeted instead of always receiving the fixed
  unknown-identity copy — already flagged in that plan's status line.
- PC-1 needs a small state machine and a CLI/voice entry point that do not
  exist yet; this ADR authorizes and scopes that work, it does not implement
  it.

## Review

Revisit this decision if: the `family` profile's onboarding
([Plan 0015](../plans/0015-personal-companion-design.md)'s later slices)
needs the local channel to resolve more than one person; `LAN_HOST` exposure
(currently opt-in per [Plan
0002c](../plans/0002c-desktop-security-and-drift.md)) becomes a supported
default, which would change what "local channel" is safe to presume; or the
first real multi-week household run shows the TTL/revoke boundary is wrong in
either direction.

## Follow-up

- [Personal companion design — PC-1](../plans/0015-personal-companion-design.md)
- [P0 operator-QA remediation design](../plans/0020-p0-operator-qa-remediation-design.md)
- [Identity, household access, and consent](../architecture/identity-and-access.md)
- [Cognitive roadmap](../roadmap/cognitive-roadmap.md)
