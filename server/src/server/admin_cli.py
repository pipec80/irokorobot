"""The `iroko-admin` command: the local amendment path after the alta closes (Plan 0073).

Local administration (ADR 0025 decisions 2 level A, 4, 11): whoever runs it on the server's
machine, with the server stopped, over SSH. It opens an existing database at the latest schema and
never creates or migrates one, prints the database it uses, shows the pool, the contacts, each
section's status and the audit, and edits a datum through the canonical writers (channel
``admin_local``). A value is read from standard input, never from an argument, so it never lands in
the shell history; a write to sensitive data or a contact asks for the owner's PIN; every write
asks for confirmation and honours ``--dry-run``. No value reaches a log.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import getpass
from pathlib import Path
import sqlite3
import sys

import httpx

from server import db
from server.conversation_admin import export_records, summary_line
from server.exceptions import AdminPinError, BrainMemoryError
from server.memory.admin_audit import (
    AdminActorRole,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    list_admin_operations,
    record_admin_operation,
)
from server.memory.admin_ops import (
    AdminActor,
    AdminOutcome,
    ContactTerms,
    apply_contact_edit,
    apply_literal_edit,
    apply_revoke,
    requires_owner_verification,
)
from server.memory.admin_pin import verify_owner_pin
from server.memory.admin_readiness import derive_section_presence, recompute_readiness
from server.memory.care_contacts import list_active_contacts
from server.memory.commissioning import (
    Section,
    SectionStatus,
    get_latest_commissioning,
    list_section_statuses,
)
from server.memory.conversation_consent import (
    CONVERSATION_NOTICE_VERSION,
    grant_conversation_consent,
    load_conversation_notice,
    revoke_conversation_consent,
)
from server.memory.conversation_record import delete_record, list_records
from server.memory.owner_credentials import get_ready_owner
from server.memory.relational_v4 import list_active_facts, list_active_relations
from server.personal_setup import check_db_available
from server.settings import settings

__all__ = ["main", "run_admin_command"]

type ReadText = Callable[[str], str]
type WriteText = Callable[[str], None]

_PROBE_TIMEOUT_S = 2.0
_CONFIRM = "SI"  # the typed confirmation word, not a secret
_MAX_PIN_TRIES = 3
_DEFAULT_ACTOR = "local-admin"
_KINDS = {
    "literal": TargetKind.POOL_LITERAL,
    "relation": TargetKind.POOL_RELATION,
    "contact": TargetKind.CARE_CONTACT,
}
_REMINDER = (
    "Este informe queda en el historial de la terminal: limpia la pantalla al terminar (cls)."
)


class _RefusedError(Exception):
    """A refusal of the command itself; its message is closed and printed as is."""


@dataclass(frozen=True)
class AdminRequest:
    """One parsed invocation of `iroko-admin` (free of argparse)."""

    command: str
    field: str | None = None
    kind: str | None = None
    row_id: int | None = None
    person_id: int | None = None
    role: str | None = None
    order: int | None = None
    limit: int = 50
    dry_run: bool = False
    actor_label: str = _DEFAULT_ACTOR
    action: str | None = None
    out: Path | None = None


def _actor(request: AdminRequest) -> AdminActor:
    return AdminActor(label=request.actor_label, role=AdminActorRole.BUILDER)


async def _owner() -> int:
    """Return the ready owner's entity id, or refuse."""
    owner = await get_ready_owner()
    if owner is None:
        raise _RefusedError(
            "No hay una persona titular lista: corre `just setup-personal` primero."
        )
    return owner


async def _grant_pin_if_needed(
    *, required: bool, read_secret: ReadText, write_text: WriteText
) -> bool:
    """Prompt and verify the owner PIN when the operation needs it; return whether it is verified.

    The PIN is read through ``read_secret`` (``getpass`` in ``main``), so it never echoes to the
    terminal or the shell history. A write that does not need the PIN returns ``True`` at once.
    """
    if not required:
        return True
    for attempt in range(_MAX_PIN_TRIES):
        try:
            await verify_owner_pin(read_secret("PIN de la persona titular: "))
        except AdminPinError:
            left = _MAX_PIN_TRIES - attempt - 1
            write_text(
                f"PIN incorrecto. Intentos restantes: {left}." if left else "PIN incorrecto."
            )
        else:
            return True
    return False


def _announce_outcome(outcome: AdminOutcome, write_text: WriteText) -> int:
    """Print the outcome and return the exit code."""
    if outcome.status.value == "applied":
        write_text(f"Operación aplicada ({outcome.operation.value}).")
        return 0
    write_text(f"Operación rechazada ({outcome.operation.value}): {outcome.reason}.")
    return 1


# --- the read sub-commands ------------------------------------------------------------------------


async def _list(owner: int, write_text: WriteText) -> int:
    """Print the owner's pool literals, relations and contacts (values, this terminal only)."""
    write_text("Datos del pozo (hechos):")
    for fact in await list_active_facts(owner):
        write_text(f"  [{fact.id}] {fact.predicate}: {fact.value_text}")
    write_text("Relaciones:")
    for relation in await list_active_relations(owner):
        write_text(f"  [{relation.id}] {relation.predicate} -> {relation.target_entity_id}")
    write_text("Contactos:")
    for contact in await list_active_contacts(owner):
        order = "-" if contact.call_order is None else contact.call_order
        write_text(
            f"  [{contact.id}] {contact.role.value} ({order}) "
            f"persona={contact.contact_entity_id} {contact.phone}"
        )
    write_text(_REMINDER)
    return 0


async def _audit(limit: int, write_text: WriteText) -> int:
    """Print the most recent admin operations, with no value."""
    write_text("Auditoría (sin valores):")
    for row in await list_admin_operations(limit):
        field_id = row.field_id or "-"
        write_text(
            f"  {row.recorded_at} {row.operation.value} {row.target_kind.value} "
            f"{field_id} -> {row.outcome.value}{'' if row.reason is None else f' [{row.reason}]'}"
        )
    return 0


# --- the write sub-commands -----------------------------------------------------------------------


async def _edit_literal(
    request: AdminRequest,
    owner: int,
    read_text: ReadText,
    read_secret: ReadText,
    write_text: WriteText,
    now: str,
) -> int:
    """Add or change one owner pool literal; the value is read from standard input."""
    field_id = request.field or ""
    value = read_text(f"Valor para «{field_id}» (se lee de la entrada estándar): ").strip()
    if not value:
        raise _RefusedError("No se escribió ningún valor: nada que guardar.")
    write_text(f"{request.command}: {field_id} = {value}")
    if not _confirm(request, read_text, write_text):
        return 1
    required = requires_owner_verification(
        target_kind=TargetKind.POOL_LITERAL, predicate=field_id, subject_is_owner=True
    )
    if not await _grant_pin_if_needed(
        required=required, read_secret=read_secret, write_text=write_text
    ):
        write_text("Sin verificación de la persona titular: no se escribió nada.")
        return 1
    outcome = await apply_literal_edit(
        actor=_actor(request),
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate=field_id,
        value=value,
        kind=AdminOperationKind(request.command),
        now=now,
        owner_verified=True,
    )
    return _announce_outcome(outcome, write_text)


async def _revoke(
    request: AdminRequest,
    read_text: ReadText,
    read_secret: ReadText,
    write_text: WriteText,
    now: str,
) -> int:
    """Revoke a row by kind and id (the id comes from `list`)."""
    target_kind = _KINDS.get(request.kind or "")
    if target_kind is None or request.row_id is None:
        raise _RefusedError("revoke necesita un tipo (literal|relation|contact) y un id.")
    write_text(f"revoke: {request.kind} [{request.row_id}]")
    if not _confirm(request, read_text, write_text):
        return 1
    # Revoking a contact, a relation (a third party) or a non-owner fact needs the PIN; the owner's
    # own pool literal does not, but we cannot cheaply know the subject here, so a contact/relation
    # always asks and a literal asks unless it is a plain owner field (conservative: always ask).
    required = target_kind is not TargetKind.POOL_LITERAL or True
    if not await _grant_pin_if_needed(
        required=required, read_secret=read_secret, write_text=write_text
    ):
        write_text("Sin verificación de la persona titular: no se revocó nada.")
        return 1
    outcome = await apply_revoke(
        actor=_actor(request),
        target_kind=target_kind,
        target_id=request.row_id,
        subject_is_owner=target_kind is TargetKind.POOL_LITERAL,
        predicate=None,
        now=now,
        owner_verified=True,
    )
    return _announce_outcome(outcome, write_text)


async def _change_contact(
    request: AdminRequest,
    owner: int,
    read_text: ReadText,
    read_secret: ReadText,
    write_text: WriteText,
    now: str,
) -> int:
    """Change an existing contact's phone (by its id from `list`); role and flags are kept."""
    if request.row_id is None:
        raise _RefusedError("change-contact necesita el id del contacto (de `list`).")
    current = next((c for c in await list_active_contacts(owner) if c.id == request.row_id), None)
    if current is None:
        raise _RefusedError("No hay un contacto activo con ese id.")
    phone = read_text("Nuevo teléfono (entrada estándar): ").strip()
    if not phone:
        raise _RefusedError("No se escribió ningún teléfono.")
    write_text(f"change-contact [{request.row_id}] nuevo teléfono")
    if not _confirm(request, read_text, write_text):
        return 1
    if not await _grant_pin_if_needed(
        required=True, read_secret=read_secret, write_text=write_text
    ):
        write_text("Sin verificación de la persona titular: no se cambió nada.")
        return 1
    terms = ContactTerms(
        phone=phone,
        phone_alt=current.phone_alt,
        relationship=current.relationship,
        call_order=current.call_order,
        has_key=current.has_key,
        may_receive_health_info=current.may_receive_health_info,
        may_view_activity=current.may_view_activity,
    )
    outcome = await apply_contact_edit(
        actor=_actor(request),
        owner_entity_id=owner,
        contact_entity_id=current.contact_entity_id,
        role=current.role,
        terms=terms,
        kind=AdminOperationKind.CHANGE,
        now=now,
        owner_verified=True,
    )
    return _announce_outcome(outcome, write_text)


def _confirm(request: AdminRequest, read_text: ReadText, write_text: WriteText) -> bool:
    """A dry run never writes; otherwise the operator types the confirmation word."""
    if request.dry_run:
        write_text("Prueba en seco: no se escribió nada.")
        return False
    if read_text(f"Escribe {_CONFIRM} para confirmar: ") != _CONFIRM:
        write_text("Operación cancelada.")
        return False
    return True


# --- status: the frozen acta beside the read-only recompute (Plan 0073 Task 7, C-2) --------------


async def _status(owner: int, write_text: WriteText) -> int:
    """Print the frozen section statuses beside the rows now, then the recomputed readiness.

    It edits nothing: `recompute_readiness` reads the active rows and the acta's frozen hardware.
    """
    record = await get_latest_commissioning()
    frozen = None if record is None else await list_section_statuses(record.id)
    presence = await derive_section_presence(owner)
    write_text("Secciones (acta vs. filas actuales):")
    for section in Section:
        acta = "-" if frozen is None else frozen[section].value
        now_has = "con datos" if presence[section] else "sin datos"
        diverges = (
            frozen is not None
            and (frozen[section] is SectionStatus.PROVIDED) != (presence[section])
        )
        write_text(
            f"  {section.value}: acta={acta} ahora={now_has}{'  <- difiere' if diverges else ''}"
        )
    write_text("Preparación de capacidades (recomputada):")
    for item in await recompute_readiness(owner):
        write_text(f"  {item.capability.value}: {item.verdict.value}")
    return 0


# --- the conversation record (Plan 0076, ADR 0027) ------------------------------------------------

_CONVERSATION_ACTIONS = ("list", "export", "delete", "consent-grant", "consent-revoke")
_EXPORT_REMINDER = (
    "Los archivos tienen texto de conversaciones: bórralos cuando termines de leerlos."
)


async def _audit_conversation(
    request: AdminRequest,
    operation: AdminOperationKind,
    target: TargetKind,
    *,
    owner: int,
    now: str,
    refused: bool = False,
) -> None:
    """Write the one audit row of a conversation operation; it never holds a text."""
    await record_admin_operation(
        actor_label=request.actor_label,
        actor_role=AdminActorRole.BUILDER,
        operation=operation,
        target_kind=target,
        field_id=None if request.row_id is None else str(request.row_id),
        target_entity_id=owner if target is TargetKind.CONVERSATION_CONSENT else None,
        outcome=AdminOutcomeStatus.REFUSED if refused else AdminOutcomeStatus.APPLIED,
        reason="pin" if refused else None,
        recorded_at=now,
    )


def _conversation_operation(request: AdminRequest) -> tuple[AdminOperationKind, TargetKind, str]:
    """Return the audited operation, its target and the line that describes it."""
    match request.action:
        case "export":
            if request.out is None:
                raise _RefusedError("export necesita --out con la carpeta de destino.")
            which = "todas" if request.row_id is None else f"la {request.row_id}"
            return (
                AdminOperationKind.EXPORT,
                TargetKind.CONVERSATION_RECORD,
                f"exportar conversaciones ({which}) a {request.out}",
            )
        case "delete":
            if request.row_id is None:
                raise _RefusedError("delete necesita --id con el número de la conversación.")
            return (
                AdminOperationKind.DELETE,
                TargetKind.CONVERSATION_RECORD,
                f"borrar la conversación {request.row_id} y su resumen",
            )
        case "consent-grant":
            return (
                AdminOperationKind.GRANT,
                TargetKind.CONVERSATION_CONSENT,
                "autorizar el registro de conversaciones",
            )
        case "consent-revoke":
            return (
                AdminOperationKind.REVOKE,
                TargetKind.CONVERSATION_CONSENT,
                "revocar el registro y BORRAR todas las conversaciones y sus resúmenes",
            )
    raise _RefusedError(f"Acción desconocida: {request.action}.")


async def _apply_conversation(request: AdminRequest, owner: int, now: str) -> str:
    """Apply one confirmed, PIN-verified conversation operation and return its closing line."""
    match request.action, request.out, request.row_id:
        case "export", Path() as out, record_id:
            written = await export_records(out, record_id=record_id)
            return f"Exportadas {written} conversaciones a {out}. {_EXPORT_REMINDER}"
        case "delete", _, int() as record_id:
            deleted = await delete_record(record_id)
            return "Conversación borrada." if deleted else "No hay una conversación con ese número."
        case "consent-grant", _, _:
            await grant_conversation_consent(
                owner, notice_version=CONVERSATION_NOTICE_VERSION, now=datetime.fromisoformat(now)
            )
            return "Registro de conversaciones autorizado."
    count = await revoke_conversation_consent(owner, now=datetime.fromisoformat(now))
    return f"Consentimiento revocado: se borraron {count} conversaciones."


async def _conversations(
    request: AdminRequest,
    owner: int,
    read_text: ReadText,
    read_secret: ReadText,
    write_text: WriteText,
    now: str,
) -> int:
    """List the record (no PIN, no text), or export, delete, grant or revoke under the PIN."""
    if request.action == "list":
        summaries = await list_records(limit=request.limit)
        for summary in summaries:
            write_text(summary_line(summary))
        if not summaries:
            write_text("No hay conversaciones guardadas.")
        return 0
    operation, target, description = _conversation_operation(request)
    if request.action == "consent-grant":
        write_text(load_conversation_notice())
    write_text(f"conversations: {description}")
    if not _confirm(request, read_text, write_text):
        return 1
    if not await _grant_pin_if_needed(
        required=True, read_secret=read_secret, write_text=write_text
    ):
        await _audit_conversation(request, operation, target, owner=owner, now=now, refused=True)
        write_text("Sin verificación de la persona titular: no se hizo nada.")
        return 1
    write_text(await _apply_conversation(request, owner, now))
    await _audit_conversation(request, operation, target, owner=owner, now=now)
    return 0


# --- the dispatcher and the entry point -----------------------------------------------------------


async def _read_command(request: AdminRequest, owner: int, write_text: WriteText) -> int:
    """Run one of the read-only sub-commands (``list``, ``status``, ``audit``)."""
    if request.command == "list":
        return await _list(owner, write_text)
    if request.command == "status":
        return await _status(owner, write_text)
    return await _audit(request.limit, write_text)


async def _dispatch(
    request: AdminRequest,
    read_text: ReadText,
    read_secret: ReadText,
    write_text: WriteText,
    now: str,
) -> int:
    await check_db_available()
    owner = await _owner()
    match request.command:
        case "list" | "status" | "audit":
            return await _read_command(request, owner, write_text)
        case "add" | "change":
            return await _edit_literal(request, owner, read_text, read_secret, write_text, now)
        case "revoke":
            return await _revoke(request, read_text, read_secret, write_text, now)
        case "change-contact":
            return await _change_contact(request, owner, read_text, read_secret, write_text, now)
        case "conversations":
            return await _conversations(request, owner, read_text, read_secret, write_text, now)
    raise _RefusedError(f"Subcomando desconocido: {request.command}.")


async def _check_schema(database: Path) -> None:
    """Refuse a database behind the latest schema before it is opened for writing."""
    try:
        version = await asyncio.to_thread(_schema_version, database)
    except sqlite3.Error as exc:
        raise _RefusedError("No se pudo leer la base de datos.") from exc
    if version != db.latest_schema_version():
        raise _RefusedError(
            "La base de datos no está en la última versión: revisa `just setup-personal status`."
        )


def _schema_version(database: Path) -> int:
    """Read ``PRAGMA user_version`` through a read-only connection (no sidecar, no checkpoint)."""
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA user_version").fetchone()
    finally:
        connection.close()
    return 0 if row is None else int(row[0])


async def run_admin_command(
    request: AdminRequest,
    *,
    read_text: ReadText,
    read_secret: ReadText,
    write_text: WriteText,
    now: str,
) -> int:
    """Run the command against the configured database and return its exit code.

    Args:
        request: The parsed invocation.
        read_text: Prompts for and returns one visible line (values, never an argument).
        read_secret: Prompts for and returns the PIN without echo (``getpass`` in ``main``).
        write_text: Prints one line (this terminal only).
        now: UTC ISO 8601 with microseconds, shared by the operation and its audit row.

    Returns:
        ``0`` on success, ``1`` on a refusal or a cancelled write.
    """
    database = settings.brain_db_path.resolve()
    write_text(f"Base de datos: {database}")
    try:
        if not database.is_file():
            raise _RefusedError("No existe la base de datos: créala con `just setup-personal`.")
        await _check_schema(database)
        await db.open_db()
        try:
            return await _dispatch(request, read_text, read_secret, write_text, now)
        finally:
            await db.close_db()
    except (_RefusedError, BrainMemoryError, ValueError) as exc:
        write_text(str(exc))
        return 1


def _server_answers() -> bool:
    """Return whether the server answers ``/health`` on this machine (probed once, 2 s)."""
    try:
        httpx.get(f"http://127.0.0.1:{settings.server_port}/health", timeout=_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return False
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iroko-admin",
        description="Administración local del hogar tras el cierre del alta (servidor apagado).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="muestra el pozo, las relaciones y los contactos")
    sub.add_parser("status", help="muestra el estado de las secciones del acta")
    audit = sub.add_parser("audit", help="muestra la auditoría (sin valores)")
    audit.add_argument("--limit", type=int, default=50)
    for verb in ("add", "change"):
        edit = sub.add_parser(verb, help=f"{verb} un campo del pozo de la persona titular")
        edit.add_argument("field", nargs="+", help="el id de catálogo del campo")
        edit.add_argument("--dry-run", action="store_true")
        edit.add_argument("--actor", nargs="+", help="etiqueta de quien administra")
    revoke = sub.add_parser("revoke", help="revoca una fila por tipo e id")
    revoke.add_argument("kind", choices=list(_KINDS))
    revoke.add_argument("row_id", type=int)
    revoke.add_argument("--dry-run", action="store_true")
    revoke.add_argument("--actor", nargs="+")
    cc = sub.add_parser("change-contact", help="cambia el teléfono de un contacto por su id")
    cc.add_argument("row_id", type=int)
    cc.add_argument("--dry-run", action="store_true")
    cc.add_argument("--actor", nargs="+")
    conv = sub.add_parser(
        "conversations", help="lista, exporta o borra el registro de conversaciones (PIN)"
    )
    conv.add_argument("action", choices=_CONVERSATION_ACTIONS)
    conv.add_argument("--id", dest="row_id", type=int)
    conv.add_argument("--out", type=Path)
    conv.add_argument("--limit", type=int, default=50)
    conv.add_argument("--dry-run", action="store_true")
    conv.add_argument("--actor", nargs="+")
    return parser


def _request(args: argparse.Namespace) -> AdminRequest:
    actor = " ".join(args.actor) if getattr(args, "actor", None) else _DEFAULT_ACTOR
    return AdminRequest(
        command=args.command,
        field=" ".join(args.field) if getattr(args, "field", None) else None,
        kind=getattr(args, "kind", None),
        row_id=getattr(args, "row_id", None),
        limit=getattr(args, "limit", 50),
        dry_run=getattr(args, "dry_run", False),
        actor_label=actor,
        action=getattr(args, "action", None),
        out=getattr(args, "out", None),
    )


def main() -> None:
    """CLI entrypoint for `iroko-admin`."""
    args = _parser().parse_args()
    if _server_answers():
        print("El servidor está encendido: detén `just run-server` antes de administrar.")  # noqa: T201
        sys.exit(1)
    code = asyncio.run(
        run_admin_command(
            _request(args),
            read_text=input,
            read_secret=getpass.getpass,
            write_text=print,
            now=datetime.now(UTC).isoformat(timespec="microseconds"),
        )
    )
    sys.exit(code)
