"""Versioned, explainable feature-detection profiles."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Mapping, Optional

import yaml


BASE_RULES = {
    "profile_version": "0.1",
    "beam_pipe_radius_max_ratio": 0.45,
    "beam_pipe_end_fraction": 0.25,
    "end_face_fraction": 0.08,
    "wall_radius_min_ratio": 0.60,
    "interior_margin_fraction": 0.12,
    "iris_radius_max_ratio": 0.45,
    "equator_radius_min_ratio": 0.85,
    "blend_radius_max_ratio": 0.14,
    "side_port_radius_min_ratio": 0.35,
    "enable_cathode_at_axis_min": False,
    "enable_side_ports": True,
}


MODEL_PROFILES = {
    "bare_cavity_500mhz": {
        **BASE_RULES,
        "description": "Axisymmetric 500 MHz bare cavity profile.",
    },
    "xband_2.3cell_gun": {
        **BASE_RULES,
        "description": "X-band gun profile with cathode-end semantics.",
        "enable_cathode_at_axis_min": True,
        "end_face_fraction": 0.10,
        "iris_radius_max_ratio": 0.40,
    },
    "normal_conducting_500mhz": {
        **BASE_RULES,
        "description": "Complex normal-conducting cavity with side-port candidates.",
        "side_port_radius_min_ratio": 0.25,
        "blend_radius_max_ratio": 0.12,
    },
}


def load_model_profile(model_type: str, rules_path: Optional[Path] = None) -> dict:
    """Load a built-in profile and merge an optional reviewed YAML override."""
    if model_type not in MODEL_PROFILES:
        raise ValueError(f"Unknown model type: {model_type}")
    profile = deepcopy(MODEL_PROFILES[model_type])
    if rules_path is None:
        return profile

    payload = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise ValueError(f"Rules YAML must contain a mapping: {rules_path}")
    overrides = payload.get("profiles", {}).get(model_type, {}) if isinstance(payload.get("profiles"), Mapping) else {}
    if not overrides and isinstance(payload.get("rules"), Mapping):
        overrides = payload["rules"]
    if not isinstance(overrides, Mapping):
        raise ValueError(f"Rules override for {model_type} must be a mapping")
    unknown = sorted(set(overrides) - set(profile))
    if unknown:
        raise ValueError(f"Unknown rule key(s) for {model_type}: {', '.join(unknown)}")
    profile.update(overrides)
    profile["rules_source"] = str(rules_path)
    return profile
