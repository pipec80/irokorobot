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

## Orthogonal policy profiles

Iroko uses one local cognitive architecture with two independent axes; this is
a product-policy choice, not a second identity system. See
[ADR 0014](../adr/0014-orthogonal-social-and-responsibility-profiles.md).

The **social profile** describes who participates:

| Profile | Primary interaction | Default privacy rule |
|---|---|---|
| `personal` | One primary owner and Iroko. | The owner has broad authority over their own permitted data and configuration. Other speakers remain public/unknown until an explicit later policy exists. |
| `family` | Multiple household members and Iroko. | Members may use permitted household data and their own allowed data. A technical owner/admin is not automatically entitled to another adult's personal data. |

The **responsibility profile** describes which bounded capabilities Iroko may
exercise: `companion`, future `care`, or future `education`. Only `companion`
is an active delivery target. Responsibility never grants identity or blanket
access; a caregiver, health professional, tutor, educator or technical
administrator requires explicit capabilities and data scope.

All combinations retain the same boundaries: identity is not authorization,
unknown is valid, local administration is the biometric recovery path, and
sensitive actions require explicit confirmation. The personal companion is the
next product milestone. General family onboarding and UI are later work under
[ADR 0006](../adr/0006-personal-and-family-companion-profiles.md).

## Future profile and consent persistence

The current SQLite installation represents one Iroko home. P3 should not add a
multi-tenant or multi-household database merely to express the social profiles.
Instead, the later migration should introduce a singleton installation-policy
record similar to:

```text
installation_profile
├── id = 1
├── social_mode: personal | family
├── responsibility_mode: companion
├── configured_by_entity_id
├── configured_at
└── updated_at
```

`responsibility_mode` is illustrative only. Activating `care` or `education`
would require a new ADR and may need capability records rather than a single
enum; this document does not prescribe that later schema.

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

**Speaker evidence calibration (Plan 0047, closed 2026-09-25).** A local, offline
study measured whether a CPU speaker embedding separates the owner from consenting
live impostors: a provisional PASS (0/24 impostor false accepts at the selected
threshold, 0/24 genuine false rejects in-sample, 6/8 replay probes accepted). It
changes no rule here: `VOICE` remains untrusted identity evidence on its own, the
study produced no enrollment or runtime adapter (PC-3B), and because replays were
accepted a voice match must never be standalone high-assurance evidence —
[ADR 0016](../adr/0016-face-and-voice-identity-fusion.md) enforces that by requiring
a face for `strong`; replay and liveness stay undefended.

**Speaker runtime evidence (Plan 0053, PC-3B; fused by Plan 0054, PC-4).** Consented
local enrolment and revocation exist behind `SPEAKER_AUTHENTICATION_ENABLED` (default
off). On a protected turn whose owner face matched, the speaker check returns a
`verified`, `unknown` or `unavailable` verdict; a `verified` voice of the same person
raises the face's assurance from `basic` to `strong`. `VOICE` is resolvable but never
trusted on its own, so it cannot identify anyone, and a voice with no owner face is
never even embedded. Replay is not defended (6 of 8 probes were accepted in the
study) and there is no liveness check. Binding a grant to one named operation is
implemented (Plan 0051, see *Locked posture and capability scope*); binding it to the
speaker remains staged by [ADR 0015](../adr/0015-owner-grant-scope-and-speaker-binding.md).

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

## Locked posture and capability scope

Per [ADR 0009](../adr/0009-locked-posture-and-scoped-capabilities.md), an
unknown actor does not disable Iroko's senses, STT, bounded general
conversation, or TTS. It disables access to protected capabilities. An unknown
or ambiguous speaker neither reads nor writes the short-term session
([ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md)) and is never
attributed or consolidated into Pipec's persistent memory.

Every PIN grant is bound to the **one operation named at unlock** (ADR 0015 decision 1,
Plan 0051, extended by [ADR 0019](../adr/0019-personal-memory-capabilities.md)). `OwnerUnlockScope`
has four members: `personal_protected_read` (the default; exactly one read of confirmed
`child_data`), `biometric_admin` (enrolling or revoking the owner's face or voice),
`personal_memory_read` (one read of the owner's own personal conversation memory) and
`personal_memory_forget` (one erasure of the owner's own personal memory). None of the
four unlocks another. A grant presented to any other operation is
refused and is **not spent**, so a bystander or a wrong call cannot burn it. A read
grant is not permission to modify memory, enroll biometrics, control lights, restart a
computer, administer the home, or invoke actuators, and an administration grant is not
permission to read protected data. Those capabilities require separately named policy
decisions, each declaring its own scope in the plan that adds it, and, where
appropriate, fresh confirmation and local safety checks. There is no global “fully
unlocked” state. The grant still proves the PIN, not the speaker (ADR 0008).

## Identity evidence

`IdentityEvidence` is immutable and contains at least:

| Field | Meaning |
|---|---|
| `source` | `face`, `voice`, `session`, `manual`, `local_unlock`, or `context`. |
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
├── assurance: none | basic | strong
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
- `assurance` is `none` for every result that is not `identified`; it never authorizes
  by itself — policy reads it only for the reserved categories.

## Fusion rules and assurance

[ADR 0016](../adr/0016-face-and-voice-identity-fusion.md) fixes the rule as one
deterministic function, `resolve_active_person`, over one enrolled owner. Fusion says
who the evidence indicates and how strongly; it never authorizes —
`evaluate_authorization` still decides whether that actor may perform the action on the
data.

| Evidence of the turn | Result | Assurance |
|---|---|---|
| Owner's face and a verified voice of the same person | `identified` | `strong` |
| Owner's face only | `identified` | `basic` |
| An optional PIN token, only when one is presented | `identified` | `strong` |
| Verified voice only | `probable` (never authorizes) | `none` |
| Face of another enrolled person, or two or more faces | `ambiguous` | `none` |
| Sources that point at different people | `ambiguous` | `none` |
| Unknown face or voice, no usable or expired evidence | `unknown` | `none` |

`basic` is enough for ordinary private data such as the child read. `strong` is required
for the categories in `HIGH_ASSURANCE_CATEGORIES` (`security` today). A capability may also
declare a minimum above the category floor: the personal-memory capabilities of ADR 0019
demand `strong` for `confirm` and `forget`, and for `biometric`, `medical` and `location`
data in every one of them (`PERSONAL_MEMORY_STRONG_CATEGORIES`), so a photograph of the owner
reaches none of it. The rank is compared through `ASSURANCE_RANK`, never with `<` on the
`str` enum. A reserved request
answered at `basic` is denied with the same generic text as any other denial; only the
authorization audit row (`policy_id` `p0.5.assurance-required`) records why, while the
server log carries the fusion reason of the turn. Positive evidence of another person vetoes even when a PIN
token is presented and does not consume it; ignorance (an unknown face, an unknown voice,
a missing signal) never vetoes and never adds. The voice is consulted only after the
owner's face matched on a protected turn. A generic turn resolves the same face first and an
observed default-scope token second, without the voice and without spending the grant
([ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) §1), except for the memory
candidates of ADR 0021: a voice turn that matches the preference gate, one that finds a
candidate waiting to be offered and a message shaped like an answer to an offer each check the
voice of that turn's own clip, in the background, concurrently with generation or before the
answer, for the person the face named; a failed face detector is
logged as `backend_unavailable` and a failed identity store as `error`, both degrading to an
unknown speaker. Evidence whose `expires_at` has passed never participates.

Since Plans 0062 and 0063 (CM-3a, [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md))
three of the ADR 0019 capabilities have a spoken caller, behind the default-off
`MEMORY_CANDIDATES_ENABLED`: `propose` (a stored taste), `read` (the first one: it asks the
policy before an offer is spoken, through `candidate_dialogue`) and `confirm` (the explicit
answer; the same step also runs inside `memory_writer.promote`). The policy minimums stay
`basic`, `basic` and `strong`, but every one of these callers demands the face and the voice
of the same person on that turn's own clip and never a token: a face alone, a PIN grant or a
second face in frame is refused before the policy is asked, and the turn is then the ordinary
one, byte for byte, so nothing reveals that a candidate exists. `correct` and `forget` are
still not connected (CM-6).

**The household pair (Plan 0065, [ADR 0022](../adr/0022-household-rules-and-third-party-memory.md)
decisions 3 and 4).** What the owner says about their own children, partner and pets has its own
pair of capabilities, `propose_household_memory` and `confirm_household_memory`, apart from the
five personal ones (whose rule, own data only, did not move). The pair is the owner only, on
`household` data, at `strong` (face and verified voice, never a token: any `local_unlock` item
denies it, so it has no PIN route) and needs granted consent only for the sensitive categories
other than `child_data`, because the owner speaks for a child as guardian. Because the policy is
pure, the request carries two closed fields the **caller classifies before any read**
(`subject_relation`: `owner`, `child`, `partner`, `pet`; `fact_shape`: `literal`, `relation`),
never from stored rows: literals are allowed for a `child` or a `pet`, relations for a `child`,
a `partner` or a `pet`, and everything else, the partner's own facts included, is denied
(`cm3b.household-memory.*`). Other adults get their name and relationship and nothing more until
the `family` profile enrols them. **Nothing consumes the pair yet** (an architecture guard pins
it); the first consumer is the Step 0 import. The writer that stores such facts
(`memory/canonical_writer.py`) assigns the classification itself and records the owner as asserter
and confirmer, with the channel; see [memory-and-world-state](memory-and-world-state.md).

**The assisted channel and the fence (Plan 0070, [ADR 0024](../adr/0024-seed-load-senses-secrets-and-channels.md)
decisions 6, 9, 10 and 15).** A second import channel, `import_assisted`, records a commissioning
interview in which the interviewer may not be the owner: the asserter is the owner's entity, the
confirmer is the owner's entity only when the owner (or a builder who is the owner) confirmed, and the
`commissioning_records` row keeps the interviewer's label and role, the confirmation mode and the
disk-encryption declaration (a declaration, never verified). The import channels authorize by local
administration, not by face and voice, and they change nothing about who may *read*. The writer fences
the household: an adult child, a relative and a contact hold a role that no relabeling can turn into
membership. The record also keeps a closed inventory of identity modalities, `pin`, `face`, `voice`
(enrollable today) and `fingerprint`, `iris`, `token` (reserved: a new modality is an adapter, its own
enrolment and consent, and an ADR that sets its assurance). Face and voice remain evidence, never
authorization.

**The commissioning session (Plan 0072, ADR 0024 decisions 13 to 15).** `just commission` is a state
machine read from the database and from the server's state (one `/health` probe): it tells the
interviewer the next step, never asks for the server to be both on and off, and delegates the three
server-stopped steps (`reset-db`, `setup-personal`, `seed-import`) by naming their command. With the
server running it shows the biometric notice (`docs/legal/biometric-notice-v1.md`, version `v1`; a legal
review is pending before it is used with anyone but the builder-owner), enrols the face in five frames and
the voice in three references. **Each enrolment spends one one-use owner-unlock token for
`biometric_admin`, so every frame and every reference asks for the PIN again** (a mistyped PIN is asked
again up to three times). The enrolment endpoints are the existing ones and did not change: the biometric
consent is granted by the enrolment itself, and the frames and the audio are embedded and discarded. At
the closing, with the server stopped, the interviewer records the pre-reset and the baseline backups (path
and destruction date), the three consents of the operations plane (telemetry, remote support, backup with
a label, [ADR 0025](../adr/0025-remote-administration-backup-updates-and-telemetry.md) decision 10) and
attests, for each capability that exists today, whether it is supported, configured and verified. The
modalities enrolled are **derived** from the database (an active PIN credential, a face consent, voice
references at or above `SPEAKER_MIN_REFERENCE_COUNT`), never typed. The acta is written under
`data/commissioning/` (ignored by git, no household value) and the window is closed for good on that
database; a recorded consent builds and enables nothing.

**The level of each channel and the importer's bypass (Plan 0071, ADR 0024 decisions 7 and 11).**
The voice channels authorize by the face **and** the voice of the same person on the turn's own
clip, never a token, through a spoken offer and an explicit spoken answer. The import channels
authorize by local administration: whoever runs `just seed-import` on the server's machine with the
server stopped (the command probes `/health` once and refuses a server that answers, and refuses a
locked database), after a dry run, the owner's review and the typed word `SI`. The importer
**bypasses the policy, the audit-before-effect rule and the `memory_enabled` switch on purpose**:
it is an administration act, not a conversation, and what replaces them is the commissioning record
(who interviewed, the confirmation mode, the file's hash, the counts, each section's status) and one
log line with counts only. It never creates the owner (the owner and the PIN must exist and the
owner's name in the file must fold to the stored one). Only `memory/write_types.py` and
`memory/seed_import.py` may name an import channel (an architecture guard). The classification and
the reads do not change with the channel. Whoever can run commands on the server can write as the
owner; that was already true, and the alternatives (the PIN, the PIN plus the face) are revisited
when a second adult is enrolled or the server is shared.

**The local admin CRUD after the closing (Plan 0073, [ADR 0025](../adr/0025-remote-administration-backup-updates-and-telemetry.md)
decisions 2 level A, 4, 11).** Once the alta closes the importer no longer runs; `iroko-admin` (run on
the machine over SSH, server stopped) is the amendment path. It writes through the same canonical
writers with a new channel `admin_local` (not an import channel) and never touches SQL itself. The
authority is access to the machine, **plus the owner's PIN for a change to sensitive data (`medical`,
`location`, `security`), a contact, or anyone but the owner** — verified offline against the stored
credential and read without echo. A second adult or a `representative` is refused until the support
session exists (decision 3). Every mutating operation writes one audit event (actor, role, channel,
operation, field or section id, outcome, time; **never a value**); a `revoke` is a supersede to
inactive, never a hard delete (CM-6).

The PIN is optional and administrative: an optional `strong` factor — consulted only on a
turn the owner's face did not resolve, never once the face matched — and the credential of
local administration. When face or voice fail, recovery is local administration on the
server host (ADR 0006), never a spoken step. Replay and liveness are measured, not
defended.

These are product rules, not permanent numeric truths. Thresholds belong in
configuration and require real family evaluation, including false-accept and
false-reject cases.

When the operation is low-risk, Iroko may ask:

> “Creo que eres Paula, ¿es correcto?”

For sensitive operations, conversational confirmation alone may be
insufficient; policy can require a fresh one-use local unlock, calibrated
biometric evidence, owner approval, or another factor.

## Conversation isolation

`conversation_id` is a client-chosen label: it must never act as identity or
authorization and it never selects history
([ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md)).

There is **one** short-term session slot in the process, because the device has one
microphone and a half-duplex loop. It belongs to a person id, so two public ids share the
identified person's session and one id shared by two people does not. It is bounded by
3000 characters and 180 seconds of silence (measured from the last written turn) and is
never persisted. Another identified person replaces it; an unknown, probable or ambiguous
speaker *suspends* it for that turn — the turn reads nothing, writes nothing, and the
owner's session survives and keeps ageing. A write carries the generation it read and is
dropped when the session moved on. The earlier proposal of per-interaction keys
(`voice:<session-id>:person:<id>`) is replaced by this slot; per-person sessions for several
enrolled members belong to the family profile (P3).

Do not merge an unknown speaker's history into a known person's history after a
late guess: there is no reconciliation, the unknown turn simply is not kept.

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
| Read, propose, correct own personal memory (ADR 0019) | Yes, own data only; `strong` for `biometric`, `medical`, `location` | No | No | No |
| Confirm own personal memory (ADR 0019); spoken answer to an offer (ADR 0021) | Yes, `strong` (face and verified voice of that turn, never a token) | No | No | No |
| Forget own personal memory (ADR 0019) | Yes, `strong` and a PIN grant spent for `personal_memory_forget` | No | No | No |
| Propose, confirm household memory about own children, partner (name and relationship only) and pets (ADR 0022; policy only) | Yes, `strong` (face and verified voice, never a token) | No | No | No |
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

### Calibration-study boundary

Before a biometric similarity score becomes runtime evidence, a bounded local
study must separate reusable engineering from private acceptance material:

- pure threshold/FAR/FRR math and corpus-schema tests use synthetic vectors;
- the backend package, model revision, license, preprocessing and score
  direction are frozen before capture;
- reference and probe sessions are separate, and live impostors participate
  only with explicit consent;
- raw frames/audio, embeddings, paths and per-sample scores remain in a
  gitignored local corpus and are deleted after an aggregate result is accepted;
- tracked evidence contains aggregate counts/rates, conditions, latency,
  limitations and the model identity, never raw biometrics or participant
  names;
- any measured false accept disqualifies that threshold; absence of a safe
  separating threshold is a valid FAIL, not permission to weaken the gate;
- replay/spoof results are reported separately from live-impostor FAR and feed
  fusion/liveness policy rather than being hidden in an average.

A calibration PASS is provisional evidence for a later runtime plan. It does
not itself create enrollment, trust an evidence source or grant authorization.

## Unknown, ambiguity, and disclosure

Safe behavior examples:

- Unknown speaker asks a general question: answer without household memory.
- Unknown speaker asks about the children: return `unauthorized`, not “I don't
  know” if the data exists but cannot be disclosed.
- Face says Felipe and voice says Paula: return `ambiguous` and request a safer
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
6. Prove “Joaquín y Martina” and the paired non-disclosure case through the real
   audio path.
7. Integrate and calibrate consented face evidence.
8. Evaluate and add local speaker verification.
9. Add conservative fusion, then diarization only when multi-speaker audio is a
   demonstrated requirement.

No step may weaken the audio contract, enroll biometrics automatically, or use
face/voice similarity as an authorization substitute.
