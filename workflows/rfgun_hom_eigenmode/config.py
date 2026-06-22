"""Configuration loading and validation for Workflow 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ResultContractConfig:
    paths: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    regional_q_paths: dict[str, str] = field(default_factory=dict)
    q0_components: tuple[str, ...] = ()
    required: tuple[str, ...] = (
        "frequency",
        "r_over_q",
        "voltage",
        "total_energy",
    )


@dataclass(frozen=True)
class FieldContractConfig:
    export_dir: Path
    patterns: dict[str, str]
    mode_field_patterns: dict[str, str] = field(default_factory=dict)
    line_result_paths: dict[str, str] = field(default_factory=dict)
    field_dataset: str = ""
    z_dataset: str = ""
    field_component: str = "z"


@dataclass(frozen=True)
class Workflow4Config:
    input_csv: Path
    template_path: Path
    output_root: Path
    campaign_dir: Path | None
    cst_library_path: Path
    connect_mode: str
    parameter_name: str
    beta: float
    offset_mm: float
    search_half_width_mhz: float
    guard_mhz: float
    max_modes: int
    max_clusters_per_window: int
    split_overlap_mhz: float
    solver_timeout_s: float
    solver_settle_s: float
    retry_attempts: int
    retry_cooldown_s: float
    fast_retry_attempts: int
    long_retry_attempts: int
    fast_retry_backoff_s: tuple[float, ...]
    long_attempt_threshold_s: float
    validation_tolerance: float
    dedup_frequency_tolerance_hz: float
    dedup_field_correlation: float
    dedup_r_over_q_tolerance: float
    match_half_width_mhz: float
    boundary_description: str
    result_contract: ResultContractConfig
    field_contract: FieldContractConfig
    source_config_path: Path
    raw: dict[str, Any]


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def load_workflow4_config(path: str | Path) -> Workflow4Config:
    """Load the ``workflow_4`` YAML section and resolve filesystem paths."""

    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        root = yaml.safe_load(handle) or {}
    raw = root.get("workflow_4", root)
    if not isinstance(raw, dict):
        raise ValueError("workflow_4 configuration must be a mapping")
    base = config_path.parent

    cst = raw.get("cst", {})
    solver = raw.get("solver", {})
    planning = raw.get("planning", {})
    physics = raw.get("physics", {})
    dedup = raw.get("dedup", {})
    matching = raw.get("matching", {})
    result_raw = raw.get("result_contract", {})
    field_raw = raw.get("field_contract", {})

    input_csv = _resolve_path(str(raw["input_csv"]), base)
    template_path = _resolve_path(str(raw["template_path"]), base)
    output_root = _resolve_path(str(raw.get("output_root", "runs/workflow4")), base)
    campaign_value = str(raw.get("campaign_dir", "")).strip()
    campaign_dir = _resolve_path(campaign_value, base) if campaign_value else None
    export_dir = _resolve_path(str(field_raw["export_dir"]), base)

    config = Workflow4Config(
        input_csv=input_csv,
        template_path=template_path,
        output_root=output_root,
        campaign_dir=campaign_dir,
        cst_library_path=_resolve_path(str(cst["library_path"]), base),
        connect_mode=str(cst.get("connect_mode", "new")),
        parameter_name=str(raw.get("parameter_name", "fHOM")),
        beta=float(physics.get("beta", 1.0)),
        offset_mm=float(physics.get("offset_mm", 2.0)),
        search_half_width_mhz=float(planning.get("search_half_width_mhz", 10.0)),
        guard_mhz=float(planning.get("guard_mhz", 1.0)),
        max_modes=int(planning.get("max_modes", 3)),
        max_clusters_per_window=int(
            planning.get("max_clusters_per_window", 3)
        ),
        split_overlap_mhz=float(planning.get("split_overlap_mhz", 2.0)),
        solver_timeout_s=float(solver.get("timeout_s", 10800.0)),
        solver_settle_s=float(solver.get("settle_s", 2.0)),
        retry_attempts=int(solver.get("retry_attempts", 2)),
        retry_cooldown_s=float(solver.get("retry_cooldown_s", 5.0)),
        fast_retry_attempts=int(solver.get("fast_retry_attempts", 4)),
        long_retry_attempts=int(solver.get("long_retry_attempts", 2)),
        fast_retry_backoff_s=tuple(
            float(value)
            for value in solver.get("fast_retry_backoff_s", (10, 30, 60))
        ),
        long_attempt_threshold_s=float(
            solver.get("long_attempt_threshold_s", 120.0)
        ),
        validation_tolerance=float(
            physics.get("native_crosscheck_relative_tolerance", 0.02)
        ),
        dedup_frequency_tolerance_hz=float(
            dedup.get("frequency_tolerance_mhz", 0.5)
        )
        * 1e6,
        dedup_field_correlation=float(
            dedup.get("field_correlation_threshold", 0.98)
        ),
        dedup_r_over_q_tolerance=float(
            dedup.get("r_over_q_relative_tolerance", 0.05)
        ),
        match_half_width_mhz=float(matching.get("half_width_mhz", 10.0)),
        boundary_description=str(raw.get("boundary_description", "")),
        result_contract=ResultContractConfig(
            paths={
                str(key): str(value)
                for key, value in result_raw.get("paths", {}).items()
            },
            units={
                str(key): str(value)
                for key, value in result_raw.get("units", {}).items()
            },
            regional_q_paths={
                str(key): str(value)
                for key, value in result_raw.get("regional_q_paths", {}).items()
            },
            q0_components=tuple(result_raw.get("q0_components", ())),
            required=tuple(
                result_raw.get(
                    "required",
                    ("frequency", "r_over_q", "voltage", "total_energy"),
                )
            ),
        ),
        field_contract=FieldContractConfig(
            export_dir=export_dir,
            patterns={
                str(key): str(value)
                for key, value in field_raw.get("patterns", {}).items()
            },
            mode_field_patterns={
                str(key): str(value)
                for key, value in field_raw.get(
                    "mode_field_patterns",
                    {
                        "e": "Mode {mode}_e.h5",
                        "h": "Mode {mode}_h.h5",
                    },
                ).items()
            },
            line_result_paths={
                str(key): str(value)
                for key, value in field_raw.get("line_result_paths", {}).items()
            },
            field_dataset=str(field_raw.get("field_dataset", "")),
            z_dataset=str(field_raw.get("z_dataset", "")),
            field_component=str(field_raw.get("field_component", "z")),
        ),
        source_config_path=config_path,
        raw=raw,
    )
    _validate_config(config)
    return config


def _validate_config(config: Workflow4Config) -> None:
    if config.max_modes != 3:
        raise ValueError("Workflow 4 v1 requires max_modes=3")
    if config.max_clusters_per_window < 1 or config.max_clusters_per_window > 3:
        raise ValueError("max_clusters_per_window must be between 1 and 3")
    if not (0 < config.beta <= 1):
        raise ValueError("physics.beta must satisfy 0 < beta <= 1")
    if config.offset_mm <= 0:
        raise ValueError("physics.offset_mm must be positive")
    if config.search_half_width_mhz <= config.guard_mhz:
        raise ValueError("planning guard must be smaller than search half width")
    if config.retry_attempts < 1:
        raise ValueError("solver.retry_attempts must be at least 1")
    if config.fast_retry_attempts < 1:
        raise ValueError("solver.fast_retry_attempts must be at least 1")
    if config.long_retry_attempts < 1:
        raise ValueError("solver.long_retry_attempts must be at least 1")
    if config.long_attempt_threshold_s <= 0:
        raise ValueError("solver.long_attempt_threshold_s must be positive")
    if any(value < 0 for value in config.fast_retry_backoff_s):
        raise ValueError("solver.fast_retry_backoff_s must be non-negative")
    required_points = {"center", "x_plus", "x_minus", "y_plus", "y_minus"}
    available_points = set(config.field_contract.patterns) | set(
        config.field_contract.line_result_paths
    )
    missing_patterns = sorted(required_points - available_points)
    if missing_patterns:
        raise ValueError(
            "field_contract must configure HDF5 patterns or 1D result paths for: "
            + ", ".join(missing_patterns)
        )
    if set(config.field_contract.mode_field_patterns) != {"e", "h"}:
        raise ValueError(
            "field_contract.mode_field_patterns must define exactly e and h"
        )
    if any(
        "{mode}" not in pattern
        for pattern in config.field_contract.mode_field_patterns.values()
    ):
        raise ValueError(
            "field_contract.mode_field_patterns entries require {mode}"
        )
    unknown_q0 = sorted(
        set(config.result_contract.q0_components)
        - set(config.result_contract.regional_q_paths)
    )
    if unknown_q0:
        raise ValueError(
            "result_contract.q0_components are not regional_q_paths: "
            + ", ".join(unknown_q0)
        )
