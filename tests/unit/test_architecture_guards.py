"""Static architecture guards (Plan 0050): the controls the audit found are permanent."""

import ast
from collections.abc import Mapping
from pathlib import Path
import re

import pytest

import server

_SERVER_ROOT = Path(server.__file__).resolve().parent

_RAW_V4_READERS = frozenset(
    {
        "get_active_literal_facts",
        "get_active_entity_relations",
        "get_literal_fact",
        "get_entity_relation",
    }
)
# The policy gate, the local setup that re-reads what it just wrote, and the one canonical
# writer, which compares the active rows' folded keys inside its own transaction (Plan 0062).
_MAY_IMPORT_RAW_V4_READERS = frozenset(
    {"memory/policy_gated_v4_reader.py", "personal_setup.py", "memory/memory_writer.py"}
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
# `PROPOSE_MEMORY` and `COMMIT_MEMORY` left in Plan 0062 (nothing consumed them); these two
# are CM-6's, so until then only the model and the policy know them.
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
# (Plan 0062): every other module reaches the actions through it.
_ACTION_HOMES = frozenset(
    {"cognition/models.py", "cognition/authorization.py", "memory/candidate_policy.py"}
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
        "text_turn.py",
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


@pytest.mark.unit
def test_the_retired_memory_actions_exist_nowhere() -> None:
    """ADR 0021 decision 11: no enum member, branch or string names them any more."""
    assert _outside(_sources(), frozenset(), _RETIRED_ACTION_NAMES) == []


# --- who may write or move a candidate (Plan 0062, ADR 0021 decisions 3 and 8) --------------
# The firewall rule (face and voice of the same person on the turn's clip) is enforced by the
# caller of the store, so the callers are pinned: a second caller must be a decision, not an
# accident. Plan 0063 adds the dialogue module that offers and answers.
_CANDIDATE_INSERT_HOMES = frozenset({"memory/candidates.py", "memory/candidate_proposal.py"})
_CANDIDATE_MOVE_HOMES = frozenset({"memory/candidates.py", "memory/memory_writer.py"})
_CANDIDATE_MOVES = frozenset(
    {"mark_offered", "resolve_candidate", "resolve_candidate_in_transaction"}
)
_WRITER_HOMES = frozenset({"memory/memory_writer.py"})


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
    }

    assert _outside(leak, _CANDIDATE_INSERT_HOMES, frozenset({"insert_candidate"})) == [
        "routers/leak.py"
    ]
    assert _outside(leak, _CANDIDATE_MOVE_HOMES, _CANDIDATE_MOVES) == ["routers/leak.py"]
    assert _outside(leak, _WRITER_HOMES, frozenset({"promote"})) == ["memory/other.py"]
