"""`iroko-admin docs add | list | remove`: the owner's documents (Plan 0088 D-16, D-19, ADR 0034).

Server stopped, each under the owner's PIN (a title can be sensitive, so ``list`` too) and with one
``admin_audit`` row per attempt that holds the source id at most, never a title or a text. ``add``
extracts the file, refuses a document that holds a code, asks the level when no flag gives it,
shows the format, the sections, the characters and the first three lines, then asks ``SI``; it
stores the source and its sections in one transaction and embeds them if Ollama answers (else the
conversation job does). ``remove`` deletes for good through the deletion register.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import TYPE_CHECKING, Final
import unicodedata

from server import db
from server.memory.admin_audit import (
    AdminActorRole,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    record_admin_operation,
)
from server.memory.deletion_register import Deletion, DeletionKind, forget
from server.memory.document_extract import DocumentRefusedError, ExtractedText, extract_text
from server.memory.document_index import backfill_sections, fit_sections
from server.memory.document_secrets import flags_secret
from server.memory.document_sections import MAX_SECTIONS, SECTION_MAX_CHARS, cut_sections
from server.memory.document_store import (
    DocumentExistsError,
    DocumentLevel,
    NewSection,
    NewSource,
    insert_source,
    sources_of,
)

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite
    import httpx

__all__ = ["DocsRequest", "run_docs"]

type ReadText = Callable[[str], str]
type WriteText = Callable[[str], None]
type VerifyPin = Callable[[], Awaitable[bool]]
type Confirm = Callable[[], bool]

_LEVELS: Final[dict[str, DocumentLevel]] = {"normal": "normal", "sensitive": "sensitive"}
_OPERATIONS: Final = {"add": AdminOperationKind.ADD, "list": AdminOperationKind.LIST}
_MAX_TITLE: Final = 120
_PREVIEW_LINES: Final = 3
_PREVIEW_CHARS: Final = 100
_HOLDS_A_CODE: Final = "Este documento tiene una clave o un código; no lo guardo."
_NO_PIN: Final = "Sin verificación de la persona titular: no se hizo nada."
_UNKNOWN: Final = "No hay un documento con ese id."
_BAD_LEVEL: Final = "El nivel es normal o sensitive."
_EXISTS: Final = "Ese archivo ya está guardado como documento."
_TOO_LONG: Final = "Ese documento es demasiado largo; no lo guardo."
# The closed refusal reason of each extraction message, for the audit row (never the message).
_REASONS: Final = {
    "Ese formato todavía no lo leo.": "format",
    "Este PDF no tiene texto que pueda leer.": "no_text",
}


@dataclass(frozen=True)
class DocsRequest:
    """One `docs` invocation, free of argparse."""

    action: str
    actor_label: str
    file: Path | None = None
    title: str | None = None
    level: str | None = None
    row_id: int | None = None


async def _audit(
    request: DocsRequest,
    operation: AdminOperationKind,
    now: str,
    *,
    source_id: int | None = None,
    refused: str | None = None,
    joined: bool = False,
) -> None:
    await record_admin_operation(
        actor_label=request.actor_label,
        actor_role=AdminActorRole.BUILDER,
        operation=operation,
        target_kind=TargetKind.DOCUMENT,
        field_id=None if source_id is None else str(source_id),
        target_entity_id=None,
        outcome=AdminOutcomeStatus.REFUSED if refused else AdminOutcomeStatus.APPLIED,
        reason=refused,
        recorded_at=now,
        manage_transaction=not joined,
    )


def _title(request: DocsRequest, path: Path) -> str:
    raw = request.title or path.stem.replace("_", " ").replace("-", " ")
    printable = "".join(c for c in raw if not unicodedata.category(c).startswith("C"))
    return " ".join(printable.split())[:_MAX_TITLE] or "Documento"


def _level(request: DocsRequest, read_text: ReadText) -> DocumentLevel | None:
    answer = request.level or read_text("Nivel (normal o sensitive): ").strip().lower()
    return _LEVELS.get(answer)


def _preview(text: ExtractedText) -> list[str]:
    lines = [line.strip() for page in text.pages for line in page.splitlines() if line.strip()]
    return [line[:_PREVIEW_CHARS] for line in lines[:_PREVIEW_LINES]]


async def _store(
    source: NewSource, sections: list[NewSection], request: DocsRequest, now: str
) -> int:
    async with db.transaction() as conn:
        source_id = await insert_source(conn, source=source, sections=sections)
        await _audit(request, AdminOperationKind.ADD, now, source_id=source_id, joined=True)
    return source_id


async def _refuse(
    request: DocsRequest, now: str, write_text: WriteText, reason: str, message: str
) -> int:
    """Audit and print one refusal of ``add``; return the exit code."""
    await _audit(request, AdminOperationKind.ADD, now, refused=reason)
    write_text(message)
    return 1


async def _readable(
    request: DocsRequest, path: Path, now: str, write_text: WriteText
) -> tuple[ExtractedText, list[NewSection]] | None:
    """The file's text and sections, or ``None`` once a refusal was audited and printed."""
    try:
        text = extract_text(path)
        sections = cut_sections(text, max_chars=SECTION_MAX_CHARS)
    except DocumentRefusedError as exc:
        await _refuse(request, now, write_text, _REASONS.get(exc.reason, "file"), exc.reason)
        return None
    if flags_secret("\n".join(text.pages)):
        await _refuse(request, now, write_text, "secret", _HOLDS_A_CODE)
        return None
    return text, sections


def _show(
    text: ExtractedText, level: str, sections: list[NewSection], write_text: WriteText
) -> None:
    write_text(
        f"Formato: {text.format}; nivel: {level}; {len(sections)} secciones; "
        f"{sum(len(s.body) for s in sections)} caracteres. Primeras líneas:"
    )
    for line in _preview(text):
        write_text(f"  {line}")


async def _add(  # noqa: PLR0911 - one audited refusal per closed reason
    request: DocsRequest,
    owner: int,
    read_text: ReadText,
    write_text: WriteText,
    now: str,
    *,
    confirm: Confirm,
    client: httpx.AsyncClient,
) -> int:
    path = request.file
    if path is None:
        write_text("docs add necesita el archivo.")
        return 1
    readable = await _readable(request, path, now, write_text)
    if readable is None:
        return 1
    text, sections = readable
    level = _level(request, read_text)
    if level is None:
        write_text(_BAD_LEVEL)
        return 1
    sections = await fit_sections(client, sections)
    if len(sections) > MAX_SECTIONS:  # cutting again to fit the window can add sections
        return await _refuse(request, now, write_text, "too_long", _TOO_LONG)
    _show(text, level, sections, write_text)
    if not confirm():
        return 1
    source = NewSource(
        owner_entity_id=owner,
        title=_title(request, path),
        file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        format=text.format,
        level=level,
        channel="admin_local",
        loaded_at=now,
        loaded_by_entity_id=owner,
    )
    try:
        source_id = await _store(source, sections, request, now)
    except DocumentExistsError:
        return await _refuse(request, now, write_text, "exists", _EXISTS)
    # What Ollama does not embed now, the conversation job does.
    embedded = await backfill_sections(client, limit=len(sections))
    write_text(
        f"Documento guardado [{source_id}]; {embedded} de {len(sections)} secciones con vector."
    )
    return 0


async def _list(request: DocsRequest, owner: int, write_text: WriteText, now: str) -> int:
    write_text("Documentos:")
    for source in await sources_of(owner_entity_id=owner):
        write_text(
            f"  [{source.id}] {source.title} ({source.format}, {source.level}, "
            f"{source.sections} secciones, {source.characters} caracteres, {source.loaded_at})"
        )
    await _audit(request, AdminOperationKind.LIST, now)
    return 0


async def _remove(
    request: DocsRequest, owner: int, write_text: WriteText, now: str, *, confirm: Confirm
) -> int:
    source = next(
        (s for s in await sources_of(owner_entity_id=owner) if s.id == request.row_id), None
    )
    if source is None:
        await _audit(request, AdminOperationKind.DELETE, now, refused="unknown")
        write_text(_UNKNOWN)
        return 1
    write_text(f"Se borra para siempre [{source.id}] {source.title} ({source.sections} secciones).")
    if not confirm():
        return 1

    async def audit(_conn: aiosqlite.Connection) -> None:
        await _audit(request, AdminOperationKind.DELETE, now, source_id=source.id, joined=True)

    await forget(
        [Deletion(DeletionKind.DOCUMENT, source.id)], now=datetime.fromisoformat(now), audit=audit
    )
    write_text("Documento borrado.")
    return 0


async def run_docs(
    request: DocsRequest,
    *,
    owner: int,
    read_text: ReadText,
    write_text: WriteText,
    now: str,
    verify_pin: VerifyPin,
    confirm: Confirm,
    client: httpx.AsyncClient,
) -> int:
    """Run one `docs` action under the owner's PIN.

    Args:
        request: The action and its arguments.
        owner: The ready owner's entity id.
        read_text: Prompts for and returns one visible line.
        write_text: Prints one line (this terminal only).
        now: UTC ISO 8601 with microseconds, shared by the operation and its audit row.
        verify_pin: Asks and verifies the owner's PIN.
        confirm: Asks ``SI`` (honours ``--dry-run``).
        client: The command's own HTTP client to Ollama (``iroko-admin`` runs with the server
            stopped, so the lifespan's client does not exist).

    Returns:
        ``0`` on success, ``1`` on a refusal or a cancelled action.
    """
    if not await verify_pin():
        await _audit(
            request, _OPERATIONS.get(request.action, AdminOperationKind.DELETE), now, refused="pin"
        )
        write_text(_NO_PIN)
        return 1
    match request.action:
        case "add":
            return await _add(
                request, owner, read_text, write_text, now, confirm=confirm, client=client
            )
        case "list":
            return await _list(request, owner, write_text, now)
        case _:
            return await _remove(request, owner, write_text, now, confirm=confirm)
