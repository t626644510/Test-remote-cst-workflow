from __future__ import annotations

import csv
from pathlib import Path

import pytest

from workflows.rfgun_hom_eigenmode.models import TargetRecord
from workflows.rfgun_hom_eigenmode.planning import (
    build_solver_windows,
    cluster_targets,
    load_target_records,
    saturation_followups,
)


FIELDNAMES = [
    "condition",
    "freq_hz",
    "freq_ghz",
    "q",
    "residual_prominence_db",
    "raw_peak_db",
    "baseline_db",
    "bandwidth_hz",
    "rank_source",
    "propagation_background",
    "suggested_span_mhz",
]


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _row(condition: str, freq_hz: float, propagation: bool = False) -> dict[str, object]:
    return {
        "condition": condition,
        "freq_hz": freq_hz,
        "freq_ghz": freq_hz / 1e9,
        "q": 10000,
        "residual_prominence_db": 10,
        "raw_peak_db": -40,
        "baseline_db": -50,
        "bandwidth_hz": 100000,
        "rank_source": "q_ranked",
        "propagation_background": str(propagation).lower(),
        "suggested_span_mhz": 1,
    }


def test_load_target_records_validates_units_and_preserves_measurement_q(
    tmp_path: Path,
) -> None:
    path = tmp_path / "targets.csv"
    _write_csv(path, [_row("a", 1.0e9), _row("b", 1.001e9, True)])

    records = load_target_records(path)

    assert len(records) == 2
    assert records[0].source_row_id.startswith("SRC_")
    assert records[0].q_measurement == 10000
    assert records[1].propagation_background is True


def test_load_target_records_rejects_hz_ghz_disagreement(tmp_path: Path) -> None:
    path = tmp_path / "targets.csv"
    row = _row("a", 1.0e9)
    row["freq_ghz"] = 1.1
    _write_csv(path, [row])

    with pytest.raises(ValueError, match="disagree"):
        load_target_records(path)


def test_complete_link_forbids_duplicate_condition_and_transitive_chaining(
    tmp_path: Path,
) -> None:
    path = tmp_path / "targets.csv"
    _write_csv(
        path,
        [
            _row("a", 1.000e9),
            _row("b", 1.004e9),
            _row("c", 1.009e9),
            _row("a", 1.003e9),
        ],
    )
    clusters = cluster_targets(load_target_records(path))

    assert all(
        len(cluster.conditions) == len(set(cluster.conditions))
        for cluster in clusters
    )
    assert not any(
        {round(record.freq_hz / 1e6) for record in cluster.records}
        == {1000, 1004, 1009}
        for cluster in clusters
    )


def test_safe_window_merge_caps_clusters_and_uses_guard_band(
    tmp_path: Path,
) -> None:
    path = tmp_path / "targets.csv"
    _write_csv(
        path,
        [
            _row("a", 1.000e9),
            _row("a", 1.006e9),
            _row("a", 1.012e9),
            _row("a", 1.018e9),
        ],
    )
    clusters = cluster_targets(load_target_records(path))
    windows = build_solver_windows(clusters)

    assert all(len(window.cluster_ids) <= 3 for window in windows)
    assert all(
        window.coverage_max_hz - window.coverage_min_hz <= 18e6
        for window in windows
    )
    assert all(
        window.search_max_hz - window.search_min_hz == pytest.approx(20e6)
        for window in windows
    )


def test_saturated_merged_window_splits_then_single_window_probes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "targets.csv"
    _write_csv(path, [_row("a", 1.000e9), _row("a", 1.010e9)])
    clusters = cluster_targets(load_target_records(path))
    merged = build_solver_windows(clusters)[0]
    by_id = {cluster.target_cluster_id: cluster for cluster in clusters}

    split, status = saturation_followups(merged, by_id)
    assert status is None
    assert len(split) == 2
    assert all(len(window.cluster_ids) == 1 for window in split)

    probes, status = saturation_followups(split[0], by_id)
    assert status is None
    assert {window.probe_offset_mhz for window in probes} == {-5.0, 5.0}

    terminal, status = saturation_followups(probes[0], by_id)
    assert terminal == []
    assert status == "mode_enumeration_incomplete"


def test_oversized_cluster_is_fully_covered_by_overlapping_windows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "targets.csv"
    row = _row("a", 1.0e9)
    row["suggested_span_mhz"] = 9.25
    _write_csv(path, [row])
    cluster = cluster_targets(load_target_records(path))[0]

    windows = build_solver_windows([cluster])

    assert len(windows) == 2
    assert windows[0].coverage_min_hz == cluster.required_min_hz
    assert windows[-1].coverage_max_hz == cluster.required_max_hz
    assert windows[1].coverage_min_hz < windows[0].coverage_max_hz
