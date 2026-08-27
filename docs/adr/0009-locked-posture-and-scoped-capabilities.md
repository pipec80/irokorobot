# 0009 — Locked posture and scoped capabilities

- **Status:** Accepted
- **Date:** 2026-08-20
- **Builds on:** [ADR 0008](0008-progressive-owner-authentication.md)

## Context

Iroko can perceive, transcribe, converse, retrieve memory, and eventually invoke
tools that affect a computer or home. These abilities must not share one global
“unlocked” switch. Otherwise, the PIN introduced to prove the first personal
memory scenario could accidentally become a master key for unrelated actions.

The product needs a useful default for a speaker without fresh authentication.
Turning Iroko completely off would prevent ordinary social interaction, but
letting an unknown speaker reach Pipec's memory or action tools would recreate
the privacy and control failure that progressive authentication is intended to
fix.

## Decision

Iroko has a **locked posture for protected capabilities**, not a locked brain.
When the current request has no fresh, valid evidence, the actor remains
`unknown` and Iroko may use only public, non-actuating capabilities.

### Capabilities available while locked

- camera and microphone input may be perceived under their existing local
  privacy settings;
- STT may transcribe the current utterance;
- Iroko may produce bounded general conversation and TTS output;
- request-local working context may be retained only inside an isolated
  unknown interaction;
- safe status or authentication guidance may be returned without confirming
  whether protected data exists.

### Capabilities unavailable while locked

- read, enumerate, summarize, or confirm personal/household memory;
- attribute or consolidate an unknown speaker's statements into Pipec's
  persistent memory;
- modify confirmed memory, identity, consent, credentials, or policy;
- control home devices, restart or administer a computer, or invoke another
  protected tool;
- enroll biometrics or turn perception into authorization.

A denied response explains that Iroko cannot confirm the speaker or authorize
the request. It must not pretend the protected fact is absent, and it must not
reveal a name, count, hint, or confirmation that the fact exists.

### Authentication grants one named capability, not a master session

There is no global operational transition from “locked” to “fully unlocked”.
Each fresh evidence/grant is bound to a named operation, data category, actor,
scope, expiry, and consumption rule. Authorization is evaluated again before
retrieval or side effect.

For the first personal-memory MVP, the local PIN grant authorizes only one
`personal_protected_read` of confirmed `child_data`. It does not authorize
memory mutation, biometric administration, home control, computer restart, or
another physical/digital action.

Future action capabilities require their own policy. High-impact or physical
actions may additionally require a fresh confirmation, local safety checks,
and narrower expiry even when Pipec is identified. Face, voice, fingerprint,
or a role such as `owner` does not silently widen a grant.

An `authenticated` or `unlocked` boolean may be displayed as a computed hint
for one capability, but it is never persisted or interpreted as general
authority.

## Alternatives considered

- **Disable all interaction while unknown:** rejected because perception,
  general conversation, and safe guidance are part of the companion product
  and do not require private authority.
- **One authenticated session unlocks everything:** rejected because a memory
  question must not grant control of the computer, home, credentials, or
  actuators.
- **Let the LLM decide whether an action is safe:** rejected because prompts
  and model judgment are not authorization or a safety boundary.
- **Treat loopback/device ownership as action permission:** rejected because
  another person can speak near or operate Pipec's PC.

## Consequences

### Positive

- Iroko remains socially useful without leaking personal memory.
- Every new tool declares its capability and authorization boundary instead of
  inheriting a broad authenticated state.
- The first PIN MVP remains narrow and cannot become accidental authority for
  later home or computer control.
- Unknown conversation and Pipec's persistent memory remain isolated.

### Negative

- Product surfaces must describe which capability is currently authorized;
  a single padlock indicator is insufficient without scope.
- Future action integrations need explicit policies, confirmations, safety
  checks, and acceptance scenarios rather than reusing the memory grant.
- Some convenient commands will be denied until their own bounded capability
  path exists.

## Follow-up

- [Identity, household access, and consent](../architecture/identity-and-access.md)
- [Owner-authenticated personal-memory MVP](../plans/completed/0024-owner-authenticated-memory-mvp-design.md)
- [One-use classic owner turn](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md)
- [Personal companion delivery map](../roadmap/personal-companion-delivery-map.md)
