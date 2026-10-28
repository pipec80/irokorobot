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
        "list_card_literals",
    }
)
# The policy gate, the local setup that re-reads what it just wrote, the candidate writer, which
# compares the active rows' folded keys inside its own transaction (Plan 0062), and the
# canonical writer, which reads the owner's relations to classify a subject and the active rows
# to make a repeat idempotent (Plan 0065).
_MAY_IMPORT_RAW_V4_READERS = frozenset(
    {
        "memory/policy_gated_v4_reader.py",
        "personal_setup.py",
        "memory/memory_writer.py",
        "memory/canonical_writer.py",
        "memory/profile_card_access.py",
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
# (Plan 0062) and the one that asks it about the profile card (Plan 0074): every other module
# reaches the actions through them.
_ACTION_HOMES = frozenset(
    {
        "cognition/models.py",
        "cognition/authorization.py",
        "memory/candidate_policy.py",
        "memory/profile_card_access.py",
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
    }

    assert _outside(leak, _DIALOGUE_HOMES, _DIALOGUE_NAMES) == [
        "memory/profile_card_access.py",
        "routers/chat.py",
        "routers/chat_card.py",
        "routers/typed.py",
        "routers/vision.py",
        "routers/vision_card.py",
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
