"""Build MemoryContext for a single conversation turn.

Three retrieval paths feed the context:
1. Relational — words like "hijos"/"mascota" trigger reverse fact lookups
   (guaranteed recall for family questions that name no entity).
2. Forward — capitalised/long tokens looked up as entity names.
3. Semantic — vector search over episodic/semantic memories.
"""

from __future__ import annotations

import logging
import re

from server.memory.declarative import load_entity_with_facts
from server.memory.lexicon import STOPWORDS_ES
from server.memory.relations import entities_for_relations
from server.memory.semantic import search_memories
from server.schemas import EntityWithFacts, MemoryContext

logger = logging.getLogger(__name__)

# Matches words of 4+ chars including Spanish accented chars.
_TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{4,}")
_MAX_CANDIDATES = 5


def _candidates(text: str) -> list[str]:
    """Extract entity name candidates from *text*.

    Stopwords are discarded first; capitalised tokens are prioritised
    (likely proper nouns) and remaining tokens fill up to
    ``_MAX_CANDIDATES``.

    Args:
        text: Raw user input text.

    Returns:
        Up to ``_MAX_CANDIDATES`` unique token candidates.
    """
    tokens = [t for t in _TOKEN_RE.findall(text) if t.lower() not in STOPWORDS_ES]
    capitalised = [t for t in tokens if t[0].isupper()]
    rest = [t for t in tokens if not t[0].isupper()]
    return list(dict.fromkeys(capitalised + rest))[:_MAX_CANDIDATES]


async def build_context(user_text: str) -> MemoryContext:
    """Build a ``MemoryContext`` for *user_text*.

    1. Resolves relation words ("mis hijos") via reverse fact lookup.
    2. Extracts candidate entity names and looks each up in declarative
       memory (deduped against the relational hits).
    3. Runs a semantic search for related memories.

    Args:
        user_text: Raw text from the current user turn.

    Returns:
        ``MemoryContext`` with resolved entities and top-K memory hits.
    """
    entities: list[EntityWithFacts] = []
    seen_ids: set[int] = set()

    for ent in await entities_for_relations(user_text):
        if ent.id not in seen_ids:
            entities.append(ent)
            seen_ids.add(ent.id)

    for candidate in _candidates(user_text):
        found = await load_entity_with_facts(candidate)
        if found is not None and found.id not in seen_ids:
            entities.append(found)
            seen_ids.add(found.id)

    memories = await search_memories(user_text)
    logger.info(
        "Context built: entities=%d memories=%d (%d chars in)",
        len(entities),
        len(memories),
        len(user_text),
        extra={
            "event": "memory.context_built",
            "entities": len(entities),
            "memories": len(memories),
            "chars": len(user_text),
        },
    )
    return MemoryContext(entities=entities, memories=memories)
