"""No-CST tolerance analysis dataset — TAM2.

Loads records (dict-shaped evaluation data), filters SUCCESS rows,
resolves metric name aliases, and constructs a deterministic
``ToleranceDataset`` for statistical analysis.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping, Sequence

import numpy as np


# ===================================================================
# Metric alias map
# ===================================================================

# Default aliases: (legacy_name -> canonical_name)
# Canonical names follow the WF1 SAO dashboard standard where possible.
_DEFAULT_ALIAS_MAP: dict[str, str] = {
    # Resonant frequency (GHz)
    "f0_ghz": "resonant_freq",
    "f0_calibrated_ghz": "resonant_freq",
    "resonant_freq": "resonant_freq",
    # Quality factors
    "q_loaded": "q_loaded",
    "q0": "q0",
    "intrinsic_q": "q0",
    # Coupling
    "coupling_beta": "coupling_beta",
    # Peak field
    "e_peak": "peak_e_field",
    "peak_e_field": "peak_e_field",
    # S-parameter
    "s11_db": "s11_db",
    # Input power — note: units may differ
    "p_input_mw": "p_input_mw",       # legacy unit: MW (divided by 1e6)
    "p_input": "p_input",              # WF3 canonical name
    # Modified Poynting
    "Sc_max": "max_modified_poynting",
    "max_modified_poynting": "max_modified_poynting",
    # Pulsed heating
    "DeltaT_K": "pulsed_heating",
    "pulsed_heating": "pulsed_heating",
    # Field flatness
    "field_flatness": "field_flatness",
}

# Metrics whose names differ from legacy but share the same units
# (no conversion needed beyond name resolution).
_SAME_UNIT_ALIASES: frozenset[str] = frozenset({
    "resonant_freq",   # f0_ghz -> resonant_freq, both in GHz
    "peak_e_field",    # e_peak -> peak_e_field, both in MV/m
    "q_loaded",
    "q0",
    "coupling_beta",
    "s11_db",
    "max_modified_poynting",
    "pulsed_heating",
    "field_flatness",
    "p_input",         # p_input_mw and p_input may differ — handled separately
    "p_input_mw",
})

# Metrics where unit conversion may be needed.
# p_input_mw is stored as MW (input_power / 1e6); p_input may be raw power in W.
# TAM2 preserves both as distinct canonical names unless explicit conversion is requested.
_UNIT_SENSITIVE_ALIASES: frozenset[str] = frozenset({
    "p_input_mw",
    "p_input",
})


def normalize_metric_name(
    name: str,
    alias_map: Mapping[str, str] | None = None,
) -> str:
    """Resolve a metric name to its canonical form via *alias_map*.

    Parameters
    ----------
    name : str
        Input metric name.
    alias_map : mapping or None
        Custom alias map.  Falls back to ``_DEFAULT_ALIAS_MAP``.

    Returns
    -------
    str
        Canonical metric name.  Returns the input unchanged if no alias found.
    """
    if alias_map is None:
        alias_map = _DEFAULT_ALIAS_MAP
    return alias_map.get(name, name)


# ===================================================================
# ToleranceDataset
# ===================================================================


@dataclasses.dataclass(frozen=True)
class ToleranceDataset:
    """A cleaned, deterministic dataset for tolerance analysis.

    Parameters
    ----------
    param_names : tuple of str
        Ordered parameter names.
    metric_names : tuple of str
        Ordered canonical metric names (after alias resolution).
    parameter_values : np.ndarray
        Shape ``(n_rows, n_params)``.
    metric_values : np.ndarray
        Shape ``(n_rows, n_metrics)``.
    source_row_count : int
        Total input rows.
    accepted_row_count : int
        Rows that passed SUCCESS/solver_ok filtering.
    skipped_row_count : int
        Rows that were filtered out.
    alias_map : dict of (str, str)
        The alias map used for resolution.
    row_keys : tuple of str or None
        Unique row keys, if available.
    """
    param_names: tuple[str, ...] = ()
    metric_names: tuple[str, ...] = ()
    parameter_values: np.ndarray = dataclasses.field(
        default_factory=lambda: np.empty((0, 0)),
    )
    metric_values: np.ndarray = dataclasses.field(
        default_factory=lambda: np.empty((0, 0)),
    )
    source_row_count: int = 0
    accepted_row_count: int = 0
    skipped_row_count: int = 0
    alias_map: dict[str, str] = dataclasses.field(default_factory=dict)
    row_keys: tuple[str, ...] = ()


# ===================================================================
# Record parsing helpers
# ===================================================================


def _extract_status(record: dict[str, Any]) -> str:
    """Extract and normalize the status string from a record."""
    raw = record.get("status", "")
    if hasattr(raw, "value"):
        return str(raw.value).strip().lower()
    return str(raw).strip().lower()


def _extract_solver_ok(record: dict[str, Any]) -> bool | None:
    """Extract solver_ok; returns None if absent."""
    val = record.get("solver_ok")
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("true", "yes", "1"):
            return True
        return False
    return bool(val)


def _extract_param_names_values(
    record: dict[str, Any],
    *,
    explicit_param_names: Sequence[str] | None = None,
) -> tuple[list[str], list[float]] | None:
    """Extract ordered parameter names and values from a record.

    Resolution order:
    1. *explicit_param_names* (caller-provided) + values from record
    2. ``parameter_identity.param_names`` + ``parameter_identity.values``
    3. Top-level ``param_names`` + ``param_values``
    """
    pid = record.get("parameter_identity")
    if pid is not None:
        pn = pid.get("param_names") if isinstance(pid, dict) else None
        pv = pid.get("values") if isinstance(pid, dict) else None
        if pn and pv:
            if explicit_param_names is not None:
                # Reorder values to match explicit_param_names if possible
                name_to_val = dict(zip(pn, pv))
                try:
                    reordered = [name_to_val[n] for n in explicit_param_names]
                    return list(explicit_param_names), reordered
                except KeyError:
                    pass
            return list(pn), list(pv)

    pn = record.get("param_names")
    pv = record.get("param_values")
    if pn and pv:
        if explicit_param_names is not None:
            name_to_val = dict(zip(pn, pv))
            try:
                reordered = [name_to_val[n] for n in explicit_param_names]
                return list(explicit_param_names), reordered
            except KeyError:
                pass
        return list(pn), list(pv)

    # Fallback: top-level parameters dict (key -> value)
    params_dict = record.get("parameters")
    if isinstance(params_dict, dict) and params_dict:
        pn = sorted(params_dict.keys())
        pv = [float(params_dict[k]) for k in pn]
        if explicit_param_names is not None:
            try:
                reordered = [params_dict[n] for n in explicit_param_names]
                return list(explicit_param_names), [float(v) for v in reordered]
            except KeyError:
                pass
        return pn, pv

    if explicit_param_names is not None:
        return None  # caller asked for specific params but record has none

    return None


def _extract_metric_value(
    record: dict[str, Any],
    canonical_name: str,
    *,
    prefer_raw: bool = True,
) -> float:
    """Extract a single metric value from a record.

    When *prefer_raw* is True (default), ``raw_metrics`` is checked first,
    then ``objective_values``.  Returns ``np.nan`` if not found.
    """
    # Check raw_metrics
    raw = record.get("raw_metrics")
    if isinstance(raw, dict):
        val = raw.get(canonical_name)
        if val is not None and _is_finite(val):
            return float(val)

    # Check objective_values
    obj = record.get("objective_values")
    if isinstance(obj, dict):
        val = obj.get(canonical_name)
        if val is not None and _is_finite(val):
            return float(val)

    # Check legacy (pre-alias) name in the record
    # Only needed if the record doesn't use canonical names yet
    return np.nan


def _is_finite(val: Any) -> bool:
    """True if val is a finite float or int."""
    if not isinstance(val, (int, float)):
        return False
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return False
    return True


# ===================================================================
# Build dataset from records
# ===================================================================


def build_tolerance_dataset_from_records(
    records: Sequence[dict[str, Any]],
    *,
    metric_names: Sequence[str] | None = None,
    param_names: Sequence[str] | None = None,
    alias_map: Mapping[str, str] | None = None,
    success_statuses: Sequence[str] | None = None,
    prefer_raw: bool = True,
    require_solver_ok: bool = True,
) -> ToleranceDataset:
    """Build a ``ToleranceDataset`` from a sequence of record dicts.

    Parameters
    ----------
    records : sequence of dict
        Input evaluation records.
    metric_names : sequence of str or None
        Desired metric columns.  Resolved through alias map.
        If None, all detected canonical metric names are used.
    param_names : sequence of str or None
        Desired parameter columns and order.
        If None, extracted from the first valid record.
    alias_map : mapping or None
        Custom alias map for metric name resolution.
    success_statuses : sequence of str or None
        Statuses considered SUCCESS.  Defaults to ``("success",)``.
    prefer_raw : bool
        If True, extract from ``raw_metrics`` before ``objective_values``.
    require_solver_ok : bool
        If True, rows must have ``solver_ok=True`` to be accepted.

    Returns
    -------
    ToleranceDataset
    """
    if alias_map is None:
        alias_map = _DEFAULT_ALIAS_MAP
    if success_statuses is None:
        success_statuses = ("success",)

    accepted: list[dict[str, Any]] = []
    skipped = 0

    for rec in records:
        status = _extract_status(rec)
        if status not in success_statuses:
            skipped += 1
            continue

        # Check synthetic skip rows
        if status in ("skipped_failure_reuse", "skipped_probably_infeasible"):
            skipped += 1
            continue

        if require_solver_ok:
            solver_ok = _extract_solver_ok(rec)
            if solver_ok is not None and solver_ok is False:
                skipped += 1
                continue

        accepted.append(rec)

    # Determine param_names
    if param_names is None:
        for rec in accepted:
            pn_pv = _extract_param_names_values(rec)
            if pn_pv is not None:
                param_names = list(pn_pv[0])
                break
        if param_names is None:
            param_names = []

    # Determine metric_names
    if metric_names is not None:
        resolved_metric_names = [normalize_metric_name(n, alias_map) for n in metric_names]
    else:
        # Detect all canonical names from accepted records
        seen: set[str] = set()
        for rec in accepted:
            for d in (rec.get("raw_metrics"), rec.get("objective_values")):
                if isinstance(d, dict):
                    for raw_name in d:
                        canonical = normalize_metric_name(str(raw_name), alias_map)
                        seen.add(canonical)
        resolved_metric_names = sorted(seen)

    n_params = len(param_names)
    n_metrics = len(resolved_metric_names)
    n_rows = len(accepted)

    param_array = np.full((n_rows, n_params), np.nan, dtype=float)
    metric_array = np.full((n_rows, n_metrics), np.nan, dtype=float)
    row_keys: list[str] = []

    for i, rec in enumerate(accepted):
        # Parameters
        pn_pv = _extract_param_names_values(rec, explicit_param_names=param_names)
        if pn_pv is not None:
            for j, v in enumerate(pn_pv[1]):
                if j < n_params:
                    param_array[i, j] = float(v)

        # Row key
        pid = rec.get("parameter_identity")
        if isinstance(pid, dict):
            row_keys.append(str(pid.get("parameter_key", "")))
        else:
            pk = rec.get("parameter_key")
            row_keys.append(str(pk) if pk else "")

        # Metrics
        for j, cn in enumerate(resolved_metric_names):
            # Check raw_metrics with canonical name
            found = False
            if prefer_raw:
                raw = rec.get("raw_metrics")
                if isinstance(raw, dict):
                    for raw_name, raw_val in raw.items():
                        if normalize_metric_name(str(raw_name), alias_map) == cn:
                            if _is_finite(raw_val):
                                metric_array[i, j] = float(raw_val)
                                found = True
                                break

            # Check objective_values
            if not found:
                obj = rec.get("objective_values")
                if isinstance(obj, dict):
                    for obj_name, obj_val in obj.items():
                        if normalize_metric_name(str(obj_name), alias_map) == cn:
                            if _is_finite(obj_val):
                                metric_array[i, j] = float(obj_val)
                                found = True
                                break

    return ToleranceDataset(
        param_names=tuple(param_names),
        metric_names=tuple(resolved_metric_names),
        parameter_values=param_array,
        metric_values=metric_array,
        source_row_count=len(records),
        accepted_row_count=n_rows,
        skipped_row_count=skipped,
        alias_map=dict(alias_map),
        row_keys=tuple(row_keys),
    )
