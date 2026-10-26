"""Spanish lexicon constants for memory retrieval.

Stopwords keep greetings from firing entity lookups; relation triggers map
possessive questions ("mis hijos", "mi mascota") to the canonical predicate
that answers them via reverse fact lookup (see memory/relations.py).

It also holds the closed Spanish grammar of memory candidates (ADR 0021): preference triggers,
lead-in, negation and clause words, articles, allowed infinitives, topics and the denied
person and sensitive vocabulary.
"""

from __future__ import annotations

import re
import unicodedata

from server import text_keys

# Common Spanish conversation words (4+ chars) that are never entity names.
# Without this filter every greeting fires LIKE queries against `entities`.
STOPWORDS_ES = frozenset(
    {
        "ahora",
        "algo",
        "alguien",
        "aquí",
        "bien",
        "bueno",
        "buenas",
        "buenos",
        "cada",
        "casa",
        "como",
        "cómo",
        "cual",
        "cuál",
        "cuales",
        "cuáles",
        "cuando",
        "cuándo",
        "cuanto",
        "cuánto",
        "decime",
        "desde",
        "días",
        "dias",
        "dime",
        "donde",
        "dónde",
        "entonces",
        "eres",
        "esta",
        "está",
        "estas",
        "estás",
        "este",
        "esto",
        "favor",
        "gracias",
        "hace",
        "hacer",
        "hasta",
        "hola",
        "llama",
        "llaman",
        "llamas",
        "llamo",
        "mucho",
        "nada",
        "noches",
        "para",
        "pero",
        "podes",
        "podés",
        "porque",
        "puedes",
        "quien",
        "quién",
        "quiero",
        "robot",
        "sabes",
        "sabés",
        "siempre",
        "sobre",
        "también",
        "tambien",
        "tarde",
        "tardes",
        "tenes",
        "tenés",
        "tengo",
        "tiene",
        "tienes",
        "todavía",
        "todo",
        "todos",
    }
)

# Relation words → canonical predicate answered by reverse fact lookup.
# "¿cómo se llaman mis hijos?" names no child, so forward name-lookup fails;
# the answer lives in facts with predicate hijo_de.
RELATION_TRIGGERS: dict[str, str] = {
    "hijo": "hijo_de",
    "hijos": "hijo_de",
    "hija": "hijo_de",
    "hijas": "hijo_de",
    "mascota": "mascota_de",
    "mascotas": "mascota_de",
    "perro": "mascota_de",
    "perra": "mascota_de",
    "perros": "mascota_de",
    "gato": "mascota_de",
    "gata": "mascota_de",
    "gatos": "mascota_de",
    "esposa": "pareja_de",
    "esposo": "pareja_de",
    "pareja": "pareja_de",
    "cumpleaños": "fecha_nacimiento",
    "nació": "fecha_nacimiento",
    "nacio": "fecha_nacimiento",
    "nací": "fecha_nacimiento",
    "naci": "fecha_nacimiento",
    # "¿cuántos años tengo?" / "¿qué edad tengo?" name no entity either —
    # self-referential age questions resolve via the owner's fecha_nacimiento
    # (found 2026-07-27 during M1: this phrasing returned zero context).
    "años": "fecha_nacimiento",
    "edad": "fecha_nacimiento",
}

_WORD_RE = re.compile(r"[a-záéíóúüñ]+")


def predicates_in(text: str) -> set[str]:
    """Return the canonical predicates triggered by relation words in *text*.

    Matches whole words only ("regata" does not trigger "gata").

    Args:
        text: Raw user input text.

    Returns:
        Set of canonical predicate names (possibly empty).
    """
    words = set(_WORD_RE.findall(text.casefold()))
    return {pred for word, pred in RELATION_TRIGGERS.items() if word in words}


# --- Memory candidates (ADR 0021, CM-3a) -----------------------------------------------
# Every word below is already folded the way `normalize_spanish` folds text: lower case, no
# accents, punctuation gone. The grammar is a closed, positive list — on doubt a phrase is
# dropped, so each table can only grow by a reviewed change.

#: The first-person phrases that may declare a taste, mapped to the canonical predicate.
#: `mi favorit[oa] es` may carry up to two words between `mi` and `favorito` ("mi color
#: favorito es", "mi comida favorita es"); that case is handled by `PREFERENCE_FAVOURITE`.
PREFERENCE_TRIGGERS: dict[str, str] = {
    "no me gusta": "dislikes",
    "no me gustan": "dislikes",
    "no soporto": "dislikes",
    "me gusta": "likes",
    "me gustan": "likes",
    "me encanta": "likes",
    "me encantan": "likes",
    "amo": "likes",
    "adoro": "likes",
    "odio": "dislikes",
    "detesto": "dislikes",
    "prefiero": "prefers",
}
PREFERENCE_FAVOURITE = re.compile(r"mi (?:[a-z]+ ){0,2}favorit[oa] es")

#: The spoken offer and its results (ADR 0021 decision 9). Neutral Spanish with tuteo (Pipec
#: lives in Santiago de Chile). ``{value}`` is the stored phrase, which already passed the gate
#: and the classifier. The offer dictates the short answer, a closed verb («sí, autorizo.»), so a
#: spoken «sí» alone can never promote anything; the statement before it names the value. It
#: promises no recall (that is CM-5). ``{verb}`` is used
#: only by the ``likes`` and ``dislikes`` statements (the plural form agrees with the value).
OFFER_STATEMENTS: dict[str, str] = {
    "likes": "Antes me dijiste que te {verb} {value}.",
    "dislikes": "Antes me dijiste que no te {verb} {value}.",
    "prefers": "Antes me dijiste que prefieres {value}.",
}
OFFER_QUESTION = "¿Quieres que lo guarde? Dime: sí, autorizo."
#: An object that starts with one of these takes the plural verb ("te gustan las empanadas").
PLURAL_ARTICLES = frozenset({"los", "las", "unos", "unas"})
OFFER_VERB_SINGULAR = "gusta"
OFFER_VERB_PLURAL = "gustan"
#: Fixed result phrases: they never carry the value, so what is said back leaks nothing.
ANSWER_SAVED_PHRASE = "Listo, lo guardé."
ANSWER_REJECTED_PHRASE = "Está bien, no lo guardo."
ANSWER_CONTRADICTION_PHRASE = "No lo guardé: ya tengo guardado algo distinto."
#: Said only to the verified owner whose open offer was found and then could not be settled,
#: so the model never improvises a "listo" for something that was not saved.
ANSWER_FAILED_PHRASE = "No pude guardarlo ahora. Dímelo de nuevo en un rato."
#: Said to a face-identified person whose open offer an answer named while their voice was not
#: verified (Plan 0068, D-1): it asks for a longer answer instead of letting the model guess. It
#: dictates, after the last colon, words the answer grammar accepts («que lo guardes»); a unit
#: test pins the round trip. It never carries the value.
ANSWER_RETRY_PHRASE = (
    "No reconocí bien tu voz. Dímelo un poco más largo: sí, autorizo que lo guardes."
)
#: The same retry for a refusal: it dictates the refusal, never an acceptance.
ANSWER_RETRY_REJECT_PHRASE = (
    "No reconocí bien tu voz. Dímelo un poco más largo: no autorizo que lo guardes."
)

#: Closed set of topics a taste may belong to; the extractor must place the object in one.
CANDIDATE_TOPICS = frozenset(
    {"food", "drink", "music", "colour", "pastime", "sport", "animal", "weather", "media"}
)

#: Words that may precede the trigger in the same clause ("la verdad, a mí me gusta ...").
#: «oye» is an interjection, never an attribution.
LEAD_IN_WORDS = frozenset(
    {
        "a", "mi", "yo", "la", "verdad", "siempre", "muy", "mucho", "muchisimo", "tambien",
        "y", "pero", "ademas", "en", "realidad", "honestamente", "sinceramente", "bueno",
        "che", "mira", "pues", "este", "eh", "igual", "entonces", "ahora", "claro",
        "personalmente", "oye",
    }
)  # fmt: skip

#: Closed filler phrases that may sit right before the trigger:
#: «la verdad es que me gusta…», «es que me encanta…». They are whole phrases, not free words,
#: so "siempre que me gusta…" (a habit or a condition) and "dice que me gusta…" still refuse.
LEAD_IN_PHRASES = ("la verdad es que", "es que")

#: Words that may open a sentence before a taste without attributing it to somebody else
#: ("hola Iroko, me gusta el mate"). A clause of other words before a soft break makes the next
#: taste somebody else's ("mi hija dice: me gusta el helado"). «es» is here only so the filler
#: «es que» / «la verdad es que» does not count as such a clause when it precedes a soft break.
GREETING_WORDS = frozenset(
    {"hola", "iroko", "oye", "dime", "escucha", "sabes", "que", "mira", "vamos", "ver", "es"}
)

#: A word that negates what follows or precedes: the only negated forms accepted are the
#: triggers `no me gusta(n)` and `no soporto` themselves.
NEGATORS = frozenset({"no", "ya", "nunca", "jamas", "tampoco", "ni"})

#: A word that opens a clause instead of naming a thing ("me gusta que ...", "prefiero que ...").
CLAUSE_OPENERS = frozenset({"que", "cuando", "si", "como", "donde", "porque", "aunque", "para"})

#: Articles a spoken object may begin with; the comparison key drops them (``text_keys``).
ARTICLES = text_keys.ARTICLES

#: A bare infinitive object ("me gusta cantar") is accepted only from this list; "vivir",
#: "hablar" or "mudarme" describe a life, not a taste.
ALLOWED_INFINITIVES = frozenset(
    {
        "cantar", "bailar", "correr", "caminar", "leer", "escribir", "cocinar", "nadar", "viajar",
        "dibujar", "pintar", "jugar", "pescar", "escuchar", "pasear", "manejar", "hornear",
        "tejer", "coser", "meditar", "esquiar", "surfear", "acampar", "madrugar", "dormir",
        "comer", "beber", "mirar",
    }
)  # fmt: skip

#: Kinship, role and person words: an object that names one is never a taste (CM-3b owns
#: third parties). The keys of `RELATION_TRIGGERS` (hijo, mascota, perro, gato, esposa, ...)
#: join this set by `candidate_denied_words`, so a pet is a third party here too.
PERSON_WORDS = frozenset(
    {
        "mama", "papa", "madre", "padre", "hermano", "hermana", "abuelo", "abuela", "tio",
        "tia", "primo", "prima", "suegro", "suegra", "cunado", "cunada", "nieto", "nieta",
        "sobrino", "sobrina", "novio", "novia", "marido", "mujer", "bebe", "nino", "nina",
        "familia", "jefe", "jefa", "amigo", "amiga", "vecino", "vecina", "companero",
        "companera", "colega", "profesor", "profesora", "maestro", "maestra", "doctor",
        "doctora", "medico", "medica", "persona", "gente",
    }
)  # fmt: skip

#: Place, health, money, credential, life-event and disclosure vocabulary: a taste whose
#: trigger-and-object words, or whose extracted object, contain one is refused. A second layer
#: under the closed topic set.
SENSITIVE_WORDS = frozenset(
    {
        # place and address
        "casa", "hogar", "ciudad", "pueblo", "barrio", "pais", "trabajo", "oficina", "escuela",
        "colegio", "calle", "departamento", "direccion", "domicilio", "mudanza", "mudarme",
        "mude", "vivir", "vivo",
        # health and body
        "salud", "enfermedad", "enfermo", "enferma", "medicina", "medicacion", "medicamento",
        "medicamentos", "pastilla", "pastillas", "hospital", "diagnostico", "dolor", "cancer",
        "depresion", "ansiedad", "terapia", "alergia", "alergico", "embarazo", "cuerpo", "peso",
        # money
        "dinero", "plata", "sueldo", "salario", "deuda", "deudas", "banco", "tarjeta", "cuenta",
        "prestamo", "credito", "ahorros", "impuestos", "factura",
        # credentials and contact
        "clave", "contrasena", "password", "pin", "codigo", "token", "usuario", "correo",
        "email", "telefono", "celular", "dni", "pasaporte",
        # life events
        "divorcio", "separacion", "funeral", "muerte", "murio", "fallecio", "boda", "despido",
        # disclosure vocabulary: an instruction to the robot is CM-3b's, never a taste
        "menciones", "mencion", "mencionar", "digas", "hables", "cuentes", "secreto",
        "secretos", "privado", "privada", "confidencial", "delante", "visitas", "invitados",
        "robot", "iroko",
        # religion, politics, sexuality, drugs and violence: never a taste of an ordinary thing
        "dios", "iglesia", "misa", "religion", "catolico", "catolicos", "catolicismo",
        "evangelico", "musulman", "judio", "politica", "politico", "partido", "gobierno",
        "voto", "votar", "gay", "lesbiana", "homosexual", "sexo", "sexual", "droga", "drogas",
        "cocaina", "marihuana", "heroina", "suicidio", "suicidarme", "matar", "inmigrantes",
        "extranjeros", "raza", "racista",
    }
)  # fmt: skip


# "pin", "mama": a two-letter word has no diminutive stem worth guessing.
_MIN_DIMINUTIVE_WORD = 2


def _inflections(word: str) -> set[str]:
    """Return a folded word with its plural and its diminutives, so a list entry is enough.

    The deny lists are written in the singular; a person, a role or a sensitive thing said in the
    plural (``vecinos``, ``hospitales``) or as a diminutive (``perritos``, ``casitas``) is the same
    thing and must be refused just as firmly.
    """
    forms = {word, f"{word}s", f"{word}es"}
    if word.endswith(("o", "a")) and len(word) > _MIN_DIMINUTIVE_WORD:
        stem = word[:-1]
        for ending in ("ito", "ita"):
            diminutive = f"{stem}{ending}"
            forms.update({diminutive, f"{diminutive}s"})
    return forms


def candidate_denied_words() -> frozenset[str]:
    """Return every folded word a candidate's object may never contain.

    Returns:
        Person and role words, place/health/money/credential/disclosure words and the folded
        keys of ``RELATION_TRIGGERS`` (hijo, mascota, perro, gato, esposa, edad, ...), each with
        its plural and diminutive forms.
    """
    relation_words = {
        unicodedata.normalize("NFD", word).encode("ascii", "ignore").decode("ascii")
        for word in RELATION_TRIGGERS
    }
    denied: set[str] = set()
    for word in PERSON_WORDS | SENSITIVE_WORDS | relation_words:
        denied |= _inflections(word)
    return frozenset(denied)
