"""Pure guard for model sentences that claim a memory action (Plan 0064, D-2, D-5).

Nothing the language model says stores anything: the only save is the deterministic promotion of
Plan 0063, and it is spoken by the robot, never by the model. A model sentence such as «Lo guardé.»
is therefore false, so it is replaced by :data:`REPLACEMENT`, which is true on that turn.

The lexicon is closed and exact. It is matched on the sentence casefolded **without** removing
accents (so ``guardé``, I saved, is a claim and ``guarde``, that I save, is not), one sentence at
a time. A bare participle («Anotado.») is not a claim: the continuity of ADR 0020 keeps what was
said. A question is never a claim, and a negation in the three words before the match cancels it.
The past and perfect forms need no object («Guardé tu café.»); the present and future forms need
one («lo guardo»), except «tomo nota», which needs none, and an offer or a condition
(«si quieres, lo guardo») makes them harmless.

Apply it to **model-generated** text only. The deterministic results of Plan 0063 and the
fallback phrases must reach the wire byte for byte.
"""

import re
import unicodedata

from server.sentences import split_first_sentence

REPLACEMENT = "Eso no lo he guardado."

# 1. The speaker's own saving verb in the past or perfect: a claim with or without an object.
_PAST_CLAIM = (
    r"(?:guardé|registré|almacené|memoricé|anoté|apunté|tomé\s+nota"
    r"|he\s+(?:guardado|registrado|almacenado|memorizado|anotado|apuntado))"
)
# 2. The state of the thing said, or «lo tengo guardado».
_STATE_VERBS = r"(?:queda|quedó|quedará|está|estará|ha\s+sido|se\s+ha|fue|será)"
_PARTICIPLES = r"(?:guardad|registrad|almacenad|memorizad|anotad|apuntad)[oa]s?"
_CLAIM_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        rf"\b{_PAST_CLAIM}\b",
        rf"\b{_STATE_VERBS}\s+{_PARTICIPLES}\b",
        r"\blo\s+tengo\s+(?:guardado|anotado|registrado)\b",
    )
)
# 3. A promise in the present or future: it needs an object (not «guardo silencio»), and an offer
# or a condition in the same sentence («si quieres», «cuando me lo pidas», «ni lo guardaré»)
# makes it harmless.
_OBJECT = r"(?:lo|la|los|las|eso|esto|todo)"
_PRESENT_FUTURE = (
    r"(?:guardaré|guardo|registraré|registro|almacenaré|almaceno"
    r"|memorizaré|memorizo|anotaré|anoto|apuntaré|apunto)"
)
_PROMISE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        rf"\b{_OBJECT}\s+{_PRESENT_FUTURE}\b",
        r"\b(?:lo|la|eso|esto)\s+recordaré\b",
        r"\bme\s+acordaré\b",
        # «tomar nota» is the same promise and, like the past «tomé nota», needs no object.
        r"\b(?:tomo|tomaré)\s+nota\b",
    )
)
_CONDITION = re.compile(r"\b(?:si|cuando|ni)\b")
# «No lo he guardado», «todavía no lo guardo» (the «no» ends the phrase): a negation in the three
# words before the match, with no punctuation between, cancels the claim.
_NEGATION_BEFORE = re.compile(r"\b(?:no|nunca|jamás|tampoco)\s+(?:\w+\s+){0,2}$")


def _fold(sentence: str) -> str:
    """Normalize to NFC and casefold, keeping the accents the lexicon depends on."""
    return unicodedata.normalize("NFC", sentence).casefold()


def claims_memory_action(sentence: str) -> bool:
    """Say whether one model sentence claims to have saved, registered or noted something.

    Args:
        sentence: One sentence of model-generated text.

    Returns:
        ``True`` when the sentence matches the closed lexicon outside a question and outside a
        negation; ``False`` otherwise (including a bare participle such as «Anotado.»).
    """
    question_start = sentence.rfind("¿")
    if question_start < 0 and "?" in sentence:
        return False  # a question written without «¿»: the whole sentence is the question
    folded = _fold(sentence)
    patterns = list(_CLAIM_PATTERNS)
    if _CONDITION.search(folded) is None:
        patterns.extend(_PROMISE_PATTERNS)
    return any(
        _NEGATION_BEFORE.search(folded[: match.start()]) is None
        and not (question_start >= 0 and match.start() > question_start)
        for pattern in patterns
        for match in pattern.finditer(folded)
    )


def replace_if_claim(sentence: str) -> str:
    """Return *sentence*, or :data:`REPLACEMENT` when it claims a memory action.

    Args:
        sentence: One sentence of model-generated text.

    Returns:
        The sentence itself, or :data:`REPLACEMENT`.
    """
    return REPLACEMENT if claims_memory_action(sentence) else sentence


def neutralize_memory_claims(text: str) -> str:
    """Replace every claiming sentence of a whole model reply.

    The reply is split into sentences (an unterminated tail counts as the last one). Consecutive
    replacements collapse into one.

    Args:
        text: A complete model reply.

    Returns:
        *text* unchanged when no sentence claims; otherwise the sentences joined by a single
        space, each claiming one replaced by :data:`REPLACEMENT`.
    """
    sentences = _sentences(text)
    if not any(claims_memory_action(sentence) for sentence in sentences):
        return text
    kept: list[str] = []
    for sentence in sentences:
        replaced = replace_if_claim(sentence)
        if replaced == REPLACEMENT and kept and kept[-1] == REPLACEMENT:
            continue
        kept.append(replaced)
    return " ".join(kept)


def _sentences(text: str) -> list[str]:
    """Split *text* into its closed sentences plus the unterminated tail, if any."""
    sentences: list[str] = []
    remainder = text
    while (split := split_first_sentence(remainder)) is not None:
        sentence, remainder = split
        sentences.append(sentence)
    if remainder.strip():
        sentences.append(remainder.strip())
    return sentences
