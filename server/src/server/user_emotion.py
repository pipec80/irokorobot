"""The user's emotion for one turn, decided from what the user said (Plan 0059).

Pure and deterministic: no I/O, no logging, no model call. The streamed reply is plain text
and carries no tag; this function is the single place that decides the ``emotion`` event
(ADR 0018). A larger model may later replace it behind the same signature.

The rules are precision-first (D-7): the result is a feeling only when the user states one
explicitly in the first person. Negation, questions, quotations, reported speech, hypotheticals
and sarcasm stay ``neutral``; a missed feeling is cheap, an invented one is not.
"""

import re
import unicodedata

from server.llm import FALLBACK_EMOTION

_INTENSIFIER = r"(?:(?:muy|tan|super|re|bien|realmente|demasiado|bastante|un poco) )?"


def _state(*words: str) -> str:
    """Build the pattern for 'estoy <feeling>' / 'me siento <feeling>' (accent-free text)."""
    return rf"\b(?:estoy|me siento) {_INTENSIFIER}(?:{'|'.join(words)})\b"


# Emotion -> first-person patterns over normalised text (lowercase, no accents, no punctuation).
_EMOTION_RULES: dict[str, tuple[str, ...]] = {
    "joy": (
        _state("feliz", "content[oa]", "alegre", "emocionad[oa]", "encantad[oa]", "radiante"),
        r"\bme (?:alegra|alegro|emociona|hace (?:muy )?feliz|pone (?:muy )?(?:feliz|content[oa]))\b",
        r"\bque (?:alegria|felicidad|dicha|emocion)\b",
    ),
    "anger": (
        _state("enojad[oa]", "furios[oa]", "enfadad[oa]", "molest[oa]", "hart[oa]", "indignad[oa]"),
        r"\bme (?:da|dio|pone|tiene) (?:(?:mucha|tanta|una) )?(?:rabia|furia|bronca|coraje|ira)\b",
        r"\bme (?:enoja|enfada|enfurece|indigna|irrita|fastidia|molesta)\b",
        r"\bque (?:rabia|furia|bronca|coraje|fastidio|indignacion)\b",
    ),
    "sadness": (
        _state(
            "triste", "deprimid[oa]", "desanimad[oa]", "abatid[oa]", "desolad[oa]", "angustiad[oa]"
        ),
        r"\bme siento (?:muy |tan )?(?:solo|sola)\b",
        r"\bme (?:entristece|deprime|da (?:mucha )?tristeza|pone (?:muy )?triste)\b",
        r"\bque (?:tristeza|lastima|desgracia)\b",
        r"\bque pena\b(?! (?:tengo|me da|da)\b)",  # "que pena tengo de..." is embarrassment
        r"\b(?:tengo ganas de|quiero) llorar\b(?! de (?:la )?(?:risa|alegria|emocion|felicidad)\b)",
    ),
    "surprise": (
        r"\bno (?:lo )?puedo creer(?:lo)?\b(?! en\b)",
        r"\bno (?:me )?lo (?:creo|esperaba)\b",
        _state("sorprendid[oa]", "asombrad[oa]", "impactad[oa]", "atonit[oa]", "boquiabiert[oa]"),
        r"\bme (?:sorprende|asombra|impresiona)\b",
        r"\bque sorpresa\b",
    ),
}
_COMPILED_RULES = tuple(
    (emotion, tuple(re.compile(pattern) for pattern in patterns))
    for emotion, patterns in _EMOTION_RULES.items()
)

# A feeling is not the user's own, current feeling when one of these words precedes it closely
# (negation, hypothetical or habitual framing, reported speech).
_BLOCKING_WORDS = frozenset(
    {"no", "nunca", "jamas", "tampoco", "ni", "sin", "si", "cuando", "aunque", "quizas", "quiza"}
    | {"ojala", "dice", "dijo", "dicen", "dijeron", "decia", "afirma", "cuenta"}
    | {"dime", "escribe", "inventa", "pon", "di", "diga", "traduce", "repite", "lee", "cita"}
    | {"llame", "llama", "piensa", "cree", "opina", "supone"}  # requests, titles, reported views
)
_BLOCKING_WINDOW = 3  # words looked at before a match
# The longest turn the API accepts (cognition.response_plan.MAX_TURN_MESSAGE_CHARS); reading
# no more bounds the work, because the rules are quadratic in the number of matches.
_MAX_CHARS = 4000

# A clause that opens with one of these is a question even when the transcript has no "?".
_QUESTION_OPENERS = ("por que ", "como ", "cuando ", "donde ", "quien ", "cual ", "acaso ")

# Text containing one of these is irony, a quotation or a repeat-after-me request: never the
# user's plain statement.
_QUOTE_CHARS = frozenset('"«»“”')
_IRONY_MARKERS = (
    "si claro",
    "ya claro",
    "como no",
    "claro que si",
    "jaja",
    "ja ja",
    "jeje",
    "repite despues de mi",
    "repite conmigo",
    "di conmigo",
    "repite lo siguiente",
)

_CLAUSE = re.compile(r"[^.,;!?¿\n]+\??")
_NON_WORD = re.compile(r"[^a-z0-9?]+")


def _normalise(text: str) -> str:
    """Lowercase and strip accents so 'Qué' and 'que' compare equal (NFD, no dependency)."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _is_plain_statement(normalised: str) -> bool:
    """Tell whether the whole text may hold a plain statement (no quotation, no irony)."""
    if any(char in _QUOTE_CHARS for char in normalised):
        return False
    return not any(marker in normalised for marker in _IRONY_MARKERS)


def _emotion_in_clause(clause: str) -> str | None:
    """Return the emotion explicitly stated by one clause of normalised text, if any."""
    words = _NON_WORD.sub(" ", clause).split()
    sentence = " ".join(words)
    if sentence.endswith("?") or sentence.startswith(_QUESTION_OPENERS):
        return None
    for emotion, patterns in _COMPILED_RULES:
        for pattern in patterns:
            for match in pattern.finditer(sentence):
                before = sentence[: match.start()].split()[-_BLOCKING_WINDOW:]
                if _BLOCKING_WORDS.isdisjoint(before):
                    return emotion
    return None


def classify_user_emotion(text: str) -> str:
    """Return the user's emotion for this turn, ``neutral`` unless a feeling is explicit.

    Case and accents are ignored. The first explicit first-person statement of a feeling
    wins (for example "estoy triste", "me alegra", "qué rabia", "no puedo creerlo"). A
    negation, a question, a quotation, a third person or sarcasm leaves the turn ``neutral``.

    Args:
        text: What the user said, as transcribed.

    Returns:
        A member of ``VALID_EMOTIONS``; ``FALLBACK_EMOTION`` when no feeling is explicit.
    """
    normalised = _normalise(text[:_MAX_CHARS])
    if not _is_plain_statement(normalised):
        return FALLBACK_EMOTION
    for clause in _CLAUSE.findall(normalised):
        emotion = _emotion_in_clause(clause)
        if emotion is not None:
            return emotion
    return FALLBACK_EMOTION
