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
# The policy gate, and the local setup that re-reads what it just wrote.
_MAY_IMPORT_RAW_V4_READERS = frozenset({"memory/policy_gated_v4_reader.py", "personal_setup.py"})
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
# CM-3 decides what happens to these four; until then only the model and the policy know them.
_LEGACY_MEMORY_ACTION_NAMES = frozenset(
    {
        "PROPOSE_MEMORY",
        "COMMIT_MEMORY",
        "DELETE_HOUSEHOLD_DATA",
        "EXPORT_HOUSEHOLD_DATA",
        "propose_memory",
        "commit_memory",
        "delete_household_data",
        "export_household_data",
    }
)
_ACTION_HOMES = frozenset({"cognition/models.py", "cognition/authorization.py"})
_MEMORY_SCOPE_MEMBER_NAMES = frozenset({"PERSONAL_MEMORY_READ", "PERSONAL_MEMORY_FORGET"})
_MEMORY_SCOPE_VALUES = frozenset({"personal_memory_read", "personal_memory_forget"})
# Only the enum names its members. The policy table repeats the plain strings because
# importing the enum there would be an import cycle (a drift test pins them together).
_SCOPE_MEMBER_HOMES = frozenset({"cognition/owner_authentication.py"})
_SCOPE_VALUE_HOMES = frozenset({"cognition/owner_authentication.py", "cognition/authorization.py"})
# `manual` evidence counts as `basic`; these are the modules that reference it today (grep on
# 2026-10-08). A new one must be a decision, not an accident.
_MANUAL_HOMES = frozenset(
    {
        "characters/__init__.py",
        "cognition/identity.py",
        "cognition/identity_sessions.py",
        "memory/consolidation.py",
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
    """Nobody else consumes `propose_memory`, `commit_memory`, delete or export (verified)."""
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
            "b = AuthorizationAction.COMMIT_MEMORY\n"
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
