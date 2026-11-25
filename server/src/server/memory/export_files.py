"""Write an export as Markdown and JSON, in its own protected folder (Plan 0087 D-3, D-4).

ADR 0032 decision 8, amended by Pipec on 2026-11-19: the folder is fixed and kept,
``data/exports/<instante>-<alcance>/`` beside the database (git-ignored, the Docker volume
later), readable by the server's user only. ``--out`` may name another folder, new or empty,
inside ``data/exports/`` or outside the repository; never the repository, the data directory
itself (the database, the register, the backups), a file or a folder that holds something.

Both files are rendered from the one ``ExportDocument``: parsing the Markdown tables back gives
exactly the JSON rows. A cell's ``\\``, ``|`` and ``<`` are escaped, a line break is ``<br>`` and
nothing is ``—``. A code (a lifecycle, a verdict) is the same string in both, and the Markdown
ends with the closed glossary that translates every code. This module holds no SQL.
"""

from __future__ import annotations

import json
import os
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from server.cognition.models import AuthorizationAction
from server.exceptions import ExportPlaceError
from server.memory.export_model import ExportScopeKind
from server.memory.write_types import IMPORT_CHANNELS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from server.memory.export_model import Cell, ExportDocument, ExportScope

__all__ = [
    "EXPORTS_DIRNAME",
    "GLOSSARY",
    "JSON_FILENAME",
    "MARKDOWN_FILENAME",
    "export_folder",
    "folder_name",
    "render_json",
    "render_markdown",
    "write_export",
]

EXPORTS_DIRNAME: Final = "exports"
MARKDOWN_FILENAME: Final = "exportacion.md"
JSON_FILENAME: Final = "exportacion.json"
_FORMAT: Final = "iroko-export"
_VERSION: Final = 1
_NOTHING: Final = "—"
_FOLDER_MODE: Final = 0o700
_FILE_MODE: Final = 0o600

_IN_REPOSITORY = (
    "Esa carpeta está dentro del repositorio: usa data/exports/ (sin --out) o una fuera de él."
)
_IN_DATA = "Esa carpeta es la de la base de datos: usa data/exports/ (sin --out) o una fuera."
_A_FILE = "Esa ruta es un archivo, no una carpeta: elige una carpeta nueva o vacía."
_NOT_EMPTY = "Esa carpeta ya tiene algo adentro: elige una nueva o vacía."

#: Every stored code an export can hold, in Spanish (D-4, «Qué significa cada valor»).
GLOSSARY: Final[Mapping[str, str]] = MappingProxyType(
    {
        # lifecycle of a fact or a relation
        "active": "vigente",
        "superseded": "reemplazado por uno más nuevo",
        "disputed": "en duda",
        "revoked": "revocado",
        "expired": "vencido",
        # sensitivity
        "normal": "normal",
        "private": "privado",
        "biometric": "biométrico",
        "medical": "de salud",
        "location": "de ubicación",
        "child_data": "de un niño o una niña",
        "security": "de seguridad",
        # visibility
        "public": "público",
        "household": "del hogar",
        "adults": "de los adultos",
        "personal": "personal: solo de la persona titular",
        "temporary": "temporal",
        # who spoke a turn
        "verified": "tu voz, verificada",
        "not_verified": "tu cara, la voz sin verificar",
        "not_owner": "otra persona, o sin cara reconocida",
        "not_checked": "respuesta fija, sin revisar quién habló",
        # kinds (a recall unit, a deletion)
        "turn": "un turno",
        "episode": "un resumen del diario",
        "literal_fact": "un dato",
        "entity_relation": "una relación",
        "care_contact": "un contacto de cuidado",
        "record": "una conversación",
        "owner_records": "todas las conversaciones de la persona titular",
        "entity": "una persona",
        "recall_unit": "un recuerdo",
        "pending_topic": "un tema pendiente",
        # states and statuses
        "unnamed": "sin nombre todavía",
        "open": "abierto",
        "asked": "ya preguntado",
        "pending": "pendiente",
        "done": "hecho",
        "skipped": "omitido",
        "failed": "falló",
        "proposed": "propuesto",
        "offered": "ofrecido para confirmar",
        "confirmed": "confirmado",
        "rejected": "rechazado",
        "provided": "respondido",
        "none": "nada que anotar",
        "unknown": "no se sabe",
        "declined": "prefirió no decir",
        "not_asked": "no se preguntó",
        # what a consent is for
        "conversation_storage": "guardar las conversaciones",
        "owner_authentication": "reconocer la cara de la persona titular",
        "speaker_evidence": "reconocer la voz",
        # roles
        "owner": "persona titular",
        "adult": "adulto",
        "child": "niño o niña",
        "guest": "visita",
        "builder": "quien armó el robot",
        "family": "familiar",
        "technician": "técnico",
        "other": "otro",
        "emergency": "emergencia",
        "caregiver": "cuidador o cuidadora",
        "doctor": "médico o médica",
        "key_holder": "tiene llave",
        "neighbor": "vecino o vecina",
        "trusted": "de confianza",
        # profiles and people
        "face": "cara",
        "voice": "voz",
        "person": "persona",
        "place": "lugar",
        "object": "objeto",
        "event": "evento",
        "preference": "preferencia",
        "schedule": "horario",
        "concept": "idea",
        # the acta
        "owner_in_person": "la persona titular, en persona",
        "representative": "un representante",
        "builder_is_owner": "quien armó el robot es la persona titular",
        "declared_yes": "sí, declarado",
        "declared_no": "no, declarado",
        "conditions": "condiciones de salud",
        "allergies": "alergias",
        "medications": "medicamentos",
        "devices": "aparatos médicos",
        "contacts": "contactos",
        "withhold": "lo que no se dice",
        "secrets": "secretos",  # pragma: allowlist secret  # an acta section's name, no value
        "documents": "documentos",
        "home": "la casa",
        "function": "para qué sirve el robot",
        # the audits
        "add": "agregar",
        "change": "cambiar",
        "revoke": "revocar",
        "grant": "dar un consentimiento",
        "export": "exportar",
        "delete": "borrar",
        "pool_literal": "un dato del pozo",
        "pool_relation": "una relación del pozo",
        "conversation_consent": "el consentimiento de las conversaciones",
        "conversation_record": "una conversación",
        "household_data": "los datos del hogar",
        "list": "listar",
        "document": "un documento",
        "applied": "hecho",
        "refused": "rechazado",
        "allowed": "permitido",
        "denied": "negado",
        "requires_confirmation": "pide confirmar",
        # how a datum arrived (the two import channels come from the vocabulary, below)
        "voice_classic": "por voz",
        "voice_stream": "por voz, en vivo",
        "admin_local": "con iroko-admin",
        **dict.fromkeys((channel.value for channel in IMPORT_CHANNELS), "cargado en el alta"),
        "scrypt": "scrypt: el PIN guardado solo como verificador",
        # what the policy was asked: the actions are named only by the model and the policy (an
        # architecture guard), so each one is listed from the enum, its words as stored
        **{
            action.value: f"lo que se le pidió a la política ({action.value.replace('_', ' ')})"
            for action in AuthorizationAction
        },
    }
)


def folder_name(scope: ExportScope, now: str) -> str:
    """The default folder's name: the instant and the scope, never a person's name.

    Args:
        scope: The export's scope.
        now: The export's instant, as UTC ISO 8601.

    Returns:
        ``20261119T120000Z-todo``, ``…-persona-<id>`` or ``…-persona`` (a name only talked about).
    """
    stamp = f"{now[0:4]}{now[5:7]}{now[8:10]}T{now[11:13]}{now[14:16]}{now[17:19]}Z"
    if scope.kind is ExportScopeKind.ALL:
        return f"{stamp}-todo"
    return f"{stamp}-persona" if scope.entity_id is None else f"{stamp}-persona-{scope.entity_id}"


def export_folder(out: Path | None, *, repository: Path, data_dir: Path, name: str) -> Path:
    """Return the folder an export is written to, resolved, or refuse it with a closed phrase.

    Args:
        out: The folder the operator named (``--out``), or ``None`` for ``data/exports/<name>``.
        repository: The repository root.
        data_dir: The database's directory (``settings.brain_db_path.parent``).
        name: The default folder's name (``folder_name``).

    Returns:
        The resolved folder (``..``, a relative path and a junction are seen as what they are).

    Raises:
        ExportPlaceError: Inside the repository or the data directory but outside
            ``data/exports/``, an existing file, or an existing folder that holds something.
    """
    exports = (data_dir / EXPORTS_DIRNAME).resolve()
    folder = exports / name if out is None else out.resolve()
    if not folder.is_relative_to(exports):
        if folder.is_relative_to(data_dir.resolve()):
            raise ExportPlaceError(_IN_DATA)
        if folder.is_relative_to(repository.resolve()):
            raise ExportPlaceError(_IN_REPOSITORY)
    if folder.is_file():
        raise ExportPlaceError(_A_FILE)
    if folder.is_dir() and any(folder.iterdir()):
        raise ExportPlaceError(_NOT_EMPTY)
    return folder


def _scope(scope: ExportScope) -> dict[str, str | int | None]:
    return {"kind": scope.kind.value, "entity_id": scope.entity_id, "words": scope.words}


def render_json(document: ExportDocument) -> str:
    """Render the export as JSON (UTF-8 text, accents kept, two-space indent, ``\\n`` ends)."""
    payload = {
        "format": _FORMAT,
        "version": _VERSION,
        "scope": _scope(document.scope),
        "generated_at": document.generated_at,
        "schema_version": document.schema_version,
        "sections": [
            {
                "key": section.key,
                "title": section.title,
                "columns": [{"key": c.key, "label": c.label} for c in section.columns],
                "rows": [
                    {column.key: cell for column, cell in zip(section.columns, row, strict=True)}
                    for row in section.rows
                ],
            }
            for section in document.sections
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _escaped(cell: Cell) -> str:
    """One table cell: ``\\``, ``|`` and ``<`` escaped, a line break as ``<br>``, ``None`` as —."""
    if cell is None:
        return _NOTHING
    text = str(cell).replace("\\", "\\\\").replace("|", "\\|").replace("<", "\\<")
    return text.replace("\r\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _scope_line(scope: ExportScope) -> str:
    if scope.kind is ExportScopeKind.ALL:
        return "todo lo que guarda Iroko"
    if scope.entity_id is not None:
        return f"una persona (id {scope.entity_id})"
    return f"una persona de quien solo se habló («{_escaped(scope.words)}»)"


def render_markdown(document: ExportDocument) -> str:
    """Render the export as a Spanish Markdown document: a header, one table per section, a glossary."""
    lines = [
        "# Exportación de Iroko",
        "",
        f"- Alcance: {_scope_line(document.scope)}",
        f"- Generada: {document.generated_at}",
        f"- Versión del esquema: {document.schema_version}",
        "- La fila de auditoría de esta exportación se escribe después de los archivos: no está aquí.",
        "- Estos archivos tienen datos personales: guárdalos en un disco cifrado, nunca en una carpeta"
        " sincronizada, y bórralos cuando ya no los necesites.",
    ]
    for section in document.sections:
        count = len(section.rows)
        lines += ["", f"## {section.title}", ""]
        if not count:
            lines.append("Sin filas.")
            continue
        lines += [f"{count} {'fila' if count == 1 else 'filas'}.", ""]
        lines.append(_row([column.label for column in section.columns]))
        lines.append(_row(["---"] * len(section.columns)))
        lines += [_row([_escaped(cell) for cell in row]) for row in section.rows]
    lines += [
        "",
        "## Qué significa cada valor",
        "",
        _row(["Código", "Significado"]),
        _row(["---", "---"]),
    ]
    lines += [_row([code, meaning]) for code, meaning in GLOSSARY.items()]
    return "\n".join(lines) + "\n"


_CREATE_FLAGS: Final = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL  # never an existing file: one planted between the check and the write refuses
    | getattr(os, "O_NOFOLLOW", 0)  # POSIX: never through a symbolic link
    | getattr(os, "O_BINARY", 0)  # Windows: the bytes as written, ``\n`` stays ``\n``
)


def _write_file(path: Path, text: str) -> None:
    """Create one export file, UTF-8 with ``\\n``, born readable by the server's user only.

    Raises:
        FileExistsError: If something is already at *path*; it is left untouched.
        OSError: If the file cannot be written; what this call created is removed.
    """
    descriptor = os.open(path, _CREATE_FLAGS, _FILE_MODE)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(text.encode("utf-8"))
    except OSError:
        path.unlink(missing_ok=True)
        raise


def write_export(document: ExportDocument, folder: Path) -> tuple[Path, Path]:
    """Write ``exportacion.json`` and ``exportacion.md`` into *folder*, or leave nothing.

    The folder (and its parents) is created when missing, readable by the server's user only
    (on Windows it inherits the data directory's permissions). A failure while writing removes
    what this run wrote, the folder too when this run created it, and re-raises.

    Args:
        document: The export.
        folder: A folder ``export_folder`` returned.

    Returns:
        The Markdown and the JSON paths.

    Raises:
        OSError: If a file cannot be written; nothing this run wrote is left.
    """
    created = not folder.exists()
    markdown, json_file = folder / MARKDOWN_FILENAME, folder / JSON_FILENAME
    written: list[Path] = []
    try:
        folder.mkdir(mode=_FOLDER_MODE, parents=True, exist_ok=True)
        if os.name != "nt":
            folder.chmod(_FOLDER_MODE)  # an existing empty --out folder is closed too
        for path, text in (
            (json_file, render_json(document)),
            (markdown, render_markdown(document)),
        ):
            _write_file(path, text)
            written.append(path)
    except OSError:
        for path in written:
            path.unlink(missing_ok=True)
        if created and folder.is_dir():
            folder.rmdir()
        raise
    return markdown, json_file
