"""RF-CEM Workbench W0-W4 derived registry and local read-only server.

The compatibility surface is lazy so importing the standalone desktop
launcher remains a thin, no-CST standard-library operation.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "BuildSummary": ("rf_cem.workbench.registry", "BuildSummary"),
    "LOOPBACK_HOST": ("rf_cem.workbench.server", "LOOPBACK_HOST"),
    "REQUIRED_W0_INSTANCES": (
        "rf_cem.workbench.indexer",
        "REQUIRED_W0_INSTANCES",
    ),
    "ResolvedWorkbenchProfile": (
        "rf_cem.workbench.profile",
        "ResolvedWorkbenchProfile",
    ),
    "RegistryReader": ("rf_cem.workbench.registry", "RegistryReader"),
    "WORKBENCH_SCHEMA_VERSION": (
        "rf_cem.workbench.registry",
        "WORKBENCH_SCHEMA_VERSION",
    ),
    "WORKBENCH_PROFILE_SCHEMA_VERSION": (
        "rf_cem.workbench.profile",
        "WORKBENCH_PROFILE_SCHEMA_VERSION",
    ),
    "WorkbenchIndexError": ("rf_cem.workbench.indexer", "WorkbenchIndexError"),
    "WorkbenchProfile": ("rf_cem.workbench.profile", "WorkbenchProfile"),
    "WorkbenchProfileError": (
        "rf_cem.workbench.profile",
        "WorkbenchProfileError",
    ),
    "WorkbenchProfileStatus": (
        "rf_cem.workbench.profile",
        "WorkbenchProfileStatus",
    ),
    "WorkbenchRegistryError": (
        "rf_cem.workbench.registry",
        "WorkbenchRegistryError",
    ),
    "WorkbenchServer": ("rf_cem.workbench.server", "WorkbenchServer"),
    "WorkbenchSourceSet": ("rf_cem.workbench.indexer", "WorkbenchSourceSet"),
    "inspect_workbench_profile": (
        "rf_cem.workbench.profile",
        "inspect_workbench_profile",
    ),
    "load_workbench_profile": (
        "rf_cem.workbench.profile",
        "load_workbench_profile",
    ),
    "rebuild_workbench": ("rf_cem.workbench.indexer", "rebuild_workbench"),
    "rebuild_workbench_profile": (
        "rf_cem.workbench.profile",
        "rebuild_workbench_profile",
    ),
    "resolve_workbench_profile": (
        "rf_cem.workbench.profile",
        "resolve_workbench_profile",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
