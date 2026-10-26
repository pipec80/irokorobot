"""The `seed-import` command: load a household's seed file, dry run by default (Plan 0071).

Local administration (ADR 0024 decision 11): whoever runs it on the server's machine, with the
server stopped. It opens an existing database at the latest schema and never creates or migrates
one, prints the database it uses, runs a dry run that writes nothing, and applies only after the
interviewer answers the owner's review question with exactly ``SI``. The report shows the values
on this terminal only; no value reaches a log.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import sys

import httpx

from server import db
from server.exceptions import (
    BrainMemoryError,
    CommissioningClosedError,
    CommissioningMissingError,
    ReplaceBlockedError,
    ReplaceRefusedError,
    SeedFileError,
    SeedOwnerError,
)
from server.memory.candidates import iso_utc
from server.memory.commissioning import (
    CommissioningInput,
    ConfirmationMode,
    DiskEncryption,
    InterviewerRole,
    Section,
    SectionStatus,
    get_open_commissioning,
)
from server.memory.seed_file import LoadedSeed, json_schema_text, load_seed_file
from server.memory.seed_import import (
    OperationOutcome,
    OperationStatus,
    SeedReport,
    resolve_ready_owner,
)
from server.memory.seed_plan import OWNER_REF, OperationKind, SeedPlan, SeedRef, build_plan
from server.memory.seed_run import run_seed
from server.personal_setup import check_db_available
from server.settings import settings

__all__ = ["main", "run_seed_command"]

type ReadText = Callable[[str], str]
type WriteText = Callable[[str], None]

_CONFIRMATION_TOKEN = "SI"  # noqa: S105 — the typed confirmation word, not a secret
_EXAMPLE_SUFFIX = ".example.toml"
_PROBE_TIMEOUT_S = 2.0
# The repository this module lives in; a seed file inside it belongs under data/ (gitignored).
_REPOSITORY = Path(__file__).resolve().parents[3]
_STATUS_WORDS = {
    OperationStatus.WRITTEN: "escribe",
    OperationStatus.UNCHANGED: "sin cambios",
    OperationStatus.REFUSED: "RECHAZADO",
    OperationStatus.SKIPPED: "OMITIDO",
}
_SECTION_WORDS = {
    SectionStatus.PROVIDED: "con datos",
    SectionStatus.NONE: "no tiene",
    SectionStatus.UNKNOWN: "no se sabe",
    SectionStatus.DECLINED: "no quiso decir",
    SectionStatus.NOT_ASKED: "no preguntada",
}
_REVIEW = {
    ConfirmationMode.OWNER_IN_PERSON: "¿La persona titular revisó este resumen y lo aprueba?",
    ConfirmationMode.BUILDER_IS_OWNER: "¿La persona titular revisó este resumen y lo aprueba?",
    ConfirmationMode.REPRESENTATIVE: (
        "¿La persona que representa a la titular revisó este resumen y lo aprueba?"
    ),
}
_REMINDERS = (
    "Recuerda: el archivo tiene datos reales y no se borró; créalo solo en esta máquina.",
    "Este informe queda en el historial de la terminal: limpia la pantalla al terminar (cls).",
)


class _RefusedError(Exception):
    """A refusal of the command itself; its message is closed and printed as is."""


def _names(plan: SeedPlan, owner_name: str) -> dict[SeedRef, str]:
    """The display name of every entity of the plan (for this terminal only)."""
    names = {OWNER_REF: owner_name}
    for operation in plan.operations:
        if operation.kind is OperationKind.CREATE_ENTITY and operation.subject is not None:
            names[operation.subject] = operation.entity_name or ""
    return names


def _describe(outcome: OperationOutcome, names: dict[SeedRef, str]) -> str:
    """One line of the report: the status, the safe label and the value it is about."""
    operation = outcome.operation
    subject = names.get(operation.subject or OWNER_REF, "")
    match operation.kind:
        case OperationKind.CREATE_ENTITY:
            what = subject
        case OperationKind.WRITE_RELATION:
            what = f"{subject} -> {names.get(operation.target or OWNER_REF, '')}"
        case OperationKind.WRITE_LITERAL:
            what = operation.value or ""
        case _:
            terms = operation.attributes
            phones = " / ".join(str(terms[k]) for k in ("phone", "phone_alt") if terms.get(k))
            what = f"{subject} ({terms.get('role')}) {phones}"
    reason = f" [{outcome.reason}]" if outcome.reason else ""
    return f"  {_STATUS_WORDS[outcome.status]}{reason}  {operation.label}: {what}"


def _print_report(report: SeedReport, names: dict[SeedRef, str], write_text: WriteText) -> None:
    """Print every operation, the section statuses and the totals, in Spanish."""
    write_text("Operaciones:")
    for outcome in report.outcomes:
        write_text(_describe(outcome, names))
    write_text("Secciones:")
    for section in Section:
        write_text(f"  {section.value}: {_SECTION_WORDS[report.statuses[section]]}")
    written = sum(o.status is OperationStatus.WRITTEN for o in report.outcomes)
    unchanged = sum(o.status is OperationStatus.UNCHANGED for o in report.outcomes)
    write_text(
        f"Total: {written} por escribir, {unchanged} sin cambios, {len(report.problems)} problemas."
    )


def _schema_version(database: Path) -> int:
    """Read ``PRAGMA user_version`` through a read-only connection.

    A read-only connection never checkpoints the write-ahead log, so a refusal leaves the file
    byte for byte as it was (a read-write open and close would fold the log into it).
    """
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA user_version").fetchone()
    finally:
        connection.close()
    return 0 if row is None else int(row[0])


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


def _check_request(path: Path, *, apply: bool, commissioning: CommissioningInput | None) -> None:
    """Refuse what can be refused before the database is touched."""
    if apply and path.name.endswith(_EXAMPLE_SUFFIX):
        raise _RefusedError(
            "Esta es la plantilla: copia la plantilla a data/seed/ y complétala allí."
        )
    if (
        commissioning is not None
        and commissioning.confirmation_mode is ConfirmationMode.BUILDER_IS_OWNER
        and commissioning.interviewer_role is not InterviewerRole.BUILDER
    ):
        raise _RefusedError("--mode builder_is_owner necesita --role builder.")


def _warn_about_the_place(path: Path, write_text: WriteText) -> None:
    resolved = path.resolve()
    inside = resolved.is_relative_to(_REPOSITORY)
    if inside and not resolved.is_relative_to(_REPOSITORY / "data"):
        write_text(
            "Aviso: el archivo está dentro del repositorio pero fuera de data/ (git lo vería)."
        )


async def _review_mode(commissioning: CommissioningInput | None) -> ConfirmationMode:
    """The confirmation mode of the open record, or the one declared for the first apply."""
    record = await get_open_commissioning()
    if record is not None:
        return record.confirmation_mode
    if commissioning is None:
        raise CommissioningMissingError
    return commissioning.confirmation_mode


async def _load_session(
    loaded: LoadedSeed,
    *,
    apply: bool,
    replace: bool,
    commissioning: CommissioningInput | None,
    read_text: ReadText,
    write_text: WriteText,
    now: str,
) -> int:
    """Everything the command does once the database is open."""
    await check_db_available()
    owner = await resolve_ready_owner(loaded.seed.owner.name)
    mode = await _review_mode(commissioning) if apply else None
    plan = build_plan(loaded.seed)
    names = _names(plan, loaded.seed.owner.name)
    dry = await run_seed(
        loaded,
        plan,
        owner_entity_id=owner,
        commit=False,
        approved=False,
        commissioning=commissioning,
        replace=replace,
        now=now,
    )
    _print_report(dry, names, write_text)
    if dry.problems:
        write_text("Hay problemas: no se escribió nada.")
        return 1
    if mode is None:
        write_text("Prueba en seco: no se escribió nada. Para aplicar, agrega --apply.")
        return 0
    write_text(_REVIEW[mode])
    if read_text(f"Escribe {_CONFIRMATION_TOKEN} para aplicar: ") != _CONFIRMATION_TOKEN:
        write_text("Carga cancelada.")
        return 1
    applied = await run_seed(
        loaded,
        plan,
        owner_entity_id=owner,
        commit=True,
        approved=True,
        commissioning=commissioning,
        replace=replace,
        now=now,
    )
    if not applied.applied:
        write_text("La carga cambió entre la prueba y la aplicación: no se escribió nada.")
        return 1
    write_text(f"Carga aplicada (acta {applied.record_id}).")
    return 0


_REFUSALS: dict[type[Exception], str] = {
    CommissioningClosedError: "El alta ya se cerró: el importador no corre después del cierre.",
    CommissioningMissingError: (
        "La primera carga necesita --interviewer, --role, --mode y --disk-encryption."
    ),
    ReplaceRefusedError: "El robot ya aprendió algo por voz: --replace ya no está disponible.",
    ReplaceBlockedError: (
        "Una persona importada antes tiene datos en otra tabla (un rol, una cara, una voz o un "
        "consentimiento): el reemplazo no la puede borrar. No se escribió nada."
    ),
}
_OWNER_REFUSALS = {
    "owner_name_mismatch": (
        "El nombre de la persona titular del archivo no coincide con el registrado."
    ),
    "owner_not_ready": "No hay una persona titular lista: corre `just setup-personal` primero.",
}


def _refusal(exc: Exception) -> list[str]:
    """The closed lines that explain a refusal; never a value of the file."""
    if isinstance(exc, SeedFileError):
        return ["El archivo tiene errores:", *(f"  {problem}" for problem in exc.problems)]
    if isinstance(exc, SeedOwnerError):
        return [_OWNER_REFUSALS[exc.reason]]
    return [_REFUSALS.get(type(exc), str(exc))]


async def run_seed_command(
    path: Path,
    *,
    apply: bool,
    replace: bool,
    commissioning: CommissioningInput | None,
    read_text: ReadText,
    write_text: WriteText,
    now: str,
) -> int:
    """Run the command against the configured database and return its exit code.

    Args:
        path: The seed file.
        apply: Ask the review question and apply on ``SI``; otherwise a dry run only.
        replace: Retract what earlier imports wrote first (only while commissioning).
        commissioning: The interviewer's declaration; required for the first apply.
        read_text: Prompts for and returns one line.
        write_text: Prints one line.
        now: UTC ISO 8601 with microseconds, shared by every row of the run.

    Returns:
        ``0`` when the dry run had no problem or the load was applied; ``1`` otherwise.
    """
    database = settings.brain_db_path.resolve()
    write_text(f"Base de datos: {database}")
    try:
        _check_request(path, apply=apply, commissioning=commissioning)
        if not database.is_file():
            raise _RefusedError("No existe la base de datos: créala con `just setup-personal`.")
        _warn_about_the_place(path, write_text)
        loaded = load_seed_file(path)
        await _check_schema(database)
        await db.open_db()
        try:
            code = await _load_session(
                loaded,
                apply=apply,
                replace=replace,
                commissioning=commissioning,
                read_text=read_text,
                write_text=write_text,
                now=now,
            )
        finally:
            await db.close_db()
    except (_RefusedError, BrainMemoryError, ValueError) as exc:
        for line in _refusal(exc):
            write_text(line)
        return 1
    for line in _REMINDERS:
        write_text(line)
    return code


def _server_answers() -> bool:
    """Return whether the server answers ``/health`` on this machine (probed once, 2 s)."""
    try:
        httpx.get(f"http://127.0.0.1:{settings.server_port}/health", timeout=_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return False
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed-import",
        description="Carga el expediente del hogar (prueba en seco por defecto).",
    )
    parser.add_argument("path", nargs="*", help="el archivo .toml (los espacios se unen)")
    parser.add_argument("--apply", action="store_true", help="aplicar tras la revisión")
    parser.add_argument("--replace", action="store_true", help="reemplazar la carga anterior")
    parser.add_argument("--interviewer", nargs="+", help="quién entrevistó (primera carga)")
    parser.add_argument("--role", choices=[r.value for r in InterviewerRole])
    parser.add_argument("--mode", choices=[m.value for m in ConfirmationMode])
    parser.add_argument("--disk-encryption", choices=["yes", "no", "unknown"])
    parser.add_argument("--print-schema", action="store_true", help="imprime el JSON Schema")
    return parser


_DISK = {
    "yes": DiskEncryption.DECLARED_YES,
    "no": DiskEncryption.DECLARED_NO,
    "unknown": DiskEncryption.UNKNOWN,
}


def _declaration(args: argparse.Namespace) -> CommissioningInput | None:
    """The interviewer's declaration, or ``None`` unless all four options are given."""
    if not (args.interviewer and args.role and args.mode and args.disk_encryption):
        return None
    return CommissioningInput(
        interviewer_label=" ".join(args.interviewer),
        interviewer_role=InterviewerRole(args.role),
        confirmation_mode=ConfirmationMode(args.mode),
        disk_encryption=_DISK[args.disk_encryption],
    )


def main() -> None:
    """CLI entrypoint for `seed-import`."""
    parser = _parser()
    args = parser.parse_args()
    if args.print_schema:
        print(json_schema_text(), end="")  # noqa: T201 — CLI adapter, not application logging
        return
    if not args.path:
        parser.error("falta la ruta del archivo")
    if _server_answers():
        print("El servidor está encendido: detén `just run-server` antes de importar.")  # noqa: T201
        sys.exit(1)
    code = asyncio.run(
        run_seed_command(
            Path(" ".join(args.path)),
            apply=args.apply,
            replace=args.replace,
            commissioning=_declaration(args),
            read_text=input,
            write_text=print,
            now=iso_utc(datetime.now(UTC)),
        )
    )
    sys.exit(code)
