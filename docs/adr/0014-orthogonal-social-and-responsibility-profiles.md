# 0014 — Keep social and responsibility profiles orthogonal

- **Status:** Accepted
- **Date:** 2026-09-04
- **Builds on:** [ADR 0006](0006-personal-and-family-companion-profiles.md)

## Context

Iroko already distinguishes two social profiles, `personal` and `family`. That
decision defines who lives with the system and how information is protected
between people, but it does not express what responsibility Iroko is authorized
to take on.

The product vision also contemplates companionship, care, and education.
Modelling those responsibilities as separate products or independent brains
would duplicate identity, memory, authorization, and conversation. Modelling
them as a single privilege scale would instead let a technical owner inherit
clinical or educational authority, or authority over another adult's private
data.

The current code only demonstrates companionship capabilities. There is not yet
a working, validated pipeline of sensors, clinical decisions, actions, outcomes,
and feedback that would justify presenting Iroko as a 24/7 nurse or as an
autonomous educator.

## Decision

Iroko keeps a single cognitive architecture and expresses its configuration
through two independent axes:

```text
Social profile
├── personal
└── family

Responsibility
├── companion
├── care
└── education
```

The social profile answers who participates and what boundaries exist between
their data:

- `personal`: one primary person administers their own data and permitted
  configuration;
- `family`: several identified people share household capabilities, without the
  administrator automatically obtaining other adults' private data.

The responsibility profile answers what class of capabilities Iroko may
exercise:

- `companion`: conversation, company, and non-clinical household assistance;
- `care`: future care capabilities, each bounded by its own policies, evidence,
  and acceptance criteria;
- `education`: future educational-support capabilities, also bounded by their
  own policies, evidence, and acceptance criteria.

Only `companion` is active as a delivery target. `care` and `education` are
future directions, not implemented modes and not product promises.

Both axes share the same controller, identity, memory, and policy evaluator.
The differences will be expressed through explicit capabilities, not through
full forks of the architecture.

Care scenarios may involve, among others, a beneficiary, a family member, a
caregiver, a health professional, a technical administrator, and an emergency
contact. Education may involve a student, a guardian, and an educator. No role
inherits general authority over another actor or their data by virtue of its
name.

A resolved identity still does not constitute authorization. An unknown person
may hold general conversation but may not read protected memory or activate
sensitive capabilities. Face and voice remain identity evidence, never an
automatic grant of permissions.

This decision is conceptual. It does not yet authorize new enums, tables,
routes, configuration, or runtime behaviour. Each executable increment must have
a `Ready` plan, typed policy, and observable acceptance.

## Alternatives considered

### One product or brain per combination

Rejected because it would duplicate the cognitive core and encourage divergence
of identity, memory, and privacy.

### A single mode with cumulative permissions

Rejected because it mixes social relationship with authority and makes implicit
privilege escalation easy.

### Implement `care` and `education` now

Rejected because there is no runtime, security, or acceptance evidence that
would sustain those responsibilities.

## Consequences

### Positive

- Allows combining, for example, `personal + companion` or `family + care`
  without creating parallel brains.
- Keeps a clear boundary between social cohabitation and responsibility.
- Prevents `owner`, administrator, or family member from becoming universal
  permissions.
- Allows closing the personal companion first and adding responsibilities only
  once they are demonstrated.

### Negative

- The policy and test matrix will grow as responsibilities are added.
- Each sensitive capability must define actor, purpose, provenance, consent,
  retention, and audit.
- Product communication must distinguish a future direction from an accepted
  capability.

## Review

Review this decision before activating the first `care` or `education`
capability, or if a combination proves to need a different runtime boundary.
Any replacement requires a new ADR.
