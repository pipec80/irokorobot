# 0076 — CM-4: the conversation record, the diary, and the retirement of the legacy memory path

> **Status:** `Ready` and `NOW`. Written 2026-10-29 and **promoted by Pipec the same day** (D-1 to D-12
> below confirmed); Pipec chose to execute it in the same session that wrote it. [ADR 0027](../../adr/0027-conversation-record-and-the-diary.md) (`Proposed`) is its design;
> it moves to `Accepted` when this plan closes. The measurement it starts from is
> [Plan 0075](../completed/0075-cm4-pre-measurement.md) ([record](../../evals/0075-cm4-pre-measurement.md)).
> Detailed against `main` at `e42346a`; queue rule 4 applies at execution: Task 0 re-verifies every
> claim below against the merged code before any code, and **stops and reports** if one is false.
> Written for an executor who has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main` (`feat/0076-cm4-conversation-record`),
> never a git worktree, subagents only if Pipec asks, this plan lives under `docs/plans/`. One commit
> per task; every test seen RED for the stated reason first. If evidence contradicts the plan, stop
> and report instead of redesigning. The Bash tool of this environment loses backslashes and
> non-ASCII characters in heredocs: use the Write and Edit tools. Commit messages: Conventional
> Commits, title at most 72 characters, check `git log` after each commit (the hook rejects silently);
> do not pipe `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false`
> as CI does, and have each test that needs memory set `settings.memory_enabled` itself. Never run
> `uv sync --all-packages --all-groups` (it removes the optional `cuda` extra). **Do not run
> `just gate` in the background while Pipec rehearses** (about 3.5 GB of RAM). **The server and the
> robot are started by Pipec**, never by the agent. Before pushing, run `pyright`, `ruff` and `mypy`
> over the **whole** project and lint `scripts/` with explicit paths (`ruff check .` skips it, the
> pre-commit hook does not).

## Decisions

Confirmed by Pipec on 2026-10-29 (before the plan was written):

- **D-1** A turn is the owner's only when **the face names the owner and the voice of the turn's own
  clip verifies** against the owner: the same check the candidate path runs (`verify_face_and_voice`).
  Voice alone does not count, so a recording of the owner cannot write into the diary. *Clarifies
  ADR 0027 decision 3, which says both «the voice decides» and «the check the candidate path already
  runs».*
- **D-2** The diary job writes **only the episode**. Candidates keep coming from the live path as
  today (ADR 0021); each recorded turn keeps its `correlation_id`, which joins it to the candidates
  and audit rows of that turn, so CM-6 can delete them in cascade. *Amends ADR 0027 decision 8.*
- **D-3** Revoking the conversation consent **stops recording and deletes every record and every
  episode**, like revoking a face or a voice deletes the prints.
- **D-4** The legacy path is retired **completely**: `build_context`, `semantic.py`, `relations.py`,
  the `MANUAL` gate of the text turn, the `memories` and `vec_memories` tables, and also the prompt
  surface that only that path fed (`MemoryContext`, the memory block, onboarding and its slot, the
  characters' `onboarding_prompt`, the eval-script variants built on them). Nothing dead is left.

The author's calls, confirmed by Pipec on promotion (2026-10-29):

- **D-5** Each turn is written **at the moment**, in a background task after the reply is sent (the
  voice check runs there too), so a crash in the middle of a conversation loses nothing already said.
- **D-6** One JSON entry per **exchange**: `{"at", "heard", "said", "voice", "cid"}`. «Who» is the
  key: `heard` is the person, `said` is the robot. `heard` is cut at 2000 characters and `said` at
  4000, so one entry always fits in a segment.
- **D-7** Recorded: every reply spoken on the classic and the streaming voice routes, generic and
  deterministic, including the fallback phrase. Not recorded: the «repeat, please» of unclear speech,
  the vision frame request cue, `/vision/respond`, `/chat` (no speech-to-text) and the memory offer
  phrase (a memory dialogue, not the conversation).
- **D-8** Defaults: the idle time is the session's (`WORKING_MEMORY_IDLE_SECONDS`, 180 s); a segment
  holds at most 60 exchanges and 64 KiB; an eligible record is kept 365 days, a not-eligible one
  30 days; the whole record is capped at 200 MB; the diary job ticks every 120 s; a summary is at
  most 600 characters. The acceptance measures real sizes (Task 13) and the defaults are revisited
  there.
- **D-9** Two kill-switches, off in the code and on in a delivered robot: `CONVERSATION_RECORD_ENABLED`
  and `CONVERSATION_EPISODES_ENABLED` (the diary needs the record). The diary is written **only while
  no conversation is open**, takes the same extraction limiter as the candidates (ADR 0027: «with the
  budget of the extraction job»), and gives up on a record after 3 failed attempts.
- **D-10** The consent is a grant row (`conversation_consent_grants`, purpose `conversation_storage`,
  with the notice version), read from a new tracked notice `docs/legal/conversation-notice-v1.md`. It
  is asked at the alta's close step and can be granted or revoked later with `iroko-admin` under the
  owner's PIN (Pipec's own alta is already closed). The acta is not changed.
- **D-11** No readiness capability yet (the diary is not read by voice until CM-5b). Writing an episode
  is a derived row, not a fact, so it asks no policy and writes no authorization audit row; every
  `iroko-admin` operation on conversations is written to `admin_audit`.
- **D-12** `memory/embeddings.py` and the `embeddings_cache` table stay: CM-5b (the next plan) indexes
  the episodes with them.

**Goal.** Iroko keeps the text of every voice conversation as a local record and, once a conversation
ends, writes a short diary entry (an episode) from the owner's verified part only. Strangers' words
are archived and never summarized. The owner can list, export, delete and revoke with `iroko-admin`
under the PIN. The unreachable legacy memory path is removed.

**Architecture.** A background task per voice turn (`memory/conversation_capture.py`) decides the
turn's voice verdict and appends the exchange to the open segment (`memory/conversation_record.py`,
the only SQL on the record). A background loop (`memory/conversation_jobs.py`) closes idle segments
and, when nobody is talking, asks the local model for one summary of the owner's part
(`memory/conversation_summary.py`) and stores it (`memory/conversation_episodes.py`). The retention
loop purges by age and size. The voice routes hand a `TurnRecorder` callback to the text service and
the stream pipeline, exactly as they already hand the `ProposalScheduler`. No route, prompt or voice
answer reads the record.

**Tech stack.** Python 3.12, FastAPI, aiosqlite, SQLite JSON1, Ollama through `llm_transport`, pytest.
No new dependency, no wire change, no robot change, one migration (013).

**Spec.** ADR 0027 (all decisions, as amended by D-1 to D-3), ADR 0025 decision 5 (local, consent,
retention, deletable, encrypted), ADR 0024 decision 3 (no audio or frames stored), ADR 0021 decision 10
(the background proposal pattern), ADR 0020 (the session idle time), ADR 0016 (the voice check).

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings, the
  notice and the summary prompt; **no voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py`).
- No `Any`, no `print` (except the existing `noqa: T201` lines of the CLIs), no `os.path`, no bare
  `except`; logging with `%`; settings only through `settings`; every public API typed and
  documented. Audio-handling functions document the contract: WAV, 16 000 Hz, mono, int16; the clip
  is held in memory only and never stored.
- **No record text, summary, transcript or exception message in any log line**: ids, counts, closed
  reasons and exception classes only.
- Timestamps are UTC ISO 8601 strings with microseconds (`dt.isoformat(timespec="microseconds")`), as
  `iroko-admin` already writes them, so text comparison orders them.
- With both new switches off every prompt, response, wire field and log line of a voice turn is
  **byte-identical** to `main`, and nothing is written to the new tables.
- No real household data anywhere: invented canaries only (`Canary`, `mate`, `Zeta`).
- The record is never read by `characters/`, `llm*.py`, `streaming*.py`, `text_turn.py`,
  `cognition/` or `routers/` (Task 6 guard).

## Review focus

Failure modes the ADR implies and no task title names; each has its test in the task that owns it.

1. A stranger's words, an owner turn without a verified voice, or a deterministic turn
   (`not_checked`) reaching the summarizer: a property test over the summarizer's input (Task 10).
2. The server stopped in the middle of a conversation and restarted the next day: the old open
   segment must be closed at start-up, never continued (Task 4 and Task 10).
3. Two captures finishing at almost the same time (a fast reply after a slow voice check): both
   exchanges are kept, nothing is overwritten (Task 4).
4. A record deleted (purge, `delete`, consent revoked) while the diary job is summarizing it: no
   orphan episode, no crash, the loop goes on (Task 10).
5. A huge transcript or reply, text with quotes, newlines or emoji, or text that reads as an
   instruction («ignora lo anterior»): stored intact as data, cut to the caps, never breaks the JSON
   or the export (Tasks 3, 4 and 11).

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `memory/context.py`, `memory/semantic.py`, `memory/relations.py`, `onboarding.py` | **Deleted** | 1, 2 |
| `text_turn.py`, `characters/__init__.py`, `characters/base.py`, `characters/parser.py`, `characters/iroko.py`, `characters/nova.py`, `llm.py`, `llm_streaming.py`, `streaming.py`, `schemas.py`, `memory/declarative.py` | Legacy surface removed | 1, 2 |
| `scripts/memory_test.py`, `scripts/eval_chat.py`, `scripts/eval_stream_protocol.py`, `scripts/stream_diagnosis_variants.py` | Legacy variants removed | 1, 2 |
| `memory/migration_013_conversation_record.sql` (new), `db.py` | Three tables, the audit rebuild, the legacy drop | 3 |
| `memory/conversation_types.py` (new) | Pure: `TurnVerdict`, `RecordedTurn`, `owner_part` | 4 |
| `memory/conversation_record.py` (new) | The only SQL on `conversation_records` | 4, 9 |
| `memory/conversation_consent.py` (new), `docs/legal/conversation-notice-v1.md` (new), `commission_cli.py`, `commission_session.py` | The consent and the alta step | 5 |
| `memory/conversation_capture.py` (new), `settings.py`, `.env.example` | The verdict and the background append | 6 |
| `text_turn.py`, `streaming.py`, `routers/transcribe.py` | `TurnRecorder` wiring | 7 |
| `memory/retention.py` | Purge by age and size | 9 |
| `memory/conversation_summary.py`, `memory/conversation_episodes.py`, `memory/conversation_jobs.py` (new), `main.py` | The diary | 10 |
| `conversation_admin.py` (new), `admin_cli.py`, `memory/admin_audit.py` | `iroko-admin conversations` | 11 |
| `tests/unit/test_architecture_guards.py`, `tests/conftest.py` | Guards, switch pins | 3 to 11 |

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** `git checkout main && git pull`, then create `feat/0076-cm4-conversation-record`.
- [ ] **Step 2:** Verify, and **stop and report** if any is false:
  - `db._MIGRATIONS` ends at `(12, "migration_012_admin_audit.sql")`; migration 012 is atomic
    (`BEGIN; … PRAGMA user_version = 12; COMMIT;`) and its CHECKs are `operation IN ('add', 'change',
    'revoke')` and `target_kind IN ('pool_literal', 'pool_relation', 'care_contact')`.
  - `select_person` has no caller (`test_nothing_in_the_server_selects_a_person_by_manual_session`),
    so `text_turn._manual_evidence` is never true at run time and `build_context` is unreachable.
  - `onboarding.next_missing_slot` has no production caller and `text_turn._memory_prompt_state`
    always returns `onboarding=False, slot=None`.
  - `memory/embeddings.embed` is called only by `memory/semantic.py`, and `relations.py` only by
    `context.py` and `onboarding.py`.
  - In `routers/transcribe.py` the classic route calls `controller.handle(event)` only when
    `decide` returned `None`, and `handle` then answers through `legacy_turn`; a plan returned by
    `decide` is deterministic.
  - `streaming_render.emit_fallback` appends the fallback phrase to `state.response_parts` (through
    `synthesize_sentence`).
  - `cognition/strong_actor.verify_face_and_voice(actor, *, wav_bytes, event)` and
    `memory/owner_credentials.get_ready_owner()` exist with those signatures;
    `memory/candidate_limits.limiter` has `try_acquire()` and `release()`.
  - `main.lifespan` opens the database and starts `retention` only with `MEMORY_ENABLED`.
- [ ] **Step 3: Count the legacy table on Pipec's database.** Ask Pipec to stop the server, then
  count rows of `memories` and `vec_memories` in `settings.brain_db_path` through a read-only
  `immutable=1` URI (counts only, never a value; see the operator manual). **If either count is above
  zero, stop and report**: migration 013 drops both tables. Write the two counts in the PR.
- [ ] **Step 4:** Run the baseline and write the count in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`.

---

### Task 1: Retire the legacy runtime path

**Files:** Delete `server/src/server/memory/context.py`, `memory/semantic.py`, `memory/relations.py`
and their tests (find them with `grep -rln "build_context\|search_memories\|store_memory\|entities_for_relations\|find_facts_by_predicate\|load_entity_by_id" tests`).
Modify `text_turn.py`, `memory/declarative.py` (remove `load_entity_with_facts`), `scripts/memory_test.py`
(remove the `memories` section of `--show-db`), `memory/embeddings.py` (its comment names
`vec_memories`: say the index of CM-5b fixes the dimension), `tests/unit/test_architecture_guards.py`;
create `tests/unit/test_prompt_golden.py` and `tests/fixtures/prompt_golden.json`.

- [ ] **Step 1: Pin the prompts before touching anything.** Write `test_prompt_golden.py`: for a fixed
  matrix it builds `characters.build_system_prompt` and the two base-prompt helpers of `llm.py` and
  `llm_streaming.py` and compares them with `prompt_golden.json`. Matrix: both characters (`iroko`,
  `nova`) × `profile_card` (`None`, a canary card) × `profile_card_position` (both) × `user_emotion`
  (`None`, `"sadness"`) × `perception` (`None`, `"una taza"`) × `active_person` (`None`, a
  face-identified canary at `basic`); `context=None`, `onboarding=False` (today's only reachable
  values). `current_date_es` is monkeypatched to a constant. Generate the JSON **on the unchanged
  code** with a throwaway helper in the scratchpad (never committed); the test passes on `main`.
- [ ] **Step 2: Guards first (RED).** In `test_architecture_guards.py`: remove `text_turn.py` from
  `_MANUAL_HOMES`; add `test_the_legacy_memory_path_has_no_reference_left` modelled on
  `test_the_retired_consolidation_writer_has_no_reference_left`, with the names `build_context`,
  `search_memories`, `store_memory`, `entities_for_relations`, `find_facts_by_predicate`,
  `load_entity_by_id`, `load_entity_with_facts`, `_memory_prompt_state`, `_manual_evidence`. Run →
  FAIL (the names exist).
- [ ] **Step 3:** Delete the three modules and their tests; in `text_turn.py` remove
  `_manual_evidence`, `_memory_prompt_state` and the `build_context` import, so `prepare_text_turn`
  always sets `context=None, onboarding=False, onboarding_slot=None` (the fields themselves go in
  Task 2). Update every test that patched `build_context` (`grep -rn build_context tests`).
- [ ] **Step 4:** `test_prompt_golden.py`, the guards, `tests/unit/test_text_turn.py`, and the whole
  unit and integration suites → PASS; `uv run mypy server/src robot/src` clean.
- [ ] **Step 5:** commit `refactor: retire the legacy memory runtime path (plan 0076)`.

---

### Task 2: Retire the legacy prompt surface

**Files:** Delete `server/src/server/onboarding.py` and its tests (`test_onboarding_checklist.py`,
`test_transcribe_onboarding.py` and any other found by `grep -rln "onboarding" tests`). Modify
`schemas.py` (remove `MemoryContext`, `MemoryHit`, and `EntityWithFacts` if nothing else references it),
`characters/__init__.py` (remove the `context`, `onboarding`, `onboarding_slot` parameters,
`_format_memory_block`, `_ONBOARDING_GOAL_TEMPLATE`), `characters/base.py` (remove `onboarding_prompt`),
`characters/parser.py` (no split: a body that still contains `# ONBOARDING PROMPT` raises `ValueError`),
`characters/iroko.py`, `characters/nova.py`, `characters/profiles/ejemplo_vendedor.md` (drop the
onboarding text), `llm.py`, `llm_streaming.py`, `streaming.py`, `text_turn.py` (remove
`PreparedTextTurn.context`, `.onboarding`, `.onboarding_slot`), the three scripts, and every test that
passes those arguments.

**Interfaces — produces:** `build_system_prompt(profile, *, user_emotion=None, active_person=None,
perception=None, profile_card=None, profile_card_position="with_memory") -> str` (keyword-only after
`profile`); `generate_response` and `generate_response_stream` lose `context`, `onboarding` and
`onboarding_slot`; `PreparedTextTurn` keeps its other fields in their order.

- [ ] **Step 1: Write the failing tests:** add to the legacy guard the names `MemoryContext`,
  `MemoryHit`, `OnboardingSlot`, `onboarding_prompt`, `next_missing_slot`, `_format_memory_block`;
  `tests/unit/test_character_parser.py` (or the existing parser test module):
  `test_a_body_with_an_onboarding_header_is_rejected`. Update `test_prompt_golden.py` to call the new
  signature with the same matrix (its expected JSON does **not** change). Run → FAIL.
- [ ] **Step 2:** Remove the surface. In `scripts/eval_chat.py` drop the cases and fields built on
  `MemoryContext`; in `scripts/eval_stream_protocol.py` drop `context`; in
  `scripts/stream_diagnosis_variants.py` drop the `NO_CONTEXT` and `PUBLIC_WITH_CONTEXT` variants and
  their test cases in `tests/unit/test_stream_diagnosis_variants.py`.
- [ ] **Step 3:** `test_prompt_golden.py` → PASS **with the unchanged JSON** (the proof that every
  reachable prompt is byte-identical); the whole unit and integration suites → PASS; `mypy`, `pyright`,
  `ruff check .` and `ruff check scripts/*.py` clean.
- [ ] **Step 4:** commit `refactor: retire the legacy prompt surface (plan 0076)`.

---

### Task 3: Migration 013

**Files:** Create `server/src/server/memory/migration_013_conversation_record.sql`,
`tests/integration/test_conversation_schema.py`; modify `db.py` (`(13, "migration_013_conversation_record.sql")`).

The script, atomic like 012 (`BEGIN; … PRAGMA user_version = 13; COMMIT;`), with a header comment that
names ADR 0027 and says it holds text, never audio:

```sql
CREATE TABLE conversation_consent_grants (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    person_entity_id  INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    purpose           TEXT NOT NULL CHECK (purpose = 'conversation_storage'),
    notice_version    TEXT NOT NULL CHECK (length(notice_version) BETWEEN 1 AND 20),
    granted_at        TEXT NOT NULL,
    revoked_at        TEXT
);
CREATE UNIQUE INDEX conversation_consent_active_idx
    ON conversation_consent_grants (person_entity_id) WHERE revoked_at IS NULL;

CREATE TABLE conversation_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    previous_id       INTEGER REFERENCES conversation_records(id) ON DELETE SET NULL,
    owner_entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    started_at        TEXT NOT NULL,
    last_turn_at      TEXT NOT NULL,
    closed_at         TEXT,
    turns             TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(turns)),
    turn_count        INTEGER NOT NULL DEFAULT 0 CHECK (turn_count >= 0),
    byte_count        INTEGER NOT NULL DEFAULT 0 CHECK (byte_count >= 0),
    eligible          INTEGER NOT NULL DEFAULT 0 CHECK (eligible IN (0, 1)),
    expires_at        TEXT,
    episode_status    TEXT NOT NULL DEFAULT 'pending'
                      CHECK (episode_status IN ('pending', 'done', 'skipped', 'failed')),
    episode_attempts  INTEGER NOT NULL DEFAULT 0 CHECK (episode_attempts >= 0),
    CHECK ((closed_at IS NULL) = (expires_at IS NULL))
);
-- At most one open segment: one microphone, one conversation.
CREATE UNIQUE INDEX conversation_records_one_open_idx
    ON conversation_records ((closed_at IS NULL)) WHERE closed_at IS NULL;
CREATE INDEX conversation_records_expiry_idx ON conversation_records (expires_at);
CREATE INDEX conversation_records_pending_idx
    ON conversation_records (episode_status, closed_at) WHERE closed_at IS NOT NULL;

CREATE TABLE conversation_episodes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_record_id  INTEGER NOT NULL UNIQUE
                      REFERENCES conversation_records(id) ON DELETE CASCADE,
    owner_entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    visibility        TEXT NOT NULL CHECK (visibility = 'personal'),
    sensitivity       TEXT NOT NULL
                      CHECK (sensitivity IN ('normal', 'private', 'medical', 'location', 'security')),
    summary           TEXT NOT NULL CHECK (length(summary) BETWEEN 1 AND 1000),
    model             TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    expires_at        TEXT NOT NULL
);
```

Then rebuild `admin_audit` with the same columns, the same index and widened CHECKs
(`operation IN ('add', 'change', 'revoke', 'grant', 'export', 'delete')`,
`target_kind IN ('pool_literal', 'pool_relation', 'care_contact', 'conversation_consent',
'conversation_record')`): create `admin_audit_new`, copy every row with its `id`, drop the old table,
rename, recreate `admin_audit_recorded_at_idx`. Finally `DROP TABLE vec_memories; DROP TABLE memories;`.

- [ ] **Step 1: Write the failing tests** (database fixtures of `tests/integration/test_memory_v4_schema.py`):
  `test_migration_013_brings_the_schema_to_13`; `test_a_second_open_segment_is_refused`
  (`sqlite3.IntegrityError`); `test_turns_must_be_valid_json`; `test_closed_and_expiry_go_together`;
  `test_deleting_a_record_deletes_its_episode_and_unlinks_the_next_segment`;
  `test_the_admin_audit_keeps_its_rows_and_accepts_the_new_operations` (insert a 012 row, migrate, the
  row and its `id` survive; a `grant` / `conversation_consent` row is accepted, an unknown one is not);
  `test_the_legacy_memory_tables_are_gone`; `test_one_active_consent_per_person`.
- [ ] **Step 2:** run → FAIL (version 12).
- [ ] **Step 3:** write the script and the `db.py` line.
- [ ] **Step 4:** the new tests, `tests/integration/test_memory_v4_schema.py`, the admin audit tests and
  the `iroko-admin` tests (`latest_schema_version` is now 13) → PASS.
- [ ] **Step 5:** commit `feat: migration 013 for the conversation record (plan 0076)`.

---

### Task 4: The record types and the record store

**Files:** Create `memory/conversation_types.py`, `memory/conversation_record.py`,
`tests/unit/test_conversation_types.py`, `tests/integration/test_conversation_record.py`; modify
`settings.py`, `.env.example`, `tests/unit/test_architecture_guards.py`.

**Interfaces — produces:**
```python
# conversation_types.py (pure)
HEARD_MAX_CHARS: Final = 2000
SAID_MAX_CHARS: Final = 4000


class TurnVerdict(StrEnum):
    VERIFIED = "verified"  # the owner's face and the owner's voice on this clip
    NOT_VERIFIED = (
        "not_verified"  # the owner's face, the voice did not verify (or was not assessable)
    )
    NOT_OWNER = "not_owner"  # no face, an unknown face or another person
    NOT_CHECKED = "not_checked"  # a deterministic reply; no speaker was resolved


@dataclass(frozen=True)
class RecordedTurn:
    at: datetime
    heard: str = field(repr=False)
    said: str = field(repr=False)
    voice: TurnVerdict
    correlation_id: UUID

    def to_json(self) -> str: ...  # keys at, heard, said, voice, cid; ensure_ascii=False
    @classmethod
    def from_json_obj(
        cls, obj: Mapping[str, object]
    ) -> RecordedTurn: ...  # ValueError if malformed


def make_turn(
    heard: str, said: str, *, voice: TurnVerdict, correlation_id: UUID, at: datetime
) -> RecordedTurn: ...  # strips, cuts at the caps
def owner_part(
    turns: Sequence[RecordedTurn],
) -> tuple[RecordedTurn, ...]: ...  # VERIFIED only, by `at`


# conversation_record.py (the only SQL on conversation_records)
class EpisodeStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class RecordSummary:  # no text
    id: int
    previous_id: int | None
    started_at: str
    closed_at: str | None
    turn_count: int
    byte_count: int
    eligible: bool
    expires_at: str | None
    episode_status: EpisodeStatus


@dataclass(frozen=True)
class RecordView:
    summary: RecordSummary
    owner_entity_id: int
    turns: tuple[RecordedTurn, ...] = field(repr=False)  # sorted by `at`


async def append_turn(turn: RecordedTurn, *, owner_entity_id: int, now: datetime) -> int: ...
async def close_idle_records(now: datetime) -> int: ...
async def has_open_record() -> bool: ...
async def list_records(limit: int = 50) -> tuple[RecordSummary, ...]: ...  # newest first
async def read_record(record_id: int) -> RecordView | None: ...
async def next_pending_record() -> RecordView | None: ...  # oldest closed `pending`
async def set_episode_status(record_id: int, status: EpisodeStatus) -> None: ...
async def count_failed_attempt(record_id: int) -> int: ...  # returns the new count
async def delete_record(record_id: int) -> bool: ...
async def delete_all_records(
    conn: aiosqlite.Connection,
) -> int: ...  # inside the caller's transaction
```

`append_turn`, in **one** `db.transaction()`: (1) read the open segment; (2) if
`turn.at - last_turn_at >= WORKING_MEMORY_IDLE_SECONDS`, close it (a new conversation follows, with
`previous_id` `NULL`); (3) if it holds `CONVERSATION_SEGMENT_MAX_TURNS` exchanges or the new entry
would pass `CONVERSATION_SEGMENT_MAX_BYTES`, close it and open the next with `previous_id` = its id
(the same conversation continues); (4) open a segment if none (`started_at = last_turn_at = turn.at`);
(5) `UPDATE … SET turns = json_insert(turns, '$[#]', json(?)), turn_count = turn_count + 1,
byte_count = byte_count + ?, last_turn_at = max(last_turn_at, ?), eligible = eligible OR ?`. The byte
count is the UTF-8 length of the entry. **Closing** sets `closed_at = now` and `expires_at = now +
CONVERSATION_RECORD_ELIGIBLE_DAYS` or `… INELIGIBLE_DAYS` by `eligible`. `close_idle_records` closes
the open segment when `now - last_turn_at >= idle`. A turn whose `at` is earlier than `last_turn_at`
(two captures finishing out of order) is appended as it is; readers sort by `at`.

Settings (each with a comment, in `.env.example`, read where used; `tests/unit/test_settings_are_read.py`):
`conversation_segment_max_turns: PositiveInt = 60`, `conversation_segment_max_bytes: PositiveInt = 65536`,
`conversation_record_eligible_days: PositiveInt = 365`, `conversation_record_ineligible_days: PositiveInt = 30`.

- [ ] **Step 1: Write the failing tests.** Unit (`pytestmark = pytest.mark.unit`):
  `test_make_turn_cuts_heard_and_said_at_their_caps`;
  `test_a_turn_round_trips_through_json_with_quotes_newlines_and_emoji` (review focus 5; an
  «ignora lo anterior» text is data);
  `test_from_json_obj_rejects_a_missing_key_or_an_unknown_verdict`;
  `test_owner_part_keeps_only_verified_turns_in_time_order` (every other verdict is dropped);
  `test_repr_never_shows_the_text`. Integration (`tests/integration`, an open database, a canary owner
  entity, an injected `now`): `test_the_first_turn_opens_a_segment`;
  `test_a_turn_after_the_idle_time_starts_a_new_conversation` (`previous_id` is `NULL`);
  `test_a_full_segment_continues_in_a_linked_one` (60 turns, then the 61st → `previous_id` set; same
  for bytes); `test_eligible_is_set_by_one_verified_turn_and_never_unset`;
  `test_closing_sets_the_expiry_by_eligibility` (365 and 30 days);
  `test_close_idle_records_closes_a_stale_open_segment` (review focus 2: last turn three days ago);
  `test_two_concurrent_appends_keep_both_turns` (`asyncio.gather` of two `append_turn`; review focus 3);
  `test_read_record_sorts_turns_by_time`; `test_next_pending_record_ignores_open_and_done_records`;
  `test_delete_record_cascades_to_the_episode` (insert an episode row through the fixture's raw
  connection). Guard (RED first): `test_the_conversation_record_is_queried_only_by_its_store`
  (`conversation_records` SQL only in `memory/conversation_record.py`), with its «detects a violation»
  companion, modelled on the candidate-table guard.
- [ ] **Step 2:** run → FAIL (modules missing).
- [ ] **Step 3:** implement; the turns JSON is parsed with `json.loads` and `RecordedTurn.from_json_obj`;
  a malformed entry raises `BrainMemoryError` with a closed message.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat: conversation record types and store (plan 0076)`.

---

### Task 5: The consent, the notice and the alta step

**Files:** Create `memory/conversation_consent.py`, `docs/legal/conversation-notice-v1.md`,
`tests/integration/test_conversation_consent.py`; modify `commission_session.py`, `commission_cli.py`,
their tests (`tests/integration/test_commission_cli.py`, `tests/unit/test_commission_session.py` or the
module that tests `read_consents`), `tests/unit/test_architecture_guards.py`.

**Interfaces — produces:**
```python
CONVERSATION_NOTICE_VERSION: Final = "v1"
CONVERSATION_NOTICE_PATH: Final[
    Path
]  # docs/legal/conversation-notice-v1.md, like BIOMETRIC_NOTICE_PATH


async def grant_conversation_consent(
    person_entity_id: int, *, notice_version: str, now: datetime
) -> int: ...
async def revoke_conversation_consent(person_entity_id: int, *, now: datetime) -> int: ...
async def has_active_conversation_consent(person_entity_id: int) -> bool: ...
def load_conversation_notice() -> str: ...  # CommissionError-like ValueError when missing
```
`grant` is idempotent (an active grant returns its id). `revoke` runs in **one** transaction: set
`revoked_at`, then `conversation_record.delete_all_records(conn)` (episodes go by cascade); after the
commit it calls `db.checkpoint_wal()` (`secure_delete` is on, so the text is overwritten in the file and
the log); it returns the number of records deleted (D-3).

The notice (Spanish, tuteo, exact text):

```markdown
# Aviso de registro de conversaciones — versión v1

> Texto que se lee a la persona titular antes de activar el registro de conversaciones (ADR 0027,
> decisión 7). La revisión legal (Ley 21.719) debe hacerse antes de usar este aviso con otra persona
> distinta del dueño-constructor. La versión (`v1`) queda registrada con el consentimiento.

Iroko puede guardar **el texto** de las conversaciones que escucha, para recordar más adelante lo que
tú le cuentas. Esto es lo que necesitas saber antes de aceptar:

- **Qué se guarda.** El texto de lo que el micrófono escucha y entiende mientras el robot conversa, y
  lo que el robot responde. **Incluye lo que digan otras personas que hablen cerca del robot**:
  avísales.
- **Qué no se guarda.** Ni audio ni imágenes. Solo texto.
- **Qué usa la memoria.** Solo lo que dices tú, cuando el robot reconoce tu cara y tu voz en ese
  momento. Lo que dicen otras personas queda archivado, pero nunca se resume ni se usa para recordar.
- **No hay filtro.** Lo que se dice en voz alta se guarda tal como se dijo, aunque sea un dato
  delicado.
- **Dónde.** Todo queda en este equipo, en la base de datos que protege el cifrado del disco. Nada
  sale a internet. Si autorizaste un respaldo cifrado, el respaldo también puede llevar este registro.
- **Cuánto tiempo.** Por defecto, las conversaciones en que el robot reconoció tu voz se guardan un
  año y las demás 30 días; después se borran solas.
- **Quién lo lee.** El robot nunca lo lee en voz alta. Solo se puede exportar desde la administración
  local, con tu PIN.
- **Puedes revocarlo cuando quieras.** Al revocarlo, el robot deja de guardar y se borran todas las
  conversaciones guardadas y sus resúmenes.

Al continuar, confirmas que lo leíste y que aceptas que Iroko guarde el texto de las conversaciones con
estas condiciones.
```

The alta: in `commission_cli._run_close`, after `read_consents`, a new `commission_session.read_conversation_consent(*, read_text, write_text) -> bool`
prints the notice and asks `¿Autorizas que Iroko guarde el texto de las conversaciones? (si/no): `; a
`si` calls `grant_conversation_consent(owner, notice_version="v1", now=…)` for the ready owner.
`_HARDWARE_ANSWERS` and the scripted answers of `tests/integration/test_commission_cli.py` gain one
answer.

- [ ] **Step 1: Write the failing tests:** `test_grant_is_idempotent_and_records_the_notice_version`;
  `test_revoke_deletes_every_record_and_episode_and_reports_the_count` (D-3);
  `test_revoke_without_a_grant_deletes_nothing_and_succeeds`;
  `test_has_active_consent_is_false_after_revoke`; `test_the_notice_file_exists_and_names_its_version`;
  `test_the_alta_close_grants_on_si_and_not_on_no` (the CLI test with scripted answers);
  guard `test_the_conversation_consent_is_queried_only_by_its_module` (+ violation companion).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement; `uv run python scripts/check_reserved_terms.py` stays clean.
- [ ] **Step 4:** run → PASS, plus the whole commissioning suite.
- [ ] **Step 5:** commit `feat: conversation storage consent and notice (plan 0076)`.

---

### Task 6: The capture, the verdict and the record switch

**Files:** Create `memory/conversation_capture.py`, `tests/unit/test_conversation_capture.py`; modify
`settings.py`, `.env.example`, `tests/conftest.py`.

**Interfaces — produces:**
```python
# settings.py
conversation_record_enabled: bool = (
    False  # kill-switch; needs memory_enabled; on in a delivered robot
)


# conversation_capture.py
class CaptureOutcome(StrEnum):
    RECORDED = "recorded"
    DISABLED = "disabled"
    NO_OWNER = "no_owner"
    NO_CONSENT = "no_consent"
    FAILED = "failed"


type OwnerReader = Callable[[], Awaitable[int | None]]
type ConsentReader = Callable[[int], Awaitable[bool]]
type Clock = Callable[[], datetime]


async def turn_verdict(
    actor: ActivePersonContext | None,
    *,
    owner_id: int,
    wav_bytes: bytes | None,
    event: CognitiveEvent[TextTurnPayload],
    verify: VoiceVerifier = verify_face_and_voice,
) -> TurnVerdict: ...


async def capture_turn(
    heard: str,
    said: str,
    actor: ActivePersonContext | None,
    *,
    wav_bytes: bytes | None,
    event: CognitiveEvent[TextTurnPayload],
    at: datetime,
    verify: VoiceVerifier = verify_face_and_voice,
    owner: OwnerReader = get_ready_owner,
    consented: ConsentReader = has_active_conversation_consent,
    clock: Clock = utc_now,
) -> CaptureOutcome: ...
```
`turn_verdict`: `actor is None` → `NOT_CHECKED`; not `is_face_actor(actor)` or `actor.person_id !=
owner_id` → `NOT_OWNER` (the voice is not computed); otherwise `await verify(actor, wav_bytes=…,
event=…)` → `VERIFIED` when it returns a fused actor whose `person_id == owner_id`, else `NOT_VERIFIED`
(D-1). `capture_turn` never raises: switch off (`memory_enabled` and `conversation_record_enabled`) →
`DISABLED`; no ready owner → `NO_OWNER`; no active consent → `NO_CONSENT`; then the verdict,
`make_turn` and `append_turn(owner_entity_id=owner, now=clock())`; any `Exception` → `FAILED`, logging
only the class and the place (copy `candidate_proposal._innermost_frame`'s approach; do not import a
private name, move it to a small shared helper if both need it). One `INFO` line per capture:
`event="conversation.capture"`, the outcome, the verdict and the correlation id; never text.
`tests/conftest.py` gets an autouse fixture `_conversation_record_off` that pins the switch to `False`.

- [ ] **Step 1: Write the failing tests** (doubles for `verify`, `owner`, `consented`; `append_turn`
  patched): `test_no_actor_is_not_checked_and_the_voice_is_never_computed`;
  `test_a_stranger_or_another_person_is_not_owner_and_the_voice_is_never_computed`;
  `test_the_owner_face_with_a_verified_voice_is_verified`;
  `test_the_owner_face_with_an_unverified_voice_is_not_verified`;
  `test_a_token_actor_is_not_owner` (an actor with a `local_unlock` item);
  `test_the_switch_off_writes_nothing_and_reads_no_owner`;
  `test_no_consent_writes_nothing`; `test_no_owner_writes_nothing`;
  `test_any_failure_is_failed_and_never_raises` (a raising `append_turn`, a raising `verify`);
  `test_the_log_carries_no_text` (`caplog` with a canary in `heard` and `said`).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run → PASS; `test_settings_are_read.py` → PASS.
- [ ] **Step 5:** commit `feat: capture a voice turn into the conversation record (plan 0076)`.

---

### Task 7: The voice routes record every spoken reply

**Files:** Modify `text_turn.py`, `streaming.py`, `routers/transcribe.py`,
`tests/unit/test_architecture_guards.py`; tests: `tests/unit/test_text_turn.py`,
`tests/unit/test_streaming*.py` (find with `grep -ln stream_pipeline tests/unit`), new
`tests/integration/test_conversation_record_routes.py` (modelled on `test_profile_card_routes.py`).

**Interfaces — produces:**
```python
# text_turn.py
#: Channel-owned callback that schedules the capture of one spoken exchange (ADR 0027). It
#: receives what was heard, what was said and the turn's speaker (``None`` for a deterministic
#: reply); the route that owns the clip and the event binds them.
TurnRecorder = Callable[[str, str, ActivePersonContext | None], None]
# process_text_turn(..., record_turn: TurnRecorder | None = None)
# stream_pipeline(..., record_turn: TurnRecorder | None = None)


# routers/transcribe.py
def _turn_recorder(
    background_tasks: BackgroundTasks, *, event: CognitiveEvent[TextTurnPayload], wav_bytes: bytes
) -> TurnRecorder | None: ...  # None unless memory_enabled and conversation_record_enabled
```
`process_text_turn` calls `record_turn(message, response, prepared.active_person)` after `_generate`,
**also when the reply is the fallback phrase**, and before the offer is finished. `stream_pipeline`
calls it with `" ".join(state.response_parts)` after the reply was spoken (success or fallback), never
on `TTSError`. `_voice_controller` gains the keyword `record_turn` and forwards it in `legacy_turn`. The
classic route records the deterministic plan (`decision is not None`, including
`scene_unavailable_plan()`) with `actor=None` right before `_classic_reply`; the stream route does the
same when `plan is not None`. The unclear-speech branch and the vision frame request record nothing
(D-7). `_turn_recorder` schedules `capture_turn(heard, said, actor, wav_bytes=…, event=…, at=utc_now())`
with `background_tasks.add_task`.

- [ ] **Step 1: Write the failing tests:**
  - `test_text_turn.py`: the recorder is called once with `(message, response, active_person)`; once
    with the fallback phrase when the model fails; not at all when no recorder is passed.
  - The stream unit tests: once with the joined spoken text; with the fallback phrase on an LLM error;
    not on a TTS error.
  - `test_turn_recorder_is_none_unless_both_switches_are_on`.
  - Integration (classic and stream, STT/LLM/TTS simulated, `capture_turn` replaced by a recorder
    double): a generic turn records `(heard, reply, the speaker)`; a deterministic turn («¿Qué fecha
    es hoy?», `CURRENT_DATE`) records `(heard, plan.response, None)`; an unclear clip records nothing; `/chat` and
    `/vision/respond` record nothing even with the switch on; with the switch off the response and the
    prompt are byte-identical to the switch-on case minus the recording.
  - Guard: `_RECORDER_NAMES = {"TurnRecorder", "record_turn", "_turn_recorder", "capture_turn"}` named
    only in `text_turn.py`, `streaming.py`, `routers/transcribe.py` and `memory/conversation_capture.py`;
    and `test_no_prompt_or_route_reads_the_record`: `memory.conversation_record`,
    `memory.conversation_episodes` and `memory.conversation_summary` are imported by nothing under
    `characters/`, `cognition/`, `routers/`, `llm*.py`, `streaming*.py` or `text_turn.py` (each with its
    violation companion).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** the new tests, the guards and the whole transcribe, stream and text-turn suites → PASS.
- [ ] **Step 5:** commit `feat: voice routes record every spoken reply (plan 0076)`.

---

### Task 8: Owner → stranger matrix

**Files:** Modify `tests/integration/test_owner_stranger_matrix.py`.

- [ ] **Step 1: Write the failing tests** (real classic and stream routes, real `capture_turn`, real
  database, simulated STT/LLM/TTS and a `verify` double): `test_the_owner_with_face_and_voice_makes_an_eligible_record`;
  `test_a_stranger_only_conversation_is_archived_and_not_eligible`;
  `test_the_owner_off_camera_is_not_owner_even_with_a_matching_voice` (D-1);
  `test_a_second_face_in_frame_is_not_owner`; `test_no_record_without_the_consent`;
  `test_no_record_line_reaches_any_log_or_response` (canary in the heard text).
- [ ] **Step 2:** run → FAIL or, if green by construction, record why and add an assertion that fails
  when `_turn_recorder` returns `None`.
- [ ] **Step 3:** fix any real gap found and report it.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `test: owner and stranger matrix covers the record (plan 0076)`.

---

### Task 9: Purge by age and by size

**Files:** Modify `memory/conversation_record.py`, `memory/retention.py`, `settings.py`, `.env.example`;
tests in `tests/integration/test_conversation_record.py` and `tests/unit/test_retention*.py`.

**Interfaces — produces:**
```python
# settings.py
conversation_record_max_total_mb: PositiveInt = 200


# conversation_record.py
async def purge_records(now: datetime) -> int: ...  # records deleted
```
One transaction: delete closed records whose `expires_at < now`; then, while `SUM(byte_count)` exceeds
the cap, delete the oldest closed **not-eligible** record, and only when none is left the oldest closed
eligible one; never the open segment. After the commit, `db.checkpoint_wal()` when anything was deleted.
`retention._run_once` calls a new `_purge_conversations()` in its own `try` (like
`_reclaim_candidates`), **whatever the switches say** (old records still expire with the record off).

- [ ] **Step 1: Write the failing tests:** `test_each_class_expires_at_its_own_age`;
  `test_the_space_cap_purges_not_eligible_first_then_the_oldest`;
  `test_the_open_segment_is_never_purged`; `test_a_purge_deletes_the_episodes_with_their_records`;
  `test_the_retention_run_purges_conversations_even_with_the_switch_off`;
  `test_a_failing_conversation_purge_does_not_stop_the_other_purges`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run → PASS, plus the retention suite.
- [ ] **Step 5:** commit `feat: purge the conversation record by age and size (plan 0076)`.

---

### Task 10: The diary

**Files:** Create `memory/conversation_summary.py`, `memory/conversation_episodes.py`,
`memory/conversation_jobs.py`, their tests (`tests/unit/test_conversation_summary.py`,
`tests/integration/test_conversation_episodes.py`, `tests/unit/test_conversation_jobs.py`); modify
`main.py`, `settings.py`, `.env.example`, `tests/conftest.py`, `tests/unit/test_architecture_guards.py`.

**Interfaces — produces:**
```python
# settings.py
conversation_episodes_enabled: bool = False  # needs conversation_record_enabled
conversation_job_interval_s: PositiveInt = 120
conversation_episode_max_chars: PositiveInt = 600

# conversation_summary.py
NOTHING_TO_REMEMBER: Final = "Conversación sin datos para recordar."
type EpisodeSensitivity = Literal["normal", "private", "medical", "location", "security"]


@dataclass(frozen=True)
class EpisodeDraft:
    summary: str = field(repr=False)
    sensitivity: EpisodeSensitivity


def summary_input(turns: Sequence[RecordedTurn]) -> str: ...  # pure: owner_part(turns) only
async def summarize_owner_part(
    client: httpx.AsyncClient, turns: Sequence[RecordedTurn]
) -> EpisodeDraft: ...


# conversation_episodes.py (the only SQL on conversation_episodes)
class EpisodeOutcome(StrEnum):
    WRITTEN = "written"
    SKIPPED = "skipped"
    BUSY = "busy"
    RETRY = "retry"
    FAILED = "failed"
    GONE = "gone"


@dataclass(frozen=True)
class Episode:
    id: int
    source_record_id: int
    owner_entity_id: int
    sensitivity: EpisodeSensitivity
    summary: str = field(repr=False)
    created_at: str
    expires_at: str


async def get_episode(record_id: int) -> Episode | None: ...
async def write_episode(
    record: RecordView,
    *,
    client: httpx.AsyncClient,
    now: datetime,
    summarize: Summarizer = summarize_owner_part,
) -> EpisodeOutcome: ...


# conversation_jobs.py
async def run_once(client: httpx.AsyncClient, now: datetime) -> None: ...  # never raises
def start_background_job(client: httpx.AsyncClient) -> None: ...
async def stop_background_job() -> None: ...
```

The summary prompt (`conversation_summary._SYSTEM`, exact text):

```text
Resumes, para el diario de un robot de compañía, lo que una persona le contó en una conversación.
Recibes solo las frases de esa persona y lo que el robot respondió a cada una.
Reglas:
- Escribe en español, de una a tres frases, en tercera persona neutra: «La persona contó que…».
- Usa solo lo que dijo la persona. Lo que dijo el robot es contexto, nunca una fuente.
- No inventes, no supongas y no agregues nada que no esté en el texto.
- Si la persona no contó nada que valga la pena recordar, escribe exactamente: «Conversación sin datos para recordar.»
- Clasifica la sensibilidad del resumen: "normal", "private" (algo íntimo), "medical" (salud), "location" (dónde vive o está) o "security" (claves, códigos o accesos). Si dudas, usa la más protectora.
Responde solo con JSON: {"summary": "...", "sensitivity": "..."}
```

`summary_input` renders `owner_part(turns)` as lines `Persona: <heard>` / `Robot: <said>`.
`summarize_owner_part` calls `ollama_chat` exactly like `candidate_extraction.extract_candidates`
(`model=settings.consolidation_model or settings.ollama_model`, `format_schema` of a pydantic model,
`temperature` 0.1, `settings.ollama_timeout_s`), validates, collapses whitespace and cuts the summary at
`CONVERSATION_EPISODE_MAX_CHARS`; invalid JSON raises `LLMError` with no model output in it.
`write_episode`: a record that is not eligible → status `skipped`, no model call; `limiter.try_acquire()`
refused → `BUSY` (try next tick); `LLMError`/`httpx.HTTPError` → `count_failed_attempt`, `RETRY`, or
`FAILED` and status `failed` at the third; a draft equal to `NOTHING_TO_REMEMBER` → status `skipped`;
otherwise one transaction inserts the episode (`visibility='personal'`, the record's owner and
`expires_at`, `model` name) and sets status `done`; an `IntegrityError` because the record was deleted
meanwhile → `GONE` (review focus 4). The limiter is always released. `run_once`: `close_idle_records(now)`;
then, only with both switches on **and** `not await has_open_record()`, mark every pending not-eligible
record `skipped` and write at most **one** eligible episode. Any exception is logged by class. The loop
runs `run_once` at start (closing a segment left open by a previous process: review focus 2) and every
`CONVERSATION_JOB_INTERVAL_S`; `main.lifespan` starts it after `retention` when `MEMORY_ENABLED` and
`CONVERSATION_RECORD_ENABLED` are on, and stops it on shutdown. `tests/conftest.py` pins
`conversation_episodes_enabled` to `False`.

- [ ] **Step 1: Write the failing tests:**
  - `test_summary_input_never_carries_a_turn_that_is_not_verified` — a property test written as a
    parametrized grid over every mix of the four verdicts in up to four turns (the project does not
    depend on Hypothesis; do not add it), with a distinct canary in each non-verified turn: none appears
    in the input (review focus 1).
  - `test_summarize_validates_and_cuts_the_summary`, `test_invalid_json_is_an_llm_error_without_output`.
  - Integration: `test_an_eligible_record_gets_one_personal_episode_with_its_expiry`;
    `test_a_not_eligible_record_is_skipped_without_a_model_call`;
    `test_nothing_to_remember_is_skipped`; `test_a_busy_limiter_leaves_it_pending`;
    `test_three_failures_mark_it_failed`; `test_a_record_deleted_meanwhile_is_gone_and_no_episode_exists`;
    `test_the_limiter_is_released_on_every_path`.
  - Jobs: `test_run_once_closes_idle_segments_even_with_the_diary_off`;
    `test_no_episode_is_written_while_a_conversation_is_open`;
    `test_at_most_one_episode_per_tick`; `test_run_once_never_raises`;
    `test_the_lifespan_starts_the_job_only_with_the_record_switch_on`.
  - Guard: `conversation_episodes` SQL only in `memory/conversation_episodes.py` (+ violation companion).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run → PASS, plus `test_settings_are_read.py` and the lifespan tests.
- [ ] **Step 5:** commit `feat: the diary job writes one episode per conversation (plan 0076)`.

---

### Task 11: `iroko-admin conversations`

**Files:** Create `server/src/server/conversation_admin.py`, `tests/integration/test_conversation_admin.py`;
modify `admin_cli.py`, `memory/admin_audit.py`, `docs/runbooks/operator-manual.md` (later in Task 13).

**Interfaces — produces:**
```python
# memory/admin_audit.py: AdminOperationKind gains GRANT="grant", EXPORT="export", DELETE="delete";
#   TargetKind gains CONVERSATION_CONSENT="conversation_consent", CONVERSATION_RECORD="conversation_record"

# conversation_admin.py — the operations; it never imports admin_cli (no cycle)
def render_record(view: RecordView, episode: Episode | None) -> str: ...  # pure
def summary_line(summary: RecordSummary) -> str: ...  # pure, no text
async def export_records(out_dir: Path, *, record_id: int | None) -> int: ...  # files written
```
`iroko-admin conversations ACTION [--id N] [--out DIR] [--dry-run]` with `ACTION` in `list`, `export`,
`delete`, `consent-grant`, `consent-revoke` (`AdminRequest` gains `action: str | None = None` and
`out: Path | None = None`; `_dispatch` gains `case "conversations"`). The CLI flow stays in
`admin_cli.py`, which already owns the PIN prompt (`_grant_pin_if_needed`), the `SI` confirmation and
the audit; `conversation_admin.py` holds what is done. `list` needs no PIN and prints one
`summary_line` per record: id, start, end, exchanges, bytes, `elegible sí/no`, episode status (never
text). Every other action asks for the owner's PIN with `_grant_pin_if_needed(required=True, …)` and
the typed confirmation `SI`, honours `--dry-run`, and writes one `admin_audit` row
(`grant`/`revoke` on `conversation_consent`, `export`/`delete` on `conversation_record`, outcome
`applied` or `refused`). `consent-grant` prints the notice first. `consent-revoke` prints how many
records it deleted. `export --out DIR` (DIR must exist or be creatable; one record with `--id`, all
otherwise) writes one UTF-8 file per record, `conversacion-<id>.md`, and reminds to delete the files
after reading. `render_record`, exact layout:

```text
# Conversación <id>

- Inicio: <started_at> UTC · Fin: <closed_at or «abierta»> UTC
- Segmento anterior: <previous_id or «—»> · Elegible: <sí|no> · Caduca: <expires_at or «—»>
- Resumen (<sensitivity>): <summary or «sin resumen»>

[<HH:MM:SS>] Persona (<tu voz verificada|tu cara, voz no verificada|otra persona o sin cara|sin revisar>): <heard>
[<HH:MM:SS>] Iroko: <said>
```

- [ ] **Step 1: Write the failing tests** (scripted `read_text`/`read_secret`, a real database, a canary
  PIN set with the existing owner-credential helper): `test_list_needs_no_pin_and_prints_no_text`;
  `test_export_needs_the_pin_and_writes_one_file_per_record`;
  `test_render_record_exact` (the layout above for a canary record with all four verdicts, quotes,
  newlines and emoji; review focus 5);
  `test_delete_needs_the_pin_and_removes_the_record_and_its_episode`;
  `test_consent_grant_prints_the_notice_and_grants`; `test_consent_revoke_deletes_everything`;
  `test_a_wrong_pin_refuses_and_is_audited_as_refused`; `test_dry_run_changes_nothing`;
  `test_every_mutating_action_writes_one_audit_row_without_text`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement; if `admin_cli.py` passes about 600 lines, move the conversation flow into
  a private `_conversations` section of the same file rather than a new module that would import its
  private helpers.
- [ ] **Step 4:** run → PASS, plus the existing `iroko-admin` suite.
- [ ] **Step 5:** commit `feat: iroko-admin conversations (plan 0076)`.

---

### Task 12: Whole-project checks

**Files:** none beyond fixes.

- [ ] **Step 1:** `uv run ruff format --check .`, `uv run ruff check .`, `uv run ruff check scripts/*.py`,
  `uv run mypy server/src robot/src`, `uv run pyright`, `uv run python scripts/check_reserved_terms.py`.
- [ ] **Step 2:** `MEMORY_ENABLED=false just gate`; write the passed count against Task 0's baseline.
- [ ] **Step 3:** fix anything found in the task that owns it (amend nothing: a new `fix:` commit).

---

### Task 13: Truth, acceptance and close

**Files:** `.env.example` (every new setting, commented), `docs/runbooks/operator-manual.md` (the
switches, the consent and how to grant it on an already-commissioned robot, `iroko-admin
conversations`, the export reminder, the retention, the closed log reasons, the counts-only legacy
check), `docs/architecture/current-state.md` (a row) and its Archify diagram (edit the JSON source, then
validate and deliver with the Archify skill), `docs/architecture/seed-data-pool.md` (the new consent),
`docs/architecture/memory-and-world-state.md` (the record and the episode), the roadmap and
`docs/roadmap/conversational-memory-delivery-map.md` (CM-4 closed), the plan indexes, the ADR index,
ADR 0027 `Accepted` with *Implementation notes* (D-1, D-2, D-3, D-6, D-7), ADR 0025 decision 5 (answered)
and ADR 0026 decision 8 (the legacy path is gone), and a new
`docs/evals/0076-conversation-record-acceptance.md`.

- [ ] **Step 1:** the documents above; every relative link resolves.
- [ ] **Step 2: Acceptance by Pipec on real hardware** (counts and yes/no only, never a text or a
  summary): with the consent granted by `iroko-admin conversations consent-grant` and both switches on:
  (1) a conversation of about five minutes facing the camera → `list` shows one eligible record and the
  export shows the exchanges with their verdicts; (2) a conversation off camera or with another person
  speaking → not eligible, no episode; (3) after 180 s of silence and one job tick, the first record
  has an episode and Pipec judges it faithful (no invented fact: yes/no); (4) the median voice-turn
  latency over 10 turns with the record on and off (the capture runs after the reply, so it should not
  change); (5) the verified share of real turns over the session (compare with the 35.5 % of Plan 0075,
  which did not need the face); (6) the bytes per exchange and per conversation, to revisit D-8's caps;
  (7) `consent-revoke` → `list` is empty; (8) `CONVERSATION_RECORD_ENABLED=false` → nothing new is
  recorded. Record them in `docs/evals/0076-conversation-record-acceptance.md`; delete the exported
  files afterwards.
- [ ] **Step 3:** commit `docs: close plan 0076` (move this plan to `completed/` with its execution
  record; update the local `docs/roadmap/tabla-tareas.md`, never committed); PR; merge only with
  Pipec's go-ahead.

---

## Non-goals

No index, embeddings or search over episodes, no recall cue, no «no me acuerdo» (CM-5b). No deletion or
correction by voice (CM-6). No candidates from the record (D-2). No recording of `/chat`,
`/vision/respond`, unclear speech or the memory offer (D-7). No speaker separation or several enrolled
speakers (P3). No change to how a clip ends (the turn-taking plan). No redaction filter, no backup
exclusion setting (the backup plan), no embedding model swap (the roadmap follow-up). No readiness
capability, no acta change (D-10, D-11). No wire, robot or dependency change.

## Self-review (2026-10-29)

Spec coverage against ADR 0027: decision 1 (two layers) Tasks 4 and 10; 2 (everything recorded, only the
owner's part feeds memory) Tasks 6, 7, 8 and 10 (the property test); 3 (per turn, face never alone, D-1)
Task 6; 4 (silence, segments, linked) Task 4; 5 (format, caps, space limit, export under PIN, no voice
read) Tasks 3, 4, 9, 11 and the guard of Task 7; 6 (two clocks) Tasks 4 and 9; 7 (consent, notice,
switch) Tasks 5 and 6; 8 (episode, candidates per D-2, source id) Task 10; 9 (delete cascade, legacy
retired) Tasks 1 to 3, 9 and 11; 10 (nothing filtered, backup) the notice of Task 5 and the non-goals;
11 (embeddings) D-12; the test consequences map to Tasks 3 to 11. Types: `RecordedTurn`, `TurnVerdict`
and `owner_part` (Task 4) are what Tasks 6, 10 and 11 use; `RecordView` (Task 4) is what
`write_episode` and `render_record` take; `TurnRecorder` (Task 7) is what `_turn_recorder` builds;
`EpisodeStatus` lives in the record store and `EpisodeOutcome` in the episode store. Proportion: fourteen
tasks, signatures, schema and test names; the only bodies are the SQL, the notice, the prompt and the
export layout, which the spec fixes as exact copy.
