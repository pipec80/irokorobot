"""What `iroko-admin conversations` does: list, render and export the record (Plan 0076).

The command's flow (the PIN, the ``SI`` confirmation, ``--dry-run`` and the audit row) stays in
``admin_cli``; this module only reads the record and writes the readable files. It never imports
``admin_cli``. Nothing here logs a text: the export goes to files the owner reads and deletes.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Final

from server.memory.conversation_episodes import get_episode
from server.memory.conversation_record import list_records, read_record
from server.memory.conversation_types import TurnVerdict

if TYPE_CHECKING:
    from pathlib import Path

    from server.memory.conversation_episodes import Episode
    from server.memory.conversation_record import RecordSummary, RecordView

__all__ = ["export_records", "render_record", "summary_line"]

_EXPORT_LIMIT: Final = 1_000_000
_SPEAKER: Final = {
    TurnVerdict.VERIFIED: "tu voz verificada",
    TurnVerdict.NOT_VERIFIED: "tu cara, voz no verificada",
    TurnVerdict.NOT_OWNER: "otra persona o sin cara",
    TurnVerdict.NOT_CHECKED: "sin revisar",
}


def _yes_no(value: bool) -> str:
    return "sí" if value else "no"


def summary_line(summary: RecordSummary) -> str:
    """Return one line of a record's metadata; never a text.

    Args:
        summary: The record's metadata.

    Returns:
        ``<id>  <start> → <end>  <n> intercambios  <bytes> B  elegible <sí|no>  diario <status>``.
    """
    end = summary.closed_at or "abierta"
    return (
        f"{summary.id}  {summary.started_at} → {end}  {summary.turn_count} intercambios  "
        f"{summary.byte_count} B  elegible {_yes_no(summary.eligible)}  "
        f"diario {summary.episode_status.value}"
    )


def render_record(view: RecordView, episode: Episode | None) -> str:
    """Render one record as a readable Markdown text.

    Args:
        view: The record with its exchanges.
        episode: Its diary entry, if any.

    Returns:
        The text written to ``conversacion-<id>.md``.
    """
    summary = view.summary
    previous = "—" if summary.previous_id is None else str(summary.previous_id)
    resumen = (
        "- Resumen: sin resumen"
        if episode is None
        else f"- Resumen ({episode.sensitivity}): {episode.summary}"
    )
    lines = [
        f"# Conversación {summary.id}",
        "",
        f"- Inicio: {summary.started_at} UTC · Fin: {summary.closed_at or 'abierta'} UTC",
        f"- Segmento anterior: {previous} · Elegible: {_yes_no(summary.eligible)} · "
        f"Caduca: {summary.expires_at or '—'}",
        resumen,
        "",
    ]
    for turn in view.turns:
        clock = turn.at.astimezone(UTC).strftime("%H:%M:%S")
        lines.append(f"[{clock}] Persona ({_SPEAKER[turn.voice]}): {turn.heard}")
        lines.append(f"[{clock}] Iroko: {turn.said}")
    return "\n".join(lines) + "\n"


async def export_records(out_dir: Path, *, record_id: int | None) -> int:
    """Write one ``conversacion-<id>.md`` per record (or only *record_id*) into *out_dir*.

    Args:
        out_dir: The destination folder; created when missing.
        record_id: One record, or ``None`` for all of them.

    Returns:
        How many files were written.

    Raises:
        OSError: If the folder or a file cannot be written.
        BrainMemoryError: If a record holds a malformed exchange.
    """
    if record_id is None:
        ids = [summary.id for summary in await list_records(limit=_EXPORT_LIMIT)]
    else:
        ids = [record_id]
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for one in ids:
        view = await read_record(one)
        if view is None:
            continue
        text = render_record(view, await get_episode(one))
        (out_dir / f"conversacion-{one}.md").write_text(text, encoding="utf-8", newline="\n")
        written += 1
    return written
