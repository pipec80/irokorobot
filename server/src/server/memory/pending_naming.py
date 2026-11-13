"""The topic of a pending plan, named by the local model in the owner's words (Plan 0084 D-6).

One call in the conversation job, never on a live turn: the model receives **only the owner's
words** of the turn and answers ``{"topic": "…"}`` at temperature 0. The answer is untrusted: it
is kept only when it is one to four words of letters, at most 40 characters, and every word but a
leading article is copied from the turn («el banco» for «voy al banco»). Nothing here logs a text,
and no exception message carries the model's output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ValidationError

from server.exceptions import LLMError
from server.llm_transport import ollama_chat, strip_json_fences
from server.settings import settings
from server.text_keys import ARTICLES, normalize_spanish

if TYPE_CHECKING:
    import httpx

__all__ = ["MAX_TOPIC_CHARS", "MAX_TOPIC_WORDS", "is_copied_topic", "name_topic"]

MAX_TOPIC_WORDS: Final = 4
MAX_TOPIC_CHARS: Final = 40
_EDGE_PUNCTUATION: Final = " .,;:!?¡¿\"'«»"

_SYSTEM = """\
Eres un asistente que nombra el tema de un plan. Recibes UNA frase dicha por una persona sobre \
algo que va a hacer.

Responde SOLO JSON conforme al esquema: {"topic": "..."}.

Reglas:
- topic: de una a cuatro palabras, con su artículo, COPIADAS de la frase: el lugar, la cita o la \
actividad («el banco», «el médico», «la reunión»).
- No inventes, no completes, no traduzcas: toda palabra del tema está en la frase.
- Si no hay un tema claro, responde {"topic": ""}.\
"""


class _Naming(BaseModel):
    """The structured answer the schema forces."""

    topic: str


def _cleaned(topic: str) -> str:
    """The topic without surrounding punctuation and with single spaces."""
    return " ".join(topic.strip(_EDGE_PUNCTUATION).split())


def is_copied_topic(topic: str, heard: str) -> bool:
    """Return whether *topic* is a valid topic copied from the owner's words (D-6).

    Args:
        topic: The cleaned topic the model answered.
        heard: The owner's words of the turn.

    Returns:
        ``True`` for one to four words of letters, at most ``MAX_TOPIC_CHARS`` characters, with
        at least one word that is not an article and every word but a leading article among the
        folded words of *heard*.
    """
    words = topic.split()
    if not 1 <= len(words) <= MAX_TOPIC_WORDS or len(topic) > MAX_TOPIC_CHARS:
        return False
    if not all(word.isalpha() for word in words):
        return False
    folded = normalize_spanish(topic).split()
    # The model may choose the article («una reunión» is said «la reunión»), never another word.
    if folded[0] in ARTICLES:
        folded = folded[1:]
    return bool(folded) and set(folded) <= set(normalize_spanish(heard).split())


async def name_topic(client: httpx.AsyncClient, heard: str) -> str | None:
    """Ask the local model to name the topic of the owner's plan in their own words.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        heard: The owner's words of the turn. Nothing else is sent.

    Returns:
        The cleaned topic, or ``None`` for an empty or invented answer (the caller drops the
        topic: one it cannot name is not kept).

    Raises:
        httpx.HTTPError: If Ollama is unreachable or answers with an error status; the caller
            keeps the topic unnamed for a later tick.
        TimeoutError: If the call times out, likewise.
        LLMError: If the answer is empty or not the schema (a model failure, kept for a later
            tick too). The message never carries the model's output.
    """
    raw = await ollama_chat(
        client,
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": heard}],
        model=settings.consolidation_model or settings.ollama_model,
        format_schema=_Naming.model_json_schema(),
        options={"temperature": 0.0},
        timeout=settings.ollama_timeout_s,
    )
    try:
        topic = _cleaned(_Naming.model_validate_json(strip_json_fences(raw)).topic)
    except (ValidationError, ValueError):
        # `from None`: a pydantic error quotes the model's own output, which must not travel in an
        # exception chain into a log line.
        raise LLMError("Pending topic naming returned an answer that is not the schema") from None
    return topic if is_copied_topic(topic, heard) else None
