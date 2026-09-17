"""Vercel entrypoint shim.

Vercel's Python auto-detection only checks a handful of default root-level
filenames, not the src-layout path the backend package actually lives at
(backend/src/silent_orchestra/main.py). Re-export the real app from here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend" / "src"))

from silent_orchestra.main import app  # noqa: E402
