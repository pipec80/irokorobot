"""Does a message ask for data about the household? Pure and closed (Plan 0077).

A sentence is a household request only when three things hold together: it names the household (a
first-person possessive before a relative or a pet: «mi hijo», «mis dos perros»), it asks for a datum
(an age, a name, a birthday, a taste, «qué sabes de…») and it has the form of a request (a question
mark, an opening interrogative, «dime», or a phrase without a verb such as «la edad de mi hija»).
Anything else is conversation: the model holds no household data, so a miss can invent and cannot
reveal a stored value.

A sentence that asks for a datum about someone it does not name as family («¿Cuándo nació Mozart?») is
left to the controller, the only place that may compare it with the household's stored names. This
module reads no store, identifies nobody and grants nothing.
"""

from itertools import pairwise
import re

from server.text_keys import normalize_spanish

__all__ = [
    "BIRTH_WORDS",
    "has_question_mark",
    "mentions_the_household",
    "names_someone_known",
    "opens_with",
    "requests_data_of_a_name",
    "requests_household_data",
    "states_a_request",
]

_POSSESSIVES = frozenset(
    {"mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras"}
)
# «¿Cómo se llama tu perro?» asks the robot and «su hijo» is someone else's.
_OWN_POSSESSIVES = frozenset({"mi", "mis", "nuestro", "nuestra", "nuestros", "nuestras"})
# Words that name the household on their own, plural forms included.
_HOUSEHOLD_WORDS = frozenset(
    {
        "hijo",
        "hija",
        "hijos",
        "hijas",
        "familia",
        "familias",
        "familiares",
        "preferencia",
        "preferencias",
        "padre",
        "madre",
        "padres",
        "madres",
        "hermano",
        "hermana",
        "hermanos",
        "hermanas",
        "abuelo",
        "abuela",
        "abuelos",
        "abuelas",
        "esposo",
        "esposa",
        "esposos",
        "esposas",
        "marido",
        "maridos",
        "mama",
        "mamas",
        "tio",
        "tia",
        "tios",
        "tias",
        "primo",
        "prima",
        "primos",
        "primas",
    }
)
# Words that mean a relative only with a possessive ("mi mujer") and mean something
# else alone ("papas fritas", "las mujeres astronautas", "la primavera").
_HOUSEHOLD_WORDS_NEEDING_POSSESSIVE = frozenset(
    {
        "nino",
        "nina",
        "ninos",
        "ninas",
        "papa",
        "papas",
        "pareja",
        "parejas",
        "mujer",
        "mujeres",
    }
)
_HOUSEHOLD_PHRASES = ("le gusta", "les gusta")
BIRTH_WORDS = frozenset({"nacio", "nacimiento", "nacimientos"})
# Relatives the older lists did not know, as Chileans of any age say them. Possessive required.
_MORE_RELATIVES = frozenset(
    [
        "nieto",
        "nieta",
        "nietos",
        "nietas",
        "bisnieto",
        "bisnieta",
        "bisnietos",
        "sobrino",
        "sobrina",
        "sobrinos",
        "sobrinas",
        "suegro",
        "suegra",
        "suegros",
        "yerno",
        "nuera",
        "cunado",
        "cunada",
        "cunados",
        "novio",
        "novia",
        "pololo",
        "polola",
        "senora",
        "senoras",
        "viejo",
        "vieja",
        "viejos",
        "viejas",
        "hijito",
        "hijita",
        "hijitos",
        "hijitas",
        "mamita",
        "papito",
        "guagua",
        "guaguas",
        "regalon",
        "regalona",
        "compadre",
        "comadre",
        "ahijado",
        "ahijada",
        "hijastro",
        "hijastra",
        "bisabuelo",
        "bisabuela",
        "nene",
        "nena",
        "bebe",
        "chiquillo",
        "chiquilla",
        "cabro",
        "cabra",
        "pequeno",
        "pequena",
    ]
)
_PET_WORDS = frozenset(
    [
        "perro",
        "perra",
        "perros",
        "perras",
        "perrito",
        "perrita",
        "quiltro",
        "cachorro",
        "cachorra",
        "gato",
        "gata",
        "gatos",
        "gatas",
        "gatito",
        "gatita",
        "michi",
        "mascota",
        "mascotas",
        "conejo",
        "coneja",
        "conejos",
        "conejito",
        "pajaro",
        "pajaros",
        "pajarito",
        "loro",
        "lorito",
        "canario",
        "cotorra",
        "tortuga",
        "tortuguita",
        "hamster",
        "cuy",
        "cobayo",
        "pez",
        "peces",
        "pececito",
        "caballo",
        "pollito",
        "chanchito",
    ]
)
_RELATIVE_OR_PET = (
    _HOUSEHOLD_WORDS | _HOUSEHOLD_WORDS_NEEDING_POSSESSIVE | _MORE_RELATIVES | _PET_WORDS
)

_DATA_WORDS = frozenset(
    [
        "anos",
        "nacimiento",
        "nacimientos",
        "nacio",
        "cumpleanos",
        "cumple",
        "cumples",
        "cumplio",
        "cumplen",
        "nombre",
        "nombres",
        "llama",
        "llaman",
        "llamaba",
        "llamaban",
        "apellido",
        "apellidos",
        "apellida",
        "gustos",
        "preferencia",
        "preferencias",
        "favorito",
        "favorita",
        "favoritos",
        "favoritas",
        "alergia",
        "alergias",
        "alergico",
        "alergica",
        "vive",
        "viven",
        "trabaja",
        "trabajan",
        "estudia",
        "estudian",
        "telefono",
        "celular",
        "numero",
        "correo",
        "direccion",
        "relacion",
    ]
)
# «¿Te gusta mi perro?» asks the robot, so a taste counts only in the third person. «edad» needs
# its neighbour: «¿A qué edad debería mi hijo empezar el colegio?» asks for advice.
_DATA_PHRASES = (
    "le gusta",
    "les gusta",
    "le gustan",
    "les gustan",
    "quien es",
    "quien fue",
    "quienes son",
    "edad tiene",
    "edad tenia",
    "edad tendra",
    "edad cumple",
    "edad de",
    "edad del",
    "edades de",
)
# «Sabes qué, mi vieja hacía sopaipillas» is a story: these count only when pointed at someone.
_SOFT_DATA_WORDS = frozenset({"sabes", "sabe", "recuerdas", "acuerdas", "acuerda"})
_SOFT_DATA_LINKS = frozenset({"de", "del", "sobre", "a"})
_ARTICLES = frozenset({"el", "la", "los", "las"})
_COUNT_WORDS = frozenset({"cuantos", "cuantas"})
_INTERROGATIVES = frozenset(
    [
        "que",
        "cual",
        "cuales",
        "quien",
        "quienes",
        "cuando",
        "cuanto",
        "cuanta",
        "cuantos",
        "cuantas",
        "como",
        "donde",
    ]
)
# Without an accent these also open a story: «cuando mi hijo llega…». The possessive right after
# them is the story; a question puts the verb there («cuando nació mi hijo»).
_SUBORDINATING_OPENERS = frozenset({"que", "cuando", "como", "donde"})
# Each opens the body of the sentence: «mi hijo vive en Temuco, sabes» is a story.
_REQUEST_PHRASES = (
    "dime",
    "digame",
    "me dices",
    "cuentame",
    "sabes",
    "recuerdas",
    "te acuerdas",
    "quiero saber",
    "necesito saber",
    "me gustaria saber",
    "quiero que me digas",
    "quiero que me diga",
    "me puedes decir",
    "puedes decirme",
    "me puede decir",
    "puede decirme",
    "me podria decir",
    "podria decirme",
    "me podrias decir",
    "podrias decirme",
    "usted sabe",
    "no me acuerdo",
    "no recuerdo",
    "se me olvido",
    "me olvide",
    "calcula",
)
# Words that may come before the request itself, a call to the robot included.
_LEADING_FILLERS = frozenset(
    [
        "iroko",
        "oye",
        "oiga",
        "hola",
        "bueno",
        "y",
        "a",
        "ya",
        "disculpa",
        "disculpe",
        "perdon",
        "perdone",
        "por",
        "favor",
        "cachai",
        "mira",
        "mire",
        "entonces",
        "pues",
        "po",
        "eh",
        "ah",
        "ok",
        "ver",
    ]
)
_TRAILING_FILLERS = frozenset({"po", "pues", "cachai", "porfa", "por", "favor", "ya"})
_VERBLESS_DATA_NOUNS = frozenset(
    [
        "fecha",
        "ano",
        "mes",
        "dia",
        "edad",
        "cumpleanos",
        "nombre",
        "nombres",
        "telefono",
        "celular",
        "numero",
        "correo",
        "direccion",
        "gustos",
    ]
)
_VERBLESS_LINKS = frozenset({"de", "del", "nacimiento", "cumpleanos", "en", "que", "nacio"})
_FIRST_PERSON_HAVE = frozenset({"tengo", "tenemos"})
# «¿Tengo hijos?», «¿qué mascotas tengo?»: no possessive, the verb is the first person.
_HAVE_REACH = 2
# «mis dos perros», «mi querida madre»: one word may sit between the possessive and the relative.
_REFERENCE_REACH = 2
# An unmarked question ends on the person: «cuando nació mi hijo», not «… llovía mucho».
_CLOSING_WORDS = 2
_VERBLESS_MIN_WORDS = 3
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# «…, ¿cachai?»: the words the mark really belongs to are in this group, and folded in _TAGS.
_CLOSING_QUESTION = re.compile(r"(?:,\s*¿?|\s¿)\s*([^,¿?]+)\?\s*$")
_TAGS = frozenset(
    [
        "cachai",
        "no",
        "cierto",
        "verdad",
        "sabes",
        "sabe",
        "sabias",
        "ya",
        "ves",
        "eh",
        "si",
        "entiendes",
    ]
) | {"te conte", "o no", "me entiendes"}


def _has_phrase(normalized: str, phrases: tuple[str, ...]) -> bool:
    """Match any phrase as whole space-delimited words."""
    padded = f" {normalized} "
    return any(f" {phrase} " in padded for phrase in phrases)


def _body(words: list[str]) -> list[str]:
    """Drop the leading call and fillers («oye Iroko, por favor…»); keep the words if all are."""
    for index, word in enumerate(words):
        if word not in _LEADING_FILLERS:
            return words[index:]
    return words


def _without_closing_fillers(words: list[str]) -> list[str]:
    """Drop what a person adds after the sentence is over («la edad de mi nieto, po»)."""
    end = len(words)
    while end > 0 and words[end - 1] in _TRAILING_FILLERS:
        end -= 1
    return words[:end]


def _sentences(message: str) -> list[str]:
    """Split the raw text on the punctuation that ends a sentence, never on «¿»."""
    return _SENTENCE_END.split(message)


def has_question_mark(message: str) -> bool:
    """Whether the raw text asks with a question mark, a closing «¿cachai?» not counted.

    Args:
        message: Raw transcript or chat text.

    Returns:
        ``True`` when a mark remains once a closing tag is set aside.
    """
    closing = _CLOSING_QUESTION.search(message)
    if closing is not None and normalize_spanish(closing.group(1)) in _TAGS:
        message = message[: closing.start()]
    return "?" in message or "¿" in message


def mentions_the_household(normalized: str) -> bool:
    """Whether a household word appears at all, a request or not.

    The broad test keeps a value about the family out of the memory-answer grammar: it is used
    only on a message that has the shape of an answer, never to refuse a conversation.

    Args:
        normalized: Text folded by ``normalize_spanish``.

    Returns:
        ``True`` when the text holds a relative, a pet of the speaker, «le gusta», or a birth word.
    """
    words = normalized.split()
    return (
        any(word in _HOUSEHOLD_WORDS | BIRTH_WORDS for word in words)
        or any(
            word in _HOUSEHOLD_WORDS_NEEDING_POSSESSIVE and previous in _POSSESSIVES
            for previous, word in pairwise(words)
        )
        or _names_the_household(words)
        or _has_phrase(normalized, _HOUSEHOLD_PHRASES)
    )


def _names_the_household(words: list[str]) -> bool:
    """Whether a first-person possessive points at a relative or a pet, within reach."""
    return any(
        word in _OWN_POSSESSIVES
        and any(
            candidate in _RELATIVE_OR_PET
            for candidate in words[index + 1 : index + 1 + _REFERENCE_REACH]
        )
        for index, word in enumerate(words)
    )


def _points_at(words: list[str], index: int, *, possessive_only: bool) -> bool:
    """Whether the soft word at *index* points at someone: «sabes de mi hijo», «recuerdas a Zeta»."""
    position = index + 1
    linked = position < len(words) and words[position] in _SOFT_DATA_LINKS
    if linked:
        position += 1
    if position < len(words) and words[position] in _ARTICLES:
        position += 1
    if position >= len(words):
        return False
    return words[position] in _OWN_POSSESSIVES or (linked and not possessive_only)


def _asks_for_a_datum(normalized: str, words: list[str], *, possessive_only: bool) -> bool:
    """Whether the words name a datum: an age, a name, a taste, «qué sabes de…»."""
    return (
        any(word in _DATA_WORDS for word in words)
        or _has_phrase(normalized, _DATA_PHRASES)
        or any(
            first in _COUNT_WORDS and second in _RELATIVE_OR_PET
            for first, second in pairwise(words)
        )
        or any(
            word in _SOFT_DATA_WORDS and _points_at(words, index, possessive_only=possessive_only)
            for index, word in enumerate(words)
        )
    )


def _opens_with_an_interrogative(words: list[str]) -> bool:
    """Whether the body opens with an interrogative that is not the start of a story."""
    body = _body(words)
    if not body or body[0] not in _INTERROGATIVES:
        return False
    next_word = body[1] if len(body) > 1 else ""
    return not (body[0] in _SUBORDINATING_OPENERS and next_word in _POSSESSIVES)


def _opens_with_a_request(words: list[str]) -> bool:
    """Whether the body opens with a closed request phrase."""
    opening = " ".join(_body(words))
    return any(f"{opening} ".startswith(f"{phrase} ") for phrase in _REQUEST_PHRASES)


def opens_with(normalized: str, phrase: str) -> bool:
    """Whether *phrase* opens the message once its leading call and fillers are dropped.

    Args:
        normalized: Text folded by ``normalize_spanish``.
        phrase: A folded phrase.

    Returns:
        ``True`` when the body of the message starts with the phrase, as whole words.
    """
    return f"{' '.join(_body(normalized.split()))} ".startswith(f"{phrase} ")


def states_a_request(normalized: str, *, marked: bool) -> bool:
    """Whether the sentence has the form of a request.

    Args:
        normalized: Text folded by ``normalize_spanish``.
        marked: Whether the raw text carries a question mark. Whisper left one out on 3 of 10
            questions (ADR 0023 decision 7), so it is one signal and never the only one.

    Returns:
        ``True`` for a question mark, an opening request phrase, or an opening interrogative.
    """
    words = normalized.split()
    return marked or _opens_with_a_request(words) or _opens_with_an_interrogative(words)


def _closes_on_the_household(words: list[str]) -> bool:
    """Whether the sentence ends on the relative or the pet, closing fillers aside."""
    return any(
        word in _RELATIVE_OR_PET for word in _without_closing_fillers(words)[-_CLOSING_WORDS:]
    )


def _household_request_form(words: list[str], *, marked: bool) -> bool:
    """A request about the household; with no mark, an interrogative must close on the person."""
    return (
        marked
        or _opens_with_a_request(words)
        or (_opens_with_an_interrogative(words) and _closes_on_the_household(words))
    )


def _is_verbless_request(words: list[str]) -> bool:
    """Recognize «la fecha de nacimiento de mi hija»: a datum, then the person, and nothing else."""
    body = _body(_without_closing_fillers(words))
    if body and body[0] in _ARTICLES:
        body = body[1:]
    if len(body) < _VERBLESS_MIN_WORDS or body[0] not in _VERBLESS_DATA_NOUNS:
        return False
    return (
        body[-2] in _OWN_POSSESSIVES
        and body[-1] in _RELATIVE_OR_PET
        and all(word in _VERBLESS_LINKS for word in body[1:-2])
    )


def _asks_what_one_has(words: list[str], *, marked: bool) -> bool:
    """Recognize «¿tengo hijos?» and «¿cuántos perros tengo?», which carry no possessive."""
    if not (marked or _opens_with_an_interrogative(words)):
        return False
    for index, word in enumerate(words):
        if word in _FIRST_PERSON_HAVE:
            near = words[max(0, index - _HAVE_REACH) : index]
            near += words[index + 1 : index + 1 + _HAVE_REACH]
            if any(other in _RELATIVE_OR_PET for other in near):
                return not any(other in _OWN_POSSESSIVES for other in near)
    return False


def _sentence_requests(sentence: str) -> bool:
    """Apply the three conditions to one sentence."""
    normalized = normalize_spanish(sentence)
    words = normalized.split()
    marked = has_question_mark(sentence)
    if _asks_what_one_has(words, marked=marked):
        return True
    if not _names_the_household(words):
        return False
    return _is_verbless_request(words) or (
        _asks_for_a_datum(normalized, words, possessive_only=True)
        and _household_request_form(words, marked=marked)
    )


def requests_household_data(message: str) -> bool:
    """Whether one sentence names the household, asks for a datum and has the form of a request.

    Each sentence is judged alone, so a question and a story beside it never add up: «¿Sabes dónde
    queda la farmacia? Mi mamá necesita remedios.» is no request.

    Args:
        message: Raw transcript or chat text.

    Returns:
        ``True`` for a household request; a story or a piece of advice is ``False``.
    """
    return any(_sentence_requests(sentence) for sentence in _sentences(message))


def _sentence_requests_a_name(sentence: str) -> bool:
    """Whether one sentence asks for a datum and names no relative."""
    normalized = normalize_spanish(sentence)
    words = normalized.split()
    return (
        not _names_the_household(words)
        and _asks_for_a_datum(normalized, words, possessive_only=False)
        and states_a_request(normalized, marked=has_question_mark(sentence))
    )


def requests_data_of_a_name(message: str) -> bool:
    """Whether a message asks for a datum about someone it does not name as family.

    Args:
        message: Raw transcript or chat text.

    Returns:
        ``True`` when only a stored name can tell the household from anyone else, as in
        «¿Cuándo nació Mozart?».
    """
    return any(_sentence_requests_a_name(sentence) for sentence in _sentences(message))


def names_someone_known(message: str, names: frozenset[str]) -> bool:
    """Whether a stored name appears in the message, as whole words after folding.

    Args:
        message: Raw transcript or chat text.
        names: The household's stored names and aliases, as stored.

    Returns:
        ``True`` when any name appears; an empty name never matches.
    """
    folded = normalize_spanish(message)
    return any(
        _has_phrase(folded, (key,)) for key in (normalize_spanish(name) for name in names) if key
    )
