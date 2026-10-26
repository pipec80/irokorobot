# 0072 — Step 0, third plan: the commissioning session (the alta of the robot)

> **Status:** `Ready` / `NOW` (rewritten 2026-10-26 from the 2026-10-23 outline; **promoted by Pipec on
> 2026-10-26** after confirming D-1 to D-13 below). [Plan 0071](../completed/0071-seed-load-file-importer.md)
> closed on 2026-10-26 (PR #214, `dcde265`), so nothing blocks it and queue rule 4 was applied: this plan
> was re-audited against the merged code of [Plan 0070](../completed/0070-seed-load-data-pool-storage.md)
> and Plan 0071 and rewritten in their format before any code. Task 0 re-audits it again against `main`.
> It is executed in a new session from `main`. It implements the rest of
> [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) (decisions 3, 13, 14 and 15) and
> the consents half of [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md)
> decision 10; **when it closes, ADR 0024 becomes `Accepted`** (its three plans done). ADR 0025 stays
> `Proposed` until Plan 0073 closes. Written for an executor who has not seen this repository: what it
> needs is here, in the ADR or in [`seed-data-pool.md`](../../architecture/seed-data-pool.md).

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main` (`feat/0072-commissioning-session`),
> never a git worktree, subagents only if Pipec asks, this plan lives under `docs/plans/`. One commit per
> task; every code test observed RED for the stated reason first (the tasks that are text or manual say
> so). If evidence contradicts the plan, stop and report instead of redesigning. The Bash tool of this
> environment loses backslashes and non-ASCII characters in heredocs: use the Write and Edit tools. Run
> the suite with `MEMORY_ENABLED=false` (CI does). Pin the clock in any test with a date. Never run
> `uv sync --all-packages --all-groups` (it removes the optional `cuda` extra: use `--extra cuda`);
> commit `uv.lock` before `just gate` if it changed. **The processes (server, robot) are started by
> Pipec**, never by the agent.

**Goal.** Pipec's definition of Step 0 is the **alta** of the robot: one guided session in which an
interviewer and the owner load the data pool and enrol face and voice, so the tools defined now and
later find their data and hardware ready. Plans 0070 and 0071 gave the database its places and the
importer. This plan gives the **session**: one command, `just commission`, driven by the state of the
database and of the server (as [`scripts/onboard.py`](../../../scripts/onboard.py) is), that tells the
interviewer the exact next step and never asks for the server to be both on and off. It walks the
checklist of [ADR 0024 decision 13](../../adr/0024-seed-load-senses-secrets-and-channels.md), reads the
biometric notice and records the consents, enrols the face in several frames and the voice in a short
session, produces the readiness report of decision 14, writes the acta, records the baseline backup and
closes the window. It enables no capability: a stored phone still calls nobody.

**Architecture.** (1) The acta columns that migration 011 already created but nobody fills yet
(`biometric_notice_version`, `consents_json`, `modalities_json`, the two backup references and their
destruction dates, `readiness_json`) gain their writer and reader **in `commissioning.py`**, the one
module with SQL on the two tables. (2) A pure capability catalogue and a pure readiness evaluator derive
each capability's data-readiness from the section statuses and the rows, and combine it with a typed
hardware status. (3) A session module drives the existing face and voice enrolment endpoints over
loopback (several frames, three or more voice references), the biometric notice and the consents, all
through injected adapters so they test without a camera or a microphone. (4) An acta renderer writes a
Markdown record under `data/commissioning/` (**no household value**), records the baseline backup and
derives the modalities from the database, then calls the existing `close_commissioning`. (5) A
status-driven command, `commission`, is the state machine: it performs the biometric, readiness, acta and
closing steps itself and **delegates** the three server-stopped, already-guarded steps (`reset-db`,
`setup-personal`, `seed-import`) by telling the interviewer the exact command, the way `onboard.py`
tells you to start the server.

**Tech Stack.** Python 3.12, aiosqlite, pydantic, httpx (already a dependency; used synchronously in the
command for the health probe, like `seed_cli`), pytest. **No new dependency. No migration (migration 011
already has every column). No new route, status code or response field.** One new console script and one
`just` recipe.

**Spec:** [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) decisions 3, 13, 14 and 15
(and the consents of decision 6/13), [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md)
decision 10, [`seed-data-pool.md`](../../architecture/seed-data-pool.md) (*Capabilities and what they
need*), [Plan 0070](../completed/0070-seed-load-data-pool-storage.md) and
[Plan 0071](../completed/0071-seed-load-file-importer.md) (the interfaces they produced).

## Decisions

Pipec confirmed D-1 to D-13 on 2026-10-26, which lets the plan be written; it stays `Draft` until he
promotes it. D-1 to D-8 are the eight he was asked; D-9 to D-13 are the implementation decisions the
re-audit raised.

1. **D-1 — One command, a state machine.** `just commission`, driven by the database and the server
   state like `scripts/onboard.py`: it tells the exact next step, never asks for the server to be both
   on and off, and is safe to re-run. Not a runbook document. *Cost: more code than a document, in
   exchange for an automatic acta and no skipped step.*
2. **D-2 — No per-person voice settings or pronunciation table.** The seeded names are already the
   recognizer's hotwords (the catalogue says so); a per-person settings table would be code with no
   consumer (YAGNI). ADR 0024 decision 15 defers *to this plan* whether a pronunciation field joins the
   pool: this plan **records that it does not**, with no code. Added when a measurement asks for it.
3. **D-3 — The biometric notice** is a short Spanish text, `tú`, version `v1`, tracked in the repository
   at `docs/legal/biometric-notice-v1.md`; the command reads it, shows it and stores its version in
   `biometric_notice_version`. It does not block the owner-builder; a legal review (Law 21.719) must
   come before it is used with another person. *Cost: a later legal review bumps the version; it is
   versioned, so that is cheap.*
4. **D-4 — The readiness report covers only the capabilities that exist today** (the six `exists` rows
   of the catalogue): speak, understand speech, recognize the owner by face, recognize the owner by
   voice, remember a taste, describe a scene. Every `planned`/`idea` capability reports **not
   supported** automatically. Data-readiness is **derived** (statuses and rows, never typed);
   `supported`, `configured`, `verified` are typed by a person, one capability at a time; `verified`
   means a concrete real turn the interviewer marks.
5. **D-5 — The acta** is a Markdown file under `data/commissioning/` (git-ignored), **no household
   value**, kept by Pipec. The structured acta lives in the record's columns; the file is its readable
   rendering.
6. **D-6 — Five face frames and three voice references**, the minimum of ADR 0024 decision 15 (three is
   `settings.speaker_min_reference_count`): face near, far, with and without glasses, another light;
   voice three clips of a short read script. Recalibrated when the robot moves to the Raspberry Pi.
7. **D-7 — The real database is reset only at the start of the real alta**, after this plan is merged
   and proven on a database kept apart, with a backup. It is the acceptance step (Task 8); no plan code
   triggers a reset.
8. **D-8 — The amendment path for contacts and medications after the closing is Plan 0073**, already
   owned by ADR 0024 decision 8 and ADR 0025. This plan enables no alert or reminder, so the gap does
   not bite in Phase 0.
9. **D-9 — The modalities enrolled are derived from the database, not typed:** `pin` from the active
   owner credential, `face` from a stored face profile, `voice` from voice profiles at or above
   `settings.speaker_min_reference_count`. More honest than a typed list and it cannot drift.
10. **D-10 — The voice session unlocks once per reference.** Each `/auth/owner/voice/enroll` consumes a
    one-use owner-unlock token (ADR 0015), so three references prompt the PIN three times (and the five
    face frames five times). No endpoint changes; the demos already work this way.
11. **D-11 — The session-details writer lives in `commissioning.py`.** It is the only module allowed SQL
    on `commissioning_records` and `commissioning_sections` (an architecture guard), so the new columns
    are written and read there; the readiness, acta and session modules call it.
12. **D-12 — The operations-plane consents are typed by the interviewer** at the notice step: `telemetry`,
    `remote_support` and `backup` (yes/no) and a free-text label for the backup destination
    (ADR 0025 decision 10). They are stored in `consents_json`; recording a consent enables nothing.
13. **D-13 — The command delegates the three server-stopped steps.** `reset-db`, `setup-personal` and
    `seed-import` are already guarded, idempotent, server-stopped recipes; the state machine detects
    where the session is and prints the exact command to run next (as `onboard.py` tells you to start
    the server), rather than re-implementing them. It performs directly only the steps that have no
    command yet: the notice and consents, the face and voice sessions, the verification prompt, the
    readiness report, the baseline backup record, the acta and the closing.

## Review Focus

The failure modes the tasks' main tests would miss; each line has its test in the task named.

1. A **closed commissioning**: every session-details write (notice, consents, modalities, backups,
   readiness) raises `CommissioningClosedError` and stores nothing, as `record_import` already does
   (Task 1).
2. The **acta holds no household value**: a canary owner name, a child name, a phone or a taste stored in
   the pool is absent from the rendered Markdown, every log record and the record's `repr` (Task 7).
3. **Speaker authentication disabled** (`SPEAKER_AUTHENTICATION_ENABLED=false`): `/voice/enroll` returns
   503; the voice session reports the modality as not enrolled, records `voice` **outside** the
   modalities, and the command does not crash (Task 5).
4. A capability with **data present but hardware not verified** is reported *blocked by hardware*, never
   *ready*; one with hardware and no data is *blocked by data*; approving the form turns nothing on
   (Tasks 2, 3).
5. The state machine **never asks for the server to be both on and off**: an off-step while the server
   answers `/health` is refused with the next step named, and an on-step while it does not answer is
   refused likewise (Task 6).

## Global Constraints

- **No real household data anywhere:** invented canaries (`scripts/check_reserved_terms.py`), invented
  phones such as `+56900000001`. The acta and every log carry **no** household value; the interviewer's
  label is the record's only free text (it never reaches a log or a `repr`, as today).
- `.claude/rules/` apply: English identifiers, docstrings and comments; Google docstrings on every public
  function; type hints everywhere; no `print()` outside a CLI adapter; logging with `%` and never a
  value; specific exceptions, always chained (`from exc`); `pathlib`; `match` for dispatch; functions of
  about 30 lines, files of about 200 (split when a second responsibility appears); `Any` only with its
  reason.
- **The command performs the health probe synchronously before `asyncio.run`** (the pattern of
  `seed_cli.main`), with the port from the settings; it must not construct an `httpx.AsyncClient` outside
  the lifespan (the architecture guard) and must not block the event loop.
- A value appears only on the terminal of the person who runs the command, never in a logger. Secret and
  biometric handling is untouched: audio and frames are embedded and discarded by the existing endpoints,
  never stored.
- No new dependency, **no migration**, no new route, status code, response field or setting. `robot/src`,
  `/chat`, `/transcribe`, the policy (`cognition/authorization.py`), the spoken dialogue, the seed
  importer (`memory/seed_*`) and `personal_setup.py` are **not** edited.
- Titles of commits at most 72 characters; one commit per task; `ruff` over explicit paths including
  `scripts/`; `mypy server/src robot/src` and `pyright` clean; `just gate` green with
  `MEMORY_ENABLED=false`.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/` (including
  `scripts-powershell.md` and `fastapi.md`).
- [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) (decisions 3, 6, 13, 14, 15),
  [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md) (decisions 9, 10, 11),
  [`seed-data-pool.md`](../../architecture/seed-data-pool.md) (*Capabilities and what they need*),
  Plans 0070 and 0071 (the interfaces they produced and their execution records).
- `server/src/server/memory/commissioning.py` (the columns, `_COLUMNS`, `CommissioningRecord`,
  `record_import`, `set_section_status`, `list_section_statuses`, `close_commissioning`,
  `importer_window_open`, `get_open_commissioning`, `ENROLLABLE_MODALITIES`, the enums),
  `server/src/server/memory/migration_011_contacts_and_commissioning.sql` (the nullable acta columns),
  `server/src/server/memory/{seed_import,seed_run}.py` (`count_rows`, `count_v4_rows`,
  `count_active_contacts`, `resolve_ready_owner`), `server/src/server/memory/care_contacts.py`
  (`list_active_contacts`).
- `server/src/server/seed_cli.py` (the command shape, the health probe, injected adapters),
  `server/src/server/personal_setup.py` (`read_personal_setup_status`, `check_db_available`),
  `scripts/onboard.py` (the status-driven state machine, the face phase),
  `scripts/speaker_auth_demo.py`, `scripts/face_auth_demo.py`, `scripts/mic_test.py` (levels and
  devices), `server/src/server/routers/auth.py` (`/auth/owner/unlock`, `/auth/owner/face/enroll`,
  `/auth/owner/voice/enroll`, the 503 when speaker auth is off), `server/src/server/settings.py`
  (`speaker_min_reference_count`, `speaker_min_enrollment_s`, `face_authentication_enabled`,
  `speaker_authentication_enabled`, the port), `scripts/reset_db.ps1`, `justfile`, `server/pyproject.toml`.
- `tests/unit/test_architecture_guards.py`, `tests/integration/test_commissioning.py`,
  `tests/integration/test_owner_face_enrollment.py`, `tests/integration/test_owner_voice_enrollment.py`.

## Permitted files

- Production: `server/src/server/memory/commissioning.py`; new
  `server/src/server/memory/commissioning_readiness.py`, `server/src/server/memory/commissioning_acta.py`;
  new `server/src/server/commission_session.py`, `server/src/server/commission_cli.py`;
  `server/pyproject.toml` (one script: `commission = "server.commission_cli:main"`); `justfile`
  (one recipe). New `docs/legal/biometric-notice-v1.md`.
- Tests: the files named in each task and their new files.
- Docs (Task 8): the list there.

No migration, no new route, status code, response field or setting. `robot/src`, the policy, the spoken
dialogue, the seed importer and `personal_setup.py` are not edited.

---

## Task 0: Revalidate the baseline

- [ ] **Step 0:** this plan says `Ready` and Pipec confirmed D-1 to D-13 in writing. Otherwise stop.
- [ ] **Step 1:** `git checkout main && git pull`, a clean tree,
  `git checkout -b feat/0072-commissioning-session`.
- [ ] **Step 2:** `just gate` with `MEMORY_ENABLED=false`; record the count (4720 at `dcde265`,
  otherwise the count of `main` now).
- [ ] **Step 3: Re-audit** (each must find what the plan names, or a difference is reported before any
  code): the acta columns exist and are nullable
  (`rg -n "biometric_notice_version|consents_json|modalities_json|readiness_json|baseline_backup_reference" server/src/server/memory/migration_011_contacts_and_commissioning.sql`);
  `commissioning._COLUMNS` and `CommissioningRecord` stop at `closed_at` and read none of the five;
  `close_commissioning`, `list_section_statuses`, `get_open_commissioning` exist as Plan 0070 produced
  them (`rg -n "def close_commissioning|def list_section_statuses|def get_open_commissioning" server/src`);
  the count helpers exist (`rg -n "def count_rows|def count_v4_rows|def count_active_contacts|def resolve_ready_owner" server/src`);
  `list_active_contacts` exists (`rg -n "def list_active_contacts" server/src`); the enrolment endpoints
  and the 503 gate (`rg -n "/face/enroll|/voice/enroll|speaker_authentication_enabled" server/src/server/routers/auth.py`);
  the architecture guard that limits SQL on the two commissioning tables
  (`rg -n "commissioning_records|commissioning_sections" tests/unit/test_architecture_guards.py`);
  `settings.speaker_min_reference_count` and the health-probe pattern of `seed_cli.main`.

## Task 1: The acta columns — the session-details writer and reader

**Files:** `server/src/server/memory/commissioning.py`; tests `tests/integration/test_commissioning.py`
(new cases) and `tests/unit/test_architecture_guards.py` (unchanged, run as a guard).

**Interfaces — Consumes:** the open record (`get_open_commissioning`, `_read_open`). **Produces** in
`commissioning.py` (every write joinable with `manage_transaction=False`, every one refusing a closed
record through `_read_open`):

- `async record_biometric_notice(record_id: int, version: str, *, manage_transaction: bool = True) -> None`
  — sets `biometric_notice_version`; refuses a version not matching `r"v[0-9]+"`.
- `async record_consents(record_id: int, consents: Consents, *, manage_transaction: bool = True) -> None`
  — stores a frozen `Consents(telemetry: bool, remote_support: bool, backup: bool, backup_destination: str | None)`
  as `consents_json`; the destination label is 0 to 80 printable characters and carries no household value
  (the same control-character check as the interviewer label).
- `async record_modalities(record_id: int, modalities: frozenset[Modality], *, manage_transaction: bool = True) -> None`
  — stores the enrolled modalities as a sorted JSON list in `modalities_json`; every member must be in
  `ENROLLABLE_MODALITIES`.
- `async record_backup(record_id: int, *, which: BackupKind, reference: str, destroy_by: str, manage_transaction: bool = True) -> None`
  — `BackupKind(StrEnum)` is `PRE_RESET` and `BASELINE`; writes `backup_reference`/`backup_destroy_by` or
  `baseline_backup_reference`/`baseline_destroy_by`; `reference` 1 to 200 printable characters (a path),
  `destroy_by` a date `r"\d{4}-\d{2}-\d{2}"`.
- `async record_readiness(record_id: int, readiness_json: str, *, manage_transaction: bool = True) -> None`
  — stores the readiness report as a JSON string (built by Task 2); refuses a string that does not parse.
- A new `SessionDetails` frozen dataclass and `async read_session_details(record_id: int) -> SessionDetails`
  returning the five columns decoded (the notice version, the consents, the modalities, the two backups,
  the readiness), for the acta of Task 7. `_COLUMNS` is extended to select them and `_record`/`read_session_details`
  decode them; `CommissioningRecord` keeps its current fields (the acta reads the details through
  `read_session_details`, so no existing caller changes).

- [ ] **Step 1: Failing tests** (temporary SQLite, canaries). Open a record; each writer stores its
  column and `read_session_details` returns it; a second write overwrites; every writer on a **closed**
  record raises `CommissioningClosedError` and stores nothing; `record_biometric_notice` refuses `"1"`
  and `"draft"`; `record_consents` refuses a destination with a control character and stores `None` when
  absent; `record_modalities` refuses `fingerprint`; `record_backup` refuses a bad date and writes the
  baseline columns only for `BASELINE`; `record_readiness` refuses non-JSON. A **canary destination
  label and a canary notice version leave no household value in a log** (`caplog` at DEBUG). The
  architecture guard still passes (no new module has SQL on the two tables). **Expected RED:** the
  functions do not exist; `read_session_details` is undefined.
- [ ] **Step 2: Implement** the writers (each `UPDATE ... WHERE id = ?` inside `_transaction`), the
  frozen `Consents`, `BackupKind` and `SessionDetails`, and extend `_COLUMNS`/`read_session_details`.
- [ ] **Step 3:** run `test_commissioning.py` and the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): write the commissioning acta columns (plan 0072)`.

## Task 2: The capability catalogue and the pure readiness evaluator

**Files:** new `server/src/server/memory/commissioning_readiness.py`; tests new
`tests/unit/test_commissioning_readiness.py`, `tests/integration/test_commissioning_readiness_gather.py`.

**Interfaces — Consumes:** `Section`, `SectionStatus` (Task 1 / Plan 0070), `list_section_statuses`,
`care_contacts.list_active_contacts`, `seed_import.count_v4_rows`. **Produces:**

- `Capability(StrEnum)` with exactly the six `exists` capabilities of the catalogue: `speak_reply`,
  `understand_speech`, `recognize_face`, `recognize_voice`, `remember_taste`, `describe_scene`.
- frozen `CatalogueEntry(capability, data_sections: frozenset[Section], needs_data: bool)` and a module
  tuple `CATALOGUE` with one entry per capability (the *Data it needs from the pool* column: e.g.
  `describe_scene` needs `function`; `speak_reply` and `remember_taste` need none).
- frozen `HardwareStatus(supported: bool, configured: bool, verified: bool)` (the typed triple of D-4).
- frozen `CapabilityReadiness(capability, data_present: bool, hardware: HardwareStatus, verdict: Verdict)`
  where `Verdict(StrEnum)` is `ready`, `blocked_by_data`, `blocked_by_hardware`, `blocked_by_both`.
- `evaluate_readiness(statuses: Mapping[Section, SectionStatus], contact_count: int, v4_counts: V4Counts, hardware: Mapping[Capability, HardwareStatus]) -> tuple[CapabilityReadiness, ...]`
  — **pure**: a capability's `data_present` is true when it needs no data, or when every section it needs
  is `provided`; the verdict is `ready` only when `data_present` and `supported and configured and
  verified`, else the matching `blocked_*`. `readiness_to_json(report) -> str` and its inverse for the
  acta.
- `async gather_hardware_inputs(record_id: int) -> tuple[Mapping[Section, SectionStatus], int, V4Counts]`
  — reads the statuses, the active-contact count and the V4 counts (the async shell around the pure core).

- [ ] **Step 1: Failing tests.** *Pure:* a capability needing no data is `data_present` regardless of the
  statuses; `describe_scene` is present only when `function` is `provided` (not `none`, `not_asked`,
  `declined`); the verdict is `ready` only with all three hardware booleans true and the data present;
  data yes / hardware no is `blocked_by_hardware`, data no / hardware yes is `blocked_by_data`, neither is
  `blocked_by_both`; `readiness_to_json` round-trips. `CATALOGUE` has exactly the six capabilities and no
  `planned`/`idea` one. *Gather:* on a temporary database it returns the statuses of the open record, the
  contact count and the V4 counts. **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement** the catalogue as a table, the pure evaluator and the thin gatherer; no clock.
- [ ] **Step 3:** run both files; lint and types.
- [ ] **Step 4: Commit** `feat(server): derive the capability readiness report (plan 0072)`.

## Task 3: The biometric notice and the consents step

**Files:** new `docs/legal/biometric-notice-v1.md`; new (or extended) `server/src/server/commission_session.py`;
tests new `tests/unit/test_commission_notice.py`.

**Interfaces — Produces** in `commission_session.py`: `BIOMETRIC_NOTICE_VERSION = "v1"`;
`BIOMETRIC_NOTICE_PATH` (the tracked doc); `load_biometric_notice() -> str` (reads the doc, raises a
closed `CommissionError(ValueError)` if it is missing); `read_consents(read_text: ReadText) -> Consents`
(asks the three yes/no questions in Spanish — `tú` — and the backup destination label, returns the frozen
`Consents` of Task 1); the notice and the questions are printed by an injected `write_text`.

- [ ] **Step 1: Failing tests.** `load_biometric_notice` returns the file's text and raises
  `CommissionError` for a missing path (monkeypatched). `read_consents` with stubbed answers returns the
  expected `Consents`; `no`/anything but `si` is false; an empty destination is `None`; the questions are
  in `tú` (a test greps the prompts for voseo forms and finds none). `BIOMETRIC_NOTICE_VERSION` matches
  `r"v[0-9]+"`. **Expected RED:** the module and the constant do not exist.
- [ ] **Step 2: Write** the notice (short, Spanish, `tú`: what face and voice are stored for, that they
  are local, consented and revocable, that audio and frames are discarded after the turn, who to tell to
  revoke; no household value) and the two functions.
- [ ] **Step 3:** run the file; `uv run python scripts/check_reserved_terms.py`; lint and types.
- [ ] **Step 4: Commit** `feat(server): add the biometric notice and the consents step (plan 0072)`.

## Task 4: The face session (several frames)

**Files:** `server/src/server/commission_session.py`; tests new `tests/unit/test_commission_face_session.py`.

**Interfaces — Produces:** `async run_face_session(*, unlock, capture, enroll, write_text, frames: int = 5) -> int`
— the number of frames enrolled. The adapters are injected exactly like `seed_cli`: `unlock()` returns a
one-use token (the owner PIN unlock for `biometric_admin`), `capture()` returns one JPEG frame, `enroll(token, frame)`
posts to `/auth/owner/face/enroll` and returns the profile id or raises. The function guides the five
poses of D-6 (distance, glasses, lighting) through `write_text`, unlocks **once per frame** (D-10), and
stops with a clear message if a frame is rejected (`no_face`, `multiple_faces`, `low_quality`,
`face_too_small`), returning how many succeeded.

- [ ] **Step 1: Failing tests** (all adapters stubbed; no camera, no HTTP). Five good frames enrol five
  times, each with its own `unlock`, and the five pose prompts appear in order; a rejected frame stops the
  session and the count reflects the successes; an `unlock` that raises propagates a `CommissionError`; no
  frame, token or image byte reaches a log. **Expected RED:** `run_face_session` does not exist.
- [ ] **Step 2: Implement** with the injected adapters (the real adapters, wired in Task 6, reuse
  `scripts/onboard.py`'s unlock-and-capture and the `/face/enroll` call).
- [ ] **Step 3:** run the file; lint and types.
- [ ] **Step 4: Commit** `feat(server): drive the face enrolment session (plan 0072)`.

## Task 5: The voice session (script, references, level check)

**Files:** `server/src/server/commission_session.py`; tests new `tests/unit/test_commission_voice_session.py`.

**Interfaces — Produces:** `READING_SCRIPT` (a short Spanish paragraph, `tú`, read aloud by the owner;
no household value); `async run_voice_session(*, unlock, record, level_check, enroll, write_text, references: int | None = None) -> int`
— the number of references enrolled (`references` defaults to `settings.speaker_min_reference_count`).
`record()` returns one contract WAV clip (16 kHz mono int16); `level_check(clip)` returns whether the
level and distance are acceptable (reuses `mic_test`'s level logic through the adapter); `enroll(token, clip)`
posts to `/auth/owner/voice/enroll`. The function prints the reading script, captures and enrols the
references one at a time (an unlock each, D-10), warns and re-captures on a failed level check, and
**handles the 503** when `SPEAKER_AUTHENTICATION_ENABLED=false`: it reports the voice modality as not
enrolled and returns 0 (Review Focus 3). Audio is embedded and discarded by the endpoint; the session
stores nothing.

- [ ] **Step 1: Failing tests** (adapters stubbed). Three good clips enrol three references and print the
  script; a clip that fails the level check is re-captured and does not consume a reference; a stubbed 503
  from `enroll` returns 0 and prints a clear message without crashing; an `unlock` that raises propagates;
  no clip or token reaches a log. **Expected RED:** `run_voice_session` does not exist.
- [ ] **Step 2: Implement** with the injected adapters (wired in Task 6 to the unlock, a microphone
  capture like `speaker_auth_demo._record`, and the `/voice/enroll` call).
- [ ] **Step 3:** run the file; lint and types.
- [ ] **Step 4: Commit** `feat(server): drive the voice enrolment session (plan 0072)`.

## Task 6: The orchestrating command and its status-driven state machine

**Files:** new `server/src/server/commission_cli.py`; `server/pyproject.toml`
(`commission = "server.commission_cli:main"`); `justfile` (recipe `commission *ARGS`, ASCII-only echo,
Spanish comment); tests new `tests/integration/test_commission_cli.py`.

**Interfaces — Consumes:** `read_personal_setup_status`, `importer_window_open`, `get_open_commissioning`,
Tasks 1 to 5. **Produces:** `CommissioningStep(StrEnum)` (`preflight`, `reset`, `owner`, `notice_consent`,
`face`, `voice`, `load`, `verify`, `readiness_backup_acta`, `close`, `done`), mirroring ADR 0024
decision 13; `async decide_step(*, server_up: bool) -> CommissioningStep` — the pure-ish state function
that reads the database and the server state and returns the next step, **refusing a step whose server
state is wrong** (an off-step with `server_up`, an on-step without: Review Focus 5); `async run_commission(...)`
that performs the current step (delegating `reset`, `owner`, `load` by printing the exact command —
`just reset-db`, `just setup-personal`, `just seed-import ... --apply` — D-13) and drives the rest with
the sessions of Tasks 3 to 5 and the acta of Task 7; `main()` with the **synchronous** health probe
before `asyncio.run` (the `seed_cli` pattern), so the command knows the server state without being asked.

- [ ] **Step 1: Failing tests** (database state and server state stubbed; the step adapters stubbed).
  `decide_step` returns each step for the matching database state (no owner → `owner`; owner ready, no
  open record and the server up → `notice_consent`/`face`; an open record with the biometrics enrolled →
  `load`; a closed record → `done`); an **off-step with the server up** and an **on-step with the server
  down** are refused with the next action named and nothing is performed; the delegated steps print the
  exact command and perform no write; the command is re-runnable (running twice from the same state is
  idempotent). **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement** the state machine; wire the real adapters of Tasks 3 to 5 (`onboard`-style
  unlock and capture, the enrol calls); `argparse` with any free-text argument as `nargs="+"` (the `just`
  rule on Windows); never create a database or run migrations here.
- [ ] **Step 3:** run the file; `ruff` over `server/src scripts tests`; types.
- [ ] **Step 4: Commit** `feat(server): add the commission command and its state machine (plan 0072)`.

## Task 7: The acta, the baseline backup and the closing

**Files:** new `server/src/server/memory/commissioning_acta.py`; `server/src/server/commission_cli.py`
(the closing step calls it); tests new `tests/integration/test_commissioning_acta.py`.

**Interfaces — Consumes:** `read_session_details`, `read_personal_setup_status`, `list_section_statuses`,
`get_open_commissioning`, `close_commissioning`, Task 2's report, `ENROLLABLE_MODALITIES`. **Produces:**

- `async derive_modalities() -> frozenset[Modality]` — `pin` from the active owner credential, `face`
  from a stored face profile, `voice` from voice profiles at or above `settings.speaker_min_reference_count`
  (D-9), reading each repository through its existing getter (no SQL here; the guard allows none).
- `render_acta(record: CommissioningRecord, details: SessionDetails, statuses: Mapping[Section, SectionStatus], readiness: tuple[CapabilityReadiness, ...]) -> str`
  — **pure**: a Markdown acta with the date, the interviewer's label and role, the confirmation mode, the
  installation id, the consents, the modalities, each section's status, the file hash, the counts, the
  backup paths and destruction dates, the disk declaration and the readiness report — and **no household
  value** (a test asserts canaries are absent).
- `async write_acta(record_id: int, *, out_dir: Path, now: str) -> Path` — renders and writes
  `data/commissioning/acta-<installation_id>.md`, creating `data/commissioning/` (git-ignored); returns
  the path.
- `async close_session(record_id: int, *, baseline_reference: str, baseline_destroy_by: str, out_dir: Path, now: str) -> Path`
  — records the baseline backup (Task 1), derives and records the modalities and the readiness, writes the
  acta and calls `close_commissioning`; returns the acta path.

- [ ] **Step 1: Failing tests** (temporary SQLite, canaries). `derive_modalities` returns `pin` after
  `setup-personal`, adds `face`/`voice` when a profile exists at or above the reference count. `render_acta`
  contains the structured fields and **none** of a canary owner name, child name, phone or taste. `write_acta`
  writes the file under a temporary `out_dir`. `close_session` records the baseline columns, the modalities
  and the readiness, writes the acta and sets `closed_at`; a second close raises `CommissioningClosedError`;
  after it `importer_window_open` is false. **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement** with small functions; the acta renderer is pure and the writers join no
  transaction they do not own.
- [ ] **Step 3:** run the file, `test_commissioning.py` and the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): write the acta and close the commissioning (plan 0072)`.

## Task 8: Documentation truth, ADR 0024 `Accepted`, and the real commissioning (text and a hardware session)

- [ ] [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) → **`Accepted`** (its three
  plans closed), its *Follow-up* and *Implemented by* updated; [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md)
  decision 10 pointer (the consents are now captured; its status stays `Proposed` until Plan 0073);
  [`seed-data-pool.md`](../../architecture/seed-data-pool.md) (the commissioning's consents and backups
  now shipped; the readiness report); `identity-and-access.md` (the modalities enrolled, the consents);
  `current-state.md` and its Archify diagram (validate, then deliver); the roadmap's Step 0 row; the plan
  index, the open-plan index and the ADR index; the local tracking table (never committed). Move this plan
  to `completed/` with its execution record.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, `uv run python scripts/check_reserved_terms.py`,
  every relative link resolves, `just gate` with `MEMORY_ENABLED=false`.
- [ ] **Acceptance by Pipec — the real alta** (his machine, his `.env`; outcomes only in
  `docs/evals/0072-commissioning-acceptance.md`, never a household value; D-7): reset his real database
  with a backup, `just setup-personal` with his PIN, `just commission` through the notice, consents, five
  face frames and three voice references, load his real file with `just seed-import ... --apply`, verify a
  real turn by face and voice and the children's count, the readiness report, the baseline backup, the
  acta and the closing. The record notes outcomes only; the import file and the paper form are destroyed.
- [ ] Commit `docs: close plan 0072`; PR; merge only with Pipec's go-ahead.

## ADR 0024 coverage

| ADR 0024 | Where |
|---|---|
| 3 the privacy of the senses (audio and frames discarded; consents recorded) | Tasks 3, 4, 5 |
| 6/13 the consents, the modalities, the backups in the record | Tasks 1, 3, 7 |
| 13 the order of the commissioning and the freeze | Tasks 6, 7 |
| 14 a capability is ready only with data and hardware | Tasks 2, 3 |
| 15 the identity modalities and the voice session | Tasks 4, 5, 7 |
| ADR 0025 decision 10 (the operations-plane consents) | Tasks 1, 3 |

## Completion criteria

1. Tasks 0 to 8 done, one commit per task, every code test RED before GREEN (Task 8 is text and a
   hardware session, declared).
2. `just gate` green with `MEMORY_ENABLED=false`; the Plan 0070 and 0071 tests unchanged; no migration,
   no new route or setting.
3. The acta carries no household value; a closed commissioning refuses every session-details write; the
   readiness report is derived for data and typed for hardware and turns nothing on; the voice session
   survives the speaker-auth-off 503; the state machine never asks for the server to be both on and off.
4. ADR 0024 is `Accepted`; the real commissioning is accepted on Pipec's machine with outcomes recorded.

## Rollback boundary

Each task is one commit and there is no migration. Tasks 1 to 7 only add functions and two modules that
nothing else calls until Task 6 wires them, so reverting any one is safe. The command and the recipe are
additive. Task 8 is documentation and an acceptance run.

## Not here, and why

- **The amendment path for contacts and medications after the closing:** [Plan 0073](0073-local-admin-crud.md)
  (ADR 0024 decision 8); this plan enables no alert or reminder.
- **Per-person voice settings and a pronunciation field:** out of scope (D-2); added when a measurement
  asks for it.
- **Reading any of the pool by voice, the audience rule, the emergency sheet, the call and the alert:**
  CM-5 and the care ADR.
- **A fingerprint, iris or chip adapter:** the electronics track and its own ADR.
- **The Excel/CSV to TOML converter and the 107-question interview interface:** a later Step 0 plan.
- **The remote operations plane (telemetry, backup, updates, support session):** [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md);
  this plan only records the consents.
