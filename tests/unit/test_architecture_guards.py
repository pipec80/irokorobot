"""Static architecture guards (Plan 0050): the controls the audit found are permanent."""

import ast
from collections.abc import Callable, Mapping
import inspect
from pathlib import Path
import re
import unicodedata

import pytest
from server.memory import recall_store
from server.secret_values import SECRET_WORDS

import server

_SERVER_ROOT = Path(server.__file__).resolve().parent

_RAW_V4_READERS = frozenset(
    {
        "get_active_literal_facts",
        "get_active_entity_relations",
        "get_literal_fact",
        "get_entity_relation",
        "list_card_literals",
    }
)
# The policy gate, the local setup that re-reads what it just wrote, the candidate writer, which
# compares the active rows' folded keys inside its own transaction (Plan 0062), and the
# canonical writer, which reads the owner's relations to classify a subject and the active rows
# to make a repeat idempotent (Plan 0065), and the owner's sensitive read, which keeps the rows
# stored with the labels of its topic (Plan 0079).
_MAY_IMPORT_RAW_V4_READERS = frozenset(
    {
        "memory/policy_gated_v4_reader.py",
        "personal_setup.py",
        "memory/memory_writer.py",
        "memory/canonical_writer.py",
        "memory/profile_card_access.py",
        "memory/sensitive_store.py",
    }
)
# The repository itself, and the setup status that counts child links.
_MAY_QUERY_V4_TABLES = frozenset({"memory/relational_v4.py", "personal_setup.py"})
_V4_TABLE_SQL = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(?:literal_facts_v4|entity_relations_v4)\b"
)


def _sources() -> dict[str, str]:
    """Return every server module's text, keyed by its path under the package."""
    return {
        path.relative_to(_SERVER_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(_SERVER_ROOT.rglob("*.py"))
    }


def _http_client_builders(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides main.py, that construct an `httpx.AsyncClient`."""
    return [
        name
        for name, text in sources.items()
        if name != "main.py"
        and any(
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == "AsyncClient")
                or (isinstance(node.func, ast.Name) and node.func.id == "AsyncClient")
            )
            for node in ast.walk(ast.parse(text))
        )
    ]


def _raw_v4_reader_importers(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the allowed two, that import a raw v4 reader."""
    return [
        name
        for name, text in sources.items()
        if name not in _MAY_IMPORT_RAW_V4_READERS
        and name != "memory/relational_v4.py"
        and any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name in _RAW_V4_READERS for alias in node.names)
            for node in ast.walk(ast.parse(text))
        )
    ]


def _v4_table_queriers(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the allowed two, that put SQL on a v4 table."""
    return [
        name
        for name, text in sources.items()
        if name not in _MAY_QUERY_V4_TABLES and _V4_TABLE_SQL.search(text)
    ]


@pytest.mark.unit
def test_the_lifespan_owns_the_only_http_client() -> None:
    """No module builds its own client: every call shares the lifespan-owned one (Plan 0039)."""
    assert _http_client_builders(_sources()) == []


@pytest.mark.unit
def test_raw_v4_readers_are_reachable_only_through_the_policy_gate() -> None:
    """A new module reading v4 rows must go through `PolicyGatedV4Reader`."""
    assert _raw_v4_reader_importers(_sources()) == []


@pytest.mark.unit
def test_v4_tables_are_queried_only_by_the_repository_and_setup_status() -> None:
    """No module writes its own SQL against the v4 memory tables."""
    assert _v4_table_queriers(_sources()) == []


@pytest.mark.unit
def test_the_guards_detect_a_violation() -> None:
    """Each guard flags a synthetic offender, so a green run means something."""
    leak = {
        "leak.py": (
            "import httpx\n"
            "from server.memory.relational_v4 import get_active_literal_facts\n"
            'client = httpx.AsyncClient()\nSQL = "SELECT * FROM literal_facts_v4"\n'
        )
    }

    assert _http_client_builders(leak) == ["leak.py"]
    assert _raw_v4_reader_importers(leak) == ["leak.py"]
    assert _v4_table_queriers(leak) == ["leak.py"]


@pytest.mark.unit
def test_the_aware_utc_check_is_defined_once() -> None:
    """The timezone-aware timestamp check lives in `cognition/models.py`; no module keeps a copy."""
    copies = [
        name
        for name, text in _sources().items()
        if re.search(r"def _?(?:require|normalize_optional)_aware_utc\(", text)
    ]

    assert copies == ["cognition/models.py"]


# --- Plan 0060: personal-memory capabilities are policy only (ADR 0019 §6) ---------------

_NEW_ACTION_NAMES = frozenset(
    {
        "READ_PERSONAL_CONVERSATION_MEMORY",
        "PROPOSE_PERSONAL_MEMORY",
        "CONFIRM_PERSONAL_MEMORY",
        "CORRECT_PERSONAL_MEMORY",
        "FORGET_PERSONAL_MEMORY",
        "read_personal_conversation_memory",
        "propose_personal_memory",
        "confirm_personal_memory",
        "correct_personal_memory",
        "forget_personal_memory",
    }
)
# `PROPOSE_MEMORY` and `COMMIT_MEMORY` left in Plan 0062 (nothing consumed them). Delete and
# export are CM-6's, so until then only the model and the policy know them.
_LEGACY_MEMORY_ACTION_NAMES = frozenset(
    {
        "DELETE_HOUSEHOLD_DATA",
        "EXPORT_HOUSEHOLD_DATA",
        "delete_household_data",
        "export_household_data",
    }
)
_RETIRED_ACTION_NAMES = frozenset(
    {"PROPOSE_MEMORY", "COMMIT_MEMORY", "propose_memory", "commit_memory"}
)
# The model and the policy, plus the one module that asks the policy about a candidate step
# (Plan 0062), the one that asks it about the profile card (Plan 0074) and the one that asks it
# about a recall (Plan 0078) and the one that asks it about the owner's sensitive data (Plan 0079):
# every other module reaches the actions through them.
_ACTION_HOMES = frozenset(
    {
        "cognition/models.py",
        "cognition/authorization.py",
        "memory/candidate_policy.py",
        "memory/profile_card_access.py",
        "memory/recall_access.py",
        "memory/sensitive_access.py",
        # Plan 0084: the pending-topic follow-up asks the policy for the owner's own topic.
        "memory/pending_follow_up.py",
    }
)
_MEMORY_SCOPE_MEMBER_NAMES = frozenset({"PERSONAL_MEMORY_READ", "PERSONAL_MEMORY_FORGET"})
_MEMORY_SCOPE_VALUES = frozenset({"personal_memory_read", "personal_memory_forget"})
# Only the enum names its members. The policy table repeats the plain strings because
# importing the enum there would be an import cycle (a drift test pins them together).
_SCOPE_MEMBER_HOMES = frozenset({"cognition/owner_authentication.py"})
_SCOPE_VALUE_HOMES = frozenset({"cognition/owner_authentication.py", "cognition/authorization.py"})
# `manual` evidence counts as `basic`; these are the modules that reference it today (grep on
# 2026-10-08, minus `memory/consolidation.py`, whose `consolidate_turn` left in Plan 0062). A new
# one must be a decision, not an accident.
_MANUAL_HOMES = frozenset(
    {
        "characters/__init__.py",
        "cognition/identity.py",
        "cognition/identity_sessions.py",
    }
)
_GRANT_FIELD_NAMES = frozenset({"grant_spent", "grant_scope"})
_GRANT_FIELD_HOMES = frozenset(
    {"cognition/identity.py", "cognition/identity_sessions.py", "cognition/authorization.py"}
)


def _outside(sources: Mapping[str, str], homes: frozenset[str], names: frozenset[str]) -> list[str]:
    """Modules, besides `homes`, that reference any of `names`.

    A reference is an attribute access, a bare name or a keyword argument equal to a name, or
    a string constant equal to one (so `Enum["NAME"]` and `getattr(Enum, "NAME")` count).
    Prose inside a longer string is not a reference.
    """
    found = set()
    for module, text in sources.items():
        for node in ast.walk(ast.parse(text)):
            if (
                (isinstance(node, ast.Attribute) and node.attr in names)
                or (isinstance(node, ast.Name) and node.id in names)
                or (isinstance(node, ast.keyword) and node.arg in names)
                or (isinstance(node, ast.Constant) and node.value in names)
            ):
                found.add(module)
    return sorted(found - homes)


def _calls(sources: Mapping[str, str], method: str) -> list[str]:
    """Modules that call `method` (a definition is not a call)."""
    return [
        name
        for name, text in sources.items()
        if any(
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == method)
                or (isinstance(node.func, ast.Name) and node.func.id == method)
            )
            for node in ast.walk(ast.parse(text))
        )
    ]


def _issued_as_manual(sources: Mapping[str, str]) -> list[str]:
    """Modules that call `issue_for_person` with a `...MANUAL` source."""
    return [
        name
        for name, text in sources.items()
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "issue_for_person"
            and any(
                keyword.arg == "source"
                and any(
                    isinstance(inner, ast.Attribute) and inner.attr == "MANUAL"
                    for inner in ast.walk(keyword.value)
                )
                for keyword in node.keywords
            )
            for node in ast.walk(ast.parse(text))
        )
    ]


@pytest.mark.unit
def test_the_personal_memory_actions_exist_only_in_the_model_and_the_policy() -> None:
    """Nothing is wired: no route, store or prompt names a personal-memory action yet."""
    assert _outside(_sources(), _ACTION_HOMES, _NEW_ACTION_NAMES) == []


@pytest.mark.unit
def test_the_legacy_memory_actions_are_used_only_by_the_model_and_the_policy() -> None:
    """Nobody else consumes delete or export (verified)."""
    assert _outside(_sources(), _ACTION_HOMES, _LEGACY_MEMORY_ACTION_NAMES) == []


@pytest.mark.unit
def test_the_personal_memory_unlock_scopes_have_no_consumer_yet() -> None:
    sources = _sources()

    assert _outside(sources, _SCOPE_MEMBER_HOMES, _MEMORY_SCOPE_MEMBER_NAMES) == []
    assert _outside(sources, _SCOPE_VALUE_HOMES, _MEMORY_SCOPE_VALUES) == []


@pytest.mark.unit
def test_nothing_in_the_server_selects_a_person_by_manual_session() -> None:
    """`select_person` mints `manual` evidence, which counts as `basic`; it has no caller."""
    assert _calls(_sources(), "select_person") == []


@pytest.mark.unit
def test_manual_evidence_is_referenced_only_where_it_is_today_and_never_issued_as_a_grant() -> None:
    sources = _sources()

    assert _outside(sources, _MANUAL_HOMES, frozenset({"MANUAL"})) == []
    assert _issued_as_manual(sources) == []


@pytest.mark.unit
def test_the_grant_fields_are_read_and_written_only_by_the_identity_and_policy_modules() -> None:
    assert _outside(_sources(), _GRANT_FIELD_HOMES, _GRANT_FIELD_NAMES) == []


@pytest.mark.unit
def test_the_personal_memory_guards_detect_a_violation() -> None:
    """Each guard flags a synthetic offender and spares a synthetic home."""
    leak = {
        "routers/leak.py": (
            "from server.cognition.models import AuthorizationAction\n"
            "a = AuthorizationAction.FORGET_PERSONAL_MEMORY\n"
            "b = AuthorizationAction.DELETE_HOUSEHOLD_DATA\n"
            "c = OwnerUnlockScope.PERSONAL_MEMORY_FORGET\n"
            'd = "read_personal_conversation_memory"\n'
            'e = "delete_household_data"\n'
            'f = "personal_memory_read"\n'
            "g = registry.select_person(7)\n"
            "h = IdentityEvidenceSource.MANUAL\n"
            "i = registry.issue_for_person(person, source=IdentityEvidenceSource.MANUAL)\n"
            'j = evidence.model_copy(update={"grant_spent": True})\n'
            'k = Evidence(grant_scope="personal_memory_forget")\n'
        ),
        "routers/subscript.py": 'x = AuthorizationAction["FORGET_PERSONAL_MEMORY"]\n',
        "routers/getattr.py": 'x = getattr(AuthorizationAction, "FORGET_PERSONAL_MEMORY")\n',
        "routers/scope_getattr.py": 'x = getattr(OwnerUnlockScope, "PERSONAL_MEMORY_READ")\n',
        "cognition/authorization.py": "x = AuthorizationAction.FORGET_PERSONAL_MEMORY\ny = 1\n",
        "prose.py": '"""Forgetting uses forget_personal_memory in prose, which is not a reference."""\n',
    }

    assert _outside(leak, _ACTION_HOMES, _NEW_ACTION_NAMES) == [
        "routers/getattr.py",
        "routers/leak.py",
        "routers/subscript.py",
    ]
    assert _outside(leak, _ACTION_HOMES, _LEGACY_MEMORY_ACTION_NAMES) == ["routers/leak.py"]
    assert _outside(leak, _SCOPE_MEMBER_HOMES, _MEMORY_SCOPE_MEMBER_NAMES) == [
        "routers/leak.py",
        "routers/scope_getattr.py",
    ]
    assert _outside(leak, _SCOPE_VALUE_HOMES, _MEMORY_SCOPE_VALUES) == ["routers/leak.py"]
    assert _outside(leak, _MANUAL_HOMES, frozenset({"MANUAL"})) == ["routers/leak.py"]
    assert _outside(leak, _GRANT_FIELD_HOMES, _GRANT_FIELD_NAMES) == ["routers/leak.py"]
    assert _calls(leak, "select_person") == ["routers/leak.py"]
    assert _issued_as_manual(leak) == ["routers/leak.py"]


# --- Plan 0065: the household pair of capabilities is policy only (ADR 0022 decision 3) ----

# Nothing consumes the pair yet. Its homes are the model and the policy only, and are NOT
# `_ACTION_HOMES`: `memory/candidate_policy.py` asks the policy about the five personal actions
# and must not reach the household ones. The first consumer (the import of Step 0, or tranche B)
# extends this guard.
_HOUSEHOLD_ACTION_NAMES = frozenset(
    {
        "PROPOSE_HOUSEHOLD_MEMORY",
        "CONFIRM_HOUSEHOLD_MEMORY",
        "propose_household_memory",
        "confirm_household_memory",
    }
)
_HOUSEHOLD_ACTION_HOMES = frozenset({"cognition/models.py", "cognition/authorization.py"})


@pytest.mark.unit
def test_the_household_memory_actions_exist_only_in_the_model_and_the_policy() -> None:
    """No route, store, prompt or candidate step names a household-memory action yet."""
    assert _outside(_sources(), _HOUSEHOLD_ACTION_HOMES, _HOUSEHOLD_ACTION_NAMES) == []


@pytest.mark.unit
def test_the_household_memory_guard_detects_a_violation() -> None:
    """A synthetic offender is flagged, the two homes and a prose mention are spared."""
    leak = {
        "routers/leak.py": (
            "from server.cognition.models import AuthorizationAction\n"
            "a = AuthorizationAction.PROPOSE_HOUSEHOLD_MEMORY\n"
        ),
        "routers/value.py": 'x = "confirm_household_memory"\n',
        "routers/subscript.py": 'x = AuthorizationAction["CONFIRM_HOUSEHOLD_MEMORY"]\n',
        "routers/getattr.py": 'x = getattr(AuthorizationAction, "PROPOSE_HOUSEHOLD_MEMORY")\n',
        # A home of the five personal actions, but not of the household pair.
        "memory/candidate_policy.py": "x = AuthorizationAction.CONFIRM_HOUSEHOLD_MEMORY\n",
        "cognition/authorization.py": "x = AuthorizationAction.PROPOSE_HOUSEHOLD_MEMORY\ny = 1\n",
        "cognition/models.py": 'PROPOSE_HOUSEHOLD_MEMORY = "propose_household_memory"\n',
        "prose.py": '"""The pair propose_household_memory is policy only: prose, not a reference."""\n',
    }

    assert _outside(leak, _HOUSEHOLD_ACTION_HOMES, _HOUSEHOLD_ACTION_NAMES) == [
        "memory/candidate_policy.py",
        "routers/getattr.py",
        "routers/leak.py",
        "routers/subscript.py",
        "routers/value.py",
    ]
    assert not _HOUSEHOLD_ACTION_NAMES & _NEW_ACTION_NAMES
    assert "memory/candidate_policy.py" in _ACTION_HOMES
    assert "memory/candidate_policy.py" not in _HOUSEHOLD_ACTION_HOMES


# --- the short-term continuity session (Plan 0061, ADR 0020) ----------------------------
_SESSION_HOME = "memory/continuity.py"
_SESSION_CALLERS = frozenset({_SESSION_HOME, "text_turn.py"})
_SESSION_PRIVATE_NAMES = frozenset({"_session", "_slot", "ContinuitySession"})
_GENERIC_IDENTITY_HOME = "cognition/generic_identity.py"


def _keyword_values(sources: Mapping[str, str], module: str, keyword: str) -> list[ast.expr]:
    """The value of every `keyword=...` argument used anywhere in one module."""
    return [
        node.value
        for node in ast.walk(ast.parse(sources[module]))
        if isinstance(node, ast.keyword) and node.arg == keyword
    ]


@pytest.mark.unit
def test_the_session_is_opened_and_written_only_by_the_text_turn_service() -> None:
    """A route or a tool that read the session would bypass the speaker's transition."""
    sources = _sources()

    assert sorted(_calls(sources, "open_turn")) == sorted(_SESSION_CALLERS)
    assert sorted(_calls(sources, "record_pair")) == sorted(_SESSION_CALLERS)
    assert _outside(sources, frozenset({_SESSION_HOME}), _SESSION_PRIVATE_NAMES) == []


@pytest.mark.unit
def test_identifying_a_generic_turn_never_spends_a_grant_or_computes_a_voice() -> None:
    """ADR 0020 §1: observe the token (`peek_actor`), and pass no audio to the resolver."""
    sources = _sources()

    assert _calls({_GENERIC_IDENTITY_HOME: sources[_GENERIC_IDENTITY_HOME]}, "resolve_actor") == []
    assert (
        _calls({_GENERIC_IDENTITY_HOME: sources[_GENERIC_IDENTITY_HOME]}, "resolve_consent") == []
    )
    wav_values = _keyword_values(sources, _GENERIC_IDENTITY_HOME, "wav_bytes")
    assert wav_values
    assert all(isinstance(v, ast.Constant) and v.value is None for v in wav_values)


@pytest.mark.unit
def test_the_continuity_guards_detect_a_violation() -> None:
    leak = {
        "routers/leak.py": (
            "turn = continuity.open_turn(7)\n"
            "ok = continuity.record_pair(turn, 'a', 'b')\n"
            "slot = continuity._session\n"
        ),
        "cognition/generic_identity.py": (
            "actor = await fused.resolve_actor(event)\n"
            "fused = build(pin, frame=frame, wav_bytes=audio)\n"
        ),
        "memory/continuity.py": "x = _session.open_turn(1)\n",
    }

    assert _calls(leak, "open_turn") == ["routers/leak.py", "memory/continuity.py"]
    assert _outside(leak, frozenset({_SESSION_HOME}), _SESSION_PRIVATE_NAMES) == ["routers/leak.py"]
    assert _calls({_GENERIC_IDENTITY_HOME: leak[_GENERIC_IDENTITY_HOME]}, "resolve_actor") == [
        _GENERIC_IDENTITY_HOME
    ]
    (wav_value,) = _keyword_values(leak, _GENERIC_IDENTITY_HOME, "wav_bytes")
    assert not (isinstance(wav_value, ast.Constant) and wav_value.value is None)


# --- memory candidates (Plan 0062, ADR 0021) ---------------------------------------------
# The store is the only module that issues SQL against the candidate table, so the scrub, the
# compare-and-set and the cap cannot be bypassed by a second writer.
_CANDIDATE_TABLE_SQL = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+memory_candidates\b"
)
_MAY_QUERY_CANDIDATES = frozenset({"memory/candidates.py"})


def _candidate_table_queriers(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the store, that put SQL on `memory_candidates`."""
    return [
        name
        for name, text in sources.items()
        if name not in _MAY_QUERY_CANDIDATES and _CANDIDATE_TABLE_SQL.search(text)
    ]


@pytest.mark.unit
def test_the_candidate_table_is_queried_only_by_the_store() -> None:
    assert _candidate_table_queriers(_sources()) == []


@pytest.mark.unit
def test_the_candidate_guard_detects_a_violation() -> None:
    leak = {
        "memory/leak.py": "SQL = \"UPDATE memory_candidates SET status = 'offered'\"\n",
        "memory/candidates.py": 'SQL = "SELECT 1 FROM memory_candidates"\n',
        "prose.py": '"""The memory_candidates table is described here."""\n',
    }

    assert _candidate_table_queriers(leak) == ["memory/leak.py"]


# --- who may start a candidate proposal (Plan 0062, ADR 0021 decision 1) -----------------
# Only the two voice routes and the text-turn service they call may name the proposal entry
# point or its scheduler: `/chat` and `/vision/respond` have no audio, so they have no `strong`
# and must never create a candidate. `consolidate_turn` is gone for good.
_PROPOSAL_NAMES = frozenset({"propose_candidates", "schedule_proposal", "ProposalScheduler"})
_PROPOSAL_HOMES = frozenset(
    {
        "memory/candidate_proposal.py",
        "routers/transcribe.py",
        "streaming.py",
        "text_turn.py",
    }
)


@pytest.mark.unit
def test_only_the_voice_routes_and_the_text_turn_service_start_a_proposal() -> None:
    assert _outside(_sources(), _PROPOSAL_HOMES, _PROPOSAL_NAMES) == []


def _imports_name(sources: Mapping[str, str], name: str) -> list[str]:
    """Modules that import *name* (an import alias is not a Name node)."""
    return [
        module
        for module, text in sources.items()
        if any(
            isinstance(node, ast.ImportFrom) and any(alias.name == name for alias in node.names)
            for node in ast.walk(ast.parse(text))
        )
    ]


@pytest.mark.unit
def test_the_retired_consolidation_writer_has_no_reference_left() -> None:
    sources = _sources()

    assert _outside(sources, frozenset(), frozenset({"consolidate_turn"})) == []
    assert _imports_name(sources, "consolidate_turn") == []


# The legacy memory path retired by Plan 0076 (ADR 0027 decision 9): the `MANUAL`-gated
# `build_context`, the vector store over `memories` and everything only it fed.
_RETIRED_LEGACY_MEMORY_NAMES = frozenset(
    {
        "build_context",
        "search_memories",
        "store_memory",
        "entities_for_relations",
        "find_facts_by_predicate",
        "load_entity_by_id",
        "load_entity_with_facts",
        "_memory_prompt_state",
        "_manual_evidence",
        # The prompt surface only that path fed (Plan 0076 Task 2).
        "MemoryContext",
        "MemoryHit",
        "EntityWithFacts",
        "OnboardingSlot",
        "onboarding_slot",
        "onboarding_prompt",
        "next_missing_slot",
        "_format_memory_block",
    }
)


def _definers(sources: Mapping[str, str], names: frozenset[str]) -> list[str]:
    """Modules that define a function or class named in `names`."""
    return sorted(
        module
        for module, text in sources.items()
        if any(
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and node.name in names
            for node in ast.walk(ast.parse(text))
        )
    )


@pytest.mark.unit
def test_the_legacy_memory_path_has_no_reference_left() -> None:
    sources = _sources()

    assert _outside(sources, frozenset(), _RETIRED_LEGACY_MEMORY_NAMES) == []
    assert _definers(sources, _RETIRED_LEGACY_MEMORY_NAMES) == []
    for name in _RETIRED_LEGACY_MEMORY_NAMES:
        assert _imports_name(sources, name) == []


@pytest.mark.unit
def test_the_legacy_guard_detects_a_violation() -> None:
    sources = {"memory/back.py": "async def build_context():\n    return await search_memories()\n"}

    assert _outside(sources, frozenset(), _RETIRED_LEGACY_MEMORY_NAMES) == ["memory/back.py"]
    assert _definers(sources, _RETIRED_LEGACY_MEMORY_NAMES) == ["memory/back.py"]


@pytest.mark.unit
def test_the_proposal_guards_detect_a_violation() -> None:
    leak = {
        "routers/chat.py": "x = propose_candidates(client, text, actor)\n",
        "routers/vision.py": "process_text_turn(c, m, i, schedule_proposal=cb)\n",
        "routers/transcribe.py": "x = propose_candidates\n",
        "memory/legacy.py": "from x import consolidate_turn\n",
    }

    assert _outside(leak, _PROPOSAL_HOMES, _PROPOSAL_NAMES) == [
        "routers/chat.py",
        "routers/vision.py",
    ]
    assert _imports_name(leak, "consolidate_turn") == ["memory/legacy.py"]


# --- who may offer or answer (Plan 0063, ADR 0021 decision 9) ---------------------------------
# The offer and the answer need the voice of the turn's own clip: only the voice routes bind
# them, and the text turn, the stream and the controller carry the seams. `/chat` and
# `/vision/respond` have no audio, so they never offer and never answer.
#
# Plan 0074: the profile card is read by the same two routes (the provider names), and the access
# module, which never names the provider, is not a home.
_DIALOGUE_NAMES = frozenset(
    {
        "prepare_offer",
        "OfferPreparer",
        "answer_offer",
        "MemoryAnswerer",
        "memory_answerer",
        "profile_card_provider",
        "ProfileCardProvider",
        "_profile_card_provider",
        "profile_summarizer",
        "ProfileSummarizer",
        "_profile_summarizer",
    }
)
_DIALOGUE_HOMES = frozenset(
    {
        "memory/candidate_dialogue.py",
        "routers/transcribe.py",
        "streaming.py",
        "text_turn.py",
        "cognition/controller.py",
    }
)


@pytest.mark.unit
def test_only_the_voice_routes_offer_or_answer_a_memory() -> None:
    assert _outside(_sources(), _DIALOGUE_HOMES, _DIALOGUE_NAMES) == []


@pytest.mark.unit
def test_the_dialogue_guard_detects_a_violation() -> None:
    leak = {
        "routers/chat.py": "controller = CognitiveController(memory_answerer=a)\n",
        "routers/vision.py": "x = prepare_offer(actor)\n",
        "routers/transcribe.py": "x = prepare_offer(actor)\n",
        # The profile card (Plan 0074) is read by the voice routes only.
        "routers/chat_card.py": "x = await process_text_turn(c, m, i, profile_card_provider=p)\n",
        "routers/vision_card.py": "x = _profile_card_provider(correlation_id)\n",
        "routers/typed.py": "def f(p: ProfileCardProvider) -> None: ...\n",
        "memory/profile_card_access.py": "x = profile_card_provider\n",
        # So is the explicit «¿qué sabes de mí?» (Plan 0074).
        "routers/chat_summary.py": "c = CognitiveController(profile_summarizer=s)\n",
        "routers/vision_summary.py": "s = _profile_summarizer()\n",
        "routers/typed_summary.py": "def f(s: ProfileSummarizer) -> None: ...\n",
    }

    assert _outside(leak, _DIALOGUE_HOMES, _DIALOGUE_NAMES) == [
        "memory/profile_card_access.py",
        "routers/chat.py",
        "routers/chat_card.py",
        "routers/chat_summary.py",
        "routers/typed.py",
        "routers/typed_summary.py",
        "routers/vision.py",
        "routers/vision_card.py",
        "routers/vision_summary.py",
    ]


# The offer's own steps (Plan 0063): the store's offer lookups are reached only by the dialogue,
# and the dialogue's commit only by the text-turn service that owns the reply. grep on 2026-10-15.
_OFFER_LOOKUP_NAMES = frozenset({"find_offered", "next_offerable", "still_offerable"})
_OFFER_LOOKUP_HOMES = frozenset({"memory/candidates.py", "memory/candidate_dialogue.py"})
_OFFER_COMMIT_NAMES = frozenset({"commit_offer"})
_OFFER_COMMIT_HOMES = frozenset({"memory/candidate_dialogue.py", "text_turn.py"})
# `start_offer` and `finish_offer` belong to the text-turn service; the stream drives them too.
_OFFER_LIFECYCLE_NAMES = frozenset({"start_offer", "finish_offer"})
_OFFER_LIFECYCLE_HOMES = frozenset({"text_turn.py", "streaming.py"})


@pytest.mark.unit
def test_the_offer_steps_are_named_only_by_the_dialogue_and_the_text_turn() -> None:
    sources = _sources()

    assert _outside(sources, _OFFER_LOOKUP_HOMES, _OFFER_LOOKUP_NAMES) == []
    assert _outside(sources, _OFFER_COMMIT_HOMES, _OFFER_COMMIT_NAMES) == []
    assert _outside(sources, _OFFER_LIFECYCLE_HOMES, _OFFER_LIFECYCLE_NAMES) == []


@pytest.mark.unit
def test_the_offer_step_guards_detect_a_violation() -> None:
    leak = {
        "routers/chat.py": (
            "offered = await candidates.find_offered(conn, person_id)\n"
            "await commit_offer(pending)\n"
            "task = start_offer(prepare, actor)\n"
        ),
        "routers/transcribe.py": "x = await still_offerable(conn, candidate)\n",
        "memory/other.py": "x = next_offerable(conn, person_id)\nawait commit_offer(p)\n",
        "memory/candidates.py": "x = find_offered(c)\ny = next_offerable(c)\n",
        "memory/candidate_dialogue.py": "await commit_offer(p)\nawait still_offerable(c)\n",
        "text_turn.py": "await commit_offer(p)\nt = start_offer(a, b)\n",
        "streaming.py": "t = start_offer(a, b)\nawait finish_offer(t)\n",
    }

    assert _outside(leak, _OFFER_LOOKUP_HOMES, _OFFER_LOOKUP_NAMES) == [
        "memory/other.py",
        "routers/chat.py",
        "routers/transcribe.py",
    ]
    assert _outside(leak, _OFFER_COMMIT_HOMES, _OFFER_COMMIT_NAMES) == [
        "memory/other.py",
        "routers/chat.py",
    ]
    assert _outside(leak, _OFFER_LIFECYCLE_HOMES, _OFFER_LIFECYCLE_NAMES) == ["routers/chat.py"]


@pytest.mark.unit
def test_the_retired_memory_actions_exist_nowhere() -> None:
    """ADR 0021 decision 11: no enum member, branch or string names them any more."""
    assert _outside(_sources(), frozenset(), _RETIRED_ACTION_NAMES) == []


# --- who may write or move a candidate (Plan 0062, ADR 0021 decisions 3 and 8) --------------
# The firewall rule (face and voice of the same person on the turn's clip) is enforced by the
# caller of the store, so the callers are pinned: a second caller must be a decision, not an
# accident. Plan 0063 added the dialogue module, which offers, rejects and asks the writer.
_CANDIDATE_INSERT_HOMES = frozenset({"memory/candidates.py", "memory/candidate_proposal.py"})
_CANDIDATE_MOVE_HOMES = frozenset(
    {"memory/candidates.py", "memory/memory_writer.py", "memory/candidate_dialogue.py"}
)
_CANDIDATE_MOVES = frozenset(
    {"mark_offered", "resolve_candidate", "resolve_candidate_in_transaction"}
)
_WRITER_HOMES = frozenset({"memory/memory_writer.py", "memory/candidate_dialogue.py"})


@pytest.mark.unit
def test_only_the_proposal_inserts_and_only_the_writer_resolves_a_candidate() -> None:
    sources = _sources()

    assert _outside(sources, _CANDIDATE_INSERT_HOMES, frozenset({"insert_candidate"})) == []
    assert _outside(sources, _CANDIDATE_MOVE_HOMES, _CANDIDATE_MOVES) == []
    assert _outside(sources, _WRITER_HOMES, frozenset({"promote"})) == []


@pytest.mark.unit
def test_the_candidate_caller_guards_detect_a_violation() -> None:
    leak = {
        "routers/leak.py": "await insert_candidate(p)\nawait candidates.mark_offered(1)\n",
        "memory/candidate_proposal.py": "await insert_candidate(p)\n",
        "memory/memory_writer.py": "await resolve_candidate_in_transaction(c)\nawait promote(1)\n",
        "memory/other.py": "await promote(1)\n",
        "memory/candidate_dialogue.py": "await mark_offered(1)\nawait promote(1)\n",
    }

    assert _outside(leak, _CANDIDATE_INSERT_HOMES, frozenset({"insert_candidate"})) == [
        "routers/leak.py"
    ]
    assert _outside(leak, _CANDIDATE_MOVE_HOMES, _CANDIDATE_MOVES) == ["routers/leak.py"]
    assert _outside(leak, _WRITER_HOMES, frozenset({"promote"})) == ["memory/other.py"]


# --- who may call the repository's writers (Plan 0065, ADR 0022 decision 2) ------------------
# One canonical writer stores a household fact whatever the channel. The local setup and the
# legacy migration are the two documented exceptions the Step 0 ADR decides; a third caller of
# the repository's `assert_*` must be a decision, not an accident.
_REPOSITORY_WRITERS = frozenset({"assert_literal_fact", "assert_entity_relation"})
_REPOSITORY_WRITER_HOMES = frozenset(
    {
        "memory/relational_v4.py",
        "memory/canonical_writer.py",
        "personal_setup.py",
        "memory/legacy_v4_migration.py",
    }
)


@pytest.mark.unit
def test_only_the_canonical_writer_and_the_documented_setups_call_the_repository_writers() -> None:
    assert _outside(_sources(), _REPOSITORY_WRITER_HOMES, _REPOSITORY_WRITERS) == []


@pytest.mark.unit
def test_the_repository_writer_guard_detects_a_violation() -> None:
    leak = {
        "routers/leak.py": "await assert_literal_fact(subject_entity_id=1)\n",
        "memory/other.py": "await relational_v4.assert_entity_relation(source_entity_id=1)\n",
        "memory/canonical_writer.py": "await assert_literal_fact(subject_entity_id=1)\n",
        "personal_setup.py": "await assert_entity_relation(source_entity_id=1)\n",
        "memory/prose.py": '"""assert_literal_fact is only named in prose here."""\n',
    }

    assert _outside(leak, _REPOSITORY_WRITER_HOMES, _REPOSITORY_WRITERS) == [
        "memory/other.py",
        "routers/leak.py",
    ]


# --- care contacts (Plan 0070, ADR 0024 decision 5) -----------------------------------------
# One module writes and reads the contacts table, so the classification, the phone format and the
# order rule cannot be bypassed by a second writer.
_CARE_CONTACT_SQL = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+care_contacts\b")
_MAY_QUERY_CARE_CONTACTS = frozenset({"memory/care_contacts.py"})


def _care_contact_queriers(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the contacts writer, that put SQL on `care_contacts`."""
    return [
        name
        for name, text in sources.items()
        if name not in _MAY_QUERY_CARE_CONTACTS and _CARE_CONTACT_SQL.search(text)
    ]


@pytest.mark.unit
def test_the_contacts_table_is_queried_only_by_the_contacts_writer() -> None:
    assert _care_contact_queriers(_sources()) == []


@pytest.mark.unit
def test_the_contacts_guard_detects_a_violation() -> None:
    leak = {
        "memory/leak.py": 'SQL = "UPDATE care_contacts SET phone = ?"\n',
        "routers/leak.py": 'SQL = "SELECT phone FROM care_contacts"\n',
        "memory/care_contacts.py": 'SQL = "SELECT 1 FROM care_contacts"\n',
        "prose.py": '"""The care_contacts table is described here."""\n',
    }

    assert _care_contact_queriers(leak) == ["memory/leak.py", "routers/leak.py"]


# --- the commissioning record (Plan 0070, ADR 0024 decision 6) ------------------------------
# One module opens, writes and closes the acta, so the one-open-record rule, the closed-record
# rule and the rule that it holds no household value cannot be bypassed by a second writer.
_COMMISSIONING_SQL = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+commissioning_(?:records|sections)\b"
)
_MAY_QUERY_COMMISSIONING = frozenset({"memory/commissioning.py"})


def _commissioning_queriers(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the commissioning module, that put SQL on its two tables."""
    return [
        name
        for name, text in sources.items()
        if name not in _MAY_QUERY_COMMISSIONING and _COMMISSIONING_SQL.search(text)
    ]


@pytest.mark.unit
def test_the_commissioning_tables_are_queried_only_by_the_commissioning_module() -> None:
    assert _commissioning_queriers(_sources()) == []


@pytest.mark.unit
def test_the_commissioning_guard_detects_a_violation() -> None:
    leak = {
        "memory/leak.py": 'SQL = "UPDATE commissioning_records SET closed_at = NULL"\n',
        "routers/leak.py": 'SQL = "INSERT INTO commissioning_sections (section) VALUES (?)"\n',
        "memory/commissioning.py": 'SQL = "SELECT 1 FROM commissioning_records"\n',
        "prose.py": '"""The commissioning_records table is described here."""\n',
    }

    assert _commissioning_queriers(leak) == ["memory/leak.py", "routers/leak.py"]


# --- the admin audit (Plan 0073, ADR 0025 decision 4) ---------------------------------------
# One module writes and reads the admin audit, so the "one row per operation, no value" rule
# cannot be bypassed by a second writer.
_ADMIN_AUDIT_SQL = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+admin_audit\b")
_MAY_QUERY_ADMIN_AUDIT = frozenset({"memory/admin_audit.py"})


def _admin_audit_queriers(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the audit repository, that put SQL on `admin_audit`."""
    return [
        name
        for name, text in sources.items()
        if name not in _MAY_QUERY_ADMIN_AUDIT and _ADMIN_AUDIT_SQL.search(text)
    ]


@pytest.mark.unit
def test_the_admin_audit_table_is_queried_only_by_its_repository() -> None:
    assert _admin_audit_queriers(_sources()) == []


@pytest.mark.unit
def test_the_admin_audit_guard_detects_a_violation() -> None:
    leak = {
        "memory/leak.py": 'SQL = "INSERT INTO admin_audit (operation) VALUES (?)"\n',
        "routers/leak.py": 'SQL = "SELECT operation FROM admin_audit"\n',
        "memory/admin_audit.py": 'SQL = "SELECT 1 FROM admin_audit"\n',
        "prose.py": '"""The admin_audit table is described here."""\n',
    }

    assert _admin_audit_queriers(leak) == ["memory/leak.py", "routers/leak.py"]


# --- the import channels (Plan 0071, ADR 0024 decision 7) -----------------------------------
# The import bypasses the policy on purpose, so only the vocabulary and the applier may name its
# channels: a route or a store that wrote as an import would skip the face-and-voice rule. The
# retraction speaks of `IMPORT_CHANNELS`, never of one channel.
_IMPORT_CHANNEL_NAMES = frozenset(
    {"IMPORT_FILE", "IMPORT_ASSISTED", "import_file", "import_assisted"}
)
_IMPORT_CHANNEL_HOMES = frozenset({"memory/write_types.py", "memory/seed_import.py"})


@pytest.mark.unit
def test_only_the_vocabulary_and_the_applier_name_an_import_channel() -> None:
    assert _outside(_sources(), _IMPORT_CHANNEL_HOMES, _IMPORT_CHANNEL_NAMES) == []


@pytest.mark.unit
def test_the_import_channel_guard_detects_a_violation() -> None:
    leak = {
        "routers/leak.py": "x = WriteChannel.IMPORT_ASSISTED\n",
        "memory/other.py": 'x = WriteChannel("import_file")\n',
        "memory/seed_import.py": "x = WriteChannel.IMPORT_ASSISTED\n",
        "memory/prose.py": '"""The importer writes with import_assisted, in prose."""\n',
    }

    assert _outside(leak, _IMPORT_CHANNEL_HOMES, _IMPORT_CHANNEL_NAMES) == [
        "memory/other.py",
        "routers/leak.py",
    ]


# --- memory does not depend on a command (Plan 0071) -----------------------------------------
# `personal_setup` and `seed_cli` are command-line adapters over memory; the dependency points one
# way only.
_COMMAND_MODULES = frozenset({"server.personal_setup", "server.seed_cli"})


def _memory_modules_importing_a_command(sources: Mapping[str, str]) -> list[str]:
    """Modules under `memory/` that import a command module."""
    return sorted(
        name
        for name, text in sources.items()
        if name.startswith("memory/")
        and any(
            (isinstance(node, ast.ImportFrom) and node.module in _COMMAND_MODULES)
            or (
                isinstance(node, ast.Import)
                and any(alias.name in _COMMAND_MODULES for alias in node.names)
            )
            for node in ast.walk(ast.parse(text))
        )
    )


@pytest.mark.unit
def test_no_memory_module_imports_a_command() -> None:
    assert _memory_modules_importing_a_command(_sources()) == []


@pytest.mark.unit
def test_the_command_guard_detects_a_violation() -> None:
    leak = {
        "memory/leak.py": "from server.personal_setup import read_personal_setup_status\n",
        "memory/other.py": "import server.seed_cli\n",
        "personal_setup.py": "from server.memory.declarative import upsert_entity\n",
    }

    assert _memory_modules_importing_a_command(leak) == ["memory/leak.py", "memory/other.py"]


# --- the conversation record (Plan 0076, ADR 0027) -------------------------------------------------
# Each table has one store; no prompt, route, controller or voice answer reads the record, so
# its text can never reach a reply; only the voice routes and the text service name the recorder.
_CONVERSATION_TABLE_HOMES = {
    "conversation_records": "memory/conversation_record.py",
    "conversation_episodes": "memory/conversation_episodes.py",
    "conversation_consent_grants": "memory/conversation_consent.py",
}
# The recall store may JOIN a unit to its record, only to skip an expired one (Plan 0078): no
# other statement on the table, and never the record's turns.
_CONVERSATION_TABLE_JOINERS = {"conversation_records": frozenset({"memory/recall_store.py"})}
_RECORD_READER_MODULES = frozenset(
    {
        "server.memory.conversation_record",
        "server.memory.conversation_episodes",
        "server.memory.conversation_summary",
    }
)
_NO_RECORD_READS = ("characters/", "cognition/", "routers/", "llm", "streaming", "text_turn.py")
_RECORDER_NAMES = frozenset({"TurnRecorder", "record_turn", "_turn_recorder", "capture_turn"})
_RECORDER_HOMES = frozenset(
    {
        "text_turn.py",
        "streaming.py",
        "routers/transcribe.py",
        "memory/conversation_capture.py",
    }
)


def _conversation_table_queriers(sources: Mapping[str, str]) -> list[str]:
    """Modules that put SQL on a conversation table they do not own."""
    found = []
    for table, home in _CONVERSATION_TABLE_HOMES.items():
        sql = re.compile(rf"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+{table}\b")
        beyond_a_join = re.compile(rf"\b(?:FROM|INTO|UPDATE)\s+{table}\b|\bturns\b")
        joiners = _CONVERSATION_TABLE_JOINERS.get(table, frozenset())
        found += [
            name
            for name, text in sources.items()
            if name != home
            and sql.search(text)
            and (name not in joiners or beyond_a_join.search(text))
        ]
    return sorted(found)


def _record_readers(sources: Mapping[str, str]) -> list[str]:
    """Prompt, route and voice modules that import the record, the diary or the summary."""
    return sorted(
        name
        for name, text in sources.items()
        if name.startswith(_NO_RECORD_READS)
        and any(
            (isinstance(node, ast.ImportFrom) and node.module in _RECORD_READER_MODULES)
            or (
                isinstance(node, ast.Import)
                and any(alias.name in _RECORD_READER_MODULES for alias in node.names)
            )
            for node in ast.walk(ast.parse(text))
        )
    )


_NO_HOUSEHOLD_READS = ("characters/", "llm", "streaming", "text_turn.py")
_HOUSEHOLD_READER_MODULES = frozenset(
    {
        "server.cognition.household_tools",
        "server.memory.declarative",
        "server.memory.entity_labels",
        "server.memory.policy_gated_v4_reader",
    }
)


def _household_readers(sources: Mapping[str, str]) -> list[str]:
    """Prompt-path modules that import a store of household data."""
    return sorted(
        name
        for name, text in sources.items()
        if name.startswith(_NO_HOUSEHOLD_READS)
        and any(
            isinstance(node, ast.ImportFrom) and node.module in _HOUSEHOLD_READER_MODULES
            for node in ast.walk(ast.parse(text))
        )
    )


@pytest.mark.unit
def test_the_generic_prompt_reads_no_household_store() -> None:
    """Plan 0077 rests on this: a turn routed to the model by mistake holds nothing to reveal.

    Whoever needs household data in the prompt must first make the household rule broad again.
    """
    assert _household_readers(_sources()) == []


@pytest.mark.unit
def test_the_household_prompt_guard_detects_a_violation() -> None:
    sources = {
        "text_turn.py": "from server.memory.entity_labels import list_known_names\n",
        "routers/chat.py": "from server.memory.entity_labels import read_household_names\n",
    }

    assert _household_readers(sources) == ["text_turn.py"]


@pytest.mark.unit
def test_each_conversation_table_is_queried_only_by_its_store() -> None:
    assert _conversation_table_queriers(_sources()) == []


@pytest.mark.unit
def test_the_recall_store_may_only_join_the_record_for_its_expiry() -> None:
    joined = 'SQL = "SELECT u.id FROM recall_units u JOIN conversation_records r ON 1"\n'
    sources = {
        "memory/recall_store.py": joined,
        "memory/other.py": joined,
    }
    assert _conversation_table_queriers(sources) == ["memory/other.py"]

    for leak in (
        'SQL = "SELECT r.turns FROM recall_units u JOIN conversation_records r ON 1"\n',
        'SQL = "UPDATE conversation_records SET eligible = 0"\n',
    ):
        assert _conversation_table_queriers({"memory/recall_store.py": leak}) == [
            "memory/recall_store.py"
        ]


@pytest.mark.unit
def test_no_prompt_or_route_reads_the_record() -> None:
    assert _record_readers(_sources()) == []


@pytest.mark.unit
def test_only_the_voice_routes_and_the_text_service_name_the_recorder() -> None:
    assert _outside(_sources(), _RECORDER_HOMES, _RECORDER_NAMES) == []


@pytest.mark.unit
def test_the_conversation_guards_detect_a_violation() -> None:
    sources = {
        "memory/leak.py": 'SQL = "SELECT turns FROM conversation_records"\n',
        "memory/conversation_record.py": 'SQL = "SELECT 1 FROM conversation_records"\n',
        "routers/chat.py": (
            "from server.memory.conversation_record import read_record\nrecord_turn = None\n"
        ),
        "characters/__init__.py": "import server.memory.conversation_summary\n",
    }

    assert _conversation_table_queriers(sources) == ["memory/leak.py"]
    assert _record_readers(sources) == ["characters/__init__.py", "routers/chat.py"]
    assert _outside(sources, _RECORDER_HOMES, _RECORDER_NAMES) == ["routers/chat.py"]


# --- recall (Plan 0078) -----------------------------------------------------------------------

# The modules that read the recall units or word them; no prompt module may import one, so the
# generic prompt still reads no household store and a recall answer is a controller branch.
_RECALL_READER_MODULES = frozenset(
    {
        "server.memory.recall_store",
        "server.memory.recall_search",
        "server.memory.recall_access",
        "server.memory.recall_answer",
        "server.memory.recall_index",
    }
)
_RECALL_MODULES = tuple(f"memory/{name.rsplit('.', 1)[1]}.py" for name in _RECALL_READER_MODULES)
_RECALL_TABLE_SQL = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+recall_units(?:_fts|_vec)?\b"
)
_RECALL_TABLE_HOME = "memory/recall_store.py"

# The modules that decide, word or read a sensitive question or a spoken secret (Plan 0079); no
# prompt module may import one, so the model never receives a stored sensitive value.
_SENSITIVE_READER_MODULES = frozenset(
    {
        "server.cognition.sensitive_questions",
        "server.cognition.sensitive_answers",
        "server.memory.sensitive_access",
        "server.memory.sensitive_store",
        "server.secret_values",
        # Plan 0082: the contacts and the rest of the alta, read and said the same way.
        "server.cognition.contact_answers",
        "server.cognition.contact_questions",
        "server.memory.contact_access",
        "server.memory.alta_reach",
    }
)


def _recall_prompt_readers(sources: Mapping[str, str]) -> list[str]:
    """Prompt-path modules that import a recall module."""
    return sorted(
        name
        for name, text in sources.items()
        if name.startswith(_NO_HOUSEHOLD_READS)
        and any(
            (isinstance(node, ast.ImportFrom) and node.module in _RECALL_READER_MODULES)
            or (
                isinstance(node, ast.Import)
                and any(alias.name in _RECALL_READER_MODULES for alias in node.names)
            )
            for node in ast.walk(ast.parse(text))
        )
    )


def _recall_table_queriers(sources: Mapping[str, str]) -> list[str]:
    """Modules other than the recall store that put SQL on a recall table."""
    return sorted(
        name
        for name, text in sources.items()
        if name != _RECALL_TABLE_HOME and _RECALL_TABLE_SQL.search(text)
    )


def _recall_record_readers(sources: Mapping[str, str]) -> list[str]:
    """Recall modules that import the record, the diary or the summary (they read units)."""
    return sorted(
        name
        for name, text in sources.items()
        if name in _RECALL_MODULES
        and any(
            isinstance(node, ast.ImportFrom) and node.module in _RECORD_READER_MODULES
            for node in ast.walk(ast.parse(text))
        )
    )


def _prompt_path_importers(
    sources: Mapping[str, str],
    modules: frozenset[str],
    prefixes: tuple[str, ...] = _NO_HOUSEHOLD_READS,
) -> list[str]:
    """Prompt-path modules that import any of `modules`, as `import a.b`, `from a.b import x`
    or `from a import b`.

    A module is on the prompt path when its path starts with one of `prefixes` (by default
    `_NO_HOUSEHOLD_READS`); the `llm` entry is a prefix, so it covers every future `llm*` module
    without editing the list.
    """
    return sorted(
        name
        for name, text in sources.items()
        if name.startswith(prefixes)
        and any(
            (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and (
                    node.module in modules
                    or any(f"{node.module}.{alias.name}" in modules for alias in node.names)
                )
            )
            or (isinstance(node, ast.Import) and any(alias.name in modules for alias in node.names))
            for node in ast.walk(ast.parse(text))
        )
    )


@pytest.mark.unit
def test_the_generic_prompt_still_reads_no_household_store() -> None:
    """ADR 0028 decision 8 and ADR 0029: the recall and the sensitive answers are controller
    branches, never in the prompt.
    """
    sources = _sources()

    assert _household_readers(sources) == []
    assert _recall_prompt_readers(sources) == []
    assert _prompt_path_importers(sources, _SENSITIVE_READER_MODULES) == []


@pytest.mark.unit
def test_only_recall_store_touches_the_recall_tables() -> None:
    assert _recall_table_queriers(_sources()) == []


@pytest.mark.unit
def test_the_record_is_still_read_by_no_route() -> None:
    """The 0076 guard keeps passing, and recall reads units, not records."""
    sources = _sources()

    assert _record_readers(sources) == []
    assert _recall_record_readers(sources) == []


@pytest.mark.unit
def test_the_recall_guards_detect_a_violation() -> None:
    sources = {
        "text_turn.py": "from server.memory.recall_search import search_recall\n",
        "llm_streaming.py": "import server.memory.recall_store\n",
        "routers/transcribe.py": "from server.memory.recall_access import recall_reply\n",
        "memory/leak.py": 'SQL = "SELECT body FROM recall_units WHERE 1"\n',
        "memory/recall_store.py": 'SQL = "SELECT body FROM recall_units_fts"\n',
        "memory/recall_search.py": "from server.memory.conversation_record import read_record\n",
    }

    assert _recall_prompt_readers(sources) == ["llm_streaming.py", "text_turn.py"]
    assert _recall_table_queriers(sources) == ["memory/leak.py"]
    assert _recall_record_readers(sources) == ["memory/recall_search.py"]


# --- the sensitive read and the secret rule (Plan 0079, ADR 0029) -----------------------------


@pytest.mark.unit
def test_the_sensitive_prompt_guard_detects_a_violation() -> None:
    sources = {
        "text_turn.py": "from server.cognition.sensitive_questions import match_sensitive\n",
        "llm_streaming.py": "import server.secret_values\n",
        "streaming.py": "from server.cognition import sensitive_answers\n",
        "characters/__init__.py": "from server.memory.sensitive_access import SensitiveReader\n",
        "llm.py": "from server.memory.sensitive_store import read_owner_literals\n",
        # Not a prompt-path module: the controller and the routes are the readers.
        "cognition/controller.py": "from server.cognition.sensitive_answers import spanish_join\n",
        "routers/transcribe.py": "from server.memory.sensitive_access import SensitiveReader\n",
        # A prompt-path module importing something else is spared.
        "llm_other.py": "from server.cognition.sensitive_other import x\nimport server.config\n",
    }

    assert _prompt_path_importers(sources, _SENSITIVE_READER_MODULES) == [
        "characters/__init__.py",
        "llm.py",
        "llm_streaming.py",
        "streaming.py",
        "text_turn.py",
    ]


# The secret words are decided once, in `server/secret_values.py` (D-2): the recall classifier and
# the sensitive grammar import them. A second spelling would drift, and a drift here is a spoken
# secret reaching the model or the disk.
_WORDS_HOME = "secret_values.py"
_D2_SECRET_WORDS = frozenset(
    {"clave", "claves", "contrasena", "contrasenas", "codigo", "codigos", "pin"}
)
# A literal with at least this many of the seven words outside the home is a copy of them.
_SECRET_WORDS_COPY_THRESHOLD = 4
# `memory/lexicon.py` is the one exempt module: its `SENSITIVE_WORDS` is a broad vocabulary of
# place, health, money, credential and life-event words (a taste is never stored with them) that
# happens to hold four of the seven («clave», «contrasena», «pin», «codigo»); it is a different
# list for a different purpose, not a second spelling of the secret words.
_WORDS_EXEMPT = frozenset({"memory/lexicon.py"})


def _string_elements(node: ast.AST) -> set[str]:
    """The string constants directly listed in a set, list or tuple display."""
    if not isinstance(node, ast.Set | ast.List | ast.Tuple):
        return set()
    return {
        element.value
        for element in node.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }


def _secret_word_set_builders(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the home, with a literal holding several of the D-2 secret words.

    Any set, list or tuple display counts, wrapped in `set(...)`/`frozenset(...)` or not (the
    wrapped display is a node of its own), and so does a copy of only some of the words: four of
    the seven is a copy that drifted, not a coincidence.
    """
    found = []
    for name, text in sources.items():
        if name == _WORDS_HOME or name in _WORDS_EXEMPT:
            continue
        if any(
            len(_string_elements(node) & _D2_SECRET_WORDS) >= _SECRET_WORDS_COPY_THRESHOLD
            for node in ast.walk(ast.parse(text))
        ):
            found.append(name)
    return found


def _imports_from_module(sources: Mapping[str, str], module: str, name: str) -> list[str]:
    """Modules that run `from <module> import <name>`."""
    return [
        source
        for source, text in sources.items()
        if any(
            isinstance(node, ast.ImportFrom)
            and node.module == module
            and any(alias.name == name for alias in node.names)
            for node in ast.walk(ast.parse(text))
        )
    ]


@pytest.mark.unit
def test_the_secret_words_are_defined_once() -> None:
    """Only `secret_values.py` spells the D-2 set; the recall classifier imports it."""
    sources = _sources()

    assert SECRET_WORDS == _D2_SECRET_WORDS
    assert _secret_word_set_builders(sources) == []
    assert "memory/recall_sensitivity.py" in _imports_from_module(
        sources, "server.secret_values", "SECRET_WORDS"
    )


@pytest.mark.unit
def test_the_secret_words_guard_detects_a_violation() -> None:
    words = '"clave", "claves", "contrasena", "contrasenas", "codigo", "codigos", "pin"'
    leak = {
        "memory/set_copy.py": "W = {" + words + "}\n",
        "memory/frozen_copy.py": "W = frozenset({" + words + ', "alarma"})\n',
        "memory/list_copy.py": "W = frozenset([" + words + "])\n",
        # A bare tuple or list, and a split copy of four of the words, are copies too.
        "memory/tuple_copy.py": "W = (" + words + ")\n",
        "memory/split_copy.py": 'W = {"clave", "claves", "contrasena", "contrasenas"}\n',
        "memory/mixed_copy.py": 'W = ["pin", "codigo", "codigos", "clave", "alarma"]\n',
        # The home spells them, by definition.
        "secret_values.py": "SECRET_WORDS = frozenset({" + words + "})\n",
        # A derived set, a partial set and a prose mention are spared.
        "memory/derived.py": 'W = SECRET_WORDS | {"alarma", "llave"}\n',
        "memory/partial.py": 'W = {"clave", "pin", "codigo"}\n',
        "memory/prose.py": f'"""The words {words} are in prose."""\n',
    }

    assert _secret_word_set_builders(leak) == [
        "memory/set_copy.py",
        "memory/frozen_copy.py",
        "memory/list_copy.py",
        "memory/tuple_copy.py",
        "memory/split_copy.py",
        "memory/mixed_copy.py",
    ]
    assert _imports_from_module(
        {"memory/recall_sensitivity.py": "from server.secret_values import SECRET_WORDS\n"},
        "server.secret_values",
        "SECRET_WORDS",
    ) == ["memory/recall_sensitivity.py"]
    assert (
        _imports_from_module(
            {"memory/recall_sensitivity.py": 'SECRET_WORDS = frozenset({"clave"})\n'},
            "server.secret_values",
            "SECRET_WORDS",
        )
        == []
    )


# The owner's sensitive read keeps only the rows stored with the labels of its topic, so it may
# read the pool of active literals; so do the writers that compare or make a repeat idempotent and
# the policy gate. Any other caller reads the pool without those labels: a decision, not an
# accident (Plan 0079). `_MAY_IMPORT_RAW_V4_READERS` covers all the raw readers; this is the
# narrower list for `get_active_literal_facts` alone.
_LITERAL_POOL_READER = "get_active_literal_facts"
_LITERAL_POOL_DEFINER = "memory/relational_v4.py"
_LITERAL_POOL_CALLERS = frozenset(
    {
        "memory/canonical_writer.py",
        "memory/memory_writer.py",
        "memory/policy_gated_v4_reader.py",
        "memory/sensitive_store.py",
    }
)


def _literal_pool_users(sources: Mapping[str, str]) -> set[str]:
    """Modules, besides the definer, that import or name `get_active_literal_facts`."""
    names = frozenset({_LITERAL_POOL_READER})
    return (
        set(_outside(sources, frozenset(), names))
        | set(_imports_name(sources, _LITERAL_POOL_READER))
    ) - {_LITERAL_POOL_DEFINER}


@pytest.mark.unit
def test_the_pool_literals_are_read_only_where_allowed() -> None:
    """The pool of active literals is read by exactly the four allowed modules."""
    assert _literal_pool_users(_sources()) == _LITERAL_POOL_CALLERS


@pytest.mark.unit
def test_the_pool_literals_guard_detects_a_violation() -> None:
    leak = {
        "routers/leak.py": "facts = await get_active_literal_facts(subject_entity_id=1)\n",
        "cognition/import_only.py": "from server.memory.relational_v4 import get_active_literal_facts\n",
        "memory/attr.py": "facts = await repo.get_active_literal_facts(definition=d)\n",
        "memory/sensitive_store.py": "facts = await get_active_literal_facts(definition=d)\n",
        "memory/relational_v4.py": "async def get_active_literal_facts(): ...\nx = get_active_literal_facts\n",
        "memory/other_reader.py": "rows = await get_literal_fact(fact_id=1)\n",
        "memory/prose.py": '"""get_active_literal_facts is only named in prose here."""\n',
    }

    users = _literal_pool_users(leak)

    assert users - _LITERAL_POOL_CALLERS == {
        "routers/leak.py",
        "cognition/import_only.py",
        "memory/attr.py",
    }
    assert "memory/sensitive_store.py" in users
    assert "memory/relational_v4.py" not in users
    assert "memory/other_reader.py" not in users


# --- the MVP recall phrasings (Plan 0080) -----------------------------------------------------

# The words that name a mother, a father, a daughter or a son are decided once, in
# `cognition/recall_cues.py` (`_RELATION_WORDS`, `_CHILD_WORDS`, `RELATIVE_WORDS`): the classifier,
# the sensitive grammar and the relatives route import them through `RELATIVE_WORDS` and
# `relation_of`. A second spelling would drift, and a drift here is a question that reaches the
# model or the wrong side of the family.
_RELATIVE_WORDS_HOME = "cognition/recall_cues.py"
_RELATIVE_SINGULAR_WORDS = frozenset({"mama", "papa", "madre", "padre", "hija", "hijo"})
# A literal with at least this many of the six words outside the home is a copy of them.
_RELATIVE_COPY_THRESHOLD = 2
# Three existing lists of a different purpose that happen to hold several of the six words; they
# are not a second spelling of the recall words and are allowed on purpose:
# - `cognition/household_request.py`: `CHILD_WORDS` and the household vocabulary that decides
#   whether a message is a household request at all (relatives, partners, pets, kin).
# - `memory/lexicon.py`: `PERSON_WORDS` (a taste never names a person) and the predicate triggers.
# - `memory/normalize.py`: the aliases of the legacy extractor's predicate drift ("hijo", "hija").
_RELATIVE_WORDS_EXEMPT = frozenset(
    {"cognition/household_request.py", "memory/lexicon.py", "memory/normalize.py"}
)


def _folded(text: str) -> str:
    """Lowercase *text* and strip its accents, as the spoken-text folding of the grammars does."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _folded_words(node: ast.AST) -> set[str]:
    """The folded string constants listed in a set, list or tuple display or as dict keys."""
    if isinstance(node, ast.Dict):
        elements: list[ast.expr | None] = list(node.keys)
    elif isinstance(node, ast.Set | ast.List | ast.Tuple):
        elements = list(node.elts)
    else:
        return set()
    return {
        _folded(element.value)
        for element in elements
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }


def _spells_relative_words(text: str) -> bool:
    """Whether *text* has a literal holding several of the relative words."""
    return any(
        len(_folded_words(node) & _RELATIVE_SINGULAR_WORDS) >= _RELATIVE_COPY_THRESHOLD
        for node in ast.walk(ast.parse(text))
    )


def _relative_word_set_builders(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the home and the exempt lists, spelling several relative words.

    A set, list or tuple display (wrapped in `set(...)`/`frozenset(...)`/`dict.fromkeys(...)` or
    not) and a dict display both count, and so does a copy of only two of the words with an
    accent or not: «mamá» and «papá» are a copy that drifted, not a coincidence.
    """
    return [
        name
        for name, text in sources.items()
        if name != _RELATIVE_WORDS_HOME
        and name not in _RELATIVE_WORDS_EXEMPT
        and _spells_relative_words(text)
    ]


@pytest.mark.unit
def test_the_relative_words_are_defined_once() -> None:
    """Only `recall_cues` spells the mother/father/parent/child words; the rest import them."""
    sources = _sources()

    assert _relative_word_set_builders(sources) == []
    # The home does spell them, and the grammars of Plans 0079 and 0080 import them from it.
    assert _spells_relative_words(sources[_RELATIVE_WORDS_HOME])
    assert "memory/sensitive_access.py" in _imports_from_module(
        sources, "server.cognition.recall_cues", "RELATIVE_WORDS"
    )
    assert "cognition/intent_resolution.py" in _imports_from_module(
        sources, "server.cognition.recall_cues", "relation_of"
    )


@pytest.mark.unit
def test_the_relative_words_guard_detects_a_violation() -> None:
    leak = {
        "memory/set_copy.py": 'W = {"mama", "papa", "perro"}\n',
        "memory/frozen_copy.py": 'W = frozenset({"madre", "padre"})\n',
        "memory/dict_copy.py": 'W = {"hija": "daughter_of", "hijo": "son_of"}\n',
        "memory/fromkeys_copy.py": 'W = dict.fromkeys(("mama", "madre"), "has_mother")\n',
        # A copy with accents, as it would be written in a spoken template, is a copy too.
        "memory/accent_copy.py": 'W = ["Mamá", "Papá"]\n',
        # The home spells them, by definition; the exempt lists are other vocabularies.
        "cognition/recall_cues.py": 'W = {"mama", "papa", "madre", "padre"}\n',
        "memory/lexicon.py": 'W = {"mama", "papa", "madre", "padre"}\n',
        # One word, a derived set, a spread of the shared set and prose are spared.
        "memory/single.py": 'W = {"mama", "perro", "gato"}\n',
        "memory/derived.py": 'W = RELATIVE_WORDS | {"tio"}\n',
        "memory/spread.py": 'W = frozenset({*RELATIVE_WORDS, "tio"})\n',
        "memory/prose.py": '"""The words "mama", "papa" and "madre" are in prose."""\n',
    }

    assert _relative_word_set_builders(leak) == [
        "memory/set_copy.py",
        "memory/frozen_copy.py",
        "memory/dict_copy.py",
        "memory/fromkeys_copy.py",
        "memory/accent_copy.py",
    ]


# The spoken sentences of the relatives answers (ADR 0028 decision 9, Plan 0080 D-5) are fixed
# templates in one module: the controller words nothing about the mother, the father or a child.
_TEMPLATES_HOME = "cognition/relatives_answers.py"
_TEMPLATE_TABLE_NAMES = frozenset({"_RELATIVES_TEMPLATES", "_SIDED_TEMPLATES"})
# «Tu mamá se llama {}.», «Tus papás se llaman {}.», «Tu papá o tu mamá se llama {}.»: a spoken
# string that opens with «Tu(s)» and says «se llama(n)» before any placeholder, and the whole
# list of children «Tus hijos son {}.» (Plan 0080 fix round 1). The «cómo se llama» patterns and
# the prose of a docstring do not open that way.
_RELATIVES_SENTENCE = re.compile(r"^(?:Tus? [^{}]*\bse llam(?:a|an)\b|Tus hijos son\b)")


def _defines_relatives_templates(text: str) -> bool:
    """Whether *text* assigns a relatives template table or holds one of its sentences."""
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in _TEMPLATE_TABLE_NAMES
            for target in node.targets
        ):
            return True
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in _TEMPLATE_TABLE_NAMES
        ):
            return True
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _RELATIVES_SENTENCE.match(node.value)
        ):
            return True
    return False


def _relatives_template_definers(sources: Mapping[str, str]) -> list[str]:
    """Modules, besides the answers module, that define a relatives template or its sentence."""
    return [
        name
        for name, text in sources.items()
        if name != _TEMPLATES_HOME and _defines_relatives_templates(text)
    ]


@pytest.mark.unit
def test_the_relatives_templates_live_in_one_module() -> None:
    """`relatives_answers.py` owns the spoken sentences; the controller defines none."""
    sources = _sources()

    assert _defines_relatives_templates(sources[_TEMPLATES_HOME])
    assert _relatives_template_definers(sources) == []


@pytest.mark.unit
def test_the_relatives_templates_guard_detects_a_violation() -> None:
    leak = {
        "cognition/controller.py": (
            '_RELATIVES_TEMPLATES = {"has_parent": ("Tu papá o tu mamá se llama {}.", "x")}\n'
        ),
        "cognition/sided_copy.py": "_SIDED_TEMPLATES: dict[str, str] = {}\n",
        "cognition/sentence_copy.py": 'reply = "Tu mamá se llama {}.".format(name)\n',
        "cognition/fstring_copy.py": 'reply = f"Tus papás se llaman {names}."\n',
        "cognition/children_copy.py": 'reply = f"Tus hijos son {names}."\n',
        # The home defines them, by definition.
        "cognition/relatives_answers.py": (
            '_SIDED_TEMPLATES = {"a": ("Tu mamá se llama {}.", "b")}\n'
        ),
        # A pattern, a docstring and another sentence of the controller are spared.
        "cognition/patterns.py": 'P = ("como se llama mi hija", "Tu mamá es buena")\n',
        "cognition/prose.py": '"""Says «Tu mamá se llama» only in prose, after the opening."""\n',
        "cognition/other.py": 'reply = f"Tienes {count} hijos."\n',
    }

    assert _relatives_template_definers(leak) == [
        "cognition/controller.py",
        "cognition/sided_copy.py",
        "cognition/sentence_copy.py",
        "cognition/fstring_copy.py",
        "cognition/children_copy.py",
    ]


# The recall units are read through one filtered statement (ADR 0031 decision 2, Plan 0080 D-10):
# `units_by_id` re-checks owner, visibility, sensitivity and expiry at delivery time. Only the
# search that fused the ids may call it, and its signature keeps the two filters keyword-only so a
# later refactor cannot drop them without a test saying so.
_UNITS_READER = "units_by_id"
_UNITS_READER_HOME = "memory/recall_store.py"
_MAY_READ_UNITS = frozenset({"memory/recall_search.py"})
_UNITS_DELIVERY_FILTERS = frozenset({"owner_entity_id", "now"})


def _units_readers(sources: Mapping[str, str]) -> set[str]:
    """Modules, besides the store, that call, import or name `units_by_id`."""
    return (
        set(_outside(sources, frozenset(), frozenset({_UNITS_READER})))
        | set(_calls(sources, _UNITS_READER))
        | set(_imports_name(sources, _UNITS_READER))
    ) - {_UNITS_READER_HOME}


def _not_keyword_only(function: Callable[..., object], names: frozenset[str]) -> list[str]:
    """The names in *names* that *function* does not take as a keyword-only parameter."""
    parameters = inspect.signature(function).parameters
    return sorted(
        name
        for name in names
        if name not in parameters or parameters[name].kind is not inspect.Parameter.KEYWORD_ONLY
    )


@pytest.mark.unit
def test_recall_units_are_read_only_through_the_filtered_store() -> None:
    """Only `recall_search` reads units by id; only `recall_store` defines the reader."""
    sources = _sources()

    assert _units_readers(sources) == _MAY_READ_UNITS
    assert _definers(sources, frozenset({_UNITS_READER})) == [_UNITS_READER_HOME]
    assert _not_keyword_only(recall_store.units_by_id, _UNITS_DELIVERY_FILTERS) == []


@pytest.mark.unit
def test_the_recall_units_guard_detects_a_violation() -> None:
    leak = {
        "memory/recall_search.py": "units = await units_by_id(ids, owner_entity_id=1, now=n)\n",
        "memory/recall_store.py": "async def units_by_id(ids, *, owner_entity_id, now): ...\n",
        "memory/attr_call.py": "units = await recall_store.units_by_id(ids)\n",
        "routers/import_only.py": "from server.memory.recall_store import units_by_id\n",
        "cognition/alias.py": "reader = recall_store.units_by_id\n",
        "memory/redefined.py": "async def units_by_id(ids): ...\n",
        "memory/prose.py": '"""units_by_id is only named in prose here."""\n',
    }

    assert _units_readers(leak) == {
        "memory/recall_search.py",
        "memory/attr_call.py",
        "routers/import_only.py",
        "cognition/alias.py",
    }
    # A second definition is not a reader; the definers check is what catches it.
    assert _definers(leak, frozenset({_UNITS_READER})) == [
        "memory/recall_store.py",
        "memory/redefined.py",
    ]


@pytest.mark.unit
def test_the_delivery_filters_guard_detects_a_dropped_filter() -> None:
    def positional(ids: list[int], owner_entity_id: int, now: str) -> None: ...

    def without_now(ids: list[int], *, owner_entity_id: int) -> None: ...

    def keyword_only(ids: list[int], *, owner_entity_id: int, now: str) -> None: ...

    assert _not_keyword_only(positional, _UNITS_DELIVERY_FILTERS) == ["now", "owner_entity_id"]
    assert _not_keyword_only(without_now, _UNITS_DELIVERY_FILTERS) == ["now"]
    assert _not_keyword_only(keyword_only, _UNITS_DELIVERY_FILTERS) == []


# --- Plan 0082: the alta read only reads (ADR 0037 decisions 1 and 5) ---------------------------

_ALTA_READ_MODULES = (
    "cognition/contact_answers.py",
    "cognition/contact_questions.py",
    "memory/contact_access.py",
    "memory/alta_reach.py",
)
_WRITER_MODULES = frozenset({"server.memory.canonical_writer", "server.memory.memory_writer"})
_WRITER_NAMES = frozenset({"write_contact", "revoke_contact", "delete_contacts_by_channel"})


def _writes_imported(text: str) -> list[str]:
    """The writer modules or writer functions one source imports."""
    found: list[str] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module in _WRITER_MODULES:
                found.append(node.module)
            found += [alias.name for alias in node.names if alias.name in _WRITER_NAMES]
        elif isinstance(node, ast.Import):
            found += [alias.name for alias in node.names if alias.name in _WRITER_MODULES]
    return found


@pytest.mark.unit
def test_the_alta_read_writes_nothing() -> None:
    sources = _sources()
    offenders = {name: _writes_imported(sources[name]) for name in _ALTA_READ_MODULES}
    assert {name: found for name, found in offenders.items() if found} == {}


@pytest.mark.unit
def test_the_alta_write_guard_detects_a_violation() -> None:
    assert _writes_imported("from server.memory.care_contacts import write_contact\n") == [
        "write_contact"
    ]
    assert _writes_imported("import server.memory.canonical_writer\n") == [
        "server.memory.canonical_writer"
    ]
    assert _writes_imported("from server.memory.care_contacts import list_active_contacts\n") == []


# Plan 0083: one reader of spoken time (ADR 0037 decision 4), a pure occurred time, and the
# occurred columns touched only by the recall store.
_SPOKEN_TIME_HOME = "cognition/spoken_dates.py"
_TIME_WORDS = re.compile(
    r"\b(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo|enero|febrero|marzo|abril|mayo"
    r"|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|pasado manana)\b"
)
_PURE_TIME_MODULES = frozenset(
    # Plan 0084: the announcement grammar and the follow-up sentence are pure too.
    {"cognition/spoken_dates.py", "cognition/occurred_time.py", "cognition/pending_topics.py"}
)
_IMPURE_PREFIXES = ("server.settings", "server.db", "server.memory", "aiosqlite", "httpx")
_OCCURRED_COLUMNS = re.compile(r"\boccurred_(?:start|end)\b")
_OCCURRED_COLUMN_HOME = "memory/recall_store.py"


def _compiled_patterns(text: str) -> list[str]:
    """The string literals inside every ``re.compile(...)`` call of a module."""
    literals: list[str] = []
    for node in ast.walk(ast.parse(text)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re"
        ):
            literals.extend(
                part.value
                for part in ast.walk(node)
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
    return literals


def _date_parsers(sources: Mapping[str, str]) -> list[str]:
    return sorted(
        name
        for name, text in sources.items()
        if name != _SPOKEN_TIME_HOME
        and any(_TIME_WORDS.search(literal) for literal in _compiled_patterns(text))
    )


def _impure_time_modules(sources: Mapping[str, str]) -> list[str]:
    found: list[str] = []
    for name in sorted(_PURE_TIME_MODULES & sources.keys()):
        for node in ast.walk(ast.parse(sources[name])):
            # ``from server import db`` names its module through the alias: check both.
            modules = (
                [node.module or "", *(f"{node.module}.{alias.name}" for alias in node.names)]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            if any(module.startswith(_IMPURE_PREFIXES) for module in modules):
                found.append(name)
                break
    return found


_MONTH_NAMES = frozenset(
    {"enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre"}
    | {"octubre", "noviembre", "diciembre"}
)
_MONTH_LIST_LIMIT = 6
_MONTH_LIST_HOMES = frozenset(
    {"cognition/spoken_dates.py", "characters/__init__.py", "memory/normalize.py"}
)


def _month_list_holders(sources: Mapping[str, str]) -> list[str]:
    """Modules outside the homes whose string literals name six or more months."""
    found: list[str] = []
    for name, text in sorted(sources.items()):
        words = {
            word
            for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            for word in re.findall(r"[a-z]+", node.value)
        }
        if name not in _MONTH_LIST_HOMES and len(words & _MONTH_NAMES) >= _MONTH_LIST_LIMIT:
            found.append(name)
    return found


def _occurred_column_users(sources: Mapping[str, str]) -> list[str]:
    return sorted(
        name
        for name, text in sources.items()
        if name != _OCCURRED_COLUMN_HOME and _OCCURRED_COLUMNS.search(text)
    )


@pytest.mark.unit
def test_one_reader_of_spoken_time() -> None:
    assert _date_parsers(_sources()) == []


@pytest.mark.unit
def test_occurred_time_is_pure() -> None:
    assert _impure_time_modules(_sources()) == []


@pytest.mark.unit
def test_only_the_store_touches_the_occurred_columns() -> None:
    assert _occurred_column_users(_sources()) == []


@pytest.mark.unit
def test_the_spoken_time_guards_detect_a_violation() -> None:
    leak = {
        # ``from server import db`` is the repository's own idiom: it must be caught too.
        "cognition/spoken_dates.py": 'from server import db\nP = re.compile(r"el sabado")\n',
        "cognition/second_parser.py": 'P = re.compile(r"(?:enero|marzo) de [0-9]{4}")\n',
        "cognition/tomorrow.py": 'P = re.compile("pasado manana")\n',
        "cognition/formatting.py": 'DAYS = ("lunes", "martes")\n',
        "cognition/occurred_time.py": "from server.settings import settings\n",
        "memory/peek.py": 'SQL = "SELECT occurred_start FROM recall_units"\n',
        "memory/months.py": 'M = "enero|febrero|marzo|abril|mayo|junio"\n',
    }

    assert _date_parsers(leak) == ["cognition/second_parser.py", "cognition/tomorrow.py"]
    assert _impure_time_modules(leak) == ["cognition/occurred_time.py", "cognition/spoken_dates.py"]
    assert _occurred_column_users(leak) == ["memory/peek.py"]
    assert _month_list_holders(leak) == ["memory/months.py"]


@pytest.mark.unit
def test_month_word_lists_live_only_where_they_are_needed() -> None:
    """A list of months is a date reader in waiting: only the reader and two formatters hold one.

    ``characters`` formats today's date for the prompt and ``memory/normalize.py`` refuses a date
    as an entity name (both older than Plan 0083); any other module reads spoken time through
    ``spoken_dates``. A pattern built from an f-string escapes ``test_one_reader_of_spoken_time``,
    so this guard watches the word lists themselves.
    """
    assert _month_list_holders(_sources()) == []


# --- pending topics (Plan 0084) ------------------------------------------------------------------

# The modules that keep, name, read or pick up a pending topic. The prompt builders import none, so
# the generic prompt reads no topic (Plan 0077 guard); the text turn and the stream may import only
# the follow-up seam and the switch, never a read of the store.
_PENDING_MODULES = frozenset(
    {
        "server.memory.pending_store",
        "server.memory.pending_follow_up",
        "server.memory.pending_naming",
        "server.memory.pending_capture",
    }
)
_PROMPT_BUILDERS = ("characters/", "llm")
_PENDING_SEAM_USERS = ("streaming", "text_turn.py")
# The names of the follow-up seam the text turn and the stream may import: a type, the commit and
# the note that an offer won; never a store read, a log helper or an outcome (Task 8 review).
_PENDING_SEAM_NAMES = frozenset(
    {"FollowUpPreparer", "PendingFollowUp", "commit_follow_up", "yield_to_offer"}
)
_PENDING_STORE_SWITCH = frozenset({"pending_topics_on"})
_PENDING_TABLE_SQL = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+pending_topics\b")
_PENDING_TABLE_HOME = "memory/pending_store.py"


def _pending_table_queriers(sources: Mapping[str, str]) -> list[str]:
    """Modules other than the pending store that put SQL on ``pending_topics``."""
    return sorted(
        name
        for name, text in sources.items()
        if name != _PENDING_TABLE_HOME and _PENDING_TABLE_SQL.search(text)
    )


def _pending_seam_overreach(sources: Mapping[str, str]) -> list[str]:
    """Text-turn and stream modules that import more of the pending topics than the seam."""
    found: list[str] = []
    for name, text in sorted(sources.items()):
        if not name.startswith(_PENDING_SEAM_USERS):
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import) and any(
                alias.name in _PENDING_MODULES for alias in node.names
            ):
                found.append(name)
                break
            if not isinstance(node, ast.ImportFrom) or node.module not in _PENDING_MODULES:
                continue
            names = {alias.name for alias in node.names}
            if node.module == "server.memory.pending_store" and names <= _PENDING_STORE_SWITCH:
                continue
            if node.module == "server.memory.pending_follow_up" and names <= _PENDING_SEAM_NAMES:
                continue
            found.append(name)
            break
    return found


@pytest.mark.unit
def test_only_the_store_touches_pending_topics() -> None:
    assert _pending_table_queriers(_sources()) == []


@pytest.mark.unit
def test_the_generic_prompt_reads_no_pending_topic() -> None:
    sources = _sources()

    assert _prompt_path_importers(sources, _PENDING_MODULES, _PROMPT_BUILDERS) == []
    assert _pending_seam_overreach(sources) == []


@pytest.mark.unit
def test_the_pending_topics_guards_detect_a_violation() -> None:
    leak = {
        "memory/peek.py": 'SQL = "SELECT topic FROM pending_topics WHERE 1"\n',
        "memory/pending_store.py": 'SQL = "DELETE FROM pending_topics"\n',
        "llm.py": "from server.memory.pending_store import due_topic\n",
        "characters/__init__.py": "import server.memory.pending_follow_up\n",
        "text_turn.py": "from server.memory.pending_store import due_topic, pending_topics_on\n",
        "streaming.py": "from server.memory.pending_follow_up import FollowUpPreparer\n",
        "streaming_render.py": "from server.memory.pending_store import pending_topics_on\n",
        "streaming_protocol.py": "from server.memory.pending_follow_up import log_follow_up\n",
        "cognition/pending_topics.py": "from server.memory.recall_search import household_zone\n",
    }

    assert _pending_table_queriers(leak) == ["memory/peek.py"]
    assert _prompt_path_importers(leak, _PENDING_MODULES, _PROMPT_BUILDERS) == [
        "characters/__init__.py",
        "llm.py",
    ]
    assert _pending_seam_overreach(leak) == ["streaming_protocol.py", "text_turn.py"]
    assert _impure_time_modules(leak) == ["cognition/pending_topics.py"]
