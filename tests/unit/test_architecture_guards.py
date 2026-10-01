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
