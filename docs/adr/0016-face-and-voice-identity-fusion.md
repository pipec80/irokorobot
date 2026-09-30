# 0016 — Identify the owner by face; require more assurance for reserved data

- **Status:** Accepted (2026-09-30, Pipec)
- **Date:** 2026-09-30
- **Builds on:** [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0008](0008-progressive-owner-authentication.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md)
- **Refines:** [ADR 0015](0015-owner-grant-scope-and-speaker-binding.md) decision 2
  (speaker binding, face veto)
- **Implemented by:** PC-4, a future numbered plan under `docs/plans/`

## Context

The purpose of face and voice evidence is one thing: **not to give private data to
someone who is not the owner.** Plans 0029/0030 (face) and 0053 (voice) delivered the
evidence; this ADR decides how it combines. The model is one owner and one robot, so
recognition failures are rare and matter mostly for the few requests that touch reserved
data (account numbers, passwords), which are asked rarely. The PIN was an entry point to
prove the privacy concept; the robot has no keyboard, and it stays only because it is
already built.

**What holds today (verified in code, 2026-09-30, `main` at `aeb3e32`).**

1. **A face alone identifies the owner and unlocks protected reads.** `FACE` is in
   `_TRUSTED_IDENTIFIED_SOURCES` (`cognition/identity.py`) and `authorization.py`
   authorizes only `IDENTIFIED` actors. There is no liveness check, so a photograph
   identifies. It is recorded as a known gap in `current-state.md`.
2. **Voice evidence exists but decides nothing.** `VOICE` is absent from
   `_RESOLVABLE_SOURCES`; a `verified` verdict only attaches untrusted evidence
   (Plan 0053). Six of eight replay probes were accepted in the PC-3A study. The check
   compares *who* speaks, not *what* is said, so mispronunciation does not affect it
   (5 of 5 genuine turns verified in the 2026-09-29 acceptance).
3. **The composition is a precedence chain**: `compose_face_then_pin_resolver` tries the
   face and falls through to the PIN, and a separate wrapper in `routers/transcribe.py`
   consults the speaker only when nothing identified the actor.
4. **The speaker verdict has no "not the owner" outcome** (`verified`, `unknown`,
   `unavailable`); with one enrolled speaker a rejection cannot be told from a poor sample.
5. **The policy already has a closed sensitivity vocabulary**
   (`DataSensitivity`: `NORMAL`, `PRIVATE`, `BIOMETRIC`, `MEDICAL`, `LOCATION`,
   `CHILD_DATA`, `SECURITY`). The only protected capability implemented is the child read;
   no `SECURITY` data exists yet.
6. `identity-and-access.md` already states the conservative fusion target: face + voice
   for the same person → `identified`; one strong source → `probable`; sources pointing at
   different people → `ambiguous`.

ADR 0006 names the recovery route: *explicit local administration is the recovery route
when biometrics fail*. Identity evidence still passes through `evaluate_authorization`
(actor `IDENTIFIED`, owner role, consent); this ADR changes how identity is established
and adds an assurance level, not who authorizes.

## Decision

### 1. The face is the default way to identify the owner

The owner's face alone yields `identified` with **assurance `basic`**, as today. This is
enough for ordinary private data such as the child read.

### 2. Voice raises assurance to `strong`

If the owner's face matched and the turn's voice is verified as the same person, the
result is `identified` with **assurance `strong`**. A verified voice alone never
identifies: without an owner's face it is not consulted (and would only be `probable`).
An optional PIN token also yields `identified` with assurance `strong` (a knowledge
factor). Fusion is one deterministic rule in `resolve_active_person`, with one enrolled
owner:

| Evidence of the turn | Result | Assurance |
|---|---|---|
| Owner's face and verified voice of the same person | `identified` | `strong` |
| Owner's face only | `identified` | `basic` |
| Optional PIN token, only when one is presented | `identified` | `strong` |
| Verified voice only | `probable` (never authorizes) | — |
| Face of another enrolled person, or two or more faces | `ambiguous` | — |
| Unknown face or voice, no usable or expired evidence | `unknown` | — |

Evidence whose `expires_at` has passed never participates; biometric evidence lives only
inside its request.

### 3. Reserved categories require `strong`

`evaluate_authorization` denies a request whose sensitivity includes a category in a
closed set `HIGH_ASSURANCE_CATEGORIES` unless the actor's assurance is `strong`. The set
is `{SECURITY}` today (account numbers, passwords); other categories join it when a
capability declares them, not before. All other categories, including `CHILD_DATA`,
need `basic`. No reserved capability exists yet, so the rule is proven with a synthetic
`SECURITY` request; each future capability declares its category and inherits the rule.

### 4. Conflict vetoes; ignorance does not

Positive evidence of another person (a face matching another enrolled person, or two or
more faces in frame) makes the turn `ambiguous` **even when a PIN token is presented**,
and does not consume the token. An unknown face, an unknown voice or a missing signal
never vetoes and never adds. This resolves the open face-veto question of ADR 0015
decision 2 with its recommended candidate, restricted to positive evidence so that a
bad-light day cannot lock the owner out. A "voice rejected" verdict is **not**
introduced: with one enrolled speaker it cannot be measured honestly.

### 5. Turn order

Face first; voice only when the face matched the owner (the only case in which
corroboration exists); the PIN only when a token was presented and nothing resolved or
vetoed. Identity is resolved only on protected turns, so the embedding (about 0.5 s, one
per request) is paid there and never on public turns. Without a token there is no PIN
lookup at all.

### 6. The PIN is optional and administrative

The PIN is not promoted, prompted or documented as a normal path. It stays as (a) a valid
optional `strong` factor when a token is presented, useful for reserved data, and (b) the
credential of **local administration** for enrolling and revoking biometrics over
loopback, until Plan 0051 binds it to its operation.

### 7. Recovery is local administration

When face or voice fail (poor light, hoarseness, a fallen camera) the conversational
answer is the same generic denial. Recovery is an explicit action on the server host
(`just face-auth-demo`, `just speaker-auth-demo`, `just setup-personal`), as ADR 0006
requires. No spoken recovery step exists.

### 8. The denial reveals nothing

The spoken and returned text is the existing generic denial in every non-authorized
case, including a reserved request answered with only `basic` assurance. The reason goes
only to the server log as a closed enum with no name, distance or score: `pin`,
`face_and_voice`, `face_only`, `insufficient_assurance`, `veto_other_person`,
`veto_multiple_faces`, `backend_unavailable`, `no_evidence`. The additive response field
`identity_source` gains `"face_voice"`.

### 9. Replay and spoofing: measured, not closed

Liveness is out of scope. A photograph identifies at `basic` (unchanged from today,
accepted for ordinary private data). For reserved data a photograph alone or a recording
alone no longer opens the door; a photograph **plus** a recording of the exact question
still can. That residual risk is measured on real hardware, recorded in the plan and in
`current-state.md`, and left for a separate liveness plan only if the measurement
justifies it.

## Alternatives considered

- **Face and voice always required.** Rejected by Pipec: daily friction for a risk that
  matters only for rare reserved requests.
- **Face always sufficient, voice only recorded.** Rejected: a photograph would open
  reserved data the day it exists, and the voice evidence would have no purpose.
- **Veto on any clear non-owner face or rejected voice.** Rejected: it can lock the owner
  out on a bad day and cannot be measured with one enrolled speaker.
- **Keep a conversational PIN as recovery, or a spoken hint ("I need your PIN").**
  Rejected: the robot has no keyboard, and a hint tells a listener which factor failed.
- **A separate fusion engine beside `resolve_active_person`.** Rejected: two identity
  resolution paths are the parallel authorization system ADR 0006/0008 forbid.
- **Liveness challenge now.** Deferred: more friction and a new flow, before measuring
  whether the residual risk matters.

## Consequences

### Positive

- Daily use is unchanged: the face answers, with no PIN, keyboard or extra step.
- Reserved data gets a stronger requirement without burdening everything else; the voice
  finally has a purpose.
- One rule, one function, tested as a table; the doc, the code and the tests agree.

### Negative

- A photograph still opens ordinary private data (as today); photograph + matching
  recording still opens reserved data.
- A hoarse or dark day denies the owner reserved data until it passes or a local
  re-enrolment or PIN is used.
- A `strong` requirement pays the embedding time on every protected turn whose face
  matched, even when the data turns out to need only `basic`.
- The optional PIN remains a bearer token until Plan 0051 scopes it.

## Test consequences

Table-driven tests for the rule, including expiry, conflict and both assurance levels; a
policy test with a synthetic `SECURITY` request (denied at `basic`, allowed at `strong`)
and one showing `CHILD_DATA` still allowed at `basic`; fused-resolver tests for order,
short-circuits, token preservation on veto, one embedding per request and log reasons
without personal data; integration tests through `/transcribe` and `/transcribe/stream`.
A real-hardware matrix is measured by Pipec and only outcomes are recorded: owner (basic
and strong), photograph plus another speaker, recording alone, photograph plus recording,
two people in frame, and voice backend down.

## Review

Revisit when a measured false-rejection rate makes the reserved-data denial too costly,
when the first reserved capability (`SECURITY` data) is built, when a second household
member is enrolled (PC-6: voice can then produce a different-person outcome), when
liveness is planned, or when Plan 0051 scopes the PIN.
