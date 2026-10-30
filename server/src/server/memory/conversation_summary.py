"""The diary summary of one conversation: one local-model call over the owner's part (Plan 0076).

The model sees **only** ``owner_part(turns)`` — the owner's verified exchanges, each with the
robot's reply as context — so a stranger's words, an unverified clip or a deterministic reply
never reach it (ADR 0027 decision 2). The answer is untrusted: it is validated, cleaned and cut.
Nothing here logs a text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ValidationError

from server.exceptions import LLMError
from server.llm_transport import ollama_chat, strip_json_fences
from server.memory.conversation_types import owner_part
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    import httpx

    from server.memory.conversation_types import RecordedTurn

logger = logging.getLogger(__name__)

__all__ = [
    "NOTHING_TO_REMEMBER",
    "EpisodeDraft",
    "EpisodeSensitivity",
    "summarize_owner_part",
    "summary_input",
]

#: What the model writes when the owner told nothing worth remembering; such a record gets no episode.
NOTHING_TO_REMEMBER: Final = "Conversación sin datos para recordar."

type EpisodeSensitivity = Literal["normal", "private", "medical", "location", "security"]

_WHITESPACE = re.compile(r"\s+")

_SYSTEM = """\
Resumes, para el diario de un robot de compañía, lo que una persona le contó en una conversación.
Recibes solo las frases de esa persona y lo que el robot respondió a cada una.
Reglas:
- Escribe en español, de una a tres frases, en tercera persona neutra: «La persona contó que…».
- Usa solo lo que dijo la persona. Lo que dijo el robot es contexto, nunca una fuente.
- No inventes, no supongas y no agregues nada que no esté en el texto.
- Si la persona no contó nada que valga la pena recordar, escribe exactamente: \
«Conversación sin datos para recordar.»
- Clasifica la sensibilidad del resumen: "normal", "private" (algo íntimo), "medical" (salud), \
"location" (dónde vive o está) o "security" (claves, códigos o accesos). Si dudas, usa la más \
protectora.
Responde solo con JSON: {"summary": "...", "sensitivity": "..."}"""


class _Draft(BaseModel):
    summary: str
    sensitivity: Literal["normal", "private", "medical", "location", "security"]


@dataclass(frozen=True)
class EpisodeDraft:
    """The model's validated summary; its ``repr`` never shows the text."""

    summary: str = field(repr=False)
    sensitivity: EpisodeSensitivity


def summary_input(turns: Sequence[RecordedTurn]) -> str:
    """Render the owner's part of a record as the model's input; nothing else is included.

    Args:
        turns: Every exchange of the record.

    Returns:
        ``Persona: …`` / ``Robot: …`` lines for the verified exchanges only, oldest first.
    """
    lines: list[str] = []
    for turn in owner_part(turns):
        lines.append(f"Persona: {turn.heard}")
        lines.append(f"Robot: {turn.said}")
    return "\n".join(lines)


async def summarize_owner_part(
    client: httpx.AsyncClient, turns: Sequence[RecordedTurn]
) -> EpisodeDraft:
    """Ask the local model for the diary summary of the owner's part.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        turns: Every exchange of the record; only the owner's part is sent.

    Returns:
        The validated draft, its summary on one line and cut at ``CONVERSATION_EPISODE_MAX_CHARS``.

    Raises:
        httpx.HTTPError: If Ollama is unreachable or answers with an error status.
        LLMError: If the answer is not valid JSON or the summary is empty. The message never
            carries the model's output.
    """
    raw = await ollama_chat(
        client,
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": summary_input(turns)},
        ],
        model=settings.consolidation_model or settings.ollama_model,
        format_schema=_Draft.model_json_schema(),
        options={"temperature": 0.1},
        timeout=settings.ollama_timeout_s,
    )
    try:
        parsed = _Draft.model_validate_json(strip_json_fences(raw))
    except (ValidationError, ValueError):
        # `from None`: a pydantic error quotes the model's output; it must not reach a log.
        raise LLMError("Episode summary returned invalid JSON") from None
    summary = _WHITESPACE.sub(" ", parsed.summary).strip()[
        : settings.conversation_episode_max_chars
    ]
    if not summary:
        raise LLMError("Episode summary was empty")
    return EpisodeDraft(summary=summary, sensitivity=parsed.sensitivity)
