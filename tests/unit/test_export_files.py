"""The two files of an export and their folder (Plan 0087 Task 4, D-3 and D-4, Pipec 2026-11-19).

One model, two renderings: parsing the Markdown tables back gives exactly the JSON rows, whatever
a cell holds (a pipe, a line break, a backslash, Markdown). The folder is ``data/exports/<name>``
by default; ``--out`` may name a new or empty folder there or outside the repository, never the
repository, the data directory itself, a file or a folder with something in it. Canaries only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from server.cognition.authorization import DataSensitivity, DataVisibility
from server.cognition.identity import HouseholdRole
from server.cognition.models import AuthorizationAction
from server.exceptions import BrainMemoryError, ExportPlaceError
from server.memory import export_files
from server.memory.admin_audit import (
    AdminActorRole,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
)
from server.memory.candidate_types import CandidateChannel, CandidateStatus
from server.memory.care_contacts import ContactRole
from server.memory.commissioning import (
    ConfirmationMode,
    DiskEncryption,
    InterviewerRole,
    Section,
    SectionStatus,
)
from server.memory.conversation_record import EpisodeStatus
from server.memory.conversation_types import TurnVerdict
from server.memory.deletion_register import DeletionKind
from server.memory.export_files import (
    GLOSSARY,
    export_folder,
    folder_name,
    render_json,
    render_markdown,
    write_export,
)
from server.memory.export_model import (
    ExportColumn,
    ExportDocument,
    ExportScope,
    ExportScopeKind,
    ExportSection,
)
from server.memory.relational_v4 import AssertionLifecycle
from server.memory.write_types import WriteChannel

_NOW = "2026-11-19T12:00:00.000000+00:00"
_TRICKY = "una | barra\ndos líneas\r\ny una \\ invertida, **negrita** y <br> escrito"
_SALT = "CANARY-SALT-BYTES"


def _document(*rows: tuple[str | int | None, ...]) -> ExportDocument:
    turns = ExportSection(
        key="turnos",
        title="Turnos",
        columns=(
            ExportColumn("id", "Id"),
            ExportColumn("heard", "Lo que se oyó"),
            ExportColumn("verdict", "Quién habló"),
        ),
        rows=rows
        or ((1, _TRICKY, "verified"), (2, None, "not_owner"), (3, "  Ñandú cantó ", "verified")),
    )
    empty = ExportSection(
        key="borrados",
        title="Registro de borrados",
        columns=(ExportColumn("seq", "Número"),),
        rows=(),
    )
    return ExportDocument(
        scope=ExportScope(kind=ExportScopeKind.ALL),
        generated_at=_NOW,
        schema_version=22,
        sections=(turns, empty),
    )


def _cells(line: str) -> list[str]:
    """Split a Markdown table row on its unescaped pipes."""
    cells, current, escaped = [], "", False
    for char in line.strip()[1:-1]:
        if escaped:
            current += "\\" + char
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append(current)
            current = ""
        else:
            current += char
    cells.append(current)
    # The renderer pads each cell with exactly one space a side; a value's own spaces stay.
    return [cell[1:-1] for cell in cells]


def _unescape(cell: str) -> str | None:
    if cell == "—":
        return None
    out, index = "", 0
    while index < len(cell):
        if cell.startswith("<br>", index):
            out, index = out + "\n", index + 4
        elif cell[index] == "\\" and index + 1 < len(cell):
            out, index = out + cell[index + 1], index + 2
        else:
            out, index = out + cell[index], index + 1
    return out


def _markdown_tables(text: str) -> dict[str, list[list[str | None]]]:
    """Each ``## title`` section's table rows, unescaped (the header and the rule dropped)."""
    tables: dict[str, list[list[str | None]]] = {}
    title = None
    for line in text.splitlines():
        if line.startswith("## "):
            title = line[3:]
            tables[title] = []
        elif title is not None and line.startswith("|") and set(_cells(line)) != {"---"}:
            tables[title].append([_unescape(cell) for cell in _cells(line)])
    return {key: rows[1:] for key, rows in tables.items()}


def _as_text(value: object) -> str | None:
    return None if value is None else str(value).replace("\r\n", "\n").replace("\r", "\n")


@pytest.mark.unit
def test_the_markdown_tables_parse_back_to_the_json_rows() -> None:
    document = _document()
    parsed = json.loads(render_json(document))
    tables = _markdown_tables(render_markdown(document))
    for section in parsed["sections"]:
        expected = [
            [_as_text(row[key]) for key in [c["key"] for c in section["columns"]]]
            for row in section["rows"]
        ]
        assert tables[section["title"]] == expected


@pytest.mark.unit
def test_a_pipe_a_line_break_and_a_backslash_keep_the_table() -> None:
    markdown = render_markdown(_document())
    table = [line for line in markdown.splitlines() if line.startswith("| 1 ")]
    assert len(table) == 1
    assert len(_cells(table[0])) == 3


@pytest.mark.unit
def test_none_is_a_dash_and_an_empty_section_says_so() -> None:
    markdown = render_markdown(_document())
    assert "| 2 | — | not_owner |" in markdown
    assert "## Registro de borrados\n\nSin filas." in markdown
    assert "3 filas." in markdown


@pytest.mark.unit
def test_every_code_is_in_the_glossary() -> None:
    codes = {
        member.value
        for enum in (
            AssertionLifecycle,
            TurnVerdict,
            DeletionKind,
            CandidateStatus,
            SectionStatus,
            Section,
            ConfirmationMode,
            DiskEncryption,
            InterviewerRole,
            AdminOperationKind,
            TargetKind,
            AdminOutcomeStatus,
            AdminActorRole,
            ContactRole,
            HouseholdRole,
            EpisodeStatus,
            WriteChannel,
            CandidateChannel,
            AuthorizationAction,
            DataSensitivity,
            DataVisibility,
        )
        for member in enum
    } | {"scrypt"}
    assert codes - set(GLOSSARY) == set()
    assert "## Qué significa cada valor" in render_markdown(_document())


@pytest.mark.unit
def test_the_json_is_utf8_and_keeps_accents() -> None:
    text = render_json(_document())
    assert "Ñandú" in text
    assert "\\u00d1" not in text
    parsed = json.loads(text)
    assert parsed["format"] == "iroko-export"
    assert parsed["version"] == 1
    assert parsed["scope"] == {"kind": "all", "entity_id": None, "words": None}
    assert parsed["schema_version"] == 22
    assert parsed["sections"][0]["rows"][1] == {"id": 2, "heard": None, "verdict": "not_owner"}


@pytest.mark.unit
def test_the_folder_name_never_holds_a_name() -> None:
    assert folder_name(ExportScope(kind=ExportScopeKind.ALL), _NOW) == "20261119T120000Z-todo"
    person = ExportScope(kind=ExportScopeKind.PERSON, entity_id=7)
    assert folder_name(person, _NOW) == "20261119T120000Z-persona-7"
    only_a_name = ExportScope(kind=ExportScopeKind.PERSON, words="Canaria")
    assert folder_name(only_a_name, _NOW) == "20261119T120000Z-persona"


# --- the folder (D-3 as amended by Pipec, 2026-11-19) ------------------------------------------


@pytest.fixture
def places(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A repository with its data directory inside, and a place outside both."""
    repository = tmp_path / "repo"
    data_dir = repository / "data"
    outside = tmp_path / "elsewhere"
    data_dir.mkdir(parents=True)
    outside.mkdir()
    return repository, data_dir, outside


def _folder(out: Path | None, places: tuple[Path, Path, Path]) -> Path:
    repository, data_dir, _ = places
    return export_folder(
        out, repository=repository, data_dir=data_dir, name="20261119T120000Z-todo"
    )


@pytest.mark.integration
def test_no_out_is_the_fixed_exports_folder(places: tuple[Path, Path, Path]) -> None:
    assert _folder(None, places) == (places[1] / "exports" / "20261119T120000Z-todo").resolve()


@pytest.mark.integration
def test_out_inside_the_exports_folder_or_outside_the_repository(
    places: tuple[Path, Path, Path],
) -> None:
    _, data_dir, outside = places
    assert _folder(data_dir / "exports" / "mia", places) == (data_dir / "exports" / "mia").resolve()
    assert _folder(outside / "nueva", places) == (outside / "nueva").resolve()


@pytest.mark.integration
@pytest.mark.parametrize(
    "base, parts",
    [
        (0, ("server",)),
        (1, ("exports", "..", "..", "docs")),
        (1, ()),
        (1, ("backups",)),
    ],
    ids=["repository", "dot-dot-back-into-the-repository", "data-directory", "backups"],
)
def test_a_place_inside_the_repository_or_the_data_directory_is_refused(
    places: tuple[Path, Path, Path], base: int, parts: tuple[str, ...]
) -> None:
    target = places[base].joinpath(*parts)
    with pytest.raises(ExportPlaceError):
        _folder(target, places)


@pytest.mark.integration
def test_a_relative_path_is_resolved_before_it_is_checked(
    places: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(places[0])
    with pytest.raises(ExportPlaceError):
        _folder(Path("server"), places)


@pytest.mark.integration
def test_an_existing_file_or_a_folder_with_something_is_refused(
    places: tuple[Path, Path, Path],
) -> None:
    outside = places[2]
    (outside / "archivo.txt").write_text("x", encoding="utf-8")
    (outside / "llena").mkdir()
    (outside / "llena" / "algo.txt").write_text("x", encoding="utf-8")
    (outside / "vacia").mkdir()
    for refused in (outside / "archivo.txt", outside / "llena"):
        with pytest.raises(ExportPlaceError):
            _folder(refused, places)
    assert _folder(outside / "vacia", places) == (outside / "vacia").resolve()


@pytest.mark.integration
def test_the_refusal_is_a_closed_phrase(places: tuple[Path, Path, Path]) -> None:
    with pytest.raises(ExportPlaceError) as refused:
        _folder(places[0] / "server", places)
    assert isinstance(refused.value, BrainMemoryError)
    assert str(places[0]) not in str(refused.value)


# --- writing ------------------------------------------------------------------------------------


@pytest.mark.integration
def test_a_missing_folder_is_created_with_both_files(tmp_path: Path) -> None:
    folder = tmp_path / "a" / "b" / "nueva"
    markdown, json_file = write_export(_document(), folder)
    assert sorted(path.name for path in folder.iterdir()) == ["exportacion.json", "exportacion.md"]
    assert markdown.read_bytes().count(b"\r\n") == 0
    assert json.loads(json_file.read_text(encoding="utf-8"))["format"] == "iroko-export"


@pytest.mark.integration
def test_a_failed_second_file_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "nueva"
    real = export_files._write_file

    def _disk_full(path: Path, text: str) -> None:
        if path.name == "exportacion.md":
            raise OSError("disk full")
        real(path, text)

    monkeypatch.setattr(export_files, "_write_file", _disk_full)
    with pytest.raises(OSError, match="disk full"):
        write_export(_document(), folder)
    assert not folder.exists()


@pytest.mark.integration
def test_a_failure_in_an_existing_empty_folder_keeps_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "vacia"
    folder.mkdir()

    def _refuse(path: Path, text: str) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(export_files, "_write_file", _refuse)
    with pytest.raises(OSError, match="read-only"):
        write_export(_document(), folder)
    assert folder.is_dir()
    assert list(folder.iterdir()) == []


@pytest.mark.integration
def test_a_file_already_at_the_target_is_never_overwritten(tmp_path: Path) -> None:
    folder = tmp_path / "carrera"
    folder.mkdir()
    planted = folder / "exportacion.json"
    planted.write_text("plantado", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_export(_document(), folder)
    assert planted.read_text(encoding="utf-8") == "plantado"
    assert not (folder / "exportacion.md").exists()


@pytest.mark.unit
def test_no_file_holds_a_secret_reference_value() -> None:
    document = _document((1, "hola", "verified"))
    for text in (render_json(document), render_markdown(document)):
        assert _SALT not in text
        assert "embedding" not in text
