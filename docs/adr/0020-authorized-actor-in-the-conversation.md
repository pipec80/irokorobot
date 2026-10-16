# 0020 — Identify the speaker on every turn and keep short-term continuity for the identified person

- **Status:** Accepted (2026-10-13, Pipec) — proposed 2026-10-09 and revised 2026-10-13 after an
  independent completeness audit; accepted when Plan 0061 closed, with the four acceptance cases
  of §10 run on real hardware
- **Date:** 2026-10-09
- **Builds on:** [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md),
  [ADR 0015](0015-owner-grant-scope-and-speaker-binding.md),
  [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0018](0018-user-emotion-decided-apart.md),
  [ADR 0019](0019-personal-memory-capabilities.md)
- **Supersedes:** the sentence of [ADR 0016](0016-face-and-voice-identity-fusion.md) §5 that says
  "Identity is resolved only on protected turns, so the embedding (about 0.5 s, one per request) is
  paid there and never on public turns", and the part of the same section that makes a presented
  local-unlock grant (today issued by the PIN) unreachable after a face match even for operations
  that declare their own scope (decision 6 below). The rest of §5, §1 to §4 and §6 to §9 stand.
- **Amends:** [ADR 0016](0016-face-and-voice-identity-fusion.md) §8 (the closed log reasons):
  `error` joins the set, and `backend_unavailable`, which named a voice backend that is down,
  also names a face detector that failed (§5 below; decided in Plan 0061, D-3)
- **Amended by:** [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md) §3 and §9
  (`Accepted` 2026-10-16, implemented by Plans 0062 and 0063 behind `MEMORY_CANDIDATES_ENABLED`,
  off by default): a generic voice turn identified by the face now gets a background voice check
  on its own clip, a candidate may be extracted from it, and, while a candidate waits, the voice
  is checked concurrently with generation so that the offer can be spoken; a message with the
  shape of an answer resolves the actor (face and voice) first. Decisions 1 and 2 above are
  amended only for those turns; with the switch off they hold as written.
- **Implemented by:** CM-2, [Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md)
  (closed 2026-10-13); acceptance record in
  [the 0061 acceptance note](../evals/0061-generic-turn-continuity-acceptance.md)

## Context

The roadmap's CM-2 row asks that the actor resolved by face, voice or PIN reach the generic
conversation, with no name interpolated into the prompt and no widened grant, and that its first
visible result be short-term continuity: the last turns of the identified person reach the next
turn. Today there is none, for two independent reasons.

### What holds today (verified in code at `bbbab5c`, 2026-10-09; `main` has changed only documents and CI since)

1. A generic turn never resolves identity. The controller returns no decision for it, and none of
   the four callers of the generic turn (`POST /transcribe` and `POST /chat` through
   `process_text_turn`, `POST /transcribe/stream` through `prepare_text_turn`, and
   `POST /vision/respond`, whose actor is fixed to the public unknown) passes a resolved
   `active_person`. Face, voice and PIN resolution is lazy and runs only when a protected branch
   awaits the resolver, so identity costs nothing on a generic turn today.
2. Even a resolved actor would not open the history. `text_turn.py` opens working history only for
   `IdentityEvidenceSource.MANUAL` evidence, and no production code emits it
   (`IdentitySessionRegistry.select_person` has no caller outside tests). Every generic turn runs
   with `history=None` and `context=None`; `record_text_turn` writes the turn and clears it at once
   ("Turn memory: discarded (no verified identity — working memory cleared)"). A turn whose model
   call fails is not recorded at all.
3. Working memory is two module dictionaries in `server/memory/working.py` (turns and recent
   emotions), keyed by an arbitrary string, with no lock, no time limit and no character limit;
   only `WORKING_MEMORY_SIZE` (20 messages) bounds it. It is gated by `MEMORY_ENABLED`.
4. The history reaches the model as chat messages before the current turn (`_build_messages` in
   both `llm.py` and `llm_streaming.py`), never inside the system prompt. The speaker's name is
   never interpolated into the prompt. The recent emotion, however, is written into the system
   prompt as a tone directive, and the always-present `_MEMORY_DISCIPLINE` text says the memory
   block is the *only* source of truth about people, family, pets, dates and preferences.
5. The robot attaches a webcam frame on every turn when `ROBOT_FACE_AUTH_ENABLED` is on (default
   off); the server reads it only when `FACE_AUTHENTICATION_ENABLED` is on (default off). Voice and
   streaming requests may also carry `X-Iroko-Identity-Token`; `/chat` carries only that token.
6. `just chat-test` expects continuity between unauthenticated public requests of `/chat`; the
   server cannot give it today.
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
10. Only one server worker exists: `UVICORN_WORKERS` is typed `Literal[1]` and grants are
    process-local.

### Facts the design has to respect

1. Identity evidence is never authorization (ADR 0006, ADR 0008, ADR 0009). The locked posture
   keeps bounded general conversation for an unknown actor and never merges an unknown speaker's
   words into a known person's history.
2. `conversation_id` separates working histories and is never identity or authorization
   (`identity-and-access.md`, *Conversation isolation*).
3. Face alone gives `basic`; voice corroboration gives `strong`; ordinary private data needs only
   `basic` (ADR 0016 §1 to §3). A photograph still identifies at `basic` (ADR 0016 §9).
4. `ambiguous` and `unknown` are valid outcomes, and `ambiguous` exposes neither person's private
   context.
5. Durable memory stays blocked until its own slice: writes CM-3, episodes CM-4, retrieval CM-5.
6. A turn that carries history in the prompt is where the streaming fallback rate matters (the
   roadmap's reason to order CM-2 after the streaming repair); a history-bearing streamed turn has
   never been measured, and one reply in French is an open finding of Plan 0059.

## Decision

### 1. Every generic turn tries to identify its speaker, cheaply and without side effects

| Channel | Evidence used on a generic turn |
|---|---|
| `POST /transcribe`, `POST /transcribe/stream` | the face in the frame (when face authentication is on and a frame was sent); a presented token of the default scope only when the face did not resolve, in ADR 0016 §5 order, **observed and never spent** |
| `POST /chat` | the presented token of the default scope, observed and never spent |
| `POST /vision/respond` | none: its actor stays the public unknown, so it neither reads, writes nor changes any conversation |

The voice is never consulted on a generic turn (the roughly 0.5 s embedding is saved on every chat
turn), so a face identifies at `basic`; an observed token keeps the assurance its grant gives. The
voice is computed on demand, as today, on a protected turn whose operation needs `strong`.
Identification on a generic turn uses **its own face-only resolver instance** (built without the
audio, so no speaker factory exists), separate from the request's resolver and its cache; its
`source` and `last_reason` are never copied to a response (decision 8), and it does not change what
a protected branch decides. When `MEMORY_ENABLED` is off, generic identification is skipped
entirely, since nothing would use it.

**Failures never fail the turn.** Any error of the face or token path on a generic turn (store,
model, detector or executor) degrades the turn to `unknown`, which is answered normally and logged
with a closed reason (decision 5). STT keeps running before identification with no entity hotwords; an
identified generic turn does not load owner metadata or hotwords.

### 2. Who has continuity, and what it opens

Only a person `identified` by a trusted source (`FACE`, `LOCAL_UNLOCK` or `MANUAL`) with assurance
at least `basic` has short-term continuity, and only while `MEMORY_ENABLED` is on. This opens the
**turn history only**:

- the recent-emotion buffer stays closed: no tone directive is derived from the conversation
  (the streamed `emotion` event keeps coming from ADR 0018's pure function). This also removes the
  tone directive that a `MANUAL` turn gets today, a path only tests exercise;
- the persistent context, vector retrieval, consolidation and the presentation guidance keep their
  `MANUAL` gate, so durable memory stays off for every speaker, the identified owner included;
- the turns of the conversation carry no speaker attribution and are never extracted, consolidated
  or promoted: attributing an utterance to its speaker stays with CM-3 (ADR 0019).

A speaker who is not identified has no continuity at all: the turn is answered and forgotten. No
history of an unknown speaker is kept, not even request-local (narrower than ADR 0009 allows).

### 3. The continuity session

There is **one session slot**, in process memory and never persisted: the device has one microphone
and the loop is half-duplex. The slot records the person it belongs to and a generation counter;
`conversation_id` is never used to select it. The generation increases only when the session is
replaced (another person), deleted or expires; a suspension does not touch it, so a stranger's turn
never drops the owner's concurrent write, and two overlapping turns of the same person both write,
in order. A `MANUAL` turn uses the same slot (the separate
`session:<evidence>:person:<id>` working scope is retired).

- **Size:** at most 3000 characters of turn content. Whole user-and-assistant pairs leave oldest
  first; a single pair larger than the cap is not kept. `WORKING_MEMORY_SIZE` stays as an upper
  bound on messages.
- **Silence:** a session not extended for 180 seconds expires. Expiry is checked on every access
  against an injectable clock (no background sweeper); an expired session is dropped at that access.
  Silence is measured from the last turn written; a suspended session keeps ageing. A write is
  not an access: a turn admitted before the limit that finishes after it still writes and
  refreshes the silence, and the next opening finds it fresh.

Setting names and defaults are fixed by the plan (for example `WORKING_MEMORY_MAX_CHARS=3000` and
`WORKING_MEMORY_IDLE_SECONDS=180`, both in `.env.example`).

### 4. Transitions

| The generic turn's speaker is | Effect on the session | Does the turn read or write it? |
|---|---|---|
| the same identified person | continues | reads it, then writes the new pair |
| another identified person | the previous session is deleted; a new one starts | reads nothing, writes its own |
| `ambiguous` | **suspended**: kept, not read, not written | no |
| `unknown`, `probable`, or no evidence (including a failure, decision 1) | **suspended** | no |
| — (180 s of silence) | deleted | n/a |

A suspended session resumes only when the same person is identified again before it expires; the
turns spoken while it was suspended are not written anywhere. "Suspended" is not a stored state: an
`unknown` or `ambiguous` turn simply neither reads nor writes the session, and logs that it did so. The second row is unreachable with
one enrolled owner (another enrolled face vetoes to `ambiguous` and the PIN requires the owner), so
it is tested with synthetic evidence.

**Which turns take part.** Only generic turns read, write or apply a transition. Deterministic and
protected turns (date, age, own children, "who am I", the scene stub) neither read nor write the
session nor apply a transition, and do not extend its silence; a protected answer therefore never
enters the history, and protected data cannot reach a later prompt through it.

**When.** The transition is applied when the turn's speaker is resolved, before generation. A turn
whose generation fails, falls back, or produces nothing recordable writes nothing and leaves the
session as the transition left it. A write carries the generation it read; a write whose generation
is stale (another turn changed the session meanwhile) is dropped.

### 5. Logging

Every transition is logged with a closed reason (`continued`, `started`, `replaced`, `suspended`,
`expired`) and no content. A `suspended` line also carries the identification outcome, from a
closed set (`no_evidence`, `veto_other_person`, `veto_multiple_faces`, `backend_unavailable`,
`error`), so suspensions and deletions can be counted by cause. They are the reasons of ADR 0016 §8 plus
`error`, and `backend_unavailable` also covers a face detector that failed. The person id may appear in these lines, as it already does in the turn
actor log. Conversation text stays out of logs unless `LOG_CONVERSATION_TEXT` is on.

### 6. A local-unlock grant is consulted by operation, not by turn (supersedes ADR 0016 §5)

A local-unlock grant is the one-use, scoped token that a local factor issues. Today the only such
factor is the PIN; any future local factor that issues the same scoped `LOCAL_UNLOCK` grant (for
example a fingerprint reader) is covered by this decision without a new ADR, although adding the
factor itself needs its own.

ADR 0016 §5 stands for the default scope: when the owner's face matched, a default-scope token is
not consulted and stays unspent. The new rule is for a fusion resolver built for an operation that
declares its own scope:

> After the owner's face matched and no veto applied, a presented token of **exactly** that
> operation's scope is consulted and spent by the consuming resolver. The resolved context then
> carries the face evidence and the spent `LOCAL_UNLOCK` item (with its `grant_scope` and
> `grant_spent`), at `strong`, and the reported identity source is `local_unlock`.

A token of any other scope is still refused without being spent (ADR 0015 decision 1); the vetoes
of ADR 0016 §4 apply first, and then no token is consumed. If the token names a different person
than the matched face, the turn is `ambiguous` and the token is not consumed. `confirm` keeps
having no local-unlock route. `/chat` consults its token without any face, so it is unaffected.

**When it is built.** No route uses a declared scope on a voice or streaming turn until an
operation such as `forget` is wired, so CM-2 does **not** implement this rule (no code for a later
phase): it is decided here and implemented by the plan that wires the first operation with its own
scope (CM-6 for `forget`), in the fusion resolver, with a resolver built for the default scope
behaving exactly as today (ADR 0019 §6, obligation 1).

### 7. What the prompt receives

The history goes in the chat messages of both builders (`llm.py` and `llm_streaming.py`). No name,
id or role of the speaker is interpolated into the system prompt or the history, and no grant
widens. One sentence of `_MEMORY_DISCIPLINE` (in `characters/__init__.py`) changes, minimally: what the person said earlier in
this same conversation may also be relied on, and nothing beyond the memory block and this
conversation may be invented. Nothing else in the prompt, the streaming protocol or the emotion
function changes.

Because the prompt and the messages change, the plan measures a history-bearing streamed turn
before it closes: the fallback rate of `full` at or below 5 % (the streaming repair's rule) and
replies in Spanish, with the evaluation instruments of Plans 0056 to 0059.

### 8. Wire fields

A generic turn keeps reporting `identity_source = None` and `authentication_consumed = false` on
every channel, as today: identification on a generic turn is internal and changes no response
field. The protected turns report as before.

### 9. `just chat-test`

The smoke order stays: introduce a marker in conversation A, ask in conversation B, recall in A. A
and the recall carry an owner token (the script asks for the PIN as a hidden prompt, never logs it,
unlocks with the default scope once per run and finishes within the token's lifetime; the token is
only observed, never spent); B carries none, so it is `unknown`, suspends the session and cannot
see it, and the recall in A resumes it. Interactive mode asks for the PIN in the same way. Without a
token the script reports "continuity not checked" instead of failing. It gains no new endpoint.

### 10. Acceptance

Automated: every row of the transition table, the size and silence limits with a fake clock, the
generation rule, failures degrading to `unknown`, no grant spent and no voice embedding on a
generic turn, the default-scope token still ignored after a face match, the speaker's name absent
from prompt and history, durable memory still blocked, and a new owner-to-stranger scenario with
**no token in the request** (the owner says something, a stranger or an ambiguous turn asks for it,
nothing is disclosed). Decision 6 is not built in CM-2, so it has no test there.

By Pipec on real hardware, with no token presented: (a) a sentence followed by a question that
depends on it, answered as a continuation; (b) a second person beside the owner (suspends, nothing
answered from it) and a second person alone in frame (suspends); (c) more than 180 seconds of
silence, after which the context is gone; (d) the added latency of the face check on a generic turn
and the counts of suspensions and deletions by closed reason, measured and recorded; plus the
measurement of decision 7.

## Alternatives considered

- **Keep identity lazy and give continuity only to `MANUAL` evidence.** Rejected: no production path
  emits `MANUAL`, so the companion would still forget the previous sentence.
- **Continuity for unknown speakers in an isolated per-conversation session.** Allowed by ADR 0009
  but rejected by Pipec on 2026-10-09: it needs a way to say "the same visitor" without using
  `conversation_id` as identity, and it keeps a stranger's words in memory.
- **Delete the session on an `ambiguous` or `unknown` turn.** The roadmap's earlier wording, and the
  first draft of this ADR for `unknown`. Rejected by Pipec (2026-10-09 for `ambiguous`, 2026-10-13
  for `unknown`): any anonymous `/chat`, a turn without a frame, a camera failure or the owner
  looking away would wipe the context, and `just chat-test` could not pass. Suspending exposes
  nothing: no turn reads a suspended session, and 180 s of silence still deletes it.
- **Face and voice on every generic turn.** Detects a change of speaker better, at about 0.5 s per
  turn and a dependency on the voice model for all chat. Rejected: chat needs only `basic`.
- **Always consult a presented token, even after a face match.** Reverses Plan 0054's decision and
  spends tokens on turns that do not need them. Rejected.
- **Leave `forget` unreachable with a face.** Rejected: ADR 0019 named it a defect to fix here.
- **Leave the prompt untouched.** Rejected by Pipec on 2026-10-13: the model could answer "I don't
  remember" to something said a minute earlier.
- **Open the recent-emotion buffer with the history.** Rejected: it writes a tone directive into
  the system prompt from the conversation, which needs its own policy; ADR 0018 already gives the
  streamed emotion.
- **One session per person.** Not needed with one enrolled owner and a half-duplex device; revisit
  with the family profile (P3).

## Consequences

### Positive

- The companion remembers the last few turns of the person using it, for the first time, with no
  durable memory, no new route and no new response field.
- Unknown and ambiguous speakers get nothing from the owner's session and leave nothing behind; an
  anonymous request or a face miss no longer costs the owner the conversation.
- `forget` becomes reachable with a face in frame through its own spent grant, once wired.
- Chat turns do not pay the voice embedding.

### Negative

- A photograph of the owner in front of the camera receives the owner's session (`basic`,
  ADR 0016 §9), and a second person speaking while the owner's face stays in frame is not detected.
- Continuity exists only where there is evidence: with face authentication off, voice and streaming
  turns are `unknown`; `/chat` needs a token, which lasts `OWNER_UNLOCK_TTL_SECONDS` (300 s); a
  protected question spends that token, so the next `/chat` turn is `unknown` (the session is
  suspended, not lost) until a new unlock.
- The web chat's "new conversation" no longer separates conversations for an identified person,
  because `conversation_id` is not identity.
- A face check is paid on every generic turn when face authentication is on; the history makes the
  prompt of the 3B model longer and slower. Both are measured, not assumed.
- A transcript of the session stays in process memory until it expires and is next accessed, or the
  server restarts; a restart loses it.
- An owner token is a bearer credential (ADR 0008, ADR 0015): for its lifetime, whoever presents it
  on a turn the face did not resolve is identified as the owner on generic turns and sees the last
  180 s of the session. Observing it never spends it, so this lasts until the token expires.
- Generic and protected turns do not share context: after "what are my children called?", a
  follow-up chat turn does not know that question was asked.

## Test consequences

The tests that pin "a generic turn has no history and clears working memory" change on purpose:
`test_text_turn.py`, `test_chat_endpoint.py`, `test_transcribe_stream.py`,
`test_transcribe_pipeline.py`, `test_vision_dialog.py`, `test_chat_test.py` and
`test_working_memory.py` (new limits and API). Kept and re-run, because their guarantees must
survive: `test_transcribe_memory.py` (fallback not recorded, no hotwords, no owner metadata, no
consolidation for a face-identified turn), `test_owner_stranger_matrix.py` (plus the new scenario),
`test_face_authenticated_turn.py`, `test_identity_fusion_turn.py` and `test_speaker_evidence_turn.py`
(no embedding on a generic turn; `identity_source` still `None`), `test_vision_memoria.py` and
`test_eval_longitudinal_memory.py` (its source check on the buffers). Tests that reset the working
buffers directly (`test_memory_integration.py`, `test_transcribe_onboarding.py`) follow the new
API, and the prompt and message tests (`test_llm_generate.py`, `test_llm_streaming.py`,
`test_character_parser.py`) follow the `_MEMORY_DISCIPLINE` sentence and the history in messages. A
guard keeps every read of the session inside its own module.

## Docs to update when this ADR is Accepted

The ADR index row; ADR 0016's status line (§5 partially superseded); ADR 0019 (follow-up, the
attribution sentence and the `forget` consequence); ADR 0015's "a public turn reaches the model
with no history" and ADR 0009's request-local note (a pointer to this ADR); ADR 0005's working
history line; the CM-2 rows of the roadmap and the conversational-memory map, and the map's
*Current fracture* and reusable-capabilities lines; `identity-and-access.md` (fusion paragraph,
the locked-posture sentence, *Conversation isolation*, whose `voice:<session-id>:person:<id>`
proposal this ADR replaces with one session slot); `cognitive-contracts.md`,
`cognitive-architecture.md` and `memory-and-world-state.md` (working context lasts 180 s);
`current-state.md` (diagram line and working-memory rows) and its Archify diagram; the Plan 0059
record (its memory case becomes exercisable); `.env.example`; the operator manual's `chat-test`
line; the plan indexes.

## Review

Revisit on a measured false-rejection rate of the face that suspends sessions too often, a second
enrolled household member (P3, per-person sessions), a measured latency that makes the per-turn face
check unacceptable, a history-bearing fallback rate above the rule, liveness or replay defence
(ADR 0016 §9), a capability that consumes a personal-memory action beyond the ones CM-3a wired
(`propose`, `read` and `confirm`; CM-3b onward), the measured cost of the third face-and-voice
resolution on an answer turn (ADR 0021, Plan 0063 acceptance), a mandatory voice check on chat, or a second local-unlock factor such as a fingerprint reader on the
robot (another verifier of the same scoped grant, so decision 6 holds, but the sensor itself needs
its own ADR and the privacy contract of the senses).

## Follow-up

CM-2 is closed: [Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md) implemented
identification on generic turns per channel, the session slot with its limits and generation rule,
the transition logging, the `_MEMORY_DISCIPLINE` sentence and its measurement, and the `chat-test`
adaptation; its acceptance on real hardware is recorded in
[the acceptance note](../evals/0061-generic-turn-continuity-acceptance.md). Decision 6 is
implemented by the plan that wires the first operation with its own scope (CM-6 for `forget`).

Open after acceptance, none of them a regression of this decision (they live in the roadmap's
transversal follow-ups): the measured cost of the face check on a generic turn (median about
0.9 s, maximum 1.6 s on the development laptop) is recorded for the *Review* trigger above, not
judged; a reply of the language measurement that the word-list heuristic judged not Spanish was
not located (the report keeps counts only); and the small local model still invents a value when
the session is empty, which is the confabulation finding of Plan 0059, not a continuity defect.
