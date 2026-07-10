"""Normalized CSV and manifest outputs for Workflow 4."""

from __future__ import annotations

import csv
import json
import os
import statistics
from pathlib import Path
from typing import Any, Iterable

from .models import EigenmodeCandidate, SolverWindow, TargetCluster

EIGENMODE_FIELDS = [
    "mode_id",
    "solver_window_id",
    "attempt_id",
    "template_revision_id",
    "template_hash",
    "native_mode_number",
    "freq_sim_hz",
    "freq_sim_ghz",
    "longitudinal_R_over_Q_ohm",
    "voltage_v",
    "stored_energy_j",
    "total_loss_w",
    "residual",
    "Q_loaded_simulated",
    "Q0_simulated",
    "regional_q_json",
    "dipole_R_over_Q_ohm_per_m2",
    "dipole_R_over_Q_x_ohm_per_m2",
    "dipole_R_over_Q_y_ohm_per_m2",
    "transverse_R_over_Q_ohm_per_m",
    "circuit_transverse_R_over_Q_ohm",
    "transverse_kick_factor_V_per_C_per_m",
    "gradient_x_real_V_per_m",
    "gradient_x_imag_V_per_m",
    "gradient_y_real_V_per_m",
    "gradient_y_imag_V_per_m",
    "polarization_deg",
    "derived_valid",
    "voltage_relative_error",
    "R_over_Q_relative_error",
    "data_availability_reason",
    "warning_codes",
    "boundary_sensitive",
    "mode_count_censored",
    "duplicate_member_ids",
    "dedup_confidence",
    "field_paths_json",
    "transverse_definition",
    "normalization_convention",
]


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.replace(temporary, path)


def write_target_clusters(path: str | Path, clusters: Iterable[TargetCluster]) -> None:
    rows = []
    for cluster in clusters:
        q_values = [record.q_measurement for record in cluster.records]
        rows.append(
            {
                "target_cluster_id": cluster.target_cluster_id,
                "target_freq_hz": cluster.target_freq_hz,
                "target_freq_ghz": cluster.target_freq_hz / 1e9,
                "freq_min_hz": cluster.freq_min_hz,
                "freq_max_hz": cluster.freq_max_hz,
                "required_min_hz": cluster.required_min_hz,
                "required_max_hz": cluster.required_max_hz,
                "suggested_span_max_mhz": cluster.suggested_span_max_mhz,
                "source_row_ids": ";".join(cluster.source_row_ids),
                "source_row_numbers": ";".join(
                    str(record.source_row_number) for record in cluster.records
                ),
                "source_conditions": ";".join(cluster.conditions),
                "measurement_q_min": min(q_values),
                "measurement_q_median": statistics.median(q_values),
                "measurement_q_max": max(q_values),
                "propagation_background": str(
                    cluster.propagation_background
                ).lower(),
            }
        )
    fields = list(rows[0]) if rows else [
        "target_cluster_id",
        "target_freq_hz",
        "target_freq_ghz",
    ]
    _write_csv(Path(path), fields, rows)


def write_solver_windows(path: str | Path, windows: Iterable[SolverWindow]) -> None:
    rows = []
    for window in windows:
        rows.append(
            {
                "solver_window_id": window.solver_window_id,
                "cluster_ids": ";".join(window.cluster_ids),
                "fHOM_mhz": window.f_hom_mhz,
                "search_min_hz": window.search_min_hz,
                "search_max_hz": window.search_max_hz,
                "coverage_min_hz": window.coverage_min_hz,
                "coverage_max_hz": window.coverage_max_hz,
                "kind": window.kind,
                "parent_window_id": window.parent_window_id,
                "probe_offset_mhz": window.probe_offset_mhz,
            }
        )
    fields = list(rows[0]) if rows else ["solver_window_id", "cluster_ids", "fHOM_mhz"]
    _write_csv(Path(path), fields, rows)


def write_eigenmode_results(
    path: str | Path,
    candidates: Iterable[EigenmodeCandidate],
) -> None:
    rows = [_eigenmode_row(mode) for mode in candidates]
    _write_csv(Path(path), EIGENMODE_FIELDS, rows)


def _eigenmode_row(mode: EigenmodeCandidate) -> dict[str, Any]:
    return {
                "mode_id": mode.mode_id,
                "solver_window_id": mode.solver_window_id,
                "attempt_id": mode.attempt_id,
                "template_revision_id": mode.template_revision_id,
                "template_hash": mode.template_hash,
                "native_mode_number": mode.mode_number,
                "freq_sim_hz": mode.frequency_hz,
                "freq_sim_ghz": mode.frequency_hz / 1e9,
                "longitudinal_R_over_Q_ohm": mode.r_over_q_ohm,
                "voltage_v": mode.voltage_v,
                "stored_energy_j": mode.total_energy_j,
                "total_loss_w": mode.total_loss_w,
                "residual": mode.residual,
                "Q_loaded_simulated": mode.q_loaded,
                "Q0_simulated": mode.q0,
                "regional_q_json": json.dumps(mode.regional_q, sort_keys=True),
                "dipole_R_over_Q_ohm_per_m2": mode.dipole_a_total_ohm_per_m2,
                "dipole_R_over_Q_x_ohm_per_m2": mode.dipole_a_x_ohm_per_m2,
                "dipole_R_over_Q_y_ohm_per_m2": mode.dipole_a_y_ohm_per_m2,
                "transverse_R_over_Q_ohm_per_m": mode.transverse_r_over_q_ohm_per_m,
                "circuit_transverse_R_over_Q_ohm": mode.circuit_transverse_r_over_q_ohm,
                "transverse_kick_factor_V_per_C_per_m": (
                    mode.transverse_kick_factor_v_per_c_per_m
                ),
                "gradient_x_real_V_per_m": (
                    mode.gradient_x_v_per_m.real
                    if mode.gradient_x_v_per_m is not None
                    else None
                ),
                "gradient_x_imag_V_per_m": (
                    mode.gradient_x_v_per_m.imag
                    if mode.gradient_x_v_per_m is not None
                    else None
                ),
                "gradient_y_real_V_per_m": (
                    mode.gradient_y_v_per_m.real
                    if mode.gradient_y_v_per_m is not None
                    else None
                ),
                "gradient_y_imag_V_per_m": (
                    mode.gradient_y_v_per_m.imag
                    if mode.gradient_y_v_per_m is not None
                    else None
                ),
                "polarization_deg": mode.polarization_deg,
                "derived_valid": str(mode.derived_valid).lower(),
                "voltage_relative_error": mode.voltage_relative_error,
                "R_over_Q_relative_error": mode.r_over_q_relative_error,
                "data_availability_reason": mode.data_availability_reason,
                "warning_codes": ";".join(mode.warning_codes),
                "boundary_sensitive": str(mode.boundary_sensitive).lower(),
                "mode_count_censored": str(mode.mode_count_censored).lower(),
                "duplicate_member_ids": ";".join(mode.duplicate_member_ids),
                "dedup_confidence": mode.dedup_confidence,
                "field_paths_json": json.dumps(mode.field_paths, sort_keys=True),
                "transverse_definition": "|grad(V_parallel)|^2/(omega*U)",
                "normalization_convention": "1/(omega*U)",
            }


def write_valid_seed(
    path: str | Path,
    candidates: Iterable[EigenmodeCandidate],
    mappings: Iterable[dict[str, Any]],
) -> None:
    """Write one row per validated mode while preserving all target ambiguity."""

    by_mode: dict[str, list[dict[str, Any]]] = {}
    for mapping in mappings:
        by_mode.setdefault(str(mapping["mode_id"]), []).append(mapping)
    fields = [
        *EIGENMODE_FIELDS,
        "target_cluster_ids",
        "target_match_statuses",
        "seed_status",
    ]
    rows = []
    for mode in candidates:
        if not mode.derived_valid:
            continue
        mode_mappings = by_mode.get(mode.mode_id, [])
        row = _eigenmode_row(mode)
        row.update(
            {
                "target_cluster_ids": ";".join(
                    str(item["target_cluster_id"]) for item in mode_mappings
                ),
                "target_match_statuses": ";".join(
                    str(item["match_status"]) for item in mode_mappings
                ),
                "seed_status": (
                    "target_candidate" if mode_mappings else "extra_discovery"
                ),
            }
        )
        rows.append(row)
    _write_csv(Path(path), fields, rows)


def build_mode_target_mapping(
    candidates: Iterable[EigenmodeCandidate],
    clusters: Iterable[TargetCluster],
    *,
    match_half_width_mhz: float,
) -> tuple[list[dict[str, Any]], dict[str, list[EigenmodeCandidate]]]:
    """Create a deterministic frequency-based many-to-many target mapping."""

    mode_list = list(candidates)
    mappings: list[dict[str, Any]] = []
    by_cluster: dict[str, list[EigenmodeCandidate]] = {}
    half_width_hz = match_half_width_mhz * 1e6
    for cluster in clusters:
        matches = [
            mode
            for mode in mode_list
            if abs(mode.frequency_hz - cluster.target_freq_hz) <= half_width_hz
        ]
        matches.sort(key=lambda mode: abs(mode.frequency_hz - cluster.target_freq_hz))
        by_cluster[cluster.target_cluster_id] = matches
        status = (
            "matched"
            if len(matches) == 1
            else "ambiguous"
            if len(matches) > 1
            else "unmatched"
        )
        for rank, mode in enumerate(matches, start=1):
            delta_hz = mode.frequency_hz - cluster.target_freq_hz
            score = max(0.0, 1.0 - abs(delta_hz) / half_width_hz)
            mappings.append(
                {
                    "mode_id": mode.mode_id,
                    "target_cluster_id": cluster.target_cluster_id,
                    "match_status": status,
                    "candidate_rank": rank,
                    "frequency_score": score,
                    "delta_freq_hz": delta_hz,
                    "delta_freq_mhz": delta_hz / 1e6,
                    "target_freq_hz": cluster.target_freq_hz,
                    "freq_sim_hz": mode.frequency_hz,
                    "propagation_background": str(
                        cluster.propagation_background
                    ).lower(),
                }
            )
    return mappings, by_cluster


def write_match_outputs(
    output_dir: str | Path,
    *,
    clusters: Iterable[TargetCluster],
    candidates: Iterable[EigenmodeCandidate],
    match_half_width_mhz: float,
    cluster_failure_reasons: dict[str, str] | None = None,
) -> None:
    output = Path(output_dir)
    cluster_list = list(clusters)
    mappings, by_cluster = build_mode_target_mapping(
        candidates,
        cluster_list,
        match_half_width_mhz=match_half_width_mhz,
    )
    mapping_fields = list(mappings[0]) if mappings else [
        "mode_id",
        "target_cluster_id",
        "match_status",
    ]
    _write_csv(output / "hom_mode_target_map.csv", mapping_fields, mappings)

    condition_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    failure_reasons = cluster_failure_reasons or {}
    for cluster in cluster_list:
        matched_modes = by_cluster[cluster.target_cluster_id]
        match_status = (
            "matched"
            if len(matched_modes) == 1
            else "ambiguous"
            if len(matched_modes) > 1
            else "unmatched"
        )
        if not matched_modes:
            reason = failure_reasons.get(
                cluster.target_cluster_id,
                "propagating_no_discrete_mode"
                if cluster.propagation_background
                else "no_mode_in_window",
            )
            for record in cluster.records:
                unmatched_rows.append(
                    {
                        "source_row_id": record.source_row_id,
                        "source_row_number": record.source_row_number,
                        "target_cluster_id": cluster.target_cluster_id,
                        "condition": record.condition,
                        "measurement_freq_hz": record.freq_hz,
                        "Q_measurement": record.q_measurement,
                        "propagation_background": str(
                            record.propagation_background
                        ).lower(),
                        "reason": reason,
                    }
                )
            continue

        for mode in matched_modes:
            for record in cluster.records:
                q = record.q_measurement
                condition_rows.append(
                    {
                        "mode_id": mode.mode_id,
                        "target_cluster_id": cluster.target_cluster_id,
                        "source_row_id": record.source_row_id,
                        "source_row_number": record.source_row_number,
                        "condition": record.condition,
                        "measurement_freq_hz": record.freq_hz,
                        "Q_measurement": q,
                        "Q_source": "baseline_residual_3db",
                        "match_status": match_status,
                        "derived_valid": str(mode.derived_valid).lower(),
                        "warning_codes": ";".join(mode.warning_codes),
                        "boundary_sensitive": str(mode.boundary_sensitive).lower(),
                        "mode_count_censored": str(
                            mode.mode_count_censored
                        ).lower(),
                        "data_availability_reason": (
                            mode.data_availability_reason
                        ),
                        "longitudinal_R_over_Q_ohm": mode.r_over_q_ohm,
                        "R_parallel_from_measured_Q_ohm": (
                            mode.r_over_q_ohm * q
                            if mode.r_over_q_ohm is not None
                            else None
                        ),
                        "dipole_R_over_Q_ohm_per_m2": (
                            mode.dipole_a_total_ohm_per_m2
                        ),
                        "R_transverse_from_measured_Q_ohm_per_m2": (
                            mode.dipole_a_total_ohm_per_m2 * q
                            if mode.dipole_a_total_ohm_per_m2 is not None
                            else None
                        ),
                        "transverse_R_over_Q_ohm_per_m": (
                            mode.transverse_r_over_q_ohm_per_m
                        ),
                        "R_transverse_from_measured_Q_ohm_per_m": (
                            mode.transverse_r_over_q_ohm_per_m * q
                            if mode.transverse_r_over_q_ohm_per_m is not None
                            else None
                        ),
                        "circuit_transverse_R_over_Q_ohm": (
                            mode.circuit_transverse_r_over_q_ohm
                        ),
                        "R_circuit_transverse_from_measured_Q_ohm": (
                            mode.circuit_transverse_r_over_q_ohm * q
                            if mode.circuit_transverse_r_over_q_ohm is not None
                            else None
                        ),
                    }
                )

    condition_fields = list(condition_rows[0]) if condition_rows else [
        "mode_id",
        "target_cluster_id",
        "source_row_id",
        "condition",
        "Q_measurement",
    ]
    unmatched_fields = list(unmatched_rows[0]) if unmatched_rows else [
        "source_row_id",
        "target_cluster_id",
        "condition",
        "reason",
    ]
    _write_csv(
        output / "hom_mode_condition_results.csv",
        condition_fields,
        condition_rows,
    )
    _write_csv(
        output / "hom_unmatched_targets.csv",
        unmatched_fields,
        unmatched_rows,
    )


def write_json(path: str | Path, payload: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, destination)
