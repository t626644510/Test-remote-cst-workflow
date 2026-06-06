"""Workflow 2 placeholder runner — HOM antenna multi-project optimisation.

This module is a **compatibility planning placeholder**.  No runtime has
been migrated yet.

The current public entry point remains at the project root::

    python run_workflow_2.py

Once migration is complete this module will become the new entry, and the
root ``run_workflow_2.py`` will be repointed here (mirroring the WF1
pattern at ``workflows/rfgun_sao/run.py`` and
``workflows/rfgun_single_pass/run.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__: list[str] = [
    "LEGACY_ENTRY",
    "PACKAGE_ROOT",
    "describe_legacy_entry",
    "get_legacy_entrypoint",
]

#: Absolute path to the project root (two levels up from this file).
PACKAGE_ROOT: Path = Path(__file__).resolve().parents[2]

#: Name of the legacy root entry point script.
LEGACY_ENTRY: str = "run_workflow_2.py"


def describe_legacy_entry() -> str:
    """Return a human-readable description of the current legacy entry point.

    Returns
    -------
    str
        Description string.  Not a callable — no CST, no config, no optimiser.
    """
    return (
        f"Legacy entry point: `python {LEGACY_ENTRY}` "
        f"(located at {PACKAGE_ROOT / LEGACY_ENTRY}). "
        "See ``workflows/rfgun_hom_antenna/README.md`` or "
        "``reports/restructure_plan/workflow2_current_context.md`` "
        "for the migration plan."
    )


def get_legacy_entrypoint() -> Path:
    """Return the absolute path of the legacy root entry script.

    Returns
    -------
    Path
        Absolute ``Path`` to ``run_workflow_2.py`` at the project root.
    """
    return PACKAGE_ROOT / LEGACY_ENTRY
