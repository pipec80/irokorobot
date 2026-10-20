"""Models and fixed locations of the private speech-to-text corpus (Plan 0069).

Every WAV, manifest and per-clip result of the study lives under ``STT_CORPUS_ROOT``,
which is inside ``project-history/`` (ignored by git). Audio contract of every WAV in
it: WAV, 16 000 Hz, mono, int16.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

STT_CORPUS_ROOT: Final = Path("project-history/calibration/stt")
