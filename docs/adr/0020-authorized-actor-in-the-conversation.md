# 0020 — Identify the speaker on every turn and keep short-term continuity for the identified person

- **Status:** Proposed (2026-10-09, revised 2026-10-13) — becomes Accepted when the plan that implements it closes;
  until then nothing in `server/src` follows it
- **Date:** 2026-10-09
- **Builds on:** [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md),
  [ADR 0015](0015-owner-grant-scope-and-speaker-binding.md),
  [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md)
- **Supersedes:** the sentence of [ADR 0016](0016-face-and-voice-identity-fusion.md) §5 that says
  "Identity is resolved only on protected turns, so the embedding (about 0.5 s, one per request) is
  paid there and never on public turns", and the part of the same section that makes a presented
  local-unlock grant (today issued by the PIN) unreachable after a face match for every operation
  (decision 5 below). The rest of §5,
  §1 to §4 and §6 to §9 stand.
- **Implemented by:** CM-2, plan to be written (the next free plan number is 0061)

## Context

The roadmap's CM-2 row asks that the actor resolved by face, voice or PIN reach the generic
conversation, with no name interpolated into the prompt and no widened grant, and that its first
visible result be short-term continuity: the last turns of the identified person reach the next
turn. Today there is none, for two independent reasons.

### What holds today (verified in code at `main` `bbbab5c`, 2026-10-09)

1. A generic turn never resolves identity. The controller returns no decision for it and none of
   the three channels (`POST /transcribe`, `POST /transcribe/stream`, `POST /chat`) passes an
   `active_person` to `process_text_turn` or `prepare_text_turn`. Face, voice and PIN resolution is
   lazy and runs only when a protected branch awaits the resolver. The cost of identity on a generic
   turn is therefore zero today.
2. Even a resolved actor would not open the history. `text_turn.py` opens the working history only
   for `IdentityEvidenceSource.MANUAL` evidence, and no production code emits it
   (`IdentitySessionRegistry.select_person` has no caller outside tests). Every generic turn runs
   with `history=None` and `context=None`; `record_text_turn` writes the turn to working memory and
   clears it at once ("Turn memory: discarded (no verified identity — working memory cleared)").
3. Working memory is two module dictionaries in `server/memory/working.py` (turns and emotions),
   keyed by an arbitrary string, bounded only by `WORKING_MEMORY_SIZE` (20 messages). It has no
   time limit and no character limit.
4. The history reaches the model as chat messages before the current turn (`llm._build_messages`),
   not inside the system prompt. The speaker's name is never interpolated into the prompt; the
   presentation guidance is static text gated on `MANUAL` evidence.
5. The robot attaches a webcam frame on every turn when `ROBOT_FACE_AUTH_ENABLED` is on (default
   off); the server reads it only when `FACE_AUTHENTICATION_ENABLED` is on (default off). `/chat`
   carries no frame or audio, only an optional `X-Iroko-Identity-Token`.
6. `just chat-test` expects continuity between unauthenticated public requests of `/chat`; the
   server cannot give it today, so its "continuity" check should fail.
7. ADR 0019 left `forget` unreachable on a turn whose owner face matched, because ADR 0016 §5 does
   not consult a presented PIN token after a face match ("Fixing it belongs to the CM-2 ADR that
   revises §5"). `confirm` has no PIN route by design.
8. The PIN is checked in one place only: `unlock()` in `cognition/owner_authentication.py` calls
   `verify_pin` and, on success, issues a grant with `issue_for_person(..., source=LOCAL_UNLOCK,
   scope=...)`. Everything downstream (the grant registry, the scopes, fusion and the policy) sees
   only that scoped `LOCAL_UNLOCK` grant, never the PIN.
9. The voice is consulted only after the owner's face matched, on protected turns. On 2026-10-13 no
   voice profile is enrolled (both voice consents were revoked by the acceptance runs of Plans 0053
   and 0051), so those turns stay at `basic`; `strong` through face and voice comes back with a
   re-enrolment (`just speaker-auth-demo --enroll`).

### Facts the design has to respect

1. Identity evidence is never authorization (ADR 0006, ADR 0008, ADR 0009). The locked posture
   keeps bounded general conversation for an unknown actor; request-local working context may be
   kept only inside an isolated unknown interaction, never merged into a known person's history.
2. `conversation_id` separates working histories and is never identity or authorization
   (`identity-and-access.md`, *Conversation isolation*).
3. Face alone gives `basic`; voice corroboration gives `strong`; ordinary private data needs only
   `basic` (ADR 0016 §1 to §3). A photograph still identifies at `basic` (ADR 0016 §9, measured, not
   defended).
4. `ambiguous` and `unknown` are valid outcomes. Two faces, another enrolled person's face, or
   sources that point at different people make a turn `ambiguous`; `ambiguous` exposes neither
   person's private context.
5. Durable memory stays blocked until its own slice: writes CM-3, episodes CM-4, retrieval CM-5.
   Connecting the actor is not enabling durable memory.
6. Grants are process-local; `UVICORN_WORKERS` must stay 1.

## Decision

### 1. Every turn tries to identify its speaker, cheaply

Each generic turn resolves the speaker with the evidence the turn already carries, in a mode that
**never spends a grant** and **never computes a voice embedding**:

- voice and streaming turns: the face in the frame, when face authentication is on and a frame was
  sent;
- `/chat`: the optional identity token of the default scope, observed and not spent;
- anything else: no evidence, so the turn is `unknown`.

The voice is not consulted on a generic turn (the roughly 0.5 s embedding is saved on every chat
turn), so a face identifies at `basic`; a token observed on `/chat` keeps the assurance its grant
already gives. The voice is computed on demand, as today, on a protected turn whose operation
needs `strong`. Resolving a turn must not change what a protected
branch decides: the protected resolvers are unchanged except by decision 5.

### 2. Who has continuity

Only a person `identified` by a trusted source (`FACE`, `LOCAL_UNLOCK` or `MANUAL`) with assurance
at least `basic` has short-term continuity. This gate opens **working memory only**. The existing
`MANUAL` gate on the persistent context, vector retrieval, consolidation and the presentation
guidance is untouched, so durable memory stays off for every speaker, the identified owner included.
A speaker who is not identified has no continuity at all: the turn is answered and forgotten, as
today. No history of an unknown speaker is kept, not even request-local.

### 3. The continuity session

There is one live conversation at a time, in process memory, never persisted: the device has one
microphone and the loop is half-duplex. It records the person it belongs to (key
`continuity:person:<id>`, an opaque scope that carries the person id; `conversation_id` is never
used as identity). Two limits, both read from settings:

- **size:** at most 3000 characters of history; the oldest turns leave first. The existing
  `WORKING_MEMORY_SIZE` cap stays as an upper bound on messages;
- **silence:** a conversation not extended for 180 seconds is deleted.

Setting names and defaults are fixed by the plan (a pair such as `WORKING_MEMORY_MAX_CHARS=3000`
and `WORKING_MEMORY_IDLE_SECONDS=180`, both added to `.env.example`). The silence is measured from
the last turn written; a suspended conversation (below) keeps ageing and expires at 180 seconds like
any other.

### 4. Transitions

| The next turn is | Effect on the live conversation | Does the turn read or write it? |
|---|---|---|
| the same identified person | continues | reads it, then writes the new turn |
| another identified person | the previous conversation is deleted; a new one starts | reads nothing, writes its own |
| `ambiguous` | **suspended**: kept, but not read, not written and not shown to anyone | no |
| `unknown` (including no evidence) | deleted | no |
| idle for 180 s | deleted | n/a |

A suspended conversation resumes only if the same person is identified again before it expires. A
change of speaker is seen only through the face (decision 1): a second person who speaks while the
owner's face stays in front of the camera is not detected, which is the same limit ADR 0016 already
accepts for `basic`.

### 5. A local-unlock grant is consulted by operation, not by turn (supersedes ADR 0016 §5)

A local-unlock grant is the one-use, scoped token that a local factor issues. Today the only such
factor is the PIN; any future local factor that issues the same scoped `LOCAL_UNLOCK` grant (for
example a fingerprint reader) is covered by this decision without a new ADR, although adding the
factor itself needs its own.

ADR 0016 §5 stands for the token of the default scope: when the owner's face matched, that token is
not consulted and stays unspent. The new rule is for operations that declare their own grant:

> After the owner's face matched, a presented token is consulted if and only if its scope is the
> scope the requested operation declares **and** the evidence of the turn does not already satisfy
> that operation (a spent grant that is required and missing, or an assurance rank below the
> operation's minimum). The consuming resolver then spends it and the turn gains `LOCAL_UNLOCK`
> evidence at `strong`.

Consequences: a `personal_protected_read` token is still ignored after a face match (Plan 0054's
decision is kept); a `personal_memory_forget` token is consulted and spent on a `forget` turn even
when the face matched, so `forget` becomes reachable once a route wires it; a token of any other scope is still refused
without being spent (ADR 0015 decision 1). The vetoes of ADR 0016 §4 apply first: another enrolled
person's face, or two or more faces, make the turn `ambiguous` and no token is consumed. `confirm`
keeps having no PIN route.

CM-2 implements this rule in the fusion resolver: a resolver built for a declared scope applies it,
and one built for the default scope behaves exactly as today. Each route adopts a resolver built
for its operation's own scope when that operation is wired (ADR 0019 §6, obligation 1); until then
the routes keep their request-wide resolver of the default scope.

### 6. What the prompt receives

The history goes in the chat messages, as `llm._build_messages` already does. No name, id or role of
the speaker is interpolated into the system prompt or the history, and no grant widens. The
presentation guidance and its `MANUAL` gate do not change. Generation, the streaming protocol and
the emotion function are untouched.

### 7. `just chat-test`

`/chat` without a token stays stateless, so the A/B isolation check stays as it is. The continuity
check is rewritten to use an owner token (the script asks for the PIN as a hidden prompt, never
logs it, unlocks with the default scope once per run and finishes within the token's lifetime;
the token is only observed, never spent); without a token it reports "continuity
not checked" instead of failing. The script keeps being a smoke test and gains no new endpoint.

### 8. Acceptance

The plan that implements this ADR has an automated acceptance and a run by Pipec on real hardware:
(a) a sentence followed by a question that depends on it, answered as a continuation; (b) a second
person in frame, which suspends the history and does not answer from it; (c) more than 180 seconds
of silence, after which the context is gone; (d) the added latency of the face check on a generic
turn, measured and recorded (it is not known today). Decision 5 is accepted by automated tests
only: a resolver built for the `personal_memory_forget` scope consults and spends a forget grant
after a face match, with the real resolvers; there is no spoken `forget` to try until CM-6 wires
it. Durable memory remains blocked and tested as blocked.

## Alternatives considered

- **Keep identity lazy and give continuity only to `MANUAL` evidence.** Rejected: no production path
  emits `MANUAL`, so the companion would still forget the previous sentence; emitting `MANUAL` from
  a face would turn face evidence into the persistent-memory key, which this ADR does not open.
- **Continuity for unknown speakers in an isolated per-conversation session.** Allowed by ADR 0009
  but rejected by Pipec on 2026-10-09: it needs a way to say "the same visitor" without using
  `conversation_id` as identity, and it keeps a stranger's words in memory.
- **Delete the history on an `ambiguous` turn.** The roadmap's earlier wording; rejected by Pipec
  because a visitor entering the frame would cost the owner the context of a conversation they are
  still having. Suspending exposes nothing: no turn reads a suspended conversation.
- **Face and voice on every generic turn.** Detects a change of speaker better (a voice mismatch
  becomes `ambiguous`) at about 0.5 s per turn and a dependency on the voice model for all chat.
  Rejected: chat needs only `basic`.
- **Always consult a presented PIN token, even after a face match.** Would also rescue the "hoarse
  day", but reverses Plan 0054's accepted-on-hardware decision and spends a token on turns that do
  not need it. Rejected.
- **Leave `forget` unreachable with a face.** Rejected: the spoken "forget this" in front of the
  camera would never work, which ADR 0019 named as a defect to fix here.
- **One continuity conversation per person.** Not needed with one enrolled owner and a half-duplex
  device; revisit with the family profile (P3).

## Consequences

### Positive

- The companion remembers the last few turns of the person using it, for the first time, with no
  durable memory and no new route.
- Unknown and ambiguous speakers get nothing from the owner's conversation, and an unknown speaker
  leaves nothing behind.
- `forget` becomes reachable by voice with a face in frame, through its own spent grant.
- Chat turns do not pay the voice embedding.

### Negative

- A photograph of the owner in front of the camera receives the owner's continuity (`basic`,
  ADR 0016 §9).
- A second person speaking while the owner's face stays in frame is not detected.
- Continuity exists only where there is evidence: with `ROBOT_FACE_AUTH_ENABLED` and
  `FACE_AUTHENTICATION_ENABLED` off, voice and streaming turns are `unknown` and stateless, as
  today; `/chat` needs a token.
- A face check is paid on every generic turn when face authentication is on; the history makes the
  3B model's prompt longer and slower. Both are measured in the acceptance, not assumed.
- The state is one process's memory: a restart, or a second worker, loses the conversation.
- A dark day (the face fails) clears the conversation as an `unknown` turn.

## Test consequences

The tests that pin "a generic turn has no history and clears working memory" change on purpose
(`test_text_turn.py`, `test_chat_endpoint.py`, `test_transcribe_stream.py`,
`test_transcribe_pipeline.py`, `test_vision_dialog.py` and `test_chat_test.py`, among the ones the
plan lists after reading them). New tests pin each row of the transition table, the character cap
and the silence limit with a fake clock, that an unknown or ambiguous turn reads and writes nothing,
that no durable path opens (retrieval, consolidation and context stay off), that no resolution on a
generic turn spends a grant or computes a voice embedding, that the default-scope token is still
ignored after a face match and the forget-scope token is consulted, and that the speaker's name
reaches neither the prompt nor the history.

## Docs to update when this ADR is Accepted

The ADR index row; ADR 0016's status line (§5 partially superseded) and ADR 0019's follow-up and
negative consequences; the CM-2 rows of the roadmap and the conversational-memory map (an
`ambiguous` turn suspends instead of clearing); `identity-and-access.md` (fusion paragraph and
*Conversation isolation*); the working-memory rows, the diagram line and the Archify diagram of
`current-state.md`; `.env.example`; the operator manual's `chat-test` line; the plan indexes.

## Review

Revisit on a measured false-rejection rate of the face that clears conversations too often, a
second enrolled household member (P3, per-person conversations), a measured latency that makes the
per-turn face check unacceptable, liveness or replay defence (ADR 0016 §9), the first capability
that consumes a personal-memory action (CM-3 onward), a mandatory voice check on chat, or a second
local-unlock factor such as a fingerprint reader on the robot (it would be another verifier of the
same scoped grant, so decision 5 holds, but the sensor itself needs its own ADR and the privacy
contract of the senses).

## Follow-up

The CM-2 plan (number 0061 at the time of writing): thread the resolved actor through the channels,
the working-memory session with its two limits, the per-operation resolver, the `chat-test`
adaptation and the acceptance above. Written only after Pipec accepts this ADR.
