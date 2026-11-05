"""Does a message ask for data about the household? Pure and closed (Plan 0077).

A sentence is a household request when it names the household (a first-person possessive before a
relative or a pet: «mi hijo», «mis dos perros») and has the form of a request (a question mark, an
opening interrogative, «dime», or a phrase without a verb such as «la edad de mi hija»), unless it asks
what the speaker should do («¿qué le regalo a mi hija?») or speaks to the robot («¿te gusta mi perro?»).
A story is conversation. Since D-22 a question about the family needs no word from a list of data: on
hardware «¿qué te conté de mi familia?» and «¿sabes qué come mi perrita?» slipped past such a list and
the model invented the answer. The model holds no stored household value, so a miss can still invent
and cannot reveal one; the remaining misses are pieces of advice said in an unusual way.

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
    "sentence_body",
    "states_a_request",
    "without_leading_fillers",
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
        "chiquitito",
        "chiquitita",
        "padrino",
        "madrina",
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
        "animal",
        "animales",
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
# D-22: a question about the household asks for it, unless it asks what the speaker should do (a
# verb in the first person present, never the past: «compré», «conté» tell what happened) or speaks
# to the robot. «puedo» covers «¿qué le puedo regalar?», «debería» covers «¿a qué edad debería…?».
# A feeling of the speaker («cómo extraño a mi mamá», «cuánto quiero a mis nietos») asks nothing
# either. The words of an opening request («¿me podría decir…?») are not advice.
_ADVICE_WORDS = frozenset(
    [
        "puedo",
        "podria",
        "podriamos",
        "puedes",
        "debo",
        "deberia",
        "debemos",
        "deberiamos",
        "regalo",
        "regalamos",
        "doy",
        "damos",
        "cocino",
        "cocinamos",
        "preparo",
        "ayudo",
        "ayudamos",
        "compro",
        "llevo",
        "hago",
        "hacemos",
        "invito",
        "celebro",
        "organizo",
        "cuido",
        "enseno",
        "explico",
        "digo",
        "pongo",
        "juego",
        "veo",
        "vemos",
        "salgo",
        "salimos",
        "recomiendas",
        "recomiendo",
        "sugieres",
        "aconsejas",
        "conviene",
        "vamos",
        "quiero",
        "queremos",
        "extrano",
        "extranamos",
        "amo",
        "adoro",
        "alimento",
        "llamo",
        "envio",
        "mando",
        "consuelo",
        "calmo",
        "bano",
        "tranquilizo",
        "animo",
        "recibo",
        "vivo",
        "sigo",
        "duermo",
        "cuento",
        "leo",
        "sirvo",
        "escribo",
        "guardo",
        "decimos",
        "cantamos",
        "ponemos",
        "voy",
        "iba",
        "estoy",
        "echo",
        "sufro",
        "lloro",
        "idea",
        "ideas",
        "receta",
        "consejo",
    ]
)
_ADVICE_PHRASES = (
    "es bueno",
    "es mejor",
    "es malo",
    "sirve para",
    "lo que hizo",
    "ayudas con",
    "ayudas a",
)
_ROBOT_ADDRESS_PHRASES = (
    "te gusta",
    "te gustan",
    "te parece",
    "te cae",
    "te caen",
    "quieres",
    "te gustaria",
    "te presente",
    "te cuento",
    "te muestro",
)
# «¿Por qué mi perro ladra tanto?» asks for an explanation, not for a datum.
_WHY_OPENINGS = frozenset({("por", "que"), ("para", "que")})
# Whisper without marks writes the person first: «mi nieto cómo se llama».
_SUBJECT_FIRST_QUESTIONS = (
    "como se llama",
    "como se llaman",
    "cuantos anos",
    "que edad",
    "donde vive",
)
# «Sabes qué, mi vieja hacía sopaipillas»: with no question mark this opens a story, not a request.
_ASIDE_OPENINGS = frozenset({("sabes", "que"), ("sabe", "que")})
_ASIDE_LENGTH = 2
# «para mi nieta»: something for the household, not a question about it.
_FOR_WORD = "para"
# «Cuántos años tiene mi hijo, no me acuerdo»: the question is over, the person closes it.
_CLOSING_ASIDES = (
    ("no", "me", "acuerdo"),
    ("no", "recuerdo"),
    ("se", "me", "fue"),
    ("se", "me", "olvido"),
)
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
    "tengo una duda",
    "me puedes contar",
    "puedes contarme",
    "me podrias contar",
    "me cuentas",
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
        "apellido",
        "apellidos",
        "raza",
        "color",
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
# «cachai» asks nothing, even when Whisper opens the «¿» at the start of the sentence and spells it
# its own way: «Mi hijo vive lejos, ¿cachai?» came back as «¿Mi hijo vive lejos,Kachain?».
_FILLER_TAGS = frozenset(["cachai", "cachay", "cachain", "cachais", "kachai", "kachay", "kachain"])
_TAGS = frozenset(
    [
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
        "te das cuenta",
    ]
) | {"te conte", "o no", "me entiendes"}


def _has_phrase(normalized: str, phrases: tuple[str, ...]) -> bool:
    """Match any phrase as whole space-delimited words."""
    padded = f" {normalized} "
    return any(f" {phrase} " in padded for phrase in phrases)


def _body(words: list[str]) -> list[str]:
    """Drop the leading call, the fillers and a «sabes qué» aside; keep the words if all are.

    Without a question mark «Sabes qué, mi vieja hacía sopaipillas» is a story, and what follows the
    aside decides: «Sabes qué, dime cuántos años tiene mi hijo» is still a request.
    """
    index = 0
    while index < len(words):
        if words[index] in _LEADING_FILLERS:
            index += 1
        elif tuple(words[index : index + _ASIDE_LENGTH]) in _ASIDE_OPENINGS:
            index += _ASIDE_LENGTH
        else:
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
    if closing is not None:
        tag = normalize_spanish(closing.group(1))
        if tag in _FILLER_TAGS:
            # The «¿» that wraps the sentence was opened for the tag: only an earlier «?» asks.
            return "?" in message[: closing.start()]
        if tag in _TAGS:
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


def _points_at(words: list[str], index: int) -> bool:
    """Whether the soft word at *index* points at someone: «sabes de Zeta», «recuerdas a Zeta»."""
    position = index + 1
    if position >= len(words) or words[position] not in _SOFT_DATA_LINKS:
        return False
    position += 1
    if position < len(words) and words[position] in _ARTICLES:
        position += 1
    return position < len(words)


def _asks_for_a_datum(normalized: str, words: list[str]) -> bool:
    """Whether the words name a datum: an age, a name, a taste, «qué sabes de…»."""
    return (
        any(word in _DATA_WORDS for word in words)
        or _has_phrase(normalized, _DATA_PHRASES)
        or any(
            first in _COUNT_WORDS and second in _RELATIVE_OR_PET
            for first, second in pairwise(words)
        )
        or any(
            word in _SOFT_DATA_WORDS and _points_at(words, index)
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


def sentence_body(message: str) -> tuple[str, ...]:
    """Return the folded words of the whole message without its leading call and fillers.

    Like ``opens_with`` it reads the entire message, and the fillers stay defined here once
    («oye Iroko, …», a leading «a»: «a qué soy alérgico» comes back as «que soy alergico»).

    Args:
        message: Raw transcript or chat text.

    Returns:
        The words of the body, folded by ``normalize_spanish``; empty for an empty message.
    """
    return tuple(_body(normalize_spanish(message).split()))


def without_leading_fillers(normalized: str) -> str:
    """Return the message without its leading call, fillers and «sabes qué» aside.

    Args:
        normalized: Text folded by ``normalize_spanish``.

    Returns:
        The body of the message, as ``opens_with`` reads it.
    """
    return " ".join(_body(normalized.split()))


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
    """Whether the sentence ends on the relative or the pet, closing fillers and asides aside."""
    words = _without_closing_fillers(words)
    for aside in _CLOSING_ASIDES:
        if tuple(words[-len(aside) :]) == aside:
            words = words[: -len(aside)]
            break
    return any(word in _RELATIVE_OR_PET for word in words[-_CLOSING_WORDS:])


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
    if body[-1] not in _RELATIVE_OR_PET and len(body) > _VERBLESS_MIN_WORDS:
        body = body[:-1]  # the pet's or the person's name after it: «la edad de mi perro Zeta»
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


def _after_the_request_opening(words: list[str]) -> list[str]:
    """The body without its opening request phrase: «¿me podría decir cómo…?» keeps «cómo…»."""
    body = _body(words)
    opening = " ".join(body)
    for phrase in _REQUEST_PHRASES:
        if f"{opening} ".startswith(f"{phrase} "):
            return body[len(phrase.split()) :]
    return body


def _asks_why(words: list[str]) -> bool:
    """Whether the sentence opens with «por qué» or «para qué», the call to the robot aside."""
    for index, word in enumerate(words):
        if tuple(words[index : index + _ASIDE_LENGTH]) in _WHY_OPENINGS:
            return True
        if word not in _LEADING_FILLERS:
            return False
    return False


def _asks_advice_or_speaks_to_the_robot(words: list[str]) -> bool:
    """Whether a question asks what the speaker should do, is for the household, or asks the robot."""
    rest = _after_the_request_opening(words)
    joined = " ".join(rest)
    # «¿qué me puedes contar de…?» asks for the household: a request phrase is never advice.
    for phrase in _REQUEST_PHRASES:
        joined = f" {joined} ".replace(f" {phrase} ", " ").strip()
    rest = joined.split()
    return (
        _asks_why(words)
        or any(word in _ADVICE_WORDS for word in rest)
        or _has_phrase(joined, _ADVICE_PHRASES)
        or _has_phrase(joined, _ROBOT_ADDRESS_PHRASES)
        or any(
            first == _FOR_WORD and second in _OWN_POSSESSIVES for first, second in pairwise(rest)
        )
    )


def _subject_first_question(words: list[str]) -> bool:
    """Recognize «mi nieto cómo se llama»: the question word follows the relative right away.

    «Mi nieta quiere saber cómo se llama el planeta» has the relative as the asker, so there the
    words between them make it a story.
    """
    body = _body(words)
    if not body or body[0] not in _OWN_POSSESSIVES:
        return False
    for position in range(1, _REFERENCE_REACH + 1):
        if position < len(body) and body[position] in _RELATIVE_OR_PET:
            rest = " ".join(body[position + 1 :])
            return any(
                f"{rest} ".startswith(f"{question} ") for question in _SUBJECT_FIRST_QUESTIONS
            )
    return False


def _sentence_requests(sentence: str) -> bool:
    """Judge one sentence: a question about the household, not advice and not to the robot."""
    normalized = normalize_spanish(sentence)
    words = normalized.split()
    marked = has_question_mark(sentence)
    if _asks_what_one_has(words, marked=marked):
        return True
    if not _names_the_household(words):
        return False
    if _is_verbless_request(words):
        return True
    if "¡" in sentence and not marked:
        return False  # «¡Qué orgullo de mi hijo!»: an exclamation asks nothing
    form = _household_request_form(words, marked=marked) or _subject_first_question(words)
    return form and not _asks_advice_or_speaks_to_the_robot(words)


def requests_household_data(message: str) -> bool:
    """Whether one sentence is a question about the household that asks for no advice.

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
        and _asks_for_a_datum(normalized, words)
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
