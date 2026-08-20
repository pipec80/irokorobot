# One-Use Owner-Authenticated Classic Turn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Ready for owner review. Depends on completed Plan 0025. Do not
implement until Pipec explicitly authorizes execution.

**Goal:** Let Pipec enter the local PIN in the robot terminal, carry one opaque
short-lived grant to the server, ask “¿quiénes son mis hijos?” through classic
`POST /transcribe`, and receive the existing deterministic “Máximo y Dominga”
answer exactly once.

**Architecture:** A process-local `OwnerUnlockService` verifies the persistent
PIN, issues a 60-second single-use grant, and exposes one async resolver. The
controller asks that resolver only for protected intents, so generic turns do
not consume the grant. The grant produces both local-unlock identity evidence
and explicit scoped consent for that one protected read; authorization and the
existing v4 tool remain independent and still run before storage access.

**Tech Stack:** Python 3.12, FastAPI/Pydantic V2, process-local typed registry,
SQLite credential repository from Plan 0025, httpx, existing controller and
v4 household tools, pytest.

**Spec:** [Plan 0024 — owner-authenticated personal-memory MVP
design](0024-owner-authenticated-memory-mvp-design.md)

## Global Constraints

- Read `AGENTS.md`, Plans 0024–0025, ADR 0008, API/audio contracts, and the
  current controller/router/client tests before editing.
- Preserve every required `POST /transcribe` response field. New fields and
  headers are additive only.
- Use header `X-Iroko-Identity-Token`; never put identity, PIN, person name, or
  consent claims in the transcript, prompt, `conversation_id`, or audio body.
- The unlock endpoint is loopback-only and does not trust forwarded headers.
- PIN verification runs with `asyncio.to_thread()` so scrypt does not block the
  event loop.
- Token lifetime is exactly 60 seconds, stored only in the server process, and
  consumed atomically on the first protected controller resolution.
- A generic/date turn does not resolve the actor and therefore does not consume
  the grant.
- A consumed, replayed, expired, absent, malformed, or unknown token resolves
  to `unknown` and discloses no protected value.
- Five failed PIN attempts inside 60 seconds block new attempts for 60 seconds.
  The limiter is process-local and keyed to the single local installation; no
  PIN or candidate value is logged.
- The unlock gesture explicitly grants `child_data` consent only for the same
  one-use protected read. This is not a persistent consent grant and does not
  broaden owner permissions.
- `uvicorn_workers` must remain 1 while grants are process-local. Startup must
  fail clearly if configured otherwise; do not silently issue worker-local
  tokens in a multi-worker runtime.
- Classic `/transcribe` and `/chat` are in scope. Streaming parity is Plan 0027;
  vision/face/voice biometrics are not in scope.
- The robot remains a generic HTTP/audio client. It knows only unlock/token
  fields in the shared API contract, not SQLite, roles, policies, or children.
- No global or persistent `authenticated = true` flag.
- No RAG, LLM, face, speaker-recognition, or fingerprint change.

---

## File map

| File | Responsibility |
|---|---|
| `server/src/server/cognition/identity.py` | Add `LOCAL_UNLOCK` evidence and resolution rule. |
| `server/src/server/cognition/identity_sessions.py` | Issue/consume safe one-use evidence. |
| `server/src/server/cognition/owner_authentication.py` | PIN verification, rate limit, grant scope, request resolver. |
| `server/src/server/schemas_auth.py` | Unlock request/response contract. |
| `server/src/server/routers/auth.py` | Loopback-only unlock endpoint. |
| `server/src/server/main.py` | Mount auth router and enforce one worker. |
| `server/src/server/cognition/controller.py` | Await actor/consent resolvers. |
| `server/src/server/routers/chat.py` | Optional token header and authenticated resolver. |
| `server/src/server/routers/transcribe.py` | Optional token header for classic route. |
| `server/src/server/schemas_chat.py` | Add `authentication_consumed`. |
| `server/src/server/schemas.py` | Add `authentication_consumed`. |
| `robot/src/robot/server_client.py` | Unlock call, token header, response state. |
| `robot/src/robot/fsm_types.py` | Hold one process-local token. |
| `robot/src/robot/app.py` | Optional terminal PIN prompt at startup and token clearing. |
| `robot/src/robot/settings.py`, `.env.example` | Opt-in prompt setting. |
| tests listed below | RED/GREEN and denial proof. |

Do not touch streaming schema/render/client files; Plan 0027 owns them.

---

### Task 1: Extend identity evidence with consume-once local unlock

**Files:**

- Modify: `server/src/server/cognition/identity.py`
- Modify: `server/src/server/cognition/identity_sessions.py`
- Modify: `tests/unit/test_identity_sessions.py`
- Modify: `tests/unit/test_active_person_identity.py`

**Interfaces:**

- Produces:

```python
IdentityEvidenceSource.LOCAL_UNLOCK


def issue_for_person(self, person: PersonRecord, *, source: IdentityEvidenceSource) -> str: ...


def consume_evidence(self, token: str) -> IdentityEvidence | None: ...
```

- [ ] **Step 1: Write RED tests**

Prove `LOCAL_UNLOCK` resolves as `IDENTIFIED`, while session evidence keeps its
existing behavior. Prove consume-once:

```python
token = registry.issue_for_person(_person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK)
assert registry.consume_evidence(token) is not None
assert registry.consume_evidence(token) is None
assert registry.evidence_for(token) is None
```

Also prove expired evidence returns `None`, a non-person record is rejected,
and legacy `select_person()`/`evidence_for()` tests remain green.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_identity_sessions.py tests/unit/test_active_person_identity.py -q
```

- [ ] **Step 3: Implement the minimum compatible extension**

Keep `select_person()` as a compatibility wrapper. `consume_evidence()` must
`pop()` before returning, then reject expiry. Add `LOCAL_UNLOCK` to the trusted
candidate sources and map it to `IDENTIFIED`; do not accept `FACE`, `VOICE`, or
`CONTEXT` as identified in this plan.

- [ ] **Step 4: Run focused identity tests**

```powershell
uv run pytest -n0 tests/unit/test_identity_sessions.py tests/unit/test_active_person_identity.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/cognition/identity.py server/src/server/cognition/identity_sessions.py tests/unit/test_identity_sessions.py tests/unit/test_active_person_identity.py
git commit -m "feat(auth): add consume-once local unlock evidence"
```

---

### Task 2: Implement the owner unlock service and request resolver

**Files:**

- Create: `server/src/server/cognition/owner_authentication.py`
- Create: `tests/unit/test_owner_authentication.py`

**Interfaces:**

```python
class OwnerUnlockScope(StrEnum):
    PERSONAL_PROTECTED_READ = "personal_protected_read"


class OwnerUnlockResult(BaseModel):
    token: str
    expires_at: datetime


class OwnerRequestResolver:
    consumed: bool

    async def resolve_actor(
        self, event: CognitiveEvent[TextTurnPayload]
    ) -> ActivePersonContext: ...

    async def resolve_consent(
        self,
        event: CognitiveEvent[TextTurnPayload],
        actor: ActivePersonContext,
    ) -> ConsentStatus: ...


class OwnerUnlockService:
    async def unlock(self, pin: str) -> OwnerUnlockResult | None: ...
    def for_request(self, token: str | None) -> OwnerRequestResolver: ...
```

- [ ] **Step 1: Write RED service tests with injected boundaries**

Inject clock, credential reader, person/role readers, PIN verifier, token
registry, and `asyncio.to_thread` boundary. Cover:

- valid PIN issues opaque 60-second token;
- invalid PIN returns `None` without revealing whether owner/profile exists;
- missing/revoked credential has the same public result;
- five failures activate the exact 60-second block;
- successful verification clears failure state;
- `for_request(None)` resolves unknown;
- generic requests do not call resolver and therefore cannot consume (asserted
  later in controller tests);
- first resolver call consumes token and returns owner role/evidence;
- second resolver/token replay returns unknown;
- scoped consent is `GRANTED` only when that resolver consumed a valid owner
  grant for the same event;
- no secret appears in `caplog`.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_owner_authentication.py -q
```

- [ ] **Step 3: Implement small typed collaborators**

Use a private record tying token reference to:

```text
IdentityEvidence(LOCAL_UNLOCK, owner_id, observed_at, expires_at)
+ scope PERSONAL_PROTECTED_READ
+ originating grant id
```

Do not persist the token or consent. Load active credential/owner role before
issuing. Verify PIN off-loop. Resolver state is request-local and caches actor
plus scoped consent only after successful atomic consumption.

- [ ] **Step 4: Run focused tests**

```powershell
uv run pytest -n0 tests/unit/test_owner_authentication.py tests/unit/test_identity_sessions.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/cognition/owner_authentication.py tests/unit/test_owner_authentication.py
git commit -m "feat(auth): issue scoped one-use owner grants"
```

---

### Task 3: Add the loopback-only unlock endpoint

**Files:**

- Create: `server/src/server/schemas_auth.py`
- Create: `server/src/server/routers/auth.py`
- Modify: `server/src/server/main.py`
- Create: `tests/integration/test_owner_unlock_endpoint.py`

**Interfaces:**

```python
class OwnerUnlockRequest(BaseModel):
    pin: SecretStr


class OwnerUnlockResponse(BaseModel):
    token: str
    expires_at: datetime


POST /auth/owner/unlock
200 -> OwnerUnlockResponse
401 -> {"detail": "Owner authentication failed"}
403 -> {"detail": "Local access only"}
429 -> {"detail": "Too many attempts"}
```

- [ ] **Step 1: Write endpoint RED tests**

Using ASGI transport and injected service, assert:

- loopback + valid PIN returns only token/expiry;
- invalid/missing profile use the same 401 body;
- rate limit returns 429 without attempt details;
- non-loopback client returns 403 before PIN verification;
- request forbids extra fields;
- OpenAPI exposes no person selector, role, consent, or persistent session;
- logs contain route/status but not request PIN/token.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_owner_unlock_endpoint.py -q
```

- [ ] **Step 3: Implement router and composition root**

Use `Request.client.host` and accept only `127.0.0.1`, `::1`, and ASGI test
client hosts explicitly injected in tests. Do not consult
`X-Forwarded-For`; proxy headers are disabled.

Mount `auth.router`. During lifespan/startup, reject
`settings.uvicorn_workers != 1` while owner unlock is enabled. Do not preload
PIN bytes.

- [ ] **Step 4: Run endpoint and app regression**

```powershell
uv run pytest -n0 tests/integration/test_owner_unlock_endpoint.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_validation.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/schemas_auth.py server/src/server/routers/auth.py server/src/server/main.py tests/integration/test_owner_unlock_endpoint.py
git commit -m "feat(api): add local owner unlock endpoint"
```

---

### Task 4: Make controller actor and consent resolvers async

**Files:**

- Modify: `server/src/server/cognition/controller.py`
- Modify: `server/src/server/routers/chat.py`
- Modify: `server/src/server/routers/transcribe.py`
- Modify: `server/src/server/routers/vision.py`
- Modify: `tests/unit/test_cognitive_controller.py`

**Interfaces:**

```python
type ActivePersonResolver = Callable[
    [CognitiveEvent[TextTurnPayload]], Awaitable[ActivePersonContext]
]
type ConsentResolver = Callable[
    [CognitiveEvent[TextTurnPayload], ActivePersonContext], Awaitable[ConsentStatus]
]
```

- [ ] **Step 1: Convert test fixtures and add consumption-order RED test**

Add a test proving:

```python
plan = await controller.handle(generic_event)
resolver.assert_not_awaited()

plan = await controller.handle(children_event)
resolver.assert_awaited_once()
consent.assert_awaited_once()
```

Add a denied case where actor is unknown and assert household tool/reader is
not called.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_cognitive_controller.py -q
```

- [ ] **Step 3: Await only protected branches**

Convert the controller default and all three public route resolver functions to
`async def`. Await actor resolution in
`_protected_household_plan()` and `_own_children_plan()`, then await consent
only after a resolved actor/tool exists. Date, age, generic, and unknown
non-protected paths must not resolve or consume identity.

- [ ] **Step 4: Run controller and P0.5 tests**

```powershell
uv run pytest -n0 tests/unit/test_cognitive_controller.py tests/integration/test_p05b2_household_acceptance.py tests/integration/test_household_authorization_runtime.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/cognition/controller.py server/src/server/routers/chat.py server/src/server/routers/transcribe.py server/src/server/routers/vision.py tests/unit/test_cognitive_controller.py
git commit -m "refactor(cognition): await trusted identity resolvers"
```

---

### Task 5: Connect optional token to chat and classic transcribe

**Files:**

- Modify: `server/src/server/routers/chat.py`
- Modify: `server/src/server/routers/transcribe.py`
- Modify: `server/src/server/schemas_chat.py`
- Modify: `server/src/server/schemas.py`
- Modify: `tests/integration/test_chat_endpoint.py`
- Modify: `tests/integration/test_transcribe_pipeline.py`
- Create: `tests/integration/test_owner_authenticated_turn.py`

**Interfaces:**

```text
Optional request header: X-Iroko-Identity-Token
Additive response field: authentication_consumed: bool = false
```

- [ ] **Step 1: Write the full chat RED scenario**

Use a disposable DB configured through `apply_personal_setup()`:

```python
unlock = await service.unlock("482173")
response = await client.post(
    "/chat",
    headers={"X-Iroko-Identity-Token": unlock.token},
    json={
        "message": "¿Quiénes son mis hijos?",
        "conversation_id": "acceptance-owner",
    },
)
assert response.json()["response"] == "Tus hijos son Máximo y Dominga."
assert response.json()["authentication_consumed"] is True
```

Replay the same token and assert the existing non-disclosing denial. Assert
the first allowed audit trace contains no names/PIN/token.

- [ ] **Step 2: Write classic audio RED scenarios**

Mock only STT and TTS boundaries. STT returns the literal Spanish question;
TTS must receive exactly `Tus hijos son Máximo y Dominga.` and return a valid
WAV contract fixture. Cover valid, absent, expired, replayed, and malformed
headers. In denied cases assert the v4 reader/label lookup is never called.

- [ ] **Step 3: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_owner_authenticated_turn.py -q
```

- [ ] **Step 4: Compose one request-local resolver**

For each request:

```python
request_identity = owner_unlock_service.for_request(identity_token)
controller = CognitiveController(
    ...,
    active_person_resolver=request_identity.resolve_actor,
    consent_resolver=request_identity.resolve_consent,
)
```

Read the token with `Annotated[str | None, Header(alias=...)]`. Do not add it
to `ChatRequest` or multipart audio fields. Return
`request_identity.consumed` as the additive response value.

- [ ] **Step 5: Preserve anonymous contracts**

Update exact-response tests to include `authentication_consumed: false` while
keeping all prior fields unchanged. Requests without a header remain unknown,
stateless, memory-safe, and compatible with older clients that ignore added
response fields.

- [ ] **Step 6: Run route/controller regression**

```powershell
uv run pytest -n0 tests/integration/test_owner_authenticated_turn.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_validation.py tests/unit/test_cognitive_controller.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add server/src/server/routers/chat.py server/src/server/routers/transcribe.py server/src/server/schemas_chat.py server/src/server/schemas.py tests/integration/test_owner_authenticated_turn.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py
git commit -m "feat(cognition): authorize one-use owner child query"
```

---

### Task 6: Add the opt-in robot terminal unlock for classic mode

**Files:**

- Modify: `robot/src/robot/server_client.py`
- Modify: `robot/src/robot/fsm_types.py`
- Modify: `robot/src/robot/app.py`
- Modify: `robot/src/robot/settings.py`
- Modify: `.env.example`
- Modify: `tests/unit/test_server_client.py`
- Modify: `tests/unit/test_robot_app.py`

**Interfaces:**

```python
class OwnerUnlockResult(BaseModel):
    token: str
    expires_at: datetime


async def unlock_owner(pin: str) -> OwnerUnlockResult: ...
async def transcribe(audio: bytes, *, identity_token: str | None = None) -> TranscribeResult: ...


class TranscribeResult:
    authentication_consumed: bool = False


class LoopContext:
    identity_token: str | None = None
```

Setting:

```text
ROBOT_OWNER_UNLOCK_PROMPT=false
```

- [ ] **Step 1: Write client RED tests**

Assert unlock sends PIN only to loopback `/auth/owner/unlock`, parses token and
expiry, maps 401/429 to safe `ServerError` messages without echoing PIN, and
adds the identity header only when a token exists. `_parse_result()` tolerates
old servers missing `authentication_consumed`.

- [ ] **Step 2: Write robot RED tests**

With injected `read_secret`/unlock boundary, prove:

- setting false never prompts;
- setting true prompts once at startup;
- empty PIN continues public without a token;
- successful unlock stores only token in `LoopContext`;
- classic transcribe receives the token;
- consumed response clears it;
- non-consumed generic response retains it until expiry/server consumption;
- token/PIN are not logged.

- [ ] **Step 3: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_server_client.py tests/unit/test_robot_app.py -q
```

- [ ] **Step 4: Implement opt-in startup prompt**

Use `getpass.getpass` through `asyncio.to_thread`. Prompt before the FSM starts,
only when classic mode and `robot_owner_unlock_prompt` are enabled. If
streaming is enabled, fail with a clear message directing the operator to Plan
0027; do not silently drop the token.

Pass the token as an optional keyword argument. Clear it only when the server
returns `authentication_consumed=true`. Never inspect transcript content in
the robot.

- [ ] **Step 5: Run robot/client tests**

```powershell
uv run pytest -n0 tests/unit/test_server_client.py tests/unit/test_robot_app.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add robot/src/robot/server_client.py robot/src/robot/fsm_types.py robot/src/robot/app.py robot/src/robot/settings.py .env.example tests/unit/test_server_client.py tests/unit/test_robot_app.py
git commit -m "feat(robot): carry one-use owner unlock token"
```

---

### Task 7: Close automated Plan 0026 gates

**Files:**

- Modify: `docs/architecture/current-state.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/0026-one-use-owner-authenticated-classic-turn.md`

- [ ] **Step 1: Run the complete focused security scenario**

```powershell
uv run pytest -n0 tests/unit/test_identity_sessions.py tests/unit/test_owner_authentication.py tests/integration/test_owner_unlock_endpoint.py tests/unit/test_cognitive_controller.py tests/integration/test_owner_authenticated_turn.py tests/unit/test_server_client.py tests/unit/test_robot_app.py -q
```

- [ ] **Step 2: Run all repository gates**

```powershell
just lint
just typecheck
just test
just audit
just check
git diff --check
```

- [ ] **Step 3: Review threat cases**

Manually inspect tests/evidence for invalid PIN, brute-force block, token
expiry, replay, malformed header, missing consent scope, unknown actor,
reader-not-called, logs, one-worker invariant, and anonymous compatibility.

- [ ] **Step 4: Update status honestly**

Record automated evidence only. State that streaming parity and physical
microphone/speaker acceptance remain open under Plans 0027 and 0028.

- [ ] **Step 5: Request independent review**

Review identity/authentication/authorization separation, secret handling,
pre-retrieval denial, async resolver ordering, API compatibility, and
server↔robot boundary. Resolve findings and rerun affected gates before merge.

## Completion criteria

Plan 0026 is complete only when:

- the local endpoint issues a 60-second one-use token after valid PIN;
- classic chat/audio with that token returns exactly “Tus hijos son Máximo y
  Dominga.” from the existing v4 tool;
- absent/expired/replayed/malformed tokens deny without storage access or
  disclosure;
- the robot can opt into one startup PIN prompt and clear consumed tokens;
- required classic API/audio fields remain unchanged;
- full quality/security gates pass;
- streaming, face, voice recognition, fingerprint, RAG, and real hardware
  acceptance remain untouched.
