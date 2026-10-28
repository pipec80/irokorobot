# 0074 — CM-5a: the profile card and the explicit «what do you know about me»

> **Status:** `Ready` — `NOW`; **executed 2026-10-28 (Tasks 0 to 8, see the execution record at the end):
> Pipec's hardware acceptance (Task 8, Step 4) and the close (Step 5) are pending.** Detailed on
> 2026-10-28 and **promoted by Pipec the same day** (D-1 to D-8
> below confirmed). [ADR 0026](../../adr/0026-owner-profile-card-and-the-read-side-of-memory.md)
> (`Proposed`, merged in PR #220 and #221) is its design; this plan moves it to `Accepted` when it
> closes. Detailed against `main` at `dbb384f` by three read-only audits of the prompt path, the
> controller and the V4 repository and approved with changes by an independent architecture review
> (2026-10-28); queue rule 4 applies at execution: Task 0 re-verifies every claim below against the
> merged code before any code, and **stops and reports** if one is false. Written for an executor who
> has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main` (`feat/0074-cm5a-profile-card`),
> never a git worktree, subagents only if Pipec asks, this plan lives under `docs/plans/`. One commit
> per task; every test seen RED for the stated reason first. If evidence contradicts the plan, stop
> and report instead of redesigning. The Bash tool of this environment loses backslashes and
> non-ASCII characters in heredocs: use the Write and Edit tools. Commit messages: Conventional
> Commits, title at most 72 characters, check `git log` after each commit (the hook rejects silently);
> do not pipe `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false`
> as CI does, and have each test that needs memory set `settings.memory_enabled` itself. Never run
> `uv sync --all-packages --all-groups` (it removes the optional `cuda` extra). **Do not run
> `just gate` in the background while Pipec rehearses** (about 3.5 GB of RAM). **The server and the
> robot are started by Pipec**, never by the agent.

## Decisions confirmed by Pipec on promotion (2026-10-28)

Items marked *(author's call)* were proposed by the author and are confirmed by the promotion.

- **D-1** The card is a closed list: `preferred_name`, `address_form`, `likes`, `dislikes`, `prefers`;
  600 characters, 12 tastes, newest first, grouped by predicate (ADR 0026 decision 2).
- **D-2** The card is read on classic and streaming voice turns only; `/chat` and `/vision/respond` read
  no card (ADR 0026 decision 3, amended).
- **D-3** `PROFILE_CARD_POSITION` is configurable (`with_memory` default, `before_language`); the language
  rule stays the last block of the master prompt.
- **D-4** `usted` is one line of the card; fixed controller strings stay in tuteo.
- **D-5** One audit row per read.
- **D-6** The switch is off in the code and on in a delivered robot; the person who commissions turns it on
  and verifies it by asking (no automated test turn).
- **D-7** *(author's call)* The summary lists only what the card holds, with the fixed wording of Task 1;
  readiness gets its own capability row `answer_profile`.
- **D-8** *(author's call)* An identified non-owner and a stranger hear the same phrase; the spoken
  summary is kept out of the opt-in text log.

**Goal.** The robot reads back what it holds about the person it is talking to. A small **card**
(preferred name, form of address, tastes; ADR 0026 decision 2) goes into the prompt on every
identified generic voice turn, and «¿qué sabes de mí?» is answered by the controller with a fixed
template. The voice is not consulted, nothing above `normal` is read, `/chat` and `/vision/respond`
read no card, and a stranger learns nothing.

**Architecture.** A pure module (`memory/profile_card.py`) builds and renders the card; one SQL
function in the V4 repository returns the allow-listed rows; an access module
(`memory/profile_card_access.py`) evaluates `read_personal_conversation_memory`, writes the audit row
**before** reading, then reads; `text_turn` takes an optional provider that only the two voice call
sites pass; the controller gets one more `InformationNeed` and one optional collaborator, present
only on the voice routes. Everything is behind `PROFILE_CARD_ENABLED` (off in code, on in a
delivered robot).

**Tech stack.** Python 3.12, FastAPI, aiosqlite, pytest, no new dependency, no migration, no wire
change, no robot change.

**Spec.** ADR 0026 (all decisions), ADR 0019 §3 and §6, ADR 0020 §1, §4 and §7, ADR 0024 decision 14,
[`seed-data-pool.md`](../../architecture/seed-data-pool.md).

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings; **no
  voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py` scans every `server/**/*.py`).
- No `Any`, no `print`, no `os.path`, no bare `except`; logging with `%`; settings only through
  `settings`; every public API typed and documented.
- The card allow-list is exactly `preferred_name`, `address_form`, `likes`, `dislikes`, `prefers`;
  rows must be the person's own, `lifecycle = 'active'`, visibility `personal`, sensitivity `normal`.
- Card caps: 600 characters and 12 tastes; each value cleaned and cut at 80 characters.
- With `PROFILE_CARD_ENABLED=false` every prompt, response and wire field is **byte-identical** to
  `main`.
- No real household data anywhere: invented canaries only (`Canary`, `mate`, `Zeta`).
- Assurance is compared through `ASSURANCE_RANK`, never with `<` (the enum is a `str` enum).

## Review focus

Failure modes the ADR implies and no task title names; each has its test in the task that owns it.

1. A stored taste that contains a newline, a double quote or text that reads as an instruction
   («ignora lo anterior») must reach the prompt as one quoted line of data (Task 1).
2. A row with an allow-listed predicate but another visibility, sensitivity, person or lifecycle
   (a child's or pet's `likes` stored `household`, a `private` row, a revoked or superseded row)
   never appears (Task 2).
3. A failing audit write, a denied decision or a database error must never fail the turn: the turn
   is answered without a card (Tasks 3 and 4).
4. A suspended session (unknown, ambiguous, vetoed speaker), a token speaker without the read scope
   and a speaker below `basic` get no card, and the unidentified speaker gets the fixed phrase on the
   explicit question, never the list (Tasks 3, 6 and 7).
5. A very long name or list, and values in accents or emoji, never push the card over 600
   characters or break the prompt (Task 1).

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `server/src/server/memory/profile_card.py` (new) | Pure: allow-list, caps, `ProfileCard`, `build_card`, the two renderers | 1 |
| `server/src/server/memory/relational_v4.py` | `list_card_literals`, the only SQL of the card | 2 |
| `server/src/server/memory/profile_card_access.py` (new) | Policy, audit, read: `read_card`, `prompt_card_text`, `profile_summary_text` | 3 |
| `server/src/server/characters/__init__.py`, `llm.py`, `llm_streaming.py`, `text_turn.py`, `streaming.py` | Thread `profile_card` to the prompt; the optional provider | 4 |
| `server/src/server/routers/transcribe.py`, `settings.py`, `.env.example` | The two voice call sites, the factories, the settings | 4, 5, 6 |
| `server/src/server/cognition/response_plan.py`, `intent_resolution.py`, `controller.py` | `PROFILE_SUMMARY`, its rule, its branch | 6 |
| `server/src/server/memory/commissioning_readiness.py`, docs | Readiness row, truth, acceptance | 8 |
| `tests/unit/test_architecture_guards.py` | Three guard updates | 3, 5 |

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** `git checkout main && git pull`, then create `feat/0074-cm5a-profile-card`.
- [ ] **Step 2:** Verify, and **stop and report** if any is false: `PreparedTextTurn` is a frozen
  dataclass whose last fields are `active_person` and `continuity` with defaults (tests build it
  positionally with the first eight); `build_system_prompt` ends with `_LANGUAGE_RULE`;
  `relational_v4.list_active_facts` and `get_active_literal_facts` exist; `candidate_policy.authorize_step`
  requires `is_face_and_voice_actor` and `settings.memory_candidates_enabled` (so it cannot be reused);
  `_ACTION_HOMES` in `tests/unit/test_architecture_guards.py` lists only `cognition/models.py`,
  `cognition/authorization.py` and `memory/candidate_policy.py`; `CognitiveController.decide` is an
  exhaustive `match need:` with no `case _`; `/chat` and `/vision/respond` build the controller without
  `memory_answerer`; `cognition/strong_actor.is_face_actor` exists; the classic voice route returns the
  plan of `controller.decide(event)` without calling `handle()` again when `decide` is not `None`
  (this decides whether Task 6 needs a per-event cache: it does not unless a RED test proves a second
  `decide`); `_run_tts(text, logged_text=...)` exists (the offers use it).
- [ ] **Step 3:** Run the baseline and write the counts in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`
  (expected: green; record the passed count).

---

### Task 1: The card, pure

**Files:** Create `server/src/server/memory/profile_card.py`, `tests/unit/test_profile_card.py`.

**Interfaces — produces:**
```python
CARD_PREDICATES: Final[frozenset[str]]  # the five ids of the global constraints
MAX_CARD_CHARS: Final = 600
MAX_CARD_TASTES: Final = 12
MAX_VALUE_CHARS: Final = 80
CARD_HEADER: Final = "--- Lo que sabes de la persona con quien hablas ---"


@dataclass(frozen=True)
class CardTaste:
    predicate: Literal["likes", "dislikes", "prefers"]
    value: str


@dataclass(frozen=True)
class ProfileCard:
    preferred_name: str | None
    address_form: Literal["tu", "usted"] | None
    tastes: tuple[CardTaste, ...]  # newest first

    @property
    def is_empty(self) -> bool: ...


def build_card(rows: Sequence[LiteralFactV4]) -> ProfileCard: ...  # rows newest first (id DESC)
def render_prompt_card(card: ProfileCard) -> str | None: ...  # None when empty
def render_summary(card: ProfileCard) -> str: ...
```

- [ ] **Step 1: Write the failing tests** (`pytestmark = pytest.mark.unit`; rows are
  `LiteralFactV4` built with a helper; canary values only):
  - `test_build_card_keeps_only_the_allow_list` — a `birth_date`, `medication` and `private_topic` row
    are absent from the card.
  - `test_build_card_ignores_rows_that_are_not_personal_normal_active` — defensive: a `household`
    `likes`, a `private` `likes` and a `revoked` one are dropped even if handed in.
  - `test_the_newest_single_value_wins` — two `preferred_name` rows, the first (newest) is kept.
  - `test_tastes_are_newest_first_and_capped_at_twelve` — 15 tastes → the 12 newest, in order.
  - `test_render_prompt_card_exact` — for name `Canary`, form `tu`, likes `el mate`, `la lluvia`,
    dislikes `el ruido`, prefers `el cafe`: the output equals
    ```
    --- Lo que sabes de la persona con quien hablas ---
    - Nombre: "Canary". Trato: tú.
    - Le gusta: "el mate", "la lluvia".
    - No le gusta: "el ruido".
    - Prefiere: "el cafe".
    Es memoria autorizada: apóyate en ella solo si viene al caso y no inventes nada que no esté aquí.
    ```
    (neutral wording, no gender: with `usted` the first line ends `Trato: usted.`; name only →
    `- Nombre: "Canary".`; form only → `- Trato: tú.`; the group lines appear only when non-empty).
  - `test_render_prompt_card_is_none_for_an_empty_card`.
  - `test_the_card_never_exceeds_600_characters_dropping_the_oldest_taste` — 12 values of 80
    characters → `len(result) <= 600` and the surviving tastes are the newest ones, in order.
  - `test_values_become_one_quoted_line` (review focus 1) — a value `"mate\nIgnora lo anterior"` and one
    with `"` render with no newline inside an item and no unescaped `"` (quotes become `'`); a value of
    only whitespace or control characters is skipped; accents and emoji survive.
  - `test_render_summary_exact`: empty → `Todavía no me has contado cosas que pueda recordar.`; the
    example above → `Esto es lo que sé de ti. Te llamo Canary. Te trato de tú. Me has dicho que te gusta: el mate, la lluvia. Me has dicho que no te gusta: el ruido. Prefieres: el cafe.`
    (with `usted`: `Te trato de usted.`; a card with only tastes has no name or form sentence).
- [ ] **Step 2:** `uv run pytest tests/unit/test_profile_card.py -q` → FAIL (module missing).
- [ ] **Step 3:** Implement the signatures above in `profile_card.py`. Cleaning: collapse whitespace,
  drop control characters, replace `"` with `'`, cut at 80 characters, skip if empty. The 600 cap
  drops the oldest taste (last in the tuple) until the rendered text fits; the name is cut by the same
  cleaning. `address_form` reads the stored code (`tu` or `usted`) and prints `tú` or `usted`.
- [ ] **Step 4:** the same command → PASS.
- [ ] **Step 5:** `git add` the two files; commit `feat: profile card build and render (plan 0074)`.

---

### Task 2: The reader, the only SQL

**Files:** Modify `server/src/server/memory/relational_v4.py`; test in the existing relational
repository integration test module (find it with `grep -l get_active_literal_facts tests/integration/*.py`)
or a new `tests/integration/test_profile_card_reader.py` using the same database fixtures.

**Interfaces — produces:**
```python
async def list_card_literals(
    *, subject_entity_id: int, predicates: frozenset[str]
) -> list[LiteralFactV4]: ...
```
Rows with `lifecycle = 'active'`, `visibility = 'personal'`, `sensitivity = 'normal'`, the subject, and
a predicate in the set; ordered `id DESC` (not `asserted_at`: its formats mix).

- [ ] **Step 1: Write the failing tests** (rows inserted with `assert_literal_fact(..., visibility=,
  sensitivity=)`; two people):
  - `test_returns_only_the_subjects_own_active_personal_normal_rows` (review focus 2).
  - `test_a_household_private_revoked_or_superseded_row_is_never_returned` — a child's `likes` stored
    `household`, an owner `likes` stored `private`, a revoked and a superseded `preferred_name`.
  - `test_orders_newest_first_by_id`.
  - `test_an_empty_predicate_set_returns_nothing`.
- [ ] **Step 2:** run them → FAIL (`ImportError`).
- [ ] **Step 3:** Implement with a parameterised `IN (?,…)` and `_LITERAL_COLUMNS`; docstring states the
  SQL is the card's only door and that the caller must have authorized.
- [ ] **Step 4:** run → PASS; also `uv run pytest tests/unit/test_architecture_guards.py -q` stays green
  (the SQL is inside the allowed file).
- [ ] **Step 5:** commit `feat: list_card_literals, the card's only query (plan 0074)`.

---

### Task 3: Policy, audit and read

**Files:** Create `server/src/server/memory/profile_card_access.py`,
`tests/unit/test_profile_card_access.py`; modify `server/src/server/cognition/response_plan.py` (only to
add `ProfileSummaryReply`), `tests/unit/test_architecture_guards.py`.

**Interfaces — consumes:** `AuthorizationRequest`, `ConsentStatus`, `evaluate_authorization`,
`ASSURANCE_RANK` (`cognition/authorization.py`); `is_face_actor` (`cognition/strong_actor.py`);
`record_authorization_decision` (`memory/household_authorization.py`); `PolicyEvaluator` and
`AuditWriter` imported from `memory/candidate_policy.py` under `TYPE_CHECKING` (do not add a sixth copy
of the aliases); `list_card_literals`, `build_card`, the renderers.
**Produces:**
```python
class CardOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"  # not asked, not an owner, policy refused, audit refused
    UNAVAILABLE = "unavailable"  # the audit or the read failed


@dataclass(frozen=True)
class CardRead:
    outcome: CardOutcome
    card: ProfileCard | None  # set only when ALLOWED


type CardReader = Callable[..., Awaitable[list[LiteralFactV4]]]


async def read_card(
    actor: ActivePersonContext,
    *,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
    reader: CardReader = list_card_literals,
) -> CardRead: ...
async def prompt_card_text(
    actor, *, correlation_id, now
) -> str | None: ...  # ALLOWED card rendered, else None
async def profile_summary_text(
    actor, *, correlation_id, now
) -> ProfileSummaryReply: ...  # defined in cognition/response_plan.py (Task 6)
```
`read_card` never raises. Order: (1) **pre-check without policy or audit**: the actor must be
`IDENTIFIED` with a `person_id`, `ASSURANCE_RANK >= basic` **and `is_face_actor(actor)`** (the same test
`start_offer` uses), so a token speaker never reaches the policy and never writes a denial row per turn →
`DENIED`; (2) evaluate the policy for `action=READ_PERSONAL_CONVERSATION_MEMORY`,
`target_person_id=actor.person_id`, `visibility={PERSONAL}`, `sensitivity={NORMAL}`,
`consent=NOT_REQUIRED`; (3) **write the audit row (a denial is audited too)**, and if the write raises →
`UNAVAILABLE` and the reader is not called; (4) not allowed → `DENIED`; (5) read inside a `try` that
catches **`Exception`** and logs only the class (a corrupt row raises a pydantic `ValueError`, not only
`BrainMemoryError`/`aiosqlite.Error`) → `UNAVAILABLE`. It does **not** require the face-and-voice
composite and does **not** read `memory_candidates_enabled` (the callers check the switch, Tasks 5 and 6).
Logs: closed reasons (`not_asked`, `denied`, `audit_failed`, `unavailable`), never a value or a message.
Why not `PolicyGatedV4Reader`: it keeps only rows whose stored labels equal the **registry defaults**
(`household` for `likes`), and the owner's rows are stored `personal`, so it would withhold them. The
spoken offer's own READ step (`candidate_dialogue`) can write a second row with the same action and
`correlation_id` on the same turn; both rows join by `correlation_id`, which is expected.

- [ ] **Step 1: Write the failing tests** (style of `tests/unit/test_candidate_policy.py`: actors from
  `resolve_active_person` with canary ids, `audit=AsyncMock()`, `reader=AsyncMock()`):
  - `test_a_face_owner_at_basic_gets_the_card_and_one_audit_row_before_the_read` — a recorder shows
    the order `policy`, `audit`, `reader`; `audit` awaited once; `ALLOWED` with the built card.
  - `test_a_non_owner_is_denied_and_audited_and_never_read` — `DENIED`, `reader` not awaited.
  - `test_an_audit_failure_is_unavailable_and_never_reads` (review focus 3).
  - `test_any_read_failure_is_unavailable` — `BrainMemoryError`, `aiosqlite.Error` **and a bare
    `ValueError`** (a corrupt row) → `UNAVAILABLE`, the exception never propagates.
  - `test_an_unidentified_ambiguous_or_none_assurance_actor_is_not_asked` (review focus 4) — `DENIED`,
    `policy`, `audit`, `reader` all not awaited.
  - `test_a_token_speaker_is_not_asked_and_writes_no_row` — an actor with a `local_unlock` item →
    `DENIED`, `audit` not awaited (no denial row per turn).
  - `test_prompt_card_text_renders_only_when_allowed` and
    `test_profile_summary_text_maps_the_three_outcomes` (`ALLOWED` → text, `DENIED` → `denied=True`,
    `UNAVAILABLE` → `text=None`).
  - In `test_architecture_guards.py` (RED first): **add `memory/profile_card_access.py` to
    `_ACTION_HOMES`**, add `list_card_literals` to `_RAW_V4_READERS` and
    `memory/profile_card_access.py` to `_MAY_IMPORT_RAW_V4_READERS` (the existing guard then covers the
    new query; no new guard is written). `ProfileSummaryReply` comes from Task 6, so define it here
    first in `cognition/response_plan.py` (a frozen dataclass `text: str | None`, `denied: bool = False`)
    and keep Task 6 for its use.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Implement the three functions.
- [ ] **Step 4:** run these tests and `tests/unit/test_architecture_guards.py` → PASS.
- [ ] **Step 5:** commit `feat: profile card access with policy and audit (plan 0074)`.

---

### Task 4: The prompt

**Files:** Modify `characters/__init__.py`, `llm.py`, `llm_streaming.py`, `text_turn.py`,
`streaming.py`, `settings.py`, `.env.example`, `tests/conftest.py` (no change needed for the position
setting); tests: `tests/unit/test_prompt_language.py`, `test_memory_discipline.py`, `test_llm_generate.py`,
`test_llm_streaming.py`, `test_text_turn.py`, `test_settings.py`, and the integration fakes of
`generate_response_stream` (`grep -rn "generate_response_stream" tests/`).

**Interfaces — produces:**
```python
# settings.py declares the alias ONCE: type ProfileCardPosition = Literal["with_memory", "before_language"]
# characters/__init__.py imports it under TYPE_CHECKING (no second Literal)
def build_system_prompt(..., perception: str | None = None,
                        profile_card: str | None = None,
                        profile_card_position: ProfileCardPosition = "with_memory") -> str
# llm.py / llm_streaming.py: generate_response(..., profile_card: str | None = None);
#   generate_response_stream(..., profile_card: str | None = None); both read
#   settings.profile_card_position and pass it to the base-prompt helper.
# text_turn.py
type ProfileCardProvider = Callable[[ActivePersonContext], Awaitable[str | None]]
# PreparedTextTurn gains, LAST, profile_card: str | None = field(default=None, repr=False)
#   (repr=False like TextTurnResult.offer, so a stray %r never prints stored values)
# prepare_text_turn / process_text_turn gain keyword profile_card_provider: ProfileCardProvider | None = None
# settings.py: profile_card_position: ProfileCardPosition = "with_memory"
```
The position setting stays although it adds a code path: Pipec asked for it on 2026-10-28 («que sea
flexible») and the acceptance measures which one works better.
Placement: `with_memory` → the card goes right before the memory block (after the emotion adaptation);
`before_language` → after the perception, right before `_LANGUAGE_RULE`. `_LANGUAGE_RULE` stays the
last part of `build_system_prompt` in both. A `None` card changes nothing (byte-identical).
`_MEMORY_DISCIPLINE` is **not** edited (that would break the byte-identity with the switch off): the
card carries its own authorizing sentence (Task 1). *Deviation from ADR 0026 decision 7, to be amended
when the ADR is accepted.*

- [ ] **Step 1: Write the failing tests:**
  - `test_prompt_language.py`: add the id `card` (and `card_before_language`) to the parametrized
    `test_the_language_rule_is_the_last_part_of_the_master_prompt`; `test_a_none_card_is_byte_identical`;
    `test_the_card_sits_before_the_memory_block` / `…before_the_language_rule` (index comparisons).
  - `test_memory_discipline.py`: keep `test_the_speakers_identity_never_enters_the_system_prompt` green and
    add `test_the_display_name_never_becomes_the_card` (an identified `active_person` with a canary
    `display_name` and no card argument → canary absent).
  - `test_llm_generate.py` / `test_llm_streaming.py`: `generate_response(..., profile_card=X)` and the
    stream variant put `X` in the system prompt (read it from the mock's call args as the neighbouring
    tests do); `profile_card_position` is honoured.
  - `test_text_turn.py`: with `memory_enabled` True and an identified person at `basic`, the provider is
    awaited once with that person and `PreparedTextTurn.profile_card` holds its text; **not awaited**
    when the session is suspended (unknown, ambiguous), when the person is below `basic`, when
    `memory_enabled` is False, or when no provider is passed; a provider that raises leaves
    `profile_card=None` and the turn goes on (log class only); `_generate` and `_text_deltas` forward the
    card as `profile_card=`.
  - `test_settings.py`: default `with_memory`; a value outside the two is rejected (model on
    `test_server_settings_rejects_nonlocal_llm_provider`).
- [ ] **Step 2:** run them → FAIL for the stated reasons.
- [ ] **Step 3:** Implement: the new keyword in `build_system_prompt`, both base-prompt helpers, both
  public generate functions, `PreparedTextTurn` (last field, default), `prepare_text_turn` (call the
  provider only inside the branch where `person_id is not None and turn.writable`, wrapped so any
  exception is logged by class and ignored), `process_text_turn` (forward the provider), `_generate` and
  `streaming._text_deltas` (forward `prepared.profile_card`). The setting is declared with a comment, added
  to `.env.example`, and read in the two generate functions (`tests/unit/test_settings_are_read.py`).
  Update every fake of `generate_response_stream` found by the grep to accept `profile_card`.
- [ ] **Step 4:** run the files above plus the whole `tests/unit` and `tests/integration` of the stream
  and text-turn suites → PASS.
- [ ] **Step 5:** commit `feat: thread the profile card into the prompt (plan 0074)`.

---

### Task 5: The voice routes pass the provider

**Files:** Modify `routers/transcribe.py`, `settings.py`, `.env.example`, `tests/conftest.py`,
`tests/unit/test_architecture_guards.py`; tests: `tests/integration/test_profile_card_routes.py` (new,
modelled on `test_transcribe_memory.py` / `test_face_authenticated_turn.py`).

**Interfaces — produces:**
```python
# settings.py
profile_card_enabled: bool = False  # kill-switch; needs memory_enabled


# routers/transcribe.py
def _profile_card_provider(correlation_id: UUID) -> ProfileCardProvider | None: ...
```
`_profile_card_provider` returns `None` unless `settings.memory_enabled and settings.profile_card_enabled`;
otherwise a closure `async (actor) -> prompt_card_text(actor, correlation_id=..., now=utc_now())`.
`_voice_controller(...)` has no `event` (it is built after `event` at the classic call site), so it
gains a keyword `profile_card_provider: ProfileCardProvider | None = None` that its `legacy_turn`
closure forwards to `process_text_turn`; the classic call site passes
`_profile_card_provider(event.correlation_id)`; the stream route passes the same to
`prepare_text_turn`. `routers/chat.py` and `routers/vision.py` are **not touched**.

- [ ] **Step 1: Write the failing tests:**
  - `test_profile_card_provider_is_none_unless_both_switches_are_on` (three combinations; mirror the
    `_memory_answerer()` test in `test_memory_dialogue_routes.py`).
  - Integration, classic `/transcribe` with a face-identified owner whose `likes` is stored: the system
    prompt handed to the model contains the card; with `profile_card_enabled` False it equals today's
    byte for byte; an unknown speaker gets no card and no audit row.
  - Stream parity of the same.
  - `/chat` with an owner token and `/vision/respond`: no card even with the switch on.
  - `conftest.py`: an autouse fixture pins `profile_card_enabled` False (like `_memory_candidates_off`).
  - Guard: add `profile_card_provider`, `ProfileCardProvider`, `_profile_card_provider` to
    `_DIALOGUE_NAMES`; the homes are the files that already name the dialogue seams
    (`text_turn.py`, `routers/transcribe.py`, `cognition/controller.py`, `streaming.py`; **not**
    `memory/profile_card_access.py`, which never names the provider), so naming them in `chat.py` or
    `vision.py` fails; keep `test_the_dialogue_guard_detects_a_violation` green.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Implement the setting (comment, `.env.example`, read in `transcribe.py`), the factory and
  the two call-site changes.
- [ ] **Step 4:** run the new tests, `tests/unit/test_architecture_guards.py`, `test_settings_are_read.py`
  and the transcribe integration suites → PASS.
- [ ] **Step 5:** commit `feat: voice routes read the profile card behind a switch (plan 0074)`.

---

### Task 6: The explicit question

**Files:** Modify `cognition/response_plan.py`, `cognition/intent_resolution.py`,
`cognition/controller.py`, `routers/transcribe.py`; tests: `tests/unit/test_intent_resolution.py` with the
fixture `tests/fixtures/intent_resolution_es.json`, `tests/unit/test_cognitive_controller.py`,
`tests/integration/test_profile_card_routes.py`.

**Interfaces — produces:**
```python
# response_plan.py: InformationNeed.PROFILE_SUMMARY = "profile_summary"
# intent_resolution.py: rule id "profile.summary.v1"
_PROFILE_SUMMARY_PATTERNS = (
    "que sabes de mi",
    "que sabes sobre mi",
    "que te he contado",
    "que te conte",
    "que recuerdas de mi",
)


# response_plan.py (defined in Task 3)
@dataclass(frozen=True)
class ProfileSummaryReply:
    text: str | None  # None: the read failed (audit or database)
    denied: bool = False  # True: the policy or the pre-check refused


# controller.py
type ProfileSummarizer = Callable[
    [ActivePersonContext, CognitiveEvent[TextTurnPayload]], Awaitable[ProfileSummaryReply]
]
# CognitiveController.__init__ gains keyword-only profile_summarizer: ProfileSummarizer | None = None
_PROFILE_SUMMARY_UNKNOWN_RESPONSE = (
    "Todavía no puedo confirmar quién eres para contarte lo que sé de ti."
)
_PROFILE_SUMMARY_UNAVAILABLE_RESPONSE = (
    "Ahora no puedo revisar lo que sé de ti. Inténtalo de nuevo en un rato."
)


# routers/transcribe.py
def _profile_summarizer() -> (
    ProfileSummarizer | None
): ...  # None unless memory_enabled and profile_card_enabled
```
The rule fires only when the normalized message **equals or ends with** a pattern (`normalized == p or
normalized.endswith(" " + p)`), so «¿qué sabes de mi perro?» is not captured. It sits right after
`_active_identity_rule` in `_RULES`, before the date and memory-answer rules. The branch (new `case
InformationNeed.PROFILE_SUMMARY` in the exhaustive `match`): no summarizer → `None` (ordinary turn, byte
for byte); else `actor = await self._observed_person_resolver(event)` (a peek, never spends a grant); not
`IDENTIFIED`, **or the reply is `denied`** → `_unknown_plan(PROFILE_SUMMARY, _PROFILE_SUMMARY_UNKNOWN_RESPONSE)`
(one phrase for both, so an identified non-owner cannot be told apart from a stranger: no oracle, ADR 0026
decision 5); a reply with text becomes `ResponsePlan(need=PROFILE_SUMMARY, status=KNOWN,
source=DETERMINISTIC, response=text)`; a reply with `text is None` (not denied) becomes
`_unknown_plan(…, _PROFILE_SUMMARY_UNAVAILABLE_RESPONSE)`, reserved for an audit or database failure.
**No per-event cache**: with a summarizer present `decide` always returns a plan, so the classic route
does not run it twice (confirmed in Task 0; add the cache only if the RED test of Step 1 shows a second
`decide`). **The spoken-text log:** the summary carries stored values, so the TTS call for a
`PROFILE_SUMMARY` plan passes `logged_text` (a fixed marker such as `«resumen del perfil»`) exactly as the
offers do (the helper in `routers/transcribe.py` around line 396 that synthesizes the reply and the
offer calls `_run_tts(..., logged_text=plan.response)`; `_run_tts` and its docstring are in
`pipeline.py`; the executor finds the exact function name); `llm_response` on the wire does carry the text, because it goes to
the owner's own robot. `_profile_summarizer()` returns a closure calling `profile_summary_text(actor,
correlation_id=event.correlation_id, now=utc_now())`; it is passed to `_voice_controller` at both voice
call sites and used only in its `request_identity is not None` branch, exactly like `memory_answerer`.

- [ ] **Step 1: Write the failing tests:**
  - Fixture rows (`text`, `need`, `match`, `rule_id`): «¿Qué sabes de mí?», «Iroko, ¿qué te he contado?»,
    «Dime qué recuerdas de mí» → `profile_summary` / `exact` / `profile.summary.v1`; negatives:
    «¿Qué sabes de mi perro?» → `generic_conversation`; «¿Qué sabes de mi familia?» →
    `protected_household` (precedence); «¿Qué sabes de física?» → generic. The existing corpus tests
    (normalization stability, rule id never contains the utterance) stay green.
  - `tests/unit/test_cognitive_controller.py` (imitate the `ACTIVE_IDENTITY` and `MEMORY_ANSWER` tests:
    `_event`, `_actor`, `_resolver`, `today=lambda: date(2026, 8, 12)`):
    `test_profile_summary_speaks_the_summarizer_text_and_never_the_model` (observed resolver returns an
    identified owner; `legacy_turn.assert_not_awaited()`);
    `test_an_unidentified_speaker_gets_the_fixed_phrase_and_the_summarizer_is_not_awaited`;
    `test_a_denied_reply_gets_the_same_phrase_as_a_stranger` (the oracle test);
    `test_a_channel_without_the_summarizer_falls_through` (`decide(...) is None`, observer not awaited);
    `test_the_summary_never_spends_a_grant` (`active_person_resolver=AsyncMock`, `assert_not_awaited`);
    `test_a_failed_read_gets_the_unavailable_phrase` (`ProfileSummaryReply(text=None)`).
  - Integration: classic and stream `/transcribe` with the switch on: the owner hears the exact summary
    template of Task 1 and the stored values are in it, **and exactly one audit row** is written by the
    classic turn (this decides the cache question); a stranger hears the unknown phrase; with the
    switch off «¿qué sabes de mí?» is the ordinary turn; `/chat` never answers it deterministically; with
    `LOG_CONVERSATION_TEXT` on, no stored value reaches the spoken-text log for a summary.
  - Guard: add `profile_summarizer`, `ProfileSummarizer`, `_profile_summarizer` to `_DIALOGUE_NAMES`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Implement; then `grep -rn "InformationNeed\." server/src` for any other exhaustive use
  (a dict keyed by the enum, a second `match`) and cover the new member; `mypy` must stay clean.
- [ ] **Step 4:** run the new tests and `tests/unit/test_intent_resolution.py`,
  `test_cognitive_controller.py`, `test_architecture_guards.py` → PASS.
- [ ] **Step 5:** commit `feat: answer what do you know about me from the card (plan 0074)`.

---

### Task 7: The owner → stranger matrix

**Files:** Modify `tests/integration/test_owner_stranger_matrix.py`.

- [ ] **Step 1: Write the failing tests** (real classic route, STT/TTS/LLM simulated, invented canaries):
  `test_the_owner_hears_the_card_and_the_summary`, `test_a_stranger_learns_nothing_from_the_card_or_the_summary`
  (no canary value in the prompt, the response or any log record; the fixed unknown phrase on the
  question), `test_a_second_face_suspends_the_card`, `test_a_revoked_voice_or_face_consent_changes_nothing_in_the_card_path`
  (the card needs only the face at `basic`, so a revoked **voice** consent leaves it available and a revoked
  **face** consent removes it).
- [ ] **Step 2:** run → FAIL or, if already green by construction, record why and add an assertion that
  fails when the card path is removed.
- [ ] **Step 3:** make them pass without new production code; fix any real gap and report it.
- [ ] **Step 4:** the matrix file and `tests/integration` of the voice routes → PASS.
- [ ] **Step 5:** commit `test: owner and stranger matrix covers the profile card (plan 0074)`.

---

### Task 8: Readiness, truth, acceptance and close

**Files:** `commissioning_readiness.py` and its test, `.env.example`, `docs/runbooks/operator-manual.md`,
`docs/architecture/seed-data-pool.md`, `current-state.md` and its Archify diagram, the roadmap, the memory
map, `docs/plans/README.md`, `docs/plans/open/README.md`, `docs/adr/README.md`, ADR 0026, ADR 0020 §7,
ADR 0021 decision 13, ADR 0024 decision 7, a new `docs/evals/0074-profile-card-acceptance.md`.

- [ ] **Step 1: Readiness (RED first).** Add `Capability.ANSWER_PROFILE = "answer_profile"` with a catalogue
  entry that needs no data section. Two existing tests fail first and are updated:
  `tests/unit/test_commissioning_readiness.py` (it pins the six capability value strings) and
  `tests/integration/test_commission_cli.py` (`_HARDWARE_ANSWERS = ["si"] * 18  # six capabilities`
  becomes `* 21` and its comment «seven capabilities»; `_read_hardware` asks three questions per
  capability, so the queued answers would run out). **There is no automated verification turn in the
  code** (the audit confirmed it): the person who commissions turns `PROFILE_CARD_ENABLED=true` on in the `.env` (the alta procedure of ADR 0024
  decision 13, step 0) and verifies by asking «¿qué sabes de mí?», then types «verified». Do not build a
  test-turn automation (YAGNI). *This corrects the outline, which said the alta runs a test turn.*
- [ ] **Step 2: Truth.** `.env.example` (both settings, commented), the operator manual (the settings, the
  card, the question, the closed log reasons, the alta step), `seed-data-pool.md` («Answer the profile by
  voice» becomes `exists`, scoped to tastes and the two name datums; the row «Address the owner as they
  like», line 131, becomes `exists` too), `identity-and-access.md` (the card at `basic`, listed in ADR
  0026's *Docs to update*), `current-state.md` (a row + the
  diagram: edit the JSON source, then validate and deliver with the Archify skill), the roadmap and the
  memory map (CM-5a closed), the plan indexes (0074 `CLOSED`), the ADR index; ADR 0026 `Accepted` with its
  *Implementation notes* (the byte-identity deviation of decision 7, **and decision 3**, whose «a test turn
  in the alta» becomes «the person who commissions verifies it by asking») and the pointers in ADR 0020 §7,
  ADR 0021 decision 13 and ADR 0024 decision 7.
- [ ] **Step 3: Checks.** `uv run ruff format --check .`, `uv run ruff check .` (and with explicit paths
  for `scripts/`), `uv run mypy server/src robot/src`, `uv run pyright`,
  `uv run python scripts/check_reserved_terms.py`, every relative link of the changed documents
  resolves, then `just gate` (record the passed count against the baseline of Task 0).
- [ ] **Step 4: Acceptance by Pipec on real hardware** (outcomes only, never the values; on a database
  with data **loaded by the import**: a preferred name, a form of address and tastes): (1) «¿qué sabes de
  mí?» lists them; (2) a reply uses the preferred name; (3) a second face in frame: no card; (4) an
  unknown speaker: the unknown phrase, not the list; (5) `PROFILE_CARD_ENABLED=false`: the behaviour of
  `main`; (6) the median extra latency of the card over 10 turns; (7) `address_form=usted` tried once;
  (8) both `PROFILE_CARD_POSITION` values tried and the better one noted. Record it in
  `docs/evals/0074-profile-card-acceptance.md`.
- [ ] **Step 5:** commit `docs: close plan 0074` (move this plan to `completed/` with its execution
  record); PR; merge only with Pipec's go-ahead.

---

## Non-goals

No episodes, diary, search, embeddings or summaries (CM-4, CM-5b). No sensitive or pool read, no
«¿estás con alguien?», no liveness (ADR 0026 decision 6). No correcting or forgetting (CM-6). No change to
the writer, the policy table, the wire, the robot or the schema (no migration). No retirement of
`build_context` or the `memories` table. No `/chat` card. No greeting first, no reminders, no automated
verification turn in the alta.

## Self-review (2026-10-28)

Spec coverage: decision 1 (split) is documentation; 2 (allow-list, caps, recency, rendering) Tasks 1 and 2;
3 (when, audit, switch, `/chat` out, delivered robot) Tasks 3, 4, 5 and 8; 4 (`basic` for `normal`) Task 3;
5 (explicit question) Task 6; 6 (no sensitive read) is a non-goal pinned by the allow-list tests; 7 (two
datums in the prompt) Tasks 1 and 4, with the deviation noted; 8 (legacy untouched) is a non-goal; 9 (CM-7
gate) belongs to the plan that prepares CM-7. Types: `ProfileCardProvider` (Task 4) is what Task 5 builds;
`ProfileSummarizer` (Task 6) returns the `ProfileSummaryReply` that `profile_summary_text` (Task 3)
produces, and `ProfileSummaryReply` is defined in Task 3 so that Task 6 only uses it; `CardRead`,
`CardReader` and `list_card_literals` agree. Proportion: eight tasks, signatures and test names, no
bodies.

**Independent architecture review (2026-10-28, a read-only reviewer that had not written the plan):**
`APPROVE WITH CHANGES`, no blocker. Applied: the readiness tests that pin six capabilities (Task 8); the
token speaker that would write a denial row per turn (Task 3: `is_face_actor` in the pre-check); the
distinguishable «unavailable» answer (Task 3 tri-state, Task 6 one phrase for denied and unidentified);
`ValueError` from a corrupt row (Task 3: `except Exception`); the existing raw-reader guard instead of a
new one, and the homes of the dialogue guard (Tasks 3 and 5); the `_voice_controller` keyword (Task 5);
`repr=False` (Task 4); neutral wording (Task 1); the spoken-text log of the summary (Task 6); the
aliases not copied a sixth time (Task 3); the docs omitted (Task 8); the per-event cache removed. Not
applied, on purpose: dropping `PROFILE_CARD_POSITION` (Pipec asked for it).

## Execution record (2026-10-28)

Executed on `feat/0074-cm5a-profile-card`, one commit per task, every test seen RED for the stated reason
first (the three exceptions are listed under *Rulings*). **Not pushed, no PR.** Pipec's hardware
acceptance (Task 8, Step 4, [checklist](../../evals/0074-profile-card-acceptance.md)) and the close
(Step 5: this plan to `completed/`, ADR 0026 `Accepted`, the indexes to `CLOSED`) are pending.

| Task | Commit | What |
|---|---|---|
| 0 | none | Re-audit: every claim of Step 2 verified against `main` at `c44f820`; baseline `MEMORY_ENABLED=false`, CI selection: **4849 passed** |
| 1 | `f8df9d5` | `memory/profile_card.py` (pure) + 17 tests |
| 2 | `4324b17` | `relational_v4.list_card_literals` + 5 integration tests |
| 3 | `ea213a3` | `memory/profile_card_access.py`, `ProfileSummaryReply`, the guard homes |
| 4 | `b27b9bc` | the card in the prompt, `ProfileCardProvider`, `PROFILE_CARD_POSITION` |
| 5 | `671081a` | the two voice routes pass the provider behind `PROFILE_CARD_ENABLED` |
| 6 | `8a99935` | `PROFILE_SUMMARY`, its rule, the controller branch, the spoken-text marker |
| 7 | `ba71fc5` | the owner → stranger matrix covers the card |
| 8 | the commit that carries this record | `answer_profile` readiness capability, the docs, the diagram, the acceptance checklist |

Verification at the end of Task 8: `MEMORY_ENABLED=false just gate` → **4965 passed** (CI selection: 4948
collected against a baseline of 4849, so +99); `ruff format --check .`, `ruff check .` (and `scripts/*.py`),
`mypy server/src robot/src`, `pyright` and `scripts/check_reserved_terms.py` clean; every relative link of
the changed documents resolves.

### Rulings

- **Task 4.** `ProfileCardProvider` is a plain alias like its neighbour `ProposalScheduler`, and
  `ProfileCardPosition` is imported at run time in `characters/__init__.py` (the module has no
  `from __future__ import annotations`, so a `TYPE_CHECKING` import would need quoting). No behaviour
  differs.
- **Task 4.** `llm_streaming._build_streaming_base_prompt` takes `profile_card` with a default of `None`:
  `scripts/stream_diagnosis_variants.py`, outside this plan's scope, calls that private helper and must keep
  building the card-free prompt (`tests/unit/test_stream_diagnosis_variants.py` failed without it).
- **Task 5/6, found by the full suites.** `tests/integration/test_transcribe_pipeline.py` has a fake of
  `process_text_turn` with explicit keywords, so it gained `profile_card_provider`; and
  `tests/unit/test_memory_answer_grammar.py::_PREEMPTING_BODIES` (a guard that every rule before the answer
  rule has a case it wins) gained `profile.summary.v1`.
- **Task 6, spoken-text log.** The plan names only the classic helper, but its own integration test requires
  that no stored value reaches the log on **either** route, and `streaming.stream_response_plan` has its own
  `log_spoken`. Both now go through one function, `response_plan.spoken_log_text(plan)`, which returns the
  marker «resumen del perfil» for a known profile summary and `None` otherwise.
- **Task 6, no cache.** With a summarizer present `decide` always returns a plan, so the classic route does not
  run it twice: the integration test shows exactly one audit row (the plan's condition for adding a cache is
  not met).
- **Task 6, branches.** `ruff` allows 12 branches (`max-branches`) and the exhaustive `match` in
  `CognitiveController.decide` reached 13, so `MEMORY_ANSWER` and `PROFILE_SUMMARY` share one `case` that
  calls `_voice_dialogue_plan`; no lint configuration was touched.
- **RED that was not a failing test.** Task 6's «a channel without the summarizer falls through» and the
  negative fixture rows already held before the code (they pin behaviour that must not change). Task 7's tests
  were green by construction; with `_profile_card_provider` forced to return `None` three of the five fail (the
  owner's positive cases). Task 8's `_HARDWARE_ANSWERS = ["si"] * 21` passes before the code (extra answers are
  unused); with 18 answers eight tests fail after it.
- **Task 8, close.** Step 2 lists `Accepted` for ADR 0026 and `CLOSED` for the indexes, but those follow the
  hardware acceptance. The documents say «executed, acceptance pending» instead, and ADR 0026 got its
  *Implementation notes*. The local task table `docs/roadmap/tabla-tareas.md` (never committed) is updated at
  the close.
- **Found on Pipec's hardware run (2026-10-28).** The speech-to-text wrote «¿Qué sabe de mí?» for the question,
  which the rule did not match, so an unknown speaker got an ordinary model answer (no card, no leak, no audit
  row) instead of the fixed phrase. The rule now also accepts «sabe de mí» and «sabe sobre mí»
  (`tests/fixtures/intent_resolution_es.json`: two positive rows and the «mi perro» negative, RED first).
