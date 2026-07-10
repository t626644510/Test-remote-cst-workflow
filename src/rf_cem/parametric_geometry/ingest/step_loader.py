"""Load existing helper2 geometry manifests for the parametric MVP."""

from __future__ import annotations

import json
from pathlib import Path


def load_geometry_manifest(path: Path) -> dict:
    """Load the CadQuery/OCP geometry manifest produced by helper2."""
    if not path.exists():
        raise FileNotFoundError(f"geometry manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
