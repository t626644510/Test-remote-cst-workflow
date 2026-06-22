from __future__ import annotations

import csv
from pathlib import Path

from workflows.rfgun_hom_eigenmode.models import (
    EigenmodeCandidate,
    TargetCluster,
    TargetRecord,
)
from workflows.rfgun_hom_eigenmode.output import write_match_outputs


def _record(source_id: str, propagation: bool = False) -> TargetRecord:
    return TargetRecord(
        source_row_id=source_id,
        source_row_number=2,
        condition="condition",
        freq_hz=1e9,
        freq_ghz=1.0,
        q_measurement=10000,
        residual_prominence_db=10,
        raw_peak_db=-40,
        baseline_db=-50,
        bandwidth_hz=1e5,
        rank_source="q_ranked",
        propagation_background=propagation,
        suggested_span_mhz=1,
    )


def _cluster(record: TargetRecord) -> TargetCluster:
    return TargetCluster(
        target_cluster_id="TC_0001",
        records=(record,),
        target_freq_hz=record.freq_hz,
        freq_min_hz=record.freq_hz,
        freq_max_hz=record.freq_hz,
        suggested_span_max_mhz=1,
        required_min_hz=record.freq_hz - 1e6,
        required_max_hz=record.freq_hz + 1e6,
        propagation_background=record.propagation_background,
    )


def test_measurement_q_is_combined_per_source_row(tmp_path: Path) -> None:
    record = _record("SRC_1")
    mode = EigenmodeCandidate(
        mode_id="MODE_1",
        solver_window_id="WIN_1",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=1e9,
        r_over_q_ohm=2.0,
        dipole_a_total_ohm_per_m2=3.0,
        transverse_r_over_q_ohm_per_m=4.0,
        circuit_transverse_r_over_q_ohm=5.0,
    )

    write_match_outputs(
        tmp_path,
        clusters=[_cluster(record)],
        candidates=[mode],
        match_half_width_mhz=10,
    )
    with (tmp_path / "hom_mode_condition_results.csv").open(
        encoding="utf-8-sig"
    ) as handle:
        row = next(csv.DictReader(handle))

    assert float(row["R_parallel_from_measured_Q_ohm"]) == 20000
    assert float(row["R_transverse_from_measured_Q_ohm_per_m2"]) == 30000
    assert float(row["R_transverse_from_measured_Q_ohm_per_m"]) == 40000
    assert float(row["R_circuit_transverse_from_measured_Q_ohm"]) == 50000


def test_propagation_target_is_never_silently_dropped(tmp_path: Path) -> None:
    record = _record("SRC_PROP", propagation=True)

    write_match_outputs(
        tmp_path,
        clusters=[_cluster(record)],
        candidates=[],
        match_half_width_mhz=10,
    )
    with (tmp_path / "hom_unmatched_targets.csv").open(
        encoding="utf-8-sig"
    ) as handle:
        row = next(csv.DictReader(handle))

    assert row["source_row_id"] == "SRC_PROP"
    assert row["reason"] == "propagating_no_discrete_mode"


def test_pending_target_is_not_reported_as_physical_unmatched(
    tmp_path: Path,
) -> None:
    record = _record("SRC_PENDING", propagation=True)

    write_match_outputs(
        tmp_path,
        clusters=[_cluster(record)],
        candidates=[],
        match_half_width_mhz=10,
        cluster_failure_reasons={"TC_0001": "not_simulated"},
    )
    with (tmp_path / "hom_unmatched_targets.csv").open(
        encoding="utf-8-sig"
    ) as handle:
        row = next(csv.DictReader(handle))

    assert row["reason"] == "not_simulated"


def test_condition_output_carries_validity_and_boundary_warnings(
    tmp_path: Path,
) -> None:
    record = _record("SRC_WARNING")
    mode = EigenmodeCandidate(
        mode_id="MODE_WARN",
        solver_window_id="WIN_1",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=1e9,
        derived_valid=False,
        data_availability_reason="native_r_over_q_crosscheck_failed",
        warning_codes=["propagating_port_modes_not_considered:1_4"],
        boundary_sensitive=True,
        mode_count_censored=True,
    )

    write_match_outputs(
        tmp_path,
        clusters=[_cluster(record)],
        candidates=[mode],
        match_half_width_mhz=10,
    )
    with (tmp_path / "hom_mode_condition_results.csv").open(
        encoding="utf-8-sig"
    ) as handle:
        row = next(csv.DictReader(handle))

    assert row["derived_valid"] == "false"
    assert row["boundary_sensitive"] == "true"
    assert row["mode_count_censored"] == "true"
    assert "propagating_port_modes_not_considered" in row["warning_codes"]
    assert row["data_availability_reason"] == (
        "native_r_over_q_crosscheck_failed"
    )
