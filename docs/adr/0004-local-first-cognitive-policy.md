# 0004 — Adopt a local-first cognitive policy

- **Status:** Accepted
- **Date:** 2026-08-03

## Context

Iroko operates in a home, handles personal information, and must remain useful
when Internet access or a cloud provider is unavailable. Local models can be
less capable for some requests, but sending every interaction to a remote model
would increase privacy exposure, cost, latency variance, and operational
dependence.

The cognitive layer also needs an explicit way to represent uncertainty. A
forced answer is unsafe: missing, ambiguous, contradictory, or restricted
information must not be converted into a plausible-sounding fact.

## Decision

Iroko is local-first. Local storage is the source of truth, and local execution
is the default for memory, identity, biometrics, permissions, household state,
retrieval, and deterministic decisions.

Cloud processing is an optional escalation, not the primary brain. It may run
only when all of these conditions hold:

1. The local result is insufficient or the required capability is unavailable
   locally.
2. The active policy authorizes the task and the data category.
3. The request sends only the minimum context required.
4. The expected improvement justifies the privacy, latency, and cost impact.
5. A timeout, local fallback, and audit record identify the provider and model.

Raw biometric data, household databases, complete conversations, children's
images, medical information, location history, and home maps do not leave the
local environment by default. A future exception requires a separate ADR and
explicit owner approval.

Every cognitive result exposes one of these knowledge states:

- `known`: sufficient evidence supports one result.
- `unknown`: the available evidence is insufficient.
- `ambiguous`: available evidence supports multiple plausible results.
- `contradictory`: trusted evidence conflicts.
- `unauthorized`: policy forbids disclosing or processing the result.

`unknown` is a successful, valid outcome. Components must preserve these states
instead of forcing an answer or silently escalating to cloud. Confidence and
authorization remain separate: a high-confidence result can still be forbidden,
and an authorized operation can still be uncertain.

The implementation will use a small typed Python orchestrator. It will not add
a general agent framework, autonomous multi-agent system, or dynamic plugin
platform.

## Alternatives considered

- **Cloud-first with local fallback:** rejected because loss of Internet or a
  provider would disable the normal path and remote processing would become the
  default privacy boundary.
- **Local-only:** rejected as an absolute rule because carefully authorized
  escalation can improve difficult language or vision tasks.
- **Return only a numeric confidence:** rejected because a number cannot explain
  the difference between missing, conflicting, ambiguous, and forbidden data.
- **Always return the most likely answer:** rejected because it creates avoidable
  false positives and hides missing evidence.

## Consequences

### Positive

- Core household behavior remains private and available offline.
- Cloud usage is explicit, minimal, measurable, and replaceable.
- Callers can handle uncertainty and authorization deterministically.
- Tests can verify safe degradation without invoking models or network services.

### Negative

- Some local responses will be slower or less capable than cloud responses.
- Policy, redaction, timeout, and audit behavior require explicit implementation.
- Callers must handle several result states instead of assuming success/failure.

## Review

Revisit this decision if local hardware capability changes substantially, legal
or privacy requirements change, or measured evaluations show that an approved
cloud path is required for a defined feature. Any broader remote-data policy
must supersede this ADR rather than silently weakening it.
