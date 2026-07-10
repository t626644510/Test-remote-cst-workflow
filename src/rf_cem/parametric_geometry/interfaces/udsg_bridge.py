"""Bridge existing RF-CEM UDSG generation into parametric geometry."""

from __future__ import annotations

from rf_cem.design_package import BaselineDesignPackage, BaselinePaths
from rf_cem.history_templates import load_cst_history_templates
from rf_cem.udsg_builder import build_baseline_udsg


def build_current_udsg(paths: BaselinePaths) -> tuple[dict, dict, object]:
    """Build UDSG using the existing RF-CEM v0 path."""
    templates = load_cst_history_templates(paths.model_history_json)
    udsg, review_diff = build_baseline_udsg(paths, BaselineDesignPackage(), templates.recipe)
    return udsg, review_diff, templates
