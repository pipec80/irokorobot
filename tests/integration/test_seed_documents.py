"""The alta's documents: `documents/manifest.toml` beside the seed file (Plan 0088 Task B4, D-16).

The dry run lists each document with its sections and level; the owner's ``SI`` applies them in
the commissioning's one transaction; a missing file or an unknown level refuses the whole load;
``--replace`` replaces only the documents the alta loaded, and only while commissioning. Canary
files only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory import document_store
from server.memory.commissioning import close_commissioning, get_open_commissioning
from server.memory.document_store import NewSection, NewSource

from server import db
from tests.integration.seed_household import NOW
from tests.integration.test_seed_cli import (
    _command,
    _count,
    _details,
    _file,
    _Terminal,
    _with_db,
    prepared,
)
from tests.unit.seed_data import minimal_seed

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

__all__ = ["prepared"]  # the fixture, imported so this module can use it

_MANUAL = "# Manual\n\nzzfiltro: gírelo a la izquierda.\n\n## Tambor\n\nzztambor limpio.\n"
_RECIPE = "zzlevadura tibia.\n\nzzhorno a doscientos grados.\n"


def _alta(tmp_path: Path, manifest: str, files: dict[str, str]) -> Path:
    """A seed file with a `documents/` folder beside it."""
    seed = _file(tmp_path / "alta", minimal_seed())
    folder = seed.parent / "documents"
    folder.mkdir()
    (folder / "manifest.toml").write_bytes(manifest.encode())
    for name, text in files.items():
        (folder / name).write_bytes(text.encode())
    return seed


_TWO = """
[[document]]
file = "manual.md"
title = "Manual zzcanario"
level = "sensitive"

[[document]]
file = "receta.txt"
title = "Receta zzcanaria"
"""


async def _sources() -> list[tuple[str, str, str]]:
    async def read() -> list[tuple[str, str, str]]:
        cursor = await db.get_conn().execute(
            "SELECT title, level, channel FROM document_sources ORDER BY id"
        )
        rows = [(str(r[0]), str(r[1]), str(r[2])) for r in await cursor.fetchall()]
        await cursor.close()
        return rows

    return await _with_db(read)


async def test_the_dry_run_lists_the_documents_and_writes_nothing(
    prepared: Path, tmp_path: Path
) -> None:
    seed = _alta(tmp_path, _TWO, {"manual.md": _MANUAL, "receta.txt": _RECIPE})
    terminal = _Terminal()

    assert await _command(seed, terminal) == 0

    assert "Manual zzcanario: md, sensitive, 2 secciones" in terminal.text
    assert "Receta zzcanaria: txt, normal, 2 secciones" in terminal.text
    assert await _count("document_sources") == 0


async def test_the_apply_stores_them_in_the_commissioning_transaction(
    prepared: Path, tmp_path: Path
) -> None:
    seed = _alta(tmp_path, _TWO, {"manual.md": _MANUAL, "receta.txt": _RECIPE})

    code = await _command(seed, _Terminal("SI"), apply=True, commissioning=_details())

    assert code == 0
    assert await _sources() == [
        ("Manual zzcanario", "sensitive", "import_file"),
        ("Receta zzcanaria", "normal", "import_file"),
    ]
    assert await _count("document_sections") == 4
    assert await _with_db(get_open_commissioning) is not None


@pytest.mark.parametrize(
    "manifest, files",
    [
        ('[[document]]\nfile = "falta.md"\ntitle = "Falta"\n', {}),
        (
            '[[document]]\nfile = "manual.md"\ntitle = "Manual"\nlevel = "secret"\n',
            {"manual.md": _MANUAL},
        ),
        ('[[document]]\nfile = "wifi.txt"\ntitle = "Wifi"\n', {"wifi.txt": "clave: zorro4821"}),
        ('[[document]]\nfile = "../fuera.md"\ntitle = "Fuera"\n', {}),
    ],
)
async def test_a_bad_document_refuses_the_whole_load(
    prepared: Path, tmp_path: Path, manifest: str, files: dict[str, str]
) -> None:
    seed = _alta(tmp_path, manifest, files)
    (tmp_path / "alta" / "fuera.md").write_bytes(_MANUAL.encode())
    terminal = _Terminal("SI")

    assert await _command(seed, terminal, apply=True, commissioning=_details()) == 1

    assert await _count("document_sources") == 0
    assert await _with_db(get_open_commissioning) is None
    assert "document" in terminal.text


async def _admin_document(owner_title: str) -> None:
    async def insert() -> None:
        cursor = await db.get_conn().execute("SELECT MIN(id) FROM entities WHERE type = 'person'")
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        source = NewSource(
            owner_entity_id=int(row[0]),
            title=owner_title,
            file_sha256="f" * 64,
            format="md",
            level="normal",
            channel="admin_local",
            loaded_at=NOW,
            loaded_by_entity_id=None,
        )
        async with db.transaction() as conn:
            await document_store.insert_source(
                conn, source=source, sections=[NewSection(0, "", "zzadmin")]
            )

    await _with_db(insert)


async def test_replace_swaps_only_the_alta_documents(prepared: Path, tmp_path: Path) -> None:
    first = _alta(tmp_path / "uno", _TWO, {"manual.md": _MANUAL, "receta.txt": _RECIPE})
    assert await _command(first, _Terminal("SI"), apply=True, commissioning=_details()) == 0
    await _admin_document("Nota zzadmin")
    second = _alta(
        tmp_path / "dos",
        '[[document]]\nfile = "receta.txt"\ntitle = "Receta nueva"\n',
        {"receta.txt": _RECIPE + "\nzzotra linea.\n"},
    )

    assert await _command(second, _Terminal("SI"), apply=True, replace=True) == 0

    assert await _sources() == [
        ("Nota zzadmin", "normal", "admin_local"),
        ("Receta nueva", "normal", "import_file"),
    ]


async def test_replace_is_refused_after_the_commissioning_closed(
    prepared: Path, tmp_path: Path
) -> None:
    seed = _alta(tmp_path, _TWO, {"manual.md": _MANUAL, "receta.txt": _RECIPE})
    assert await _command(seed, _Terminal("SI"), apply=True, commissioning=_details()) == 0

    async def close() -> None:
        record = await get_open_commissioning()
        assert record is not None
        await close_commissioning(record.id, NOW)

    await _with_db(close)

    assert await _command(seed, _Terminal("SI"), apply=True, replace=True) == 1
    assert len(await _sources()) == 2


async def test_a_second_load_keeps_the_stored_documents_as_unchanged(
    prepared: Path, tmp_path: Path
) -> None:
    """Review: re-running the alta with the same manifest must not refuse the whole load."""
    seed = _alta(tmp_path, _TWO, {"manual.md": _MANUAL, "receta.txt": _RECIPE})
    assert await _command(seed, _Terminal("SI"), apply=True, commissioning=_details()) == 0
    terminal = _Terminal("SI")

    assert await _command(seed, terminal, apply=True) == 0

    assert len(await _sources()) == 2
    assert "ya guardado" in terminal.text


async def test_a_file_name_with_a_null_byte_is_refused_as_not_found(
    prepared: Path, tmp_path: Path
) -> None:
    seed = _alta(tmp_path, '[[document]]\nfile = "a\u0000b.md"\ntitle = "Nulo"\n', {})

    assert await _command(seed, _Terminal("SI"), apply=True, commissioning=_details()) == 1
