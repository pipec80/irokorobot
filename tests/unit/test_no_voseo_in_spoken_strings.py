"""Everything the robot says, and every prompt that shapes it, uses tuteo (Plan 0064, D-1).

The robot speaks neutral Spanish with tuteo. A voseo verb in a persona, a prompt template, a
controller string or a fallback phrase makes the model imitate the dialect of its prompt, so the
dialect drifts. The few files that legitimately contain voseo are an allowlist with one reason
each: they are *recognition* lexicons (they accept voseo as input) or internal prompts that are
never spoken.
"""

from pathlib import Path
import re

import pytest

import server

pytestmark = pytest.mark.unit

_SERVER_ROOT = Path(server.__file__).resolve().parent

# Closed list of voseo forms. Whole words, case-insensitive, accents as written.
_VOSEO_WORDS = (
    "sos",
    "tenés",
    "querés",
    "podés",
    "sabés",
    "preguntás",
    "volvé",
    "dejame",
    "decime",
    "mirá",
    "vení",
    "hablás",
    "vos",
    "contame",
    "acordás",
    "pensás",
    "necesitás",
    "ayudá",
    "ayudame",
    "escuchá",
    "escuchás",
    "esperá",
    "fijate",
    "avisame",
    "conocés",
    "conservás",
    "soltás",
    "ejecutás",
    "actuás",
    "suplantás",
    "explicalo",
    "explicás",
    "redirigí",
    "presentate",
    "cubrilo",
    "compartís",
    "tratás",
    "revelás",
    "reconocés",
    "saludá",
    "saludalo",
    "pedile",
    "ofrecele",
    "preguntale",
    "repetilo",
    "respondé",
    "reaccioná",
    "confirmáselo",
    "acabás",
    "convivís",
    "engañás",
    "encontrás",
    "alterás",
)
_VOSEO = re.compile(r"(?<!\w)(" + "|".join(_VOSEO_WORDS) + r")(?!\w)", re.IGNORECASE)

# Path (relative to the server package) -> why voseo is allowed there.
_ALLOWLIST: dict[str, str] = {
    "cognition/intent_resolution.py": "recognition lexicon: accepts voseo input",
    "memory/lexicon.py": "recognition lexicon: accepts voseo input",
    "memory/candidate_extraction.py": "internal extraction prompt, never spoken (measured in CM-0)",
    "memory/consolidation.py": "internal consolidation prompt, never spoken (measured in CM-0)",
}
_RECOGNITION_FILES = ("cognition/intent_resolution.py", "memory/lexicon.py")


def _sources() -> list[Path]:
    """Return every Python module and persona profile of the server package."""
    return sorted([*_SERVER_ROOT.rglob("*.py"), *_SERVER_ROOT.rglob("*.md")])


def _voseo_in(path: Path) -> set[str]:
    return {match.lower() for match in _VOSEO.findall(path.read_text(encoding="utf-8"))}


def test_no_spoken_string_or_prompt_uses_voseo() -> None:
    """A voseo word outside the allowlist is a spoken string or prompt that drifts the dialect."""
    found = {
        relative: words
        for path in _sources()
        if (relative := path.relative_to(_SERVER_ROOT).as_posix()) not in _ALLOWLIST
        if (words := _voseo_in(path))
    }

    assert found == {}


@pytest.mark.parametrize("relative", _RECOGNITION_FILES)
def test_the_allowlisted_recognition_lexicons_still_hold_voseo(relative: str) -> None:
    """The allowlist cannot silently go stale: these files exist to recognise voseo input."""
    assert _voseo_in(_SERVER_ROOT / relative)


def test_every_allowlisted_file_exists() -> None:
    assert all((_SERVER_ROOT / relative).is_file() for relative in _ALLOWLIST)
