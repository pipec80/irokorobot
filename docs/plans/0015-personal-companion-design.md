# Personal companion design — Iroko and Pipec

> **Status:** PC-1 is promoted by owner decision on 2026-08-18 and runs
> immediately after Plan 0022, ahead of the remaining P0-C slices. Its design
> is grounded by [ADR 0007](../adr/0007-first-boot-and-default-posture.md),
> accepted 2026-08-19. PC-2 through PC-5 remain proposed and still start only
> after P0-C and P0 runtime acceptance pass.

## Objective

Make Iroko a secure local companion for Pipec before introducing a general UI
or family onboarding. Normal interaction should use consented local face and
voice evidence; recovery must remain a local explicit administrative operation.

## Product boundary

This is the `personal` profile from
[ADR 0006](../adr/0006-personal-and-family-companion-profiles.md). Pipec is the
primary owner with broad authority over their own permitted data and
configuration. Other speakers may converse generally but do not receive Pipec's
private context merely by claiming a name or resembling a biometric profile.

## Required slices

### PC-1 — First boot

Per [ADR 0007](../adr/0007-first-boot-and-default-posture.md), a fresh install
has an explicit first-boot state, and completing it is what lets the local
trusted channel presume its owner. Two structures already exist with zero
production callers and get their first caller here:
`household_authorization.bootstrap_initial_owner()` and
`cognition.identity_sessions.IdentitySessionRegistry`. Two more already exist
and get wired up: `onboarding.next_missing_slot()` and
`memory.meta.set_flag`/`get_flag` (migration 002 already backs
`onboarding_complete`).

A fresh install walks, in this order, before anything else runs:

1. **Preflight.** No question asked. Reuses `just services`: models present,
   DB migrated, audio path alive. A DB that already has a `person` entity is
   already past this point (migration 002's existing backfill).
2. **Owner.** The first and only question this step may ask is the owner's
   name. Creates the `person` entity, then calls `bootstrap_initial_owner()`
   with the confirmation it already requires. No household fact (partner,
   child, pet, workplace) may be recorded before this step completes —
   the direct fix for the 2026-07-13 mis-anchoring `onboarding.py`'s own
   docstring records.
3. **Local channel.** Explains, in plain terms, what "this device, this
   network, this microphone" means once first boot completes: the local
   trusted channel will presume this owner, with a visible TTL and an
   explicit local revoke path. States that face and voice (PC-2/PC-3) are
   optional, faster paths to the same identified state — later, not now, and
   never the only recovery route.
4. **Household basics.** Runs the eight existing `onboarding.py` slots
   (`nombre`, `fecha_nacimiento`, `vive_en`, `pareja_de`, `hijo_de`,
   `mascota_de`, `trabaja_en`, `le_gusta`) — now safe to run, because step 2
   already anchored an owner.
5. **Consent.** Records, per data category (protected household, biometric
   once PC-2/PC-3 exist, retention), the local consent decisions ADR 0006
   already requires before any of them may be used.
6. **Complete.** Sets `meta.onboarding_complete = "true"`. Before this flag is
   set, any protected or self-referential question answers "not configured
   yet" — never a denial that reads as a permanent policy outcome.

Two entry points share this one state machine: the natural voice path, and a
local CLI/recovery path (`just`-driven, same shape as `reset-db`) for when
voice or biometrics are unavailable. Neither entry point is a general or
public admin API — both are loopback/local-operator constrained, and every
step is audited the same way `bootstrap_initial_owner()` already audits
itself.

### PC-2 — Consented local face evidence

Enable face enrolment only through PC-1. Store biometric templates locally,
separately from generic person facts. A local face adapter emits typed evidence
with freshness and quality metadata; it never grants permission by itself.

### PC-3 — Consented local speaker evidence

Add a local speaker enrolment/verification adapter through PC-1. Evaluate false
accepts, false rejects, changed voice, distance, noise, and microphone variation
on Pipec's actual hardware. Raw audio remains ephemeral unless an explicit later
policy changes that rule.

### PC-4 — Conservative fusion and personal response path

Fuse session, face, and voice evidence. Agreement may identify Pipec under
calibrated policy; conflict is `ambiguous`; absence or expiry is `unknown`.
Only a resolved, authorized actor may use Pipec's permitted personal/family
tools. The controller assembles a response plan; the LLM expresses only
authorized typed results.

### PC-5 — Local visual companion acceptance

For “Iroko, ¿qué ves?”, run local specialized perception in parallel:

```text
face adapter -> identity evidence
VLM/object adapters -> current scene evidence
voice adapter -> speaker evidence
controller -> identity + authorization + response plan
```

The VLM may describe a scene but is not the authority that names Pipec. The text
LLM does not receive a raw frame or decide identity. Perception claims remain
observations/inferences; relations and personal facts come from authorized
structured storage.

## Acceptance examples

- A fresh install with no `person` entity refuses every household fact until
  an owner is bootstrapped, then walks the eight-slot checklist in order —
  reproducing a corrected version of the 2026-07-13 case as a regression
  check.
- On the local trusted channel, after first boot, "¿quién soy?" greets the
  bootstrapped owner by name instead of the fixed unknown-identity copy —
  without any face or voice adapter existing yet.
- Claiming a different name than the bootstrapped owner over voice or chat on
  the same channel does not change who is presumed identified; local-channel
  presumption resolves from the session, never from spoken claims.
- Before `onboarding_complete` is set, a protected-household question answers
  with a "not configured yet" message, distinguishable from the fail-closed
  denial a configured install gives an unauthorized speaker.
- Pipec is identified from calibrated, non-conflicting local evidence and can
  ask an authorized deterministic family question.
- An unknown person receives general conversation but cannot read Pipec's
  protected data.
- Face says Pipec while voice conflicts: Iroko asks for local confirmation and
  releases no protected context.
- Camera, face, or speaker backend unavailable: Iroko explains the limitation
  and preserves the local administrative recovery route.
- “¿Qué ves?” describes only current evidence with uncertainty; it neither
  turns the frame into permanent memory nor treats a scene inference as fact.

## Explicit non-goals

- general web onboarding or family UI;
- adult-to-adult policy delegation;
- children, guests, or multi-speaker household interaction;
- directed messages, generic semantic-memory retrieval, cloud escalation,
  WorldState history, ROS2, and physical autonomy;
- PC-1 specifically: no face, no voice, no UI, no family onboarding, and no
  identity from a spoken name claim — a session on the local trusted channel
  is the only thing PC-1 lets a request presume, never a claim inside the
  message itself.

## Prerequisite and later work

This is intentionally not a Ready implementation plan. It needs a fresh
repository audit after P0-C, an accepted biometric/consent schema decision, and
a measured local model evaluation. **PC-1 is the exception:** its decision is
already accepted as [ADR 0007](../adr/0007-first-boot-and-default-posture.md),
and it needs none of the PC-2..PC-5 prerequisites above, because it only wires
together the local owner bootstrap, session registry, onboarding checklist,
and completion flag that already exist in the codebase. Its executable plan
(numbered next in [`docs/plans/`](README.md)) is written just in time once
Plan 0022's gate is green. The later `family` profile owns UI, multi-person
onboarding, household sharing defaults, and selective privacy.
