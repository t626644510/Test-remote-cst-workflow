"""RF-CEM semantic CST translation helpers.

Public compatibility exports are loaded lazily so no-CST tools such as the
Workbench Desktop launcher do not import translator or CST-facing modules.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "BaselineDesignPackage": ("rf_cem.design_package", "BaselineDesignPackage"),
    "BaselinePaths": ("rf_cem.design_package", "BaselinePaths"),
    "CstHistoryTemplates": ("rf_cem.history_templates", "CstHistoryTemplates"),
    "build_baseline_udsg": ("rf_cem.udsg_builder", "build_baseline_udsg"),
    "load_cst_history_templates": (
        "rf_cem.history_templates",
        "load_cst_history_templates",
    ),
    "translate_baseline": ("rf_cem.translator", "translate_baseline"),
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
