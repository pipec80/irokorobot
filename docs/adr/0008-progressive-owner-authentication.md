# 0008 — Progressive owner authentication

- **Status:** Accepted
- **Date:** 2026-08-20
- **Supersedes:** The automatic local-owner presumption in
  [ADR 0007](0007-first-boot-and-default-posture.md)

## Context

The immediate product promise is concrete: after Pipec authenticates and asks
“¿quiénes son mis hijos?”, Iroko answers “Máximo y Dominga”. If another person
asks the same question without valid authentication, Iroko does not reveal the
names or confirm that protected data exists.

The code already has the important foundations: owner bootstrap, structured
family relationships, policy-gated child tools, authorization audit,
`ActivePersonContext`, typed identity evidence, and temporary identity
sessions. The missing piece is a production path that creates fresh evidence
for the person making the current request.

ADR 0007 allowed a completed loopback/local channel to presume its configured
owner. That shortcut connects the authorized path, but it repeats the unsafe
assumption that “this is Pipec's PC” means “Pipec is the current speaker”. A
guest, family member, or nearby person can use the same microphone. Face and
speaker recognition are useful future evidence, but requiring both before the
first useful personal-memory scenario would delay product validation.

## Decision

Iroko will use **progressive authentication**. All authentication methods emit
the same typed, expiring evidence and feed the same active-person and
authorization pipeline. Adding a method changes how evidence is produced, not
how protected memory is authorized or retrieved.

### First useful method: explicit local one-use unlock

The first implementation will provide a local administrative unlock, initially
through a PIN or equivalent explicit local operator action. A successful
unlock creates an opaque, short-lived, scoped token for the configured owner.
The token is consumed by the next protected interaction and is then invalid.
It can also expire or be revoked before use.

This method is intentionally modest. It proves possession of the local unlock
secret, not the physical identity of the speaker. One-use scope, short expiry,
loopback/local transport, non-logging of secrets, and audit limit that risk
while the biometric adapters are added.

### Persistent configuration and transient authentication are separate

Persistent storage may record:

- the configured owner and role;
- onboarding completion;
- enabled authentication methods and their configuration;
- consent, revocation, and authorization audit records.

It must not contain a global or durable `authenticated = true` switch. Current
authentication is transient request/session state and must carry at least:

```text
AuthenticationContext
├── status: authenticated | unauthenticated | expired | ambiguous
├── person_id
├── method: local_unlock | face | voice | fingerprint
├── issued_at
├── expires_at
├── scope
├── token_reference
└── assurance
```

An `authenticated` boolean may be exposed as a computed convenience value, but
it is never the persisted source of truth and never grants broad permission.

### Identity, authentication, and authorization remain distinct

- Identity answers who the evidence points to.
- Authentication answers whether fresh evidence satisfies the method policy
  for this interaction.
- Authorization answers whether that actor may perform this action on this
  data.

Authentication does not bypass the existing role, consent, visibility, or
sensitivity policy. Authorization still happens before protected retrieval.
Unknown, expired, conflicting, missing, or already-consumed evidence fails
closed without disclosing protected values or their existence.

### Later methods reuse the contract

Consented face verification, speaker verification, and a future fingerprint
sensor are adapters to the same evidence contract. They may raise assurance or
reduce friction, but none silently authorizes access and none becomes the sole
recovery route. A spoken name, message content, `conversation_id`, device
ownership, face similarity, or voice similarity is never authorization by
itself.

## Alternatives considered

- **Persist `authenticated = true` for the installation:** rejected because it
  authenticates the device indefinitely, not the current person.
- **Continue presuming the local owner after onboarding:** superseded because
  physical access to Pipec's PC or microphone does not identify the speaker.
- **Wait for face and voice together:** rejected for the first product slice;
  it couples useful personal memory to calibration work that can be added
  progressively.
- **Trust “soy Pipec” or the wording of the question:** rejected because text
  is an untrusted claim and can be repeated by anyone.
- **Make the PIN a permanent session:** rejected for the first slice; a
  one-use token makes the security boundary and acceptance result observable.

## Consequences

### Positive

- The shortest path to the personal-companion promise uses foundations already
  present instead of replacing them.
- PIN/local unlock, face, voice, and fingerprint can be delivered and tested
  independently.
- Public and unknown conversation remains available while protected retrieval
  stays closed.
- The real runtime can exercise both authorized and denied paths now, before
  biometric quality is solved.

### Negative

- A person who obtains the local secret and uses the next interaction can be
  accepted during the short window; this is an explicit MVP limitation.
- The robot/client must safely carry an opaque token or equivalent request
  reference without breaking the existing API contract.
- Face and speaker integration still require consent, enrollment, calibration,
  conflict handling, expiry, and real-hardware evaluation.

## What remains from ADR 0007

ADR 0007's explicit first-boot state, owner-before-household invariant,
onboarding completion flag, local recovery path, and optional biometric
posture remain accepted. Only the decision that a completed local channel
automatically resolves to its owner is superseded.

## Review

Revisit token lifetime and scope after the first repeated real-PC acceptance
run. Revisit assurance requirements when LAN access, the `family` profile, a
displayed local UI, or physical actions enter scope. Do not silently widen the
one-use local unlock into a reusable network session.

## Follow-up

- [Owner-authenticated personal-memory MVP design](../plans/open/0024-owner-authenticated-memory-mvp-design.md)
- [Personal companion design](../plans/open/0015-personal-companion-design.md)
- [Identity, household access, and consent](../architecture/identity-and-access.md)
- [Memory, relationships, onboarding, and world state](../architecture/memory-and-world-state.md)
