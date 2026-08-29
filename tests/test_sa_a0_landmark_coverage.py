"""No-CST gates for Semantic Acquisition A0 landmark coverage."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from rf_cem.semantic_acquisition import (
    A0SourceSet,
    BoundaryPoint,
    BoundarySegment,
    BoundaryTrace,
    LandmarkCandidate,
    SignalParameters,
    TruthJunction,
    audit_lerec_availability,
    evaluate_coverage,
    extract_landmark_candidates,
    load_truth_junctions,
    write_a0_bundle,
)


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]
R2_RECORD = (
    ROOT
    / "analysis_outputs"
    / "rf_cem_boundary_compiler_td1_td2"
    / "r2_boundary_compiler.24bd2492658ad567"
    / "records"
    / "sls2.r149.6593e02e.compile_record.v2.json"
)
R1_GRAPH = (
    ROOT
    / "analysis_outputs"
    / "rf_cem_semantic_core"
    / "r1_semantic_core.28e8d6fa9efa221f"
    / "instances"
    / "sls2.r149.6593e02e.instance_boundary_graph.v0.json"
)


def test_analytic_curve_exposes_known_radius_and_curvature_signals() -> None:
    parameter = np.linspace(0.0, 1.0, 257)
    points = tuple(
        BoundaryPoint(
            z_mm=100.0 * (value - 0.5),
            r_mm=50.0 + 10.0 * math.sin(2.0 * math.pi * value),
        )
        for value in parameter
    )
    tangent = _unit((100.0, 20.0 * math.pi))
    trace = BoundaryTrace(
        segments=(
            BoundarySegment(
                points=points,
                start_tangent=tangent,
                end_tangent=tangent,
            ),
        )
    )
    extraction = extract_landmark_candidates(
        trace,
        SignalParameters(
            radius_prominence_mm=1.0,
            curvature_prominence_per_mm=0.0005,
            curvature_zero_per_mm=1.0e-6,
        ),
    )
    expected = {
        "radius_local_maximum": _analytic_u(0.25),
        "curvature_zero_crossing": _analytic_u(0.5),
        "radius_local_minimum": _analytic_u(0.75),
    }
    for signal, expected_u in expected.items():
        actual = min(
            candidate.u
            for candidate in extraction.candidates
            if signal in candidate.signals
        )
        assert actual == pytest.approx(expected_u, abs=0.01)
    assert any(
        "curvature_local_maximum" in candidate.signals
        for candidate in extraction.candidates
    )
    assert any("symmetry_z0" in candidate.signals for candidate in extraction.candidates)
    assert [
        candidate.u
        for candidate in extraction.candidates
        if "profile_endpoint" in candidate.signals
    ] == [0.0, 1.0]
    assert extract_landmark_candidates(
        trace,
        SignalParameters(
            radius_prominence_mm=1.0,
            curvature_prominence_per_mm=0.0005,
            curvature_zero_per_mm=1.0e-6,
        ),
    ) == extraction


def test_real_truth_uses_reviewed_graph_types_and_v2_coordinate_bindings() -> None:
    _real_inputs_or_skip()
    truth = load_truth_junctions(ROOT, R2_RECORD, R1_GRAPH)
    assert truth.record.schema_version == "compile_record.v2"
    assert truth.record.instance_id == "sls2.r149.6593e02e"
    assert len(truth.junctions) == 8
    assert [item.landmark_id.rsplit(".", 1)[-1] for item in truth.junctions] == [
        f"{index:02d}" for index in range(8)
    ]
    assert [item.u for item in truth.junctions] == sorted(
        item.u for item in truth.junctions
    )
    assert all(item.projection_residual_mm <= 1.0e-6 for item in truth.junctions)
    assert all(
        item.coordinate_source_path.endswith("compile_record.v2.json")
        and item.coordinate_source_locator.startswith("#/landmark_bindings/")
        and item.semantic_source_path.endswith("instance_boundary_graph.v0.json")
        and item.semantic_source_locator.startswith("#/landmarks/")
        for item in truth.junctions
    )
    assert truth.total_arc_length_mm == pytest.approx(962.9486091580977)

    lerec = audit_lerec_availability(ROOT)
    assert lerec.usable is False
    assert "resampleable compiled/profile geometry" in lerec.reason
    assert "coordinate-bearing reviewed junction truth" in lerec.reason
    assert len(lerec.consumed_json_paths) == 3
    assert any(
        item.get("status") == "not_read_or_parsed_scope_exclusion"
        for item in lerec.found_artifacts
    )


def test_coverage_reports_forward_matches_and_reverse_candidate_counts() -> None:
    truth = (
        _truth("junction.00", 0.10),
        _truth("junction.01", 0.50),
    )
    candidates = (
        _candidate(0.11, "radius_local_maximum"),
        _candidate(0.80, "curvature_local_minimum"),
    )
    result = evaluate_coverage(
        truth,
        candidates,
        total_arc_length_mm=100.0,
        tolerance_u=0.02,
        unstable_candidate_count=3,
    )
    assert result.all_truth_hit is False
    assert result.hit_truth_count == 1
    assert result.candidate_count == 2
    assert result.candidates_hitting_truth_count == 1
    assert result.extra_candidate_count == 1
    assert result.unstable_candidate_count == 3
    assert result.matches[0].absolute_deviation_mm == pytest.approx(1.0)
    assert result.matches[0].hit is True
    assert result.matches[1].hit is False


def test_real_a0_bundle_is_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    _real_inputs_or_skip()
    sources = A0SourceSet(
        repo_root=ROOT,
        compile_record=R2_RECORD,
        instance_graph=R1_GRAPH,
    )
    first = write_a0_bundle(sources, tmp_path / "first")
    second = write_a0_bundle(sources, tmp_path / "second")
    assert first.bundle_id == second.bundle_id
    assert first.input_sha256 == second.input_sha256
    assert _bundle_files(first.path) == _bundle_files(second.path)
    assert set(_bundle_files(first.path)) == {
        "a0_coverage_report.md",
        "a0_coverage_report.v0.json",
        "landmark_coverage.png",
        "source_binding_manifest.v0.json",
    }
    with pytest.raises(FileExistsError, match="already exists"):
        write_a0_bundle(sources, tmp_path / "first")

    coverage = first.report["coverage"]
    assert coverage["all_truth_hit"] is False
    assert coverage["hit_truth_count"] == 4
    assert coverage["truth_junction_count"] == 8
    assert coverage["candidate_count"] == 7
    assert coverage["candidates_hitting_truth_count"] == 4
    assert coverage["extra_candidate_count"] == 3
    assert coverage["unstable_candidate_count"] == 2
    assert {
        item["landmark_id"].rsplit(".", 1)[-1]
        for item in coverage["matches"]
        if not item["hit"]
    } == {"01", "03", "04", "06"}
    assert all(
        item["threshold_classification_agrees"]
        for item in first.report["continuity_corroboration"]
    )
    markdown = (first.path / "a0_coverage_report.md").read_text(encoding="utf-8")
    assert markdown.index("### Miss diagnoses") > markdown.rindex(
        "sls2.r149.6593e02e.landmark.junction.07"
    )
    canonical_bytes = b"\n".join(
        value
        for name, value in _bundle_files(first.path).items()
        if name.endswith((".json", ".md"))
    )
    assert str(ROOT).encode("utf-8") not in canonical_bytes
    assert b'"timestamp"' not in canonical_bytes
    assert b'"created_at"' not in canonical_bytes
    assert first.report["live_cst_status"] == "not_run"


def _real_inputs_or_skip() -> None:
    if not R2_RECORD.is_file() or not R1_GRAPH.is_file():
        pytest.skip("ignored canonical R1/R2 proof sources are not materialized")


def _analytic_u(target_parameter: float) -> float:
    parameter = np.linspace(0.0, 1.0, 20001)
    z_values = 100.0 * (parameter - 0.5)
    r_values = 50.0 + 10.0 * np.sin(2.0 * math.pi * parameter)
    lengths = np.hypot(np.diff(z_values), np.diff(r_values))
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    return float(np.interp(target_parameter, parameter, cumulative) / cumulative[-1])


def _unit(value: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*value)
    return value[0] / length, value[1] / length


def _truth(landmark_id: str, u_value: float) -> TruthJunction:
    return TruthJunction(
        landmark_id=landmark_id,
        interface_id=f"interface.{landmark_id}",
        point=BoundaryPoint(z_mm=u_value, r_mm=1.0),
        u=u_value,
        projection_residual_mm=0.0,
        incident_region_ids=("region.left", "region.right"),
        incident_region_types=("LeftRegion", "RightRegion"),
        coordinate_source_path="record.json",
        coordinate_source_locator="#/landmark_bindings/0",
        semantic_source_path="graph.json",
        semantic_source_locator="#/landmarks/0",
    )


def _candidate(u_value: float, signal: str) -> LandmarkCandidate:
    return LandmarkCandidate(
        u=u_value,
        u_interval=(u_value, u_value),
        signals=(signal,),
        scale_positions=((512, u_value), (2048, u_value)),
        stable=True,
    )


def _bundle_files(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }
