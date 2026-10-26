"""The seed file read from disk, and its committed JSON Schema (Plan 0071 Task 2).

Every name and value is an invented canary.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from server.exceptions import SeedFileError
from server.memory.seed_file import MAX_SEED_BYTES, SeedFile, load_seed_file

from tests.unit.seed_data import full_seed, to_toml

pytestmark = pytest.mark.integration

_SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "examples" / "seed-household.schema.json"


def _problems(path: Path) -> tuple[str, ...]:
    with pytest.raises(SeedFileError) as caught:
        load_seed_file(path)
    return caught.value.problems


def test_a_file_on_disk_loads_with_the_hash_of_its_bytes(tmp_path: Path) -> None:
    path = tmp_path / "seed.toml"
    raw = to_toml(full_seed()).encode("utf-8")
    path.write_bytes(raw)

    loaded = load_seed_file(path)

    assert loaded.seed.owner.name == "Canary Owner"
    assert loaded.sha256 == hashlib.sha256(raw).hexdigest()


def test_a_byte_order_mark_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "seed.toml"
    path.write_bytes(b"\xef\xbb\xbf" + to_toml(full_seed()).encode("utf-8"))

    assert load_seed_file(path).seed.owner.name == "Canary Owner"


def test_a_file_over_the_limit_is_refused_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "seed.toml"
    path.write_bytes(b"#" * (MAX_SEED_BYTES + 1))

    def never(_self: Path) -> bytes:
        raise AssertionError("the file was read")

    monkeypatch.setattr(Path, "read_bytes", never)

    assert _problems(path) == ("file: too_large",)


def test_invalid_utf8_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "seed.toml"
    path.write_bytes(b'schema_version = 1\nname = "\xff\xfe"\n')

    assert _problems(path) == ("file: invalid_utf8",)


def test_a_missing_path_is_refused(tmp_path: Path) -> None:
    assert _problems(tmp_path / "absent.toml") == ("file: not_found",)


def test_a_directory_is_refused(tmp_path: Path) -> None:
    assert _problems(tmp_path) == ("file: not_a_file",)


def test_the_committed_schema_is_the_models_schema() -> None:
    """Front ends validate against this file; it must change whenever the model does."""
    committed = json.loads(_SCHEMA.read_text(encoding="utf-8"))

    assert committed == SeedFile.model_json_schema()
