# 0015 — Bind the owner grant to a named operation and to speaker evidence

- **Status:** Accepted (2026-09-25, Pipec)
- **Date:** 2026-09-24
- **Builds on:** [ADR 0008](0008-progressive-owner-authentication.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md)
- **Origin:** [0049 audit](../plans/open/0049-server-objective-conformance-audit.md)
  findings F-08, F-09 and F-16; repairs that do not need this decision are in
  [Plan 0050](../plans/open/0050-server-audit-repairs.md)

## Context

The 2026-09-22 acceptance table asks that, when the owner introduces a friend
(Tom), Tom can chat but cannot read the owner's private data, change memory or
inherit the owner's authorization. Reading the protection boundary in full
(2026-09-24, baseline `ac8275d`) shows which parts hold and which do not.

**What holds.** A public turn reaches the model with no memory context and no
history; a protected question without a grant is denied before any storage read;
a stranger's words are never consolidated; a spent grant is not inherited by the
next speaker. Plan 0050 Task 11 turns these into an executable matrix.

**What does not, verified in code.**

1. **The grant is not bound to a named operation.** ADR 0009 requires each grant
   to be "bound to a named operation, data category, actor, scope, expiry, and
   consumption rule", and says the PIN grant "authorizes only one
   `personal_protected_read` of confirmed `child_data`. It does not authorize
   memory mutation, biometric administration…". The token is bound to a person, an
   expiry (`OWNER_UNLOCK_TTL_SECONDS`, 300 s by default since PR #76) and one use,
   but not to an operation. `OwnerRequestResolver.scope` is computed and read only
   by a unit test; `resolve_consent` returns `GRANTED` to whatever consumes the
   token. Three different operations consume it today: the protected child read
   (intended), "¿quién soy?" (`controller._active_identity_plan`), and
   `POST /auth/owner/face/enroll` and `/revoke` (`routers/auth.py`), which is the
   biometric administration ADR 0009 excludes. Plan 0029 chose to require the PIN
   token for enrollment without reconciling that sentence.
2. **"¿Quién soy?" spends the grant and names the owner** to whoever presents the
   token ("Sos {name}"), so a bystander can burn the owner's read grant.
3. **The grant proves the PIN, not the speaker.** ADR 0008 accepts this as an MVP
   limit. Whoever presents a valid token first is answered; the robot keeps the
   token across turns until it is consumed or expires.
4. **A visible face does not veto the grant.** `compose_face_then_pin_resolver`
   returns early only for an identified face or an ambiguous one (two or more
   faces). Any other outcome — including one clear face that is not the owner —
   falls through to the PIN. There is no liveness check, so a photograph
   identifies.
5. **No speaker evidence exists.** `VOICE` is untrusted evidence; the calibration
   study is Plan 0047.

Item 1 is a non-conformance with an accepted ADR, not a new question. What is
open is the concrete scope model and its usability cost. Items 3–5 are the
known MVP limit; they need staging, not an immediate change.

## Decision

Accepted 2026-09-25. Nothing changes in code until Plan 0051 (decision 1)
and PC-4 (decision 2) implement it.

### 1. Bind every grant to a named operation (enforces ADR 0009)

- `OwnerUnlockScope` is the closed set of operations a grant can be bound to:
  `personal_protected_read` (the default) and `biometric_admin`.
- `POST /auth/owner/unlock` accepts an optional `scope` in its JSON body. Absent
  means `personal_protected_read`, so the robot's startup prompt and every
  existing client are unchanged (an additive field).
- The token records its scope when issued. The resolver returns `GRANTED` only
  when the operation being authorized is within that scope. The child read asks
  for `personal_protected_read`; face enrollment and revocation ask for
  `biometric_admin`. A token issued for one cannot authorize the other.
- `scripts/onboard.py` unlocks with `biometric_admin` for the face phase.
- "¿Quién soy?" confirms identity from the evidence already on the request and
  does not consume a grant. Its copy is unchanged.

### 2. Speaker binding is staged, and adds no code now

- **Today:** the grant stays a bearer token for the read scope, as ADR 0008
  accepts. The limit is recorded in the capability matrix and pinned by a
  characterization test.
- **When speaker evidence and fusion exist (PC-3B, PC-4):** a protected read is
  authorized only if the turn's evidence does not contradict the grant — a
  recognized different person, or a speaker verdict "not the owner". Missing
  evidence keeps the PIN path, because face and voice are never the sole route
  (ADR 0006, ADR 0008).
- **Face veto:** whether one clear, unrecognized face should veto the PIN
  fallback depends on the false-rejection rate the owner will tolerate. Three
  options are open — keep the fallback (today), veto on any clear non-owner face,
  or veto only on a face that matches a *different enrolled person*. Decide with
  the measured FAR/FRR of Plan 0047 and the real-camera calibration; recommended
  candidate: the third.
- **Liveness** (a photograph identifies) is a PC-4 requirement, not part of this
  ADR.

### 3. The default lifetime is unchanged

`OWNER_UNLOCK_TTL_SECONDS` stays 300 s. A shorter window narrows the bearer
risk but costs a PIN more often; the setting is already the operator's lever.

## Alternatives considered

- **Leave it as is.** Rejected: ADR 0009 is accepted, and every new protected
  capability (preferences, birth dates, memory mutation) would be authorized by
  whichever request consumes the token first.
- **Spend the grant on the first utterance of any kind.** Rejected: it forces a
  PIN before every protected question and still does not bind the grant to the
  speaker.
- **A fresh PIN prompt for each administrative action, with no scope field.**
  Compatible with decision 1 in effect, but it moves the binding from the token to
  the caller's discipline; the token would still be a master key.
- **Bind the grant to face or voice alone.** Rejected: ADR 0006 and ADR 0008 say
  face and voice are never the sole route to protected data.

## Consequences

### Positive

- The code matches ADR 0009; a grant issued for a read cannot administer
  biometrics, and each new protected capability must declare its scope.
- "¿Quién soy?" can no longer waste the owner's read grant.
- The speaker limit stays explicit, tested and staged behind real evidence
  instead of being solved by guesswork.

### Negative

- `POST /auth/owner/unlock` gains a field, and the OpenAPI schema with it.
- Enrolling a face and then asking a protected question takes two unlocks: each
  grant is one-use and now names one operation.
- The bearer limit remains until PC-4: a bystander who presents a valid read
  token before it expires is still answered.

## Test consequences

The two characterization tests in
`tests/integration/test_owner_stranger_matrix.py` are rewritten by the plan that
implements decision 1: the one for "¿quién soy?" asserts the grant survives, and a
new pair asserts that a read-scoped token is refused by face enrollment and the
reverse. The bearer characterization stays until PC-4 changes it.

## Review

Revisit when Plan 0047 reports its verdict, when PC-4 defines fusion, when any new
protected capability is added, or if the extra unlock proves too costly in real
use.

## Follow-up

- Plan 0051 — scoped grants (decision 1). Unblocked by this acceptance; written
  when it reaches `NOW`, after PC-3B and PC-4 in the agreed order.
- PC-4 — speaker binding, face veto and liveness (decision 2).
- [Capability matrix](../architecture/current-state.md) (added by Plan 0050,
  Task 12).
