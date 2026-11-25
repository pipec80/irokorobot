"""The document cue: a closed grammar, no model (Plan 0088 D-11, ADR 0034 decision 3).

A **strong** cue says the owner's possession: «según mis documentos / papeles …», «busca en mis
documentos …», «¿qué dice mi {tipo} de {nombre} sobre …?», «en mi {tipo} de {nombre}, …». A
**weak** one does not: «¿qué dice el/la {tipo} de {nombre} sobre …?», «en el/la {tipo} de
{nombre}, ¿…?». ``{tipo}`` is a closed list. The cue's ``named`` words find the document by its
title; ``query`` is what to look for inside it. Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

from server.cognition.recall_cues import CueStrength, content_words, specific_words
from server.text_keys import normalize_spanish

__all__ = [
    "DOCUMENT_TYPES",
    "DocumentCue",
    "classify_document_cue",
    "is_keep_phrase",
    "is_reading_request",
]

#: The closed list of document types a cue may name (folded).
DOCUMENT_TYPES: Final = (
    "manual",
    "receta",
    "documento",
    "instructivo",
    "guia",
    "carta",
    "informe",
    "contrato",
    "nota",
    "folleto",
    "papel",
)
_TYPES: Final = "|".join(DOCUMENT_TYPES)
_COLLECTION: Final = r"mis (?:documentos|papeles)"
_ALL_SOURCES: Final = (
    re.compile(rf"(?:^| )segun {_COLLECTION} (?P<query>.+)$"),
    re.compile(rf"(?:^| )busca(?:me)? en {_COLLECTION} (?P<query>.+)$"),
)
_WHAT_IT_SAYS: Final = re.compile(
    rf"(?:^| )que dice (?P<det>mi|el|la) (?P<type>{_TYPES}) (?:de|del) (?P<rest>.+)$"
)
_INSIDE: Final = re.compile(rf"^en (?P<det>mi|el|la) (?P<type>{_TYPES}) (?:de|del) (?P<rest>.+)$")
_ABOUT: Final = re.compile(r" (?:sobre|acerca del|acerca de) ")
_OF: Final = re.compile(r" (?:de|del) ")
# The words that open the question inside «en el manual de X, ¿cuánto dura…?» without a comma.
_ASKING: Final = re.compile(
    r" (?:que|cual|cuales|cuanto|cuanta|cuantos|cuantas|como|cuando|donde) "
)


@dataclass(frozen=True)
class DocumentCue:
    """A document question.

    Attributes:
        strength: Strong when the owner's possession is said, else weak.
        named: The content words of «{tipo} {nombre}» (folded); empty for «mis documentos».
        query: What to look for, folded.
        specific: The query's specific words (``recall_cues.specific_words``), the named
            document's words left out.
    """

    strength: CueStrength
    named: tuple[str, ...]
    query: str
    specific: frozenset[str] = frozenset()


def _split_about(rest: str) -> tuple[str, str] | None:
    """``(name, query)`` of «{nombre} sobre {query}», else at the last «de»."""
    if match := _ABOUT.search(rest):
        return rest[: match.start()], rest[match.end() :]
    found = list(_OF.finditer(rest))
    if not found:
        return None
    last = found[-1]
    return rest[: last.start()], rest[last.end() :]


def _split_inside(message: str, rest: str) -> tuple[str, str] | None:
    """``(name, query)`` of «en el {tipo} de {nombre}, ¿query?»: at the comma, else the asking word."""
    if "," in message:
        after = normalize_spanish(message.split(",", 1)[1])
        name = rest.removesuffix(after).strip()
        return (name, after) if after and name else None
    if match := _ASKING.search(rest):
        return rest[: match.start()], rest[match.start() + 1 :]
    return None


def _cue(message: str, strength: CueStrength, named: str, query: str) -> DocumentCue | None:
    named_words = content_words(named)
    if not query.strip() or not content_words(query):
        return None
    excluded = set(named_words) | set(named.split())
    return DocumentCue(
        strength=strength,
        named=named_words,
        query=query.strip(),
        specific=frozenset(specific_words(message) - excluded),
    )


def classify_document_cue(message: str) -> DocumentCue | None:
    """Return the document question *message* asks, or ``None`` when it asks none.

    Args:
        message: Raw transcript or chat text in Spanish.

    Returns:
        The cue; ``None`` for no cue, or a cue with nothing to look for.
    """
    normalized = normalize_spanish(message)
    for pattern in _ALL_SOURCES:
        if match := pattern.search(normalized):
            return _cue(message, CueStrength.STRONG, "", match.group("query"))
    if match := _WHAT_IT_SAYS.search(normalized):
        parts = _split_about(match.group("rest"))
    elif match := _INSIDE.match(normalized):
        parts = _split_inside(message, match.group("rest"))
    else:
        return None
    if parts is None or not content_words(parts[0]):
        return None
    strength = CueStrength.STRONG if match.group("det") == "mi" else CueStrength.WEAK
    return _cue(message, strength, f"{match.group('type')} {parts[0]}", parts[1])


# «Iroko, lee esto» (Plan 0088 D-17): the closed shapes, folded, with the robot's name, a filler
# or «por favor» around them; nothing else may be said in the same turn.
_READING: Final = re.compile(
    r"^(?:(?:iroko|oye|a ver|por favor) )*"
    r"(?:lee esto|le esto|leeme esto|lee lo que dice|lee lo que tengo|lee este papel"
    r"|lee esta pantalla|que dice aqui|que dice aca)"
    r"(?: (?:iroko|por favor))*$"
)
# «sí, guárdalo»: the closed answer to the reading's offer (and ADR 0021's verb).
_KEEP: Final = re.compile(r"^(?:si )?guardalo(?: por favor)?$")


def is_reading_request(message: str) -> bool:
    """Whether *message* asks the robot to read aloud what is in front of the camera.

    Args:
        message: Raw transcript or chat text in Spanish.

    Returns:
        ``True`` for «lee esto» (and the STT's «le esto»), «léeme esto», «lee lo que dice»,
        «lee lo que tengo», «lee este papel», «lee esta pantalla», «¿qué dice aquí / acá?»,
        each alone or with «Iroko», «oye», «a ver» or «por favor» around it (Plan 0089 D-10).
    """
    return bool(_READING.match(normalize_spanish(message)))


def is_keep_phrase(message: str) -> bool:
    """Whether *message* is «sí, guárdalo» (or «guárdalo», with or without «por favor»)."""
    return bool(_KEEP.match(normalize_spanish(message)))
