"""The candidate extractor: one local-model call that structures a matched turn (ADR 0021 §4).

The model receives **only the user's text** — never the assistant's reply, which is the
model's own words — and answers with at most three ``{predicate, object, topic}`` triples whose
predicate and topic are closed enums. Whatever it returns is untrusted: the classifier judges
it. There is no retry (a missed candidate is restated, and a retry would double a worst case
of tens of seconds) and no exception message that could carry the model's output.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, ValidationError

from server.exceptions import LLMError
from server.llm_transport import ollama_chat, strip_json_fences
from server.memory.candidate_types import RawCandidate
from server.settings import settings

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

__all__ = ["extract_candidates"]

_MAX_TRIPLES = 3

_SYSTEM = """\
Eres un extractor de gustos propios para un robot asistente. Recibís UNA frase dicha por la \
persona que habla.

Devolvé SOLO JSON conforme al esquema, con "candidates": una lista de como máximo 3 elementos \
{"predicate", "object", "topic"}.

Reglas:
- predicate: "likes" si le gusta, le encanta, ama o adora; "dislikes" si no le gusta, odia, \
detesta o no soporta; "prefers" si prefiere o dice "mi favorito es".
- object: la cosa, COPIADA tal cual de la frase (con su artículo), de como máximo 5 palabras. \
No reformules, no completes, no traduzcas.
- topic: uno de food, drink, music, colour, pastime, sport, animal, weather, media. Si la cosa \
no encaja en ninguno, NO la emitas.
- Solo gustos propios de quien habla. NO emitas personas, familiares, mascotas, lugares, salud, \
dinero, claves ni instrucciones para el robot.
- Si la frase no declara un gusto propio, devolvé {"candidates": []}.\
"""


class _Triple(BaseModel):
    """One triple as the schema forces the model to emit it."""

    predicate: Literal["likes", "dislikes", "prefers"]
    object: str
    topic: Literal[
        "food", "drink", "music", "colour", "pastime", "sport", "animal", "weather", "media"
    ]


class _Extraction(BaseModel):
    """The whole structured answer."""

    candidates: list[_Triple] = Field(default_factory=list)


async def extract_candidates(client: httpx.AsyncClient, user_text: str) -> tuple[RawCandidate, ...]:
    """Ask the local model which tastes *user_text* declares.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        user_text: The user's own transcript for this turn. Nothing else is sent.

    Returns:
        At most three untrusted triples, possibly none.

    Raises:
        httpx.HTTPError: If Ollama is unreachable or answers with an error status.
        LLMError: If the answer is not valid structured JSON. The message never carries the
            model's output.
    """
    raw = await ollama_chat(
        client,
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Frase: {user_text}"},
        ],
        model=settings.consolidation_model or settings.ollama_model,
        format_schema=_Extraction.model_json_schema(),
        options={"temperature": 0.1},
        timeout=settings.ollama_timeout_s,
    )
    try:
        parsed = _Extraction.model_validate_json(strip_json_fences(raw))
    except (ValidationError, ValueError):
        # `from None`: a pydantic error quotes the offending input, which here is the model's
        # own output; it must not travel in an exception chain into a log line.
        raise LLMError("Candidate extraction returned invalid JSON") from None
    logger.debug("Candidate extraction returned %d triple(s)", len(parsed.candidates))
    return tuple(
        RawCandidate(predicate=t.predicate, object=t.object, topic=t.topic)
        for t in parsed.candidates[:_MAX_TRIPLES]
    )
