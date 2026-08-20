# Identity, household access, and consent

> **Status:** Canonical target design
>
> **First safety rule:** Iroko must never assume that the current speaker is the
> configured owner.

## Why this is P0

The current prompt can declare that whoever is speaking is `owner_name`, and
voice interactions share `voice-primary`. That was useful for a single-user
prototype but is unsafe in a household: a child, partner, guest, or distant
speaker can inherit the owner's conversational context and receive owner data.

Identity resolution and authorization therefore precede broader memory,
onboarding, personality adaptation, and physical actions.

## Installation policy profiles

Iroko uses one local cognitive architecture with two installation profiles;
this is a product-policy choice, not a second identity system.

| Profile | Primary interaction | Default privacy rule |
|---|---|---|
| `personal` | One primary owner and Iroko. | The owner has broad authority over their own permitted data and configuration. Other speakers remain public/unknown until an explicit later policy exists. |
| `family` | Multiple household members and Iroko. | Members may use permitted household data and their own allowed data. A technical owner/admin is not automatically entitled to another adult's personal data. |

Both profiles retain the same boundaries: identity is not authorization, unknown
is valid, local administration is the biometric recovery path, and sensitive
actions require explicit confirmation. The personal profile is the next product
milestone. General family onboarding and UI are later work under
[ADR 0006](../adr/0006-personal-and-family-companion-profiles.md).

## Future profile and consent persistence

The current SQLite installation represents one Iroko home. P3 should not add a
multi-tenant or multi-household database merely to express the two profiles.
Instead, the later migration should introduce a singleton installation-policy
record similar to:

```text
installation_profile
├── id = 1
├── mode: personal | family
├── configured_by_entity_id
├── configured_at
└── updated_at
```

The existing v4 facts/relations retain their `visibility` and `sensitivity`.
P3 consent persistence should add explicit, revocable grants rather than an
unstructured JSON flag on a person:

```text
consent_grants
├── id
├── subject_entity_id
├── grantee_kind: person | role
├── grantee_entity_id | grantee_role        (exactly one)
├── action
├── data_category
├── status: granted | revoked
├── valid_from / valid_until
├── granted_by_entity_id
├── granted_at / revoked_at
└── reason
```

`authorization_audit_events` remains the decision trace and must not contain a
protected value. The schema controls Iroko's runtime disclosure; it does not by
itself encrypt a copied SQLite file or replace operating-system disk security.
This is a target design only: no migration, UI, or public consent input is
authorized until a later Ready plan specifies constraints, indexes, lifecycle,
and rollback.

## Separate concepts

| Concept | Question | It does not prove |
|---|---|---|
| Identification | Which person does the evidence indicate? | That the evidence is fresh enough or that access is allowed. |
| Authentication | Does fresh evidence satisfy the method policy for this interaction? | Permission for a particular datum or action. |
| Authorization | May this actor perform this action on this data now? | That the underlying fact is true. |
| Face recognition | Who may be visible? | Who produced the audio or has permission. |
| Speaker identification | Whose voice is most similar? | That the speaker is alone or authorized. |
| Speaker verification | Does this voice match a claimed person? | Permission for every action. |
| Diarization | How many speakers and which segment belongs to each? | Their names. |
| Session identity | Who authenticated or selected this session? | Who is physically present. |
| Active person | Who is most likely interacting now? | Authorization by itself. |
| Role/policy | What may this actor do with this data? | That an observation or fact is correct. |

These values can agree, disagree, or be absent. Conflict is represented as
`ambiguous`; it is not resolved by choosing the highest score silently.

## Progressive authentication

[ADR 0008](../adr/0008-progressive-owner-authentication.md) defines one
authentication pipeline with replaceable evidence producers. The first useful
producer is an explicit local one-use unlock. Consented face, speaker, and a
future fingerprint reader can later produce the same typed, expiring evidence.
They do not create parallel authorization paths.

Persistent installation data includes the owner, roles, onboarding state,
configured methods, consent, and audit. Authentication itself is transient:
person ID, method, issue/expiry times, scope, opaque token reference, and
consume/revoke state. The database must not contain a durable global
`authenticated = true` switch. Such a boolean may be calculated for display or
branching from fresh evidence, but it is not an authority.

The initial unlock is intentionally one protected interaction with a short
TTL. It proves possession of the local unlock secret, not that the current
voice or face is physically Pipec. Requests without fresh, unconsumed evidence
remain unknown. Device ownership, loopback origin, a spoken name, prompt text,
or `conversation_id` never authenticates a person.

## Identity evidence

`IdentityEvidence` is immutable and contains at least:

| Field | Meaning |
|---|---|
| `source` | `face`, `voice`, `session`, `manual`, or `context`. |
| `candidate_person_id` | Existing SQLite entity ID, or null when no match exists. |
| `confidence` | Evidence-specific calibrated/estimated confidence. |
| `observed_at` | Timezone-aware UTC observation time. |
| `reference` | Safe observation/profile reference, never raw biometric content. |
| `expires_at` | Freshness boundary for transient evidence. |

Evidence does not contain a face embedding, voiceprint, frame, or audio sample.
Those remain in their local specialized stores and are referenced indirectly.

## Active person context

The first implementation should align with the current SQLite entity key:

```text
ActivePersonContext
├── person_id: int | null
├── display_name: str | null
├── status: identified | probable | unknown | ambiguous
├── confidence: Confidence
├── role: owner | adult | child | guest | unknown
├── evidence: immutable collection[IdentityEvidence]
├── resolved_at: aware UTC datetime
└── expires_at: aware UTC datetime
```

The current database uses integer entity IDs. Event and observation envelopes
may use UUIDs, but Codex must not invent a person-ID migration merely because
other domain IDs are UUIDs.

### Invariants

- Default construction produces `unknown`, no `person_id`, role `unknown`, and
  no authorization.
- `identified` requires policy-defined corroboration, not just a non-null name.
- `ambiguous` retains competing evidence and does not expose either person's
  private context.
- Expired evidence does not participate in a new turn.
- Display names are presentation only; IDs are used for relationships and
  access decisions.
- Manually confirmed identity is explicit evidence with its own expiration.

## Initial fusion rules

Rules are configurable and calibrated with the household. A conservative
starting policy is:

```text
face >= face_identified_threshold
+ voice >= voice_identified_threshold
+ both point to the same entity
=> identified

one strong source, no conflict
=> probable

strong sources point to different entities
=> ambiguous

no usable evidence
=> unknown
```

These are product rules, not permanent numeric truths. Thresholds belong in
configuration and require real family evaluation, including false-accept and
false-reject cases.

When the operation is low-risk, Iroko may ask:

> “Creo que eres Sofía, ¿es correcto?”

For sensitive operations, conversational confirmation alone may be
insufficient; policy can require a fresh one-use local unlock, calibrated
biometric evidence, owner approval, or another factor.

## Conversation isolation

`conversation_id` separates working history and must never act as identity or
authorization. The global voice ID is transitional.

After active-person resolution exists, a voice working session should be scoped
to an interaction/session and resolved person when known, for example:

```text
voice:<session-id>:person:<entity-id>
voice:<session-id>:unknown
```

Do not merge an unknown speaker's history into a known person's history after a
late guess without an explicit reconciliation rule.

## Household roles

The first local policy uses a small set of roles:

| Role | Intended scope |
|---|---|
| `owner` | Configure the household, manage memory/biometrics/policies, and access authorized family data. |
| `adult` | General household access; private data and modifications remain configurable. |
| `child` | Own/general age-appropriate information; no adult-private data or direct memory administration. |
| `guest` | Conversation and public household capabilities only; no family memory by default. |
| `unknown` | Minimal safe conversation; no protected retrieval or mutation. |

`owner` is an authorization role, not a social claim over another adult's data.
In the family profile, an adult's personal/private data remains unavailable to
the owner unless a separate explicit policy permits that access.

A future service identity for authenticated internal adapters is separate from a
human role. Do not model a device as a family member.

## Data visibility and sensitivity

Role alone is insufficient. Stored knowledge needs both visibility and
sensitivity metadata.

Suggested visibility:

- `household`: visible to authorized household members;
- `adults`: restricted to owner/adults allowed by policy;
- `personal`: visible to the subject and explicitly authorized roles;
- `private`: owner/subject policy only;
- `public`: safe for guests;
- `temporary`: available only inside an active context and TTL.

Suggested sensitivity:

- `normal`;
- `private`;
- `biometric`;
- `medical`;
- `location`;
- `child_data`;
- `security`.

These categories drive retrieval, logging, backup, cloud eligibility, and
retention. They are not adjectives inserted into an LLM prompt after retrieval.

## Authorization decision

Authorization is evaluated before reading protected memory or invoking a tool:

```text
AuthorizationDecision
├── decision: allowed | denied | requires_confirmation
├── actor_person_id: int | null
├── role
├── action
├── resource or data categories
├── policy_id
├── reason safe for logs and user explanation
├── evaluated_at
└── expires_at or turn scope
```

No decision means denied. `allowed` applies only to the named action and data
categories for the current turn; it is not a reusable master permission.

### Correct order

```text
request
  -> resolve/confirm actor
  -> authorize intended retrieval/tool/action
  -> fetch minimum allowed data
  -> build bounded context
  -> generate response
  -> validate no protected claims leaked
```

Filtering after the LLM has seen data is not access control.

## Initial role matrix

The matrix is a starting policy and must remain configurable:

| Capability | Owner | Adult | Child | Guest/unknown |
|---|---:|---:|---:|---:|
| General conversation | Yes | Yes | Yes | Yes, bounded |
| General household facts | Yes | Yes | Age-appropriate | No by default |
| Own profile | Yes | Yes | Yes | No |
| Another person's private memories | Policy | Policy | No | No |
| Modify confirmed memory | Yes | Confirmation/limited | Propose only | No |
| Enroll biometrics | Yes with subject consent | Configurable with consent | No direct administration | No |
| Export/delete household memory | Yes | No | No | No |
| Execute physical actions | Policy + local safety | Policy + local safety | Restricted | No by default |
| Approve cloud use of sensitive data | Explicit policy | Usually no | No | No |

## Biometric consent

- “Me llamo X” does not authorize face or voice enrollment.
- Enrollment requires an explicit action and consent appropriate to the subject.
- Child enrollment follows the owner's configured policy and applicable legal
  requirements; it is never silently inferred.
- Guests are never enrolled automatically.
- Raw frames and voice samples are not retained by default.
- Embeddings are sensitive biometric data even if they are not photographs or
  playable audio.
- The owner/subject must be able to inspect, revoke, delete, and optionally
  exclude biometric profiles from backup.

## Unknown, ambiguity, and disclosure

Safe behavior examples:

- Unknown speaker asks a general question: answer without household memory.
- Unknown speaker asks about the children: return `unauthorized`, not “I don't
  know” if the data exists but cannot be disclosed.
- Face says Felipe and voice says Sofía: return `ambiguous` and request a safer
  confirmation; do not choose the higher score.
- Probable child asks for their own birth date: policy may allow after a simple
  confirmation.
- Probable speaker asks to delete memory: require stronger identity and explicit
  confirmation.

The response must not reveal that a protected fact exists while refusing it
unless the policy explicitly permits that disclosure.

## Relationship to personality

Role and relationship context may adapt vocabulary, pacing, and warmth, but they
do not create separate personalities. Iroko remains one identity with different
social policies. Personality never changes permissions.

## Implementation sequence

1. Add pure typed evidence, active-person, and authorization models.
2. Replace owner-by-default with unknown-by-default at the cognitive boundary,
   preserving current endpoints through a compatibility adapter.
3. Connect first boot and the confirmed owner/relationship data path.
4. Produce short-lived, consume-once session/manual evidence through an
   explicit local unlock.
5. Resolve that evidence at channel boundaries and enforce authorization before
   deterministic family tools and retrieval.
6. Prove “Máximo y Dominga” and the paired non-disclosure case through the real
   audio path.
7. Integrate and calibrate consented face evidence.
8. Evaluate and add local speaker verification.
9. Add conservative fusion, then diarization only when multi-speaker audio is a
   demonstrated requirement.

No step may weaken the audio contract, enroll biometrics automatically, or use
face/voice similarity as an authorization substitute.
