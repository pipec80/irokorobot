# Personal companion design — Iroko and Pipec

> **Status:** Proposed — starts only after P0-C and P0 runtime acceptance pass.

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

### PC-1 — Local personal administration

Provide a local-only administrative path, initially CLI or controlled local
operator action rather than a general UI, to create/review Pipec's personal
profile, bootstrap the owner role, and record consent decisions. The path must
be loopback/local-admin constrained, auditable, and recoverable after biometric
failure.

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
  WorldState history, ROS2, and physical autonomy.

## Prerequisite and later work

This is intentionally not a Ready implementation plan. It needs a fresh
repository audit after P0-C, an accepted biometric/consent schema decision, and
a measured local model evaluation. The later `family` profile owns UI,
multi-person onboarding, household sharing defaults, and selective privacy.
