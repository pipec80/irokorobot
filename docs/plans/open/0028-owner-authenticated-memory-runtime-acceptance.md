# Owner-Authenticated Memory Runtime Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to execute this plan checkpoint-by-checkpoint.
> Steps use checkbox (`- [ ]`) syntax for tracking. Do not dispatch coding
> workers: this plan validates already-reviewed Plans 0025–0027.

**Status:** Ready for owner review. Depends on merged Plans 0025–0027 and their
green automated/CI evidence.

**Goal:** Prove repeatedly on the actual Windows PC that Pipec can authenticate
locally, speak “¿quiénes son mis hijos?”, and hear “Tus hijos son Máximo y
Dominga”, while absent, expired, and replayed grants disclose nothing.

**Architecture:** Use the real `just run-server` plus `just run-robot` path,
the local setup wizard, microphone, Faster Whisper, controller, authorization,
v4 relationship tool, Piper, and speakers. Store evidence only in an untracked
operator record; never copy PINs, tokens, or protected database contents into
Git.

**Tech Stack:** Existing `just` commands, Windows terminals, local SQLite,
Ollama/services, Faster Whisper, Piper, classic and streaming robot modes.

**Spec:** [Plan 0024 — owner-authenticated personal-memory MVP
design](0024-owner-authenticated-memory-mvp-design.md)

## Global Constraints

- This is an acceptance/evidence plan, not permission to repair code while
  testing. On any mismatch, stop, preserve safe evidence, and create a bounded
  remediation plan.
- Use a disposable acceptance database or a verified recoverable copy. Never
  reset a household database without explicit approval and a confirmed backup.
- Keep `SERVER_HOST=127.0.0.1`, `UVICORN_WORKERS=1`, and proxy headers disabled.
- Never write the real PIN or opaque token into a command line, shell history,
  screenshot, log, runbook, issue, commit, or chat transcript.
- Record literal STT text. A materially wrong transcription is a failure even
  if the intended phrase would have passed.
- Required spoken result is exact in substance and names: `Tus hijos son
  Máximo y Dominga.` No LLM paraphrase may introduce another name or fact.
- A denial must not contain either name, the count, or confirmation that a
  protected relationship exists.
- Automated tests are prerequisite evidence, not product acceptance.
- Repeat the north-star allowed and denied scenarios three times in classic
  mode and three times in streaming mode.
- Face, speaker recognition, fingerprint, vision identity, PDF/RAG, LAN, and
  physical robot movement remain out of scope.
- The accepted PIN grant is evidence only for the named child-data read. This
  plan neither implements nor implies permission for memory mutation, light
  control, PC restart, biometric administration, or actuators.

---

## Evidence record

Create an untracked local file under `project-history/acceptance/` named:

```text
YYYY-MM-DD-owner-authenticated-memory.md
```

For each case record only:

- date/time and commit SHA;
- Windows machine and Python version;
- non-secret effective settings;
- route/mode;
- literal STT transcript;
- response text;
- audible yes/no and whether audio matched text;
- `authentication_consumed` state;
- safe audit action/decision/policy IDs;
- timings;
- PASS/FAIL and defect reference.

Do not record PIN, token, salts, verifier, database dump, HTTP authorization
header, or screenshots containing them.

---

### Task 1: Freeze and verify the candidate

**Files:** None.

- [ ] **Step 1: Confirm branch and clean execution candidate**

```powershell
git status --short --branch
git rev-parse HEAD
git log -5 --oneline
```

Expected: the intended reviewed branch/commit; no unexplained working-tree
change. Documentation evidence may remain uncommitted only if this acceptance
was explicitly requested before commit; production code must be frozen.

- [ ] **Step 2: Run automated gates**

```powershell
just lint
just typecheck
just test
just audit
just check
git diff --check
```

Expected: every command exits 0. Record actual test counts and durations.

- [ ] **Step 3: Run focused auth suite**

```powershell
uv run pytest -n0 tests/unit/test_pin_credentials.py tests/integration/test_owner_credentials_schema.py tests/integration/test_personal_setup.py tests/unit/test_owner_authentication.py tests/integration/test_owner_unlock_endpoint.py tests/integration/test_owner_authenticated_turn.py tests/integration/test_owner_authenticated_stream.py tests/unit/test_server_client.py tests/unit/test_robot_app.py -q
```

Expected: PASS. If any named test file differs because an approved earlier plan
changed its name, stop and reconcile Plan 0028 instead of silently skipping it.

---

### Task 2: Prepare the disposable personal profile

**Files:** Untracked acceptance DB and evidence record only.

- [ ] **Step 1: Stop all runtime processes**

Confirm no `just run-server` or `just run-robot` process is using the selected
database.

- [ ] **Step 2: Select/backup the acceptance database**

If resetting, run the existing recoverable command only after resolving the
exact DB path:

```powershell
just reset-db
```

Record the backup path but not its contents. Confirm the next migration run
reaches version 6.

- [ ] **Step 3: Run the local setup wizard**

```powershell
just setup-personal
```

Enter the confirmed minimal security bootstrap locally. Required acceptance
relationships:

```text
Pipec <- child_of - Máximo
Pipec <- child_of - Dominga
```

Enter the PIN only in the masked prompt. Review the redacted summary and type
`SI` only if every displayed non-secret value is correct.

- [ ] **Step 4: Verify safe setup state**

Run the read-only status command defined by Plan 0025:

```powershell
just setup-personal status
```

Record only its counts/status:

- one active owner;
- two active child relations;
- derived personal-security readiness is true;
- extended `meta.onboarding_complete` remains false/absent unless separately
  completed outside this MVP;
- one active PIN credential;
- no plaintext PIN;
- schema version 6.

Do not paste names from raw database dumps into tracked evidence.

---

### Task 3: Establish the public denial baseline

**Files:** Untracked evidence record only.

- [ ] **Step 1: Configure classic public mode**

```text
ROBOT_STREAMING=false
ROBOT_OWNER_UNLOCK_PROMPT=false
VISION_ENABLED=false
SERVER_HOST=127.0.0.1
UVICORN_WORKERS=1
```

- [ ] **Step 2: Start real processes**

Terminal A:

```powershell
just services
just run-server
```

Terminal B:

```powershell
just run-robot
```

- [ ] **Step 3: Run case PA-00 three times**

Speak:

```text
¿Quiénes son mis hijos?
```

Each run must:

- show materially correct literal STT;
- speak the non-disclosing denial;
- not speak Máximo, Dominga, `dos`, or another family value;
- report `authentication_consumed=false`;
- produce a denied authorization audit and no protected v4 read.

Any leak or storage read is a critical FAIL.

---

### Task 4: Prove the classic allowed and consume-once path

**Files:** Untracked evidence record only.

- [ ] **Step 1: Enable startup unlock and restart robot**

Keep the server running. Set:

```text
ROBOT_STREAMING=false
ROBOT_OWNER_UNLOCK_PROMPT=true
```

Restart `just run-robot`, enter the PIN in the masked prompt, and do not copy
the returned token.

- [ ] **Step 2: Prove generic non-consumption (PA-01)**

Speak `¿Qué fecha es hoy?`. Required:

- deterministic date response;
- no family value;
- `authentication_consumed=false`;
- the next protected request can still use the grant if within 60 seconds.

- [ ] **Step 3: Prove allowed child retrieval (PA-02)**

Within the grant lifetime, speak `¿Quiénes son mis hijos?`. Required:

- literal STT materially matches;
- text equals `Tus hijos son Máximo y Dominga.`;
- Piper audibly says the same names and no extra protected fact;
- `authentication_consumed=true`;
- audit actions appear in order:

```text
execute_household_tool
read_household_data
```

- [ ] **Step 4: Prove replay denial (PA-03)**

Without restarting/re-entering PIN, repeat the protected question. Required:
non-disclosing denial, no names/count, no protected reader call, consumed state
false for the already-invalid token.

- [ ] **Step 5: Repeat PA-02/PA-03 three times**

Restart the robot and enter PIN for each fresh PA-02 run. Every allowed run is
followed by its replay denial. A single intermittent failure keeps acceptance
open.

- [ ] **Step 6: Prove expiry denial (PA-04)**

Authenticate, record only the displayed expiry time, allow the 60-second TTL to
pass without sending a protected request, then ask the question. Required:
non-disclosing denial and no protected read. Do not automate a blocking sleep
inside an agent command; this is an operator-timed checkpoint.

---

### Task 5: Prove streaming parity

**Files:** Untracked evidence record only.

- [ ] **Step 1: Restart in streaming mode**

```text
ROBOT_STREAMING=true
ROBOT_OWNER_UNLOCK_PROMPT=true
VISION_ENABLED=false
```

Restart server/robot as required and enter PIN locally.

- [ ] **Step 2: Run streaming allowed case PS-01**

Speak the protected question. Required:

- event order `text_heard -> emotion -> audio+ -> done`;
- audio text `Tus hijos son Máximo y Dominga.`;
- valid audible WAV chunks;
- terminal `authentication_consumed=true`;
- no duplicate/late audio or `done` without audio.

- [ ] **Step 3: Run streaming replay case PS-02**

Repeat without a fresh PIN. Required: audible non-disclosing denial, correct
event order, no names/count, no protected read.

- [ ] **Step 4: Repeat PS-01/PS-02 three times**

Restart/re-authenticate for each fresh allowed run. Record first-audio and
total latency but set no acceptance threshold not already approved by Plan
0022.

- [ ] **Step 5: Reconfirm public streaming baseline PS-03**

Disable unlock prompt/restart robot and ask once. It must deny identically to
classic public mode.

---

### Task 6: Execute and disposition Plan 0013 acceptance debt

**Files:** Untracked evidence record during the run; tracked status updates only
after the candidate has stopped.

- [ ] **Step 1: Execute R1-01 through R1-03 on the accepted candidate**

Use the exact public/classic configuration and cases from the
[P0 runtime acceptance runbook](../../runbooks/p0-runtime-acceptance.md):

- R1-01: deterministic current date;
- R1-02: non-disclosing child-name denial with no protected read;
- R1-03: generic greeting through STT, controller delegation, Piper, and
  audible speaker output.

PA-00 or PA-01 evidence may satisfy the matching R1 case only when it used the
same commit, route, public actor posture, literal utterance, and required
observations. R1-03 must still be executed; do not infer it from the protected
or deterministic cases.

- [ ] **Step 2: Record an independent R1 verdict**

Record literal STT, exact response, audible confirmation, route/configuration,
commit SHA, and pass/fail for every R1 case. Keep this verdict distinct from
the PC-1 PA/PS verdict: Plan 0013 can pass even if a new authenticated scenario
fails, and a PC-1 pass cannot hide a failed classic generic turn.

- [ ] **Step 3: Close Plan 0013 only from complete evidence**

After processes stop, and only if Plan 0013's existing automated evidence plus
R1-01–R1-03 and independent review are complete, update its execution evidence
and move it from `open/` to `completed/`. Update all canonical links in the
same documentation-only change. Otherwise leave it open with the precise
failed or missing case.

---

### Task 7: Inspect privacy-safe audit and logs

**Files:** Untracked evidence record only.

- [ ] **Step 1: Verify action sequences**

Allowed correlation IDs contain exactly tool authorization followed by reader
authorization. Denied/replay/expired IDs contain no
`read_household_data` event.

- [ ] **Step 2: Search logs for forbidden secret/data leakage**

Inspect server and robot logs without printing them wholesale. Search for
header names, credential field names, and known synthetic test PINs. Manually
verify real PIN/token never appears. Protected names may appear only in an
authorized response log if the existing log policy permits it; they must never
appear in a denied decision/audit reason.

- [ ] **Step 3: Confirm memory/RAG isolation**

For PA/PS protected child queries, evidence must show the deterministic v4 tool
source. Legacy semantic retrieval, broad prompts, document RAG, and LLM
generation must not receive the child names.

- [ ] **Step 4: Confirm the capability envelope**

Inspect the typed grant and authorization evidence. It must contain only the
one-use personal protected-read/`child_data` scope. It must contain no generic
`authenticated` authority and no memory-mutation, biometric, home-control,
PC-administration, or actuator capability. Do not add an action endpoint merely
to test this negative boundary.

---

### Task 8: Close or reject the product milestone

**Files:**

- Modify: `docs/architecture/current-state.md`
- Modify: `docs/roadmap/cognitive-roadmap.md`
- Modify: `docs/roadmap/personal-companion-delivery-map.md`
- Modify: `docs/plans/open/0015-personal-companion-design.md`
- Modify: `docs/plans/open/0024-owner-authenticated-memory-mvp-design.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/runbooks/p0-runtime-acceptance.md`
- Modify: `docs/plans/open/0028-owner-authenticated-memory-runtime-acceptance.md`
- Move on independent R1 PASS only:
  `docs/plans/open/0013-p0-voice-controller-bridge.md` to
  `docs/plans/completed/0013-p0-voice-controller-bridge.md`

- [ ] **Step 1: Apply the all-or-nothing verdict**

PASS requires every automated gate and every PA/PS repetition. A privacy leak,
wrong name, wrong route, inaudible result, incorrect STT, replay acceptance, or
missing audit ordering is FAIL.

- [ ] **Step 2: On FAIL, stop without opportunistic code edits**

Record safe observed evidence and create one bounded remediation design/plan.
Do not mark 0024/P1.1 complete and do not continue to face/voice/RAG.

- [ ] **Step 3: On PASS, update canonical status**

Record commit SHA, commands, observed counts, run date, case IDs, and safe
verdict. Mark Plan 0024/P1.1 complete only if no required work remains. Keep
face, speaker verification, fusion, visual identity, and RAG stages explicitly
future.

- [ ] **Step 4: Run documentation hooks**

```powershell
just check
git diff --check
```

- [ ] **Step 5: Request independent evidence review**

The reviewer checks literal STT, exact response, audio confirmation, denied
non-disclosure, token lifecycle, audit ordering, logs, commit SHA, and gate
outputs. Only reviewed evidence closes the milestone.

## Completion criteria

Plan 0028 is complete only when:

- classic allowed/denied/replay scenarios pass three times;
- streaming allowed/denied/replay scenarios pass three times;
- expiry and generic non-consumption pass;
- R1-01–R1-03 have an explicit independent verdict and Plan 0013 remains open
  or moves to `completed/` consistently with that evidence;
- Piper audibly says the exact authorized result;
- denied paths reveal nothing and never read protected values;
- automated, quality, security, and documentation gates pass;
- safe evidence is reviewed independently;
- no implementation change was smuggled into the acceptance run.
