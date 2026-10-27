"""The acta of the alta: a Markdown record with no household value, and the closing (Plan 0072).

ADR 0024 decisions 13 and 14. ``render_acta`` is pure; ``write_acta`` writes the file under a given
directory (``data/commissioning/`` in the real flow, git-ignored); ``close_session`` records the
baseline backup and the modalities, writes the acta and closes the window. The modalities are derived
by the caller (the command) and passed in, so this module stays within the memory layer. The acta
holds only provenance: the date, the interviewer's label and role, the installation id, the consents,
the modalities, each section's status, the file hash, the counts, the backups and the readiness —
never a household value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from server.memory.commissioning import (
    Backup,
    BackupKind,
    close_commissioning,
    get_open_commissioning,
    list_section_statuses,
    read_session_details,
    record_backup,
    record_modalities,
)
from server.memory.commissioning_readiness import readiness_from_json

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from server.memory.commissioning import (
        CommissioningRecord,
        Modality,
        Section,
        SectionStatus,
        SessionDetails,
    )
    from server.memory.commissioning_readiness import CapabilityReadiness

__all__ = ["close_session", "render_acta", "write_acta"]


def _yes_no(value: bool) -> str:
    """Render a boolean as Spanish ``sí``/``no``."""
    return "sí" if value else "no"


def render_acta(
    record: CommissioningRecord,
    details: SessionDetails,
    statuses: Mapping[Section, SectionStatus],
    readiness: tuple[CapabilityReadiness, ...],
) -> str:
    """Render the acta of a commissioning as Markdown; it carries no household value.

    Args:
        record: The commissioning record (provenance, never a household value).
        details: The acta columns the session filled.
        statuses: The status of each pool section.
        readiness: The readiness of each capability that exists today.

    Returns:
        The acta's Markdown text.
    """
    consents = details.consents
    lines = [
        "# Acta de puesta en marcha",
        "",
        f"- **Instalación:** {record.installation_id}",
        f"- **Fecha de inicio:** {record.started_at}",
        f"- **Entrevistador:** {record.interviewer_label} ({record.interviewer_role.value})",
        f"- **Modo de confirmación:** {record.confirmation_mode.value}",
        f"- **Cifrado de disco declarado:** {record.disk_encryption.value}",
        f"- **Versión del pozo de datos:** {record.pool_version}",
        f"- **Hash del archivo:** {record.seed_file_sha256 or '—'}",
        f"- **Aviso biométrico:** {details.biometric_notice_version or '—'}",
        "",
        "## Consentimientos del plano de operaciones",
    ]
    if consents is None:
        lines.append("- No registrados.")
    else:
        lines.extend(
            [
                f"- Telemetría: {_yes_no(consents.telemetry)}",
                f"- Soporte remoto: {_yes_no(consents.remote_support)}",
                f"- Respaldo: {_yes_no(consents.backup)} (destino: "
                f"{consents.backup_destination or '—'})",
            ]
        )
    lines += ["", "## Modalidades enroladas"]
    lines.append("- " + (", ".join(sorted(m.value for m in details.modalities)) or "ninguna"))
    lines += ["", "## Conteos"]
    lines += [f"- {name}: {value}" for name, value in sorted(record.counts.items())] or ["- —"]
    lines += ["", "## Respaldos", f"- {_backup_line('Pre-reset', details.pre_reset_backup)}"]
    lines.append(f"- {_backup_line('Base', details.baseline_backup)}")
    lines += ["", "## Estado de las secciones"]
    lines += [f"- {section.value}: {status.value}" for section, status in statuses.items()]
    lines += ["", "## Informe de preparación por capacidad"]
    lines += [f"- {item.capability.value}: {item.verdict.value}" for item in readiness] or ["- —"]
    return "\n".join(lines) + "\n"


def _backup_line(label: str, backup: Backup | None) -> str:
    """Render a backup as ``<label>: <path> (destruir el <date>)`` or an em dash."""
    if backup is None:
        return f"{label}: —"
    return f"{label}: {backup.reference} (destruir el {backup.destroy_by})"


async def write_acta(record_id: int, *, out_dir: Path) -> Path:
    """Render and write the acta of the open commissioning under *out_dir*.

    Args:
        record_id: The open commissioning.
        out_dir: The directory to write into (created if missing; git-ignored in the real flow).

    Returns:
        The path of the written acta, named by the installation id.

    Raises:
        ValueError: If no commissioning with that id is open.
    """
    record = await get_open_commissioning()
    if record is None or record.id != record_id:
        raise ValueError(f"commissioning {record_id} is not open")
    details = await read_session_details(record_id)
    statuses = await list_section_statuses(record_id)
    readiness = readiness_from_json(details.readiness_json) if details.readiness_json else ()
    text = render_acta(record, details, statuses, readiness)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"acta-{record.installation_id}.md"
    path.write_text(text, encoding="utf-8")
    return path


async def close_session(
    record_id: int,
    *,
    baseline_reference: str,
    baseline_destroy_by: str,
    modalities: frozenset[Modality],
    out_dir: Path,
    now: str,
) -> Path:
    """Record the baseline backup and the modalities, write the acta and close the window.

    The readiness report is recorded by the caller (the command owns the typed hardware) before this
    runs; ``write_acta`` reads it back for the acta.

    Args:
        record_id: The open commissioning.
        baseline_reference: The baseline backup's path.
        baseline_destroy_by: Its destruction date (``YYYY-MM-DD``).
        modalities: The modalities enrolled, derived by the caller.
        out_dir: Where to write the acta.
        now: The closing time, as UTC ISO 8601.

    Returns:
        The path of the written acta.

    Raises:
        CommissioningClosedError: If the commissioning is already closed.
    """
    await record_backup(
        record_id,
        which=BackupKind.BASELINE,
        reference=baseline_reference,
        destroy_by=baseline_destroy_by,
    )
    await record_modalities(record_id, modalities)
    path = await write_acta(record_id, out_dir=out_dir)
    await close_commissioning(record_id, now)
    return path
