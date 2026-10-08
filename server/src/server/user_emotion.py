"""The user's emotion for one turn, decided from what the user said (Plan 0059).

Pure and deterministic: no I/O, no logging, no model call. The streamed reply is plain text
and carries no tag; this function is the single place that decides the ``emotion`` event
(ADR 0018). A larger model may later replace it behind the same signature.
"""

from server.llm import FALLBACK_EMOTION


def classify_user_emotion(text: str) -> str:
    """Return the user's emotion for this turn, ``neutral`` unless a feeling is explicit.

    Args:
        text: What the user said, as transcribed.

    Returns:
        A member of ``VALID_EMOTIONS``.
    """
    del text  # skeleton: the rules arrive with Plan 0059 Task 2
    return FALLBACK_EMOTION
