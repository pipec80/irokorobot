# 0006 — Support personal and family companion profiles

- **Status:** Accepted
- **Date:** 2026-08-14

## Context

Iroko is intended to be a companion robot, not merely a private assistant. The
first valuable product is a trustworthy personal companion for Pipec, while the
longer-term product must interact warmly with adults, children, relatives, and
pets. Treating every household member as the owner is unsafe; treating a family
companion as a one-person assistant prevents the intended social experience.

The P0 foundation already separates identity from authorization and uses local
SQLite entities, relationships, roles, policy decisions, and audit events. It
deliberately does not yet provide public trusted identity, biometric
recognition, consent persistence, a UI, or general family onboarding.

## Decision

Iroko uses one cognitive architecture and one local data model with two
installation policy profiles:

| Profile | Purpose | Default access posture |
|---|---|---|
| `personal` | A companion centred on one primary owner. | The owner has the broadest authority over their own data and configuration; other speakers remain public/unknown until an explicit later policy says otherwise. |
| `family` | A socially aware companion for one household. | Identified members may use permitted household data and their own allowed data. The technical owner/admin does not automatically receive another adult's personal data. |

The profile changes defaults and onboarding requirements; it does not create a
second brain, database, or identity model.

In both profiles:

- identity evidence is never authorization;
- unknown and ambiguous are valid outcomes;
- explicit local administration is the recovery route when biometrics fail;
- biometric enrolment requires local authorization and subject consent;
- owner authority does not bypass confirmation for biometric changes, cloud
  disclosure, export/delete, or physical actions;
- the LLM receives only information already allowed by deterministic policy.

The next product milestone after P0 runtime closure is the `personal` profile:
local Pipec administration, consented local face and voice evidence,
conservative fusion, and an end-to-end companion acceptance run. A general UI
and the `family` profile are deliberately later work.

## Consequences

### Positive

- The first companion scenario is narrow enough to validate on current PC
  hardware without pretending a whole household implementation exists.
- Face and voice recognition improve normal interaction without becoming the
  only way to recover access.
- Family social warmth can later grow from the same entity/relationship/policy
  model without granting blanket access to adult or child data.

### Negative

- The first personal companion flow needs a local administrative path before
  the eventual UI exists.
- Family onboarding, consent UX, multi-person policy, and social greetings are
  explicitly deferred rather than partially simulated by prompts.
- Future policy changes must preserve the distinction between a technical
  owner/admin and a person's private data.

## Alternatives considered

- **One owner for every interaction:** rejected because it leaks the owner's
  context to children, guests, and background speakers.
- **Fully open family memory:** rejected because social familiarity is not
  consent to disclose personal, child, biometric, medical, location, or private
  data.
- **Biometrics as the only access mechanism:** rejected because models fail,
  environments change, and recovery must remain explicit and local.
- **Separate personal and family codebases:** rejected because the cognitive
  contracts, local database, and policy evaluator should remain shared.

## Follow-up

- [P0 runtime policy hardening design](../plans/completed/0014-p0-runtime-policy-hardening-design.md)
- [Personal companion design](../plans/open/0015-personal-companion-design.md)
- [Identity, household access, and consent](../architecture/identity-and-access.md)
- [Cognitive roadmap](../roadmap/cognitive-roadmap.md)
