# 0016 — Identify the owner by face and voice together; make the PIN optional

- **Status:** Proposed (2026-09-30, awaiting Pipec's acceptance)
- **Date:** 2026-09-30
- **Builds on:** [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0008](0008-progressive-owner-authentication.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md)
- **Refines:** [ADR 0015](0015-owner-grant-scope-and-speaker-binding.md) decision 2
  (speaker binding, face veto)
- **Implemented by:** PC-4, a future numbered plan under `docs/plans/`

## Context

The goal of face and voice evidence is one thing: **not to give private data to
someone who is not the owner**. Plan 0029/0030 (face) and Plan 0053/PC-3B (voice)
delivered the evidence; this ADR decides how it combines. The PIN was introduced
as an entry point to prove the privacy concept, and the robot will have no
keyboard to type it.

**What holds today (verified in code, 2026-09-30, `main` at `aeb3e32`).**

1. **A face alone identifies the owner and unlocks protected reads without a
   PIN.** `FACE` is in `_TRUSTED_IDENTIFIED_SOURCES`
   (`cognition/identity.py`), so one matching face yields `IDENTIFIED`;
   `authorization.py` authorizes only `IDENTIFIED`. There is no liveness check, so a
   photograph identifies. This is recorded as a known gap in `current-state.md`.
2. **Voice evidence exists but decides nothing.** `VOICE` is absent from
   `_RESOLVABLE_SOURCES`; a `verified` verdict only attaches untrusted evidence
   (Plan 0053). Six of eight replay probes were accepted in the PC-3A study.
3. **The composition is a precedence chain**, not a rule: `compose_face_then_pin_resolver`
   tries the face, falls through to the PIN, and a separate wrapper in
   `routers/transcribe.py` consults the speaker only when nothing identified the actor.
4. **The speaker verdict has no "not the owner" outcome**: `verified`, `unknown`,
   `unavailable`. With one enrolled speaker, a rejection cannot be told from a poor
   sample, so voice cannot veto anything.
5. **`identity-and-access.md` already states the conservative target** ("Initial fusion
   rules"): face + voice for the same person → `identified`; one strong source →
   `probable`; sources pointing at different people → `ambiguous`.

ADR 0006 already names the recovery route: *explicit local administration is the
recovery route when biometrics fail*. ADR 0008 says face and voice never become the
*sole recovery route* and that none "silently authorizes access"; identity evidence
still passes through `evaluate_authorization` (actor `IDENTIFIED`, owner role, consent),
so this ADR changes what counts as identified, not who authorizes.

## Decision

### 1. The owner is identified by face and voice agreeing

Fusion lives in one place, `resolve_active_person`, as a deterministic rule with a
single owner enrolled:

| Evidence of the turn | Result | Reads protected data |
|---|---|---|
| Owner's face **and** verified voice of the same person | `identified` | Yes |
| Owner's face only (a verified voice alone would also be `probable`, but voice is not consulted without an owner face) | `probable` | No |
| Face of another enrolled person, or two or more faces | `ambiguous` | No |
| Unknown face or voice, no usable or expired evidence | `unknown` | No |
| Optional PIN token, only when one is presented | `identified` (as today) | Yes |

`FACE` and `VOICE` become *corroborating* sources: neither identifies alone.
`MANUAL` and `LOCAL_UNLOCK` keep identifying alone. Evidence whose `expires_at` has
passed never participates; biometric evidence lives only inside its request.

### 2. Conflict vetoes; ignorance does not

Positive evidence of another person (a face matching another enrolled person, or
two or more faces in frame) makes the turn `ambiguous` **even when a PIN token is
presented**, and does not consume the token. An unknown face, an unknown voice or a
missing signal never vetoes and never adds. This resolves the open face-veto question of
ADR 0015 decision 2 with its recommended candidate, restricted to positive evidence
so that a bad-light day cannot lock the owner out. A "voice rejected" verdict is **not**
introduced: with one enrolled speaker it cannot be measured honestly.

### 3. Turn order

Face first; voice only when the face matched the owner (it is the only case in which
corroboration is needed, so public turns never pay the embedding); the PIN only when a
token was presented and nothing resolved or vetoed. Without a token there is no PIN
lookup at all. One embedding per request at most.

### 4. The PIN is optional and administrative

The PIN is no longer "always available" as a conversational fallback and is not
promoted, prompted or documented as a normal path. It stays as (a) a valid optional
factor when a token is presented and (b) the credential of **local administration**
for enrolling and revoking biometrics over loopback, until Plan 0051 binds it to its
operation.

### 5. Recovery is local administration

When face or voice fail (hoarseness, poor light, a fallen camera) the conversational
answer is the same generic denial. Recovery is an explicit action on the server host
(`just face-auth-demo`, `just speaker-auth-demo`, `just setup-personal`), as ADR 0006
requires. No spoken recovery step exists.

### 6. The denial reveals nothing

The spoken and returned text is the existing generic denial in every non-identified
case. The reason goes only to the server log as a closed enum with no name, distance
or score: `pin`, `face_and_voice`, `face_only`, `veto_other_person`,
`veto_multiple_faces`, `backend_unavailable`, `no_evidence`. The additive response field
`identity_source` gains `"face_voice"`.

### 7. Replay and spoofing: measured, not closed

Liveness is out of scope. A photograph alone or a recording alone stops opening the door;
a photograph **plus** a recording of the exact question still can, and that residual
risk is measured on real hardware, recorded in the plan and in `current-state.md`, and
left for a separate liveness plan only if the measurement justifies it.

### 8. Face without voice does not authenticate

With `SPEAKER_AUTHENTICATION_ENABLED=false`, a face alone stays `probable`. The server
logs a warning at startup when face authentication is on and speaker authentication is off.

## Alternatives considered

- **Keep the face alone as sufficient, voice only as a veto.** Rejected: the photograph
  stays a working key, and a voice veto needs the "rejected" verdict of point 2.
- **Veto on any clear non-owner face or rejected voice.** Rejected: it can lock the owner
  out on a bad day and cannot be measured with one enrolled speaker.
- **Keep a conversational PIN as recovery.** Rejected by Pipec: the robot has no
  keyboard and the PIN was a scaffold; ADR 0006's local administration already covers it.
- **A spoken recovery hint ("I need your PIN").** Rejected: it tells a listener which
  factor failed.
- **A separate fusion engine beside `resolve_active_person`.** Rejected: two identity
  resolution paths are the parallel authorization system ADR 0006/0008 forbid.
- **Liveness challenge now.** Deferred: more friction and a new flow, before measuring
  whether the residual risk matters.

## Consequences

### Positive

- The photograph alone and the recording alone stop opening protected reads.
- One rule, one function, tested as a table; the doc, the code and the tests agree.
- No PIN, no keyboard and no extra step in daily use; voice arrives in the same audio
  as the question, so the extra friction is the embedding time (about 0.5 s) on protected
  turns whose face matched.

### Negative

- Behavior accepted in Plan 0029 changes: a face alone no longer answers a protected
  question, and a configuration with face but no voice becomes useless (hence the
  startup warning).
- A hoarse or dark day denies the owner until it passes or the owner re-enrols locally.
- Photograph + matching recording remains a working attack; a stranger next to an
  unknown-face owner is not vetoed (no positive evidence).
- The optional PIN remains a bearer token until Plan 0051 scopes it.

## Test consequences

Table-driven tests for the rule, including expiry and conflict; fused-resolver tests for
order, short-circuits, token preservation on veto, one embedding per request and log
reasons without personal data; integration tests through `/transcribe` and
`/transcribe/stream`; the face-authenticated turn tests are rewritten because the face
alone no longer identifies. A real-hardware matrix (owner, hidden face, photo plus another
speaker, recording alone, photo plus recording, two people in frame) is measured by Pipec
and only outcomes are recorded.

## Review

Revisit when a measured false-rejection rate makes the daily denial too costly, when a
second household member is enrolled (PC-6: voice can then produce a different-person
outcome), when liveness is planned, or when Plan 0051 scopes the PIN.
