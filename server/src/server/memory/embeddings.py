"""The embedding dimension the recall index is built for.

Vector encoding in the recall store: ``struct.pack`` of ``N`` IEEE-754 float32 values; the
vectors themselves come from ``llm_transport.ollama_embed``.
"""

from __future__ import annotations

from typing import Final

# Fixed by design, NOT an environment setting. The legacy `vec_memories` index that used it went
# away with migration 013 (Plan 0076); the recall index of CM-5b fixes the dimension in its own
# table, so changing this value means migrating that table — never a hot env-var change.
EMBEDDING_DIM: Final[int] = 768
