"""No-CST tolerance sweep dataset model and loaders — TSE2.

Builds on TAM2–TAM6 to support multi-level tolerance sweep analysis.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Mapping, Sequence

from workflows.rfgun_sao.tolerance_dataset import (
    ToleranceDataset,
    build_tolerance_dataset_from_records,
)


# ===================================================================
# Unit conversion
# ===================================================================


def mm_to_um(value_mm: float) -> float:
    """Convert mm to um."""
    return value_mm * 1000.0


def um_to_mm(value_um: float) -> float:
    """Convert um to mm."""
    return value_um / 1000.0


def normalize_tolerance_level(value: float, unit: str) -> tuple[float, float]:
    """Normalize a tolerance level to ``(level_mm, level_um)``.

    Parameters
    ----------
    value : float
        Tolerance level value.
    unit : str
        ``"mm"`` or ``"um"``.

    Returns
    -------
    tuple of (float, float)
        ``(level_mm, level_um)``.

    Raises
    ------
    ValueError
        If *unit* is not ``"mm"`` or ``"um"``.
    """
    u = unit.strip().lower()
    if u == "mm":
        mm = value
        um = mm_to_um(mm)
    elif u == "um":
        um = value
        mm = um_to_mm(um)
    else:
        raise ValueError(f"Unknown tolerance unit: {unit!r} (expected 'mm' or 'um')")
    return mm, um


# ===================================================================
# Config inventory dataclasses
# ===================================================================


@dataclasses.dataclass(frozen=True)
class ToleranceParameterSpec:
    """One entry from ``tolerance.parameters``.

    Parameters
    ----------
    name : str
    enabled : bool
    nominal : float
    tolerance_abs_mm : float
        Absolute tolerance in mm from config.
    tolerance_abs_um : float
        Absolute tolerance converted to um.
    unit : str
    description : str
    """
    name: str = ""
    enabled: bool = True
    nominal: float = 0.0
    tolerance_abs_mm: float = 0.0
    tolerance_abs_um: float = 0.0
    unit: str = "mm"
    description: str = ""


@dataclasses.dataclass(frozen=True)
class ToleranceOutputSpec:
    """One entry from ``tolerance.outputs``.

    Parameters
    ----------
    name : str
    enabled : bool
    description : str
    tam_metric_alias : str or None
        Resolved alias to TAM canonical metric name.
    """
    name: str = ""
    enabled: bool = False
    description: str = ""
    tam_metric_alias: str | None = None


# Default alias map for tolerance outputs
_TOLERANCE_OUTPUT_ALIASES: dict[str, str] = {
    "f0_ghz": "resonant_freq",
    "q_loaded": "q_loaded",
    "coupling_beta": "coupling_beta",
    "q0": "q0",
    "e_peak": "peak_e_field",
    "s11_db": "s11_db",
    "p_input_mw": "p_input_mw",
    "Sc_max": "max_modified_poynting",
    "DeltaT_K": "pulsed_heating",
    "field_flatness": "field_flatness",
}


# ===================================================================
# Config inventory helpers
# ===================================================================


def _ensure_tolerance_section(cfg: dict[str, Any]) -> dict[str, Any]:
    """Extract the ``tolerance`` section or raise."""
    tol = cfg.get("tolerance")
    if tol is None or not isinstance(tol, dict):
        raise ValueError("config is missing 'tolerance' section")
    return tol


def load_tolerance_parameter_specs(
    config: dict[str, Any],
) -> tuple[ToleranceParameterSpec, ...]:
    """Load parameter specs from a config dict.

    Parameters
    ----------
    config : dict
        Full configuration dict (``config/default.yaml`` style).

    Returns
    -------
    tuple of ToleranceParameterSpec
    """
    tol = _ensure_tolerance_section(config)
    params_raw = tol.get("parameters")
    if not params_raw:
        raise ValueError("config 'tolerance' section is missing 'parameters'")

    specs: list[ToleranceParameterSpec] = []
    for p in params_raw:
        name = p.get("name")
        if not name:
            raise ValueError("tolerance parameter missing 'name'")
        nominal = p.get("nominal")
        if nominal is None:
            raise ValueError(f"tolerance parameter {name!r} missing 'nominal'")
        tol_abs = p.get("tolerance_abs")
        if tol_abs is None:
            raise ValueError(f"tolerance parameter {name!r} missing 'tolerance_abs'")
        enabled_raw = p.get("enabled", True)
        enabled = (
            enabled_raw if isinstance(enabled_raw, bool)
            else str(enabled_raw).strip().lower() == "true"
        )
        tol_mm = float(tol_abs)
        specs.append(ToleranceParameterSpec(
            name=str(name),
            enabled=enabled,
            nominal=float(nominal),
            tolerance_abs_mm=tol_mm,
            tolerance_abs_um=mm_to_um(tol_mm),
            unit=str(p.get("unit", "mm")),
            description=str(p.get("description", "")),
        ))
    return tuple(specs)


def load_tolerance_output_specs(
    config: dict[str, Any],
    alias_map: Mapping[str, str] | None = None,
) -> tuple[ToleranceOutputSpec, ...]:
    """Load output specs from a config dict.

    Parameters
    ----------
    config : dict
        Full configuration dict.
    alias_map : mapping or None
        Custom alias map.  Defaults to ``_TOLERANCE_OUTPUT_ALIASES``.

    Returns
    -------
    tuple of ToleranceOutputSpec
    """
    if alias_map is None:
        alias_map = _TOLERANCE_OUTPUT_ALIASES
    tol = _ensure_tolerance_section(config)
    outputs_raw = tol.get("outputs")
    if not outputs_raw:
        raise ValueError("config 'tolerance' section is missing 'outputs'")

    specs: list[ToleranceOutputSpec] = []
    for o in outputs_raw:
        name = o.get("name")
        if not name:
            raise ValueError("tolerance output missing 'name'")
        enabled_raw = o.get("enabled", False)
        enabled = (
            enabled_raw if isinstance(enabled_raw, bool)
            else str(enabled_raw).strip().lower() == "true"
        )
        alias = alias_map.get(str(name))
        specs.append(ToleranceOutputSpec(
            name=str(name),
            enabled=enabled,
            description=str(o.get("description", "")),
            tam_metric_alias=alias,
        ))
    return tuple(specs)


def enabled_tolerance_parameters(
    specs: tuple[ToleranceParameterSpec, ...],
) -> tuple[ToleranceParameterSpec, ...]:
    """Filter to enabled parameter specs, preserving order."""
    return tuple(s for s in specs if s.enabled)


def enabled_tolerance_outputs(
    specs: tuple[ToleranceOutputSpec, ...],
) -> tuple[ToleranceOutputSpec, ...]:
    """Filter to enabled output specs, preserving order."""
    return tuple(s for s in specs if s.enabled)


# ===================================================================
# Sweep data model
# ===================================================================


@dataclasses.dataclass(frozen=True)
class ToleranceSweepGroup:
    """One tolerance-level analysis group.

    Parameters
    ----------
    tolerance_parameter : str
    tolerance_level_um : float
        Tolerance level in microns.
    tolerance_level_mm : float
        Tolerance level in mm.
    dataset : ToleranceDataset
        TAM2 dataset for records at this level.
    source_label : str
        Deterministic label (e.g. ``"offset1_3um"``).
    db_path : str or None
        Source DB path, if available.
    nominal : float or None
        Nominal parameter value.
    unit : str
        Unit string.
    """
    tolerance_parameter: str = ""
    tolerance_level_um: float = 0.0
    tolerance_level_mm: float = 0.0
    dataset: ToleranceDataset = dataclasses.field(default_factory=ToleranceDataset)
    source_label: str = ""
    db_path: str | None = None
    nominal: float | None = None
    unit: str = "mm"


@dataclasses.dataclass(frozen=True)
class ToleranceSweepDataset:
    """Collection of sweep groups for one parameter.

    Parameters
    ----------
    tolerance_parameter : str
    groups : tuple of ToleranceSweepGroup
        Sorted by ``tolerance_level_um`` ascending.
    tolerance_levels_um : tuple of float
        Sorted tolerance levels.
    nominal : float or None
    unit : str
    """
    tolerance_parameter: str = ""
    groups: tuple[ToleranceSweepGroup, ...] = ()
    tolerance_levels_um: tuple[float, ...] = ()
    nominal: float | None = None
    unit: str = "mm"


# ===================================================================
# Sweep group builders
# ===================================================================


def build_sweep_group_from_records(
    records: Sequence[dict[str, Any]],
    tolerance_parameter: str,
    tolerance_level: float,
    tolerance_unit: str = "um",
    source_label: str | None = None,
    db_path: str | None = None,
    dataset_kwargs: dict[str, Any] | None = None,
) -> ToleranceSweepGroup:
    """Build a sweep group from in-memory records.

    Parameters
    ----------
    records : sequence of dict
        TAM2-compatible records.
    tolerance_parameter : str
    tolerance_level : float
    tolerance_unit : str
        ``"mm"`` or ``"um"``.
    source_label : str or None
    db_path : str or None
    dataset_kwargs : dict or None
        Additional kwargs passed to ``build_tolerance_dataset_from_records()``.

    Returns
    -------
    ToleranceSweepGroup
    """
    level_mm, level_um = normalize_tolerance_level(tolerance_level, tolerance_unit)

    if source_label is None:
        source_label = f"{tolerance_parameter}_{int(round(level_um))}um"

    kwargs = dict(dataset_kwargs or {})
    ds = build_tolerance_dataset_from_records(list(records), **kwargs)

    return ToleranceSweepGroup(
        tolerance_parameter=tolerance_parameter,
        tolerance_level_um=level_um,
        tolerance_level_mm=level_mm,
        dataset=ds,
        source_label=source_label,
        db_path=db_path,
    )


def build_sweep_dataset(
    groups: Sequence[ToleranceSweepGroup],
    tolerance_parameter: str | None = None,
) -> ToleranceSweepDataset:
    """Build a sweep dataset from a sequence of groups.

    Parameters
    ----------
    groups : sequence of ToleranceSweepGroup
    tolerance_parameter : str or None
        Expected tolerance parameter.  If omitted, inferred from first group.

    Returns
    -------
    ToleranceSweepDataset

    Raises
    ------
    ValueError
        If *groups* is empty, contains mixed parameters, or duplicate levels.
    """
    if not groups:
        raise ValueError("build_sweep_dataset requires at least one group")

    # Determine parameter name
    if tolerance_parameter is None:
        tolerance_parameter = groups[0].tolerance_parameter

    # Validate parameter consistency
    for g in groups:
        if g.tolerance_parameter != tolerance_parameter:
            raise ValueError(
                f"Mixed tolerance parameters: got {g.tolerance_parameter!r}, "
                f"expected {tolerance_parameter!r}",
            )

    # Sort by level_um ascending
    sorted_groups = sorted(groups, key=lambda g: g.tolerance_level_um)

    # Check duplicates
    seen: set[float] = set()
    for g in sorted_groups:
        if g.tolerance_level_um in seen:
            raise ValueError(
                f"Duplicate tolerance level: {g.tolerance_level_um} um",
            )
        seen.add(g.tolerance_level_um)

    levels_um = tuple(g.tolerance_level_um for g in sorted_groups)
    nominal = groups[0].nominal
    unit = groups[0].unit

    return ToleranceSweepDataset(
        tolerance_parameter=tolerance_parameter,
        groups=tuple(sorted_groups),
        tolerance_levels_um=levels_um,
        nominal=nominal,
        unit=unit,
    )


def build_sweep_dataset_from_record_groups(
    group_specs: Sequence[dict[str, Any]],
) -> ToleranceSweepDataset:
    """Build a sweep dataset from a sequence of group spec dicts.

    Each *group_spec* must contain:

    - ``tolerance_parameter``
    - ``tolerance_level``
    - ``tolerance_unit`` (optional, default ``"um"``)
    - ``records`` (list of TAM2-compatible records)
    - ``source_label`` (optional)
    - ``dataset_kwargs`` (optional)

    Parameters
    ----------
    group_specs : sequence of dict

    Returns
    -------
    ToleranceSweepDataset
    """
    groups: list[ToleranceSweepGroup] = []
    param_name: str | None = None
    for spec in group_specs:
        tp = spec["tolerance_parameter"]
        if param_name is None:
            param_name = tp
        groups.append(build_sweep_group_from_records(
            records=spec["records"],
            tolerance_parameter=tp,
            tolerance_level=spec["tolerance_level"],
            tolerance_unit=spec.get("tolerance_unit", "um"),
            source_label=spec.get("source_label"),
            dataset_kwargs=spec.get("dataset_kwargs"),
        ))
    return build_sweep_dataset(groups, tolerance_parameter=param_name)


# ===================================================================
# Optional DB-level loader
# ===================================================================


def build_sweep_group_from_db(
    db_path: str | Path,
    tolerance_parameter: str,
    tolerance_level: float,
    tolerance_unit: str = "um",
    source_label: str | None = None,
    dataset_kwargs: dict[str, Any] | None = None,
) -> ToleranceSweepGroup:
    """Build a sweep group from a SQLite evaluation database.

    Parameters
    ----------
    db_path : str or Path
        Path to existing SQLite evaluation DB.
    tolerance_parameter : str
    tolerance_level : float
    tolerance_unit : str
    source_label : str or None
    dataset_kwargs : dict or None

    Returns
    -------
    ToleranceSweepGroup

    Raises
    ------
    FileNotFoundError
        If *db_path* does not exist.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"DB path does not exist: {path}")

    from workflows.rfgun_sao.tolerance_db_adapter import load_records_from_sqlite_db

    records = load_records_from_sqlite_db(str(path))

    level_mm, level_um = normalize_tolerance_level(tolerance_level, tolerance_unit)

    if source_label is None:
        source_label = f"{tolerance_parameter}_{int(round(level_um))}um"

    kwargs = dict(dataset_kwargs or {})
    ds = build_tolerance_dataset_from_records(records, **kwargs)

    return ToleranceSweepGroup(
        tolerance_parameter=tolerance_parameter,
        tolerance_level_um=level_um,
        tolerance_level_mm=level_mm,
        dataset=ds,
        source_label=source_label,
        db_path=str(path),
    )
