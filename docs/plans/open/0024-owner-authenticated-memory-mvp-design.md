# Owner-authenticated personal-memory MVP design

> **Status:** Approved product direction. The documentation-only executable
> portfolio is prepared in Plans 0025–0028 and awaits Pipec's review before any
> production code is changed.

## Product result

The first marketable personal-companion proof is one spoken exchange:

```text
Pipec authenticates locally once
  -> Pipec asks: “Iroko, ¿quiénes son mis hijos?”
  -> STT produces the literal question
  -> Iroko resolves authenticated Pipec
  -> policy authorizes Pipec's protected family relationship
  -> the existing structured child tool returns Máximo and Dominga
  -> the response plan says only those authorized facts
  -> Piper speaks: “Tus hijos son Máximo y Dominga.”
```

The paired denial is equally important:

```text
No valid one-use evidence or another speaker
  -> same question
  -> no protected retrieval
  -> non-disclosing denial
  -> no names, count, hint, or confirmation that the data exists
```

This is the north-star acceptance scenario. PDF ingestion, broad RAG,
knowledge graphs, general family onboarding, and polished administration do
not block it.

## Product posture before and after the grant

Iroko without fresh authentication is not a disabled robot or a blank LLM. It
may see and hear under existing local settings, transcribe, maintain an
isolated request-local unknown context, converse about public/general topics,
and speak through TTS. It must not read or mutate personal memory, attribute an
unknown statement to Pipec, or execute protected home, computer, or physical
actions.

The MVP PIN is not a master unlock. Its only authority is one
`personal_protected_read` of confirmed `child_data`. It cannot authorize light
control, PC restart, biometric administration, memory mutation, or any future
actuator. [ADR 0009](../../adr/0009-locked-posture-and-scoped-capabilities.md)
is the normative capability boundary.

## Why this preserves existing work

The slice connects existing components instead of creating another brain:

| Need | Existing foundation | Missing connection |
|---|---|---|
| Owner record and role | owner bootstrap and household authorization | bounded first-boot caller |
| Máximo and Dominga as children | v4 entities/relations and child tools | confirmed local data entry/seed path |
| Temporary identity | `IdentitySessionRegistry` and typed evidence | production unlock entry point |
| Current actor | `ActivePersonContext` and resolver injection seams | resolver that consumes valid evidence |
| Disclosure decision | fail-closed policy and audit | authenticated actor supplied to it |
| Spoken answer | STT, controller, response plan, Piper | real end-to-end acceptance |

The server remains a generic cognitive/audio API and the robot remains a
generic audio client. They share only an extended, backward-compatible request
contract; the server never imports `robot`.

## State model

### Persistent installation state

- installation profile (`personal` for this target);
- exactly one bootstrapped owner;
- owner role and consent/policy records;
- confirmed entities and directional `child -> child_of -> owner`
  relationships;
- a derivable minimal security bootstrap: one owner, confirmed child
  relationships, and one active credential;
- extended onboarding completion remains a separate later state;
- audit events that never contain protected values or secrets.

### Transient interaction state

- opaque one-use authentication token/reference;
- authenticated person ID and method;
- issue/expiry timestamps and request scope;
- consumed/revoked state;
- resulting identity evidence and `ActivePersonContext`.

There is no durable installation-wide `authenticated = true`. A displayed
boolean is derived from fresh, unconsumed evidence for the current operation.

## Delivery order

This design is decomposed into four bounded plans. They must be reviewed and
executed in order; preparing these documents is not implementation evidence:

1. [Plan 0025](0025-personal-owner-bootstrap-and-pin-setup.md) — minimal
   security bootstrap: Pipec as owner, confirmed child relations, and local PIN
   setup without claiming extended onboarding completion;
2. [Plan 0026](0026-one-use-owner-authenticated-classic-turn.md) — one-use
   unlock and the authorized classic `/chat` and `/transcribe` paths;
3. [Plan 0027](0027-one-use-owner-streaming-parity.md) — equivalent one-use
   behavior for streaming without weakening Plan 0022;
4. [Plan 0028](0028-owner-authenticated-memory-runtime-acceptance.md) — repeated
   real microphone-to-speaker acceptance and safe evidence.

### Slice A — First boot and known personal data

Connect the existing owner bootstrap and local recovery entry point. Establish
Pipec before accepting any household relationship. Confirm and store Máximo and
Dominga as entity relationships, not as a prompt sentence or vector-only
memory. Do not block the north-star proof on birthday, home, workplace,
partner, pet, or preference collection, and do not mark the existing extended
onboarding checklist complete.

**Gate:** from an empty database, the local operator can reproducibly create
one owner and the two confirmed relationships; rerunning does not duplicate or
silently replace them.

### Slice B — One-use local authentication

Add the smallest explicit local unlock. A correct PIN or equivalent local
action issues one opaque, short-lived token. Incorrect, expired, revoked,
replayed, absent, and already-consumed tokens produce no authenticated actor.

**Gate:** automated tests prove issue, consume-once, expiry, revoke, redacted
logs, and process/restart semantics chosen by the executable plan.

### Slice C — Channel-to-actor connection

Carry the optional token/reference through a backward-compatible channel seam,
resolve it into typed evidence, and inject the resulting active person into
chat, classic voice, streaming, and visual adapters where applicable. Existing
requests without the new field remain public/unknown.

**Gate:** no route hard-codes Pipec; missing evidence stays unknown; the fixed
`POST /transcribe` fields remain present; server↔robot separation remains
intact.

### Slice D — Authorized family answer

Route the child-name intent through the controller and existing policy-gated
structured tool. Authorization occurs before storage access. The LLM may
express a bounded typed result only if the response contract needs it; it may
not invent, identify, authorize, or retrieve the names.

**Gate:** authenticated Pipec gets exactly the confirmed active child names;
unknown/expired/replayed evidence gets a non-disclosing denial and the storage
reader is not called.

### Slice E — Real product acceptance

Run the actual `just run-server` plus `just run-robot` path with the PC
microphone and speakers. Record literal STT, authentication method/status,
actor resolution, policy decision, selected deterministic tool, response text,
audible Piper result, and safe audit outcome.

**Gate:** repeat both north-star scenarios at least three times: Pipec unlocks
and hears “Máximo y Dominga”; without a fresh unlock the same question reveals
nothing. Automated tests alone do not close this gate.

## Progressive methods after the MVP

1. Integrate the existing face engine as consented, expiring identity evidence
   and calibrate it on the actual camera.
2. Add a local speaker-verification model, enrollment, and calibration on the
   actual microphone; STT and VAD are not speaker recognition.
3. Fuse non-conflicting evidence and represent conflict as `ambiguous`.
4. Add fingerprint only when physical hardware is selected; it emits the same
   evidence shape and does not create a new authorization system.

Each method gets an independent acceptance matrix. None delays the one-use
unlock proof, and none grants permission without the existing policy decision.

## Explicit non-goals

- a global `authenticated` database flag;
- owner-by-device, owner-by-loopback, owner-by-name, or owner-by-prompt;
- automatic biometric enrollment or permanent raw audio/frame retention;
- general web administration, multi-adult family privacy, or public/LAN auth;
- PDF/document ingestion, broad hybrid RAG, memory consolidation redesign, or
  a new vector database;
- wake word, ROS2, physical autonomy, or new TTS technology;
- home control, PC administration, actuator permissions, or a general
  authenticated session;
- rewriting the established controller, v4 memory, policy, audit, STT, or TTS.

## Risks and controls

| Risk | MVP control |
|---|---|
| Another person speaks after Pipec unlocks | one-use token, short TTL, explicit audible/visible unlock state |
| PIN leaks through logs/history | secret never logged; token opaque; safe audit reason only |
| Token replay | atomic consume-once semantics |
| Protected data reaches the LLM before denial | authorize before retrieval; test reader-not-called |
| The answer is correct only in unit tests | repeated real microphone-to-speaker acceptance |
| Biometrics become a new parallel architecture | every adapter emits the same typed evidence contract |

## Decisions adopted for the executable portfolio

The documentation portfolio uses the product defaults agreed in the review:

- the first unlock surface is local and explicit, with the PIN entered outside
  the conversational prompt;
- authentication authorizes exactly the next protected interaction and expires
  after a short TTL if unused;
- Pipec, Máximo, and Dominga are confirmed through the bounded personal setup
  flow before any relationship becomes durable;
- a generic turn does not consume the protected one-use grant;
- absence, expiry, replay, conflict, or invalid evidence remains `unknown` and
  causes a non-disclosing denial.

These choices are now specific enough to review Plans 0025–0028. Approval of
the documents authorizes planning only; code execution begins only after Pipec
explicitly asks to implement the first plan.
