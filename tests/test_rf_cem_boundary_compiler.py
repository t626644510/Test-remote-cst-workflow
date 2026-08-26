"""No-CST contract and real-source gates for the R2 boundary compiler."""

from __future__ import annotations

from dataclasses import dataclass, replace
from http.client import HTTPConnection
import importlib.util
import json
import math
from pathlib import Path
import tempfile
from typing import Any, Mapping

import pytest

import rf_cem.compiler.core as compiler_core
from rf_cem.compiler import (
    BaselineContract,
    CompileContractError,
    CompileRecord,
    CompileRequest,
    ContinuityInterfaceOverride,
    ContinuityRequirement,
    ContractSourceRef,
    NativeArtifactRef,
    ProfileCompiler,
    R2SourceSet,
    RegionRepresentationBinding,
    SourceNativeProvenance,
    default_boundary_continuity_policy,
    load_compile_record,
    prepare_r2_cases,
    write_r2_bundle,
)
from rf_cem.compiler.cli import main as compiler_main
from rf_cem.representation import (
    CircularArcRepresentation,
    CompositeRegionRepresentation,
    EllipseArcRepresentation,
    GeometryPatch,
    LineRepresentation,
    Point2D,
    RegionGeometry,
    RepresentationContractError,
    SplineApproxRepresentation,
    SplineNurbsRepresentation,
    representation_from_mapping,
    trim_representation,
)
from rf_cem.semantic import EvidenceRef
from rf_cem.semantic.contracts import canonical_json_bytes
from rf_cem.workbench import (
    RegistryReader,
    WorkbenchIndexError,
    WorkbenchServer,
    WorkbenchSourceSet,
    rebuild_workbench,
)


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]


def test_representation_contracts_round_trip_and_remain_generic() -> None:
    line = LineRepresentation("line", Point2D(0.0, 1.0), Point2D(1.0, 1.0))
    circle = CircularArcRepresentation(
        "circle",
        center=Point2D(1.0, 2.0),
        radius_mm=1.0,
        start_angle_rad=-math.pi / 2.0,
        end_angle_rad=0.0,
        sample_count=7,
    )
    ellipse = EllipseArcRepresentation(
        "ellipse",
        center=Point2D(0.0, 3.0),
        semi_axis_z_mm=2.0,
        semi_axis_r_mm=1.0,
        start_angle_rad=math.pi,
        end_angle_rad=math.pi / 2.0,
        sample_count=9,
    )
    legacy_spline = SplineNurbsRepresentation(
        "spline.legacy",
        degree=3,
        fit_points=(Point2D(0.0, 1.0), Point2D(0.5, 1.2), Point2D(1.0, 1.0)),
        control_points=(
            Point2D(0.0, 1.0),
            Point2D(0.3, 1.3),
            Point2D(0.7, 1.3),
            Point2D(1.0, 1.0),
        ),
        backend_point_source="control_points",
    )
    spline = SplineApproxRepresentation(
        "spline.canonical",
        max_degree=legacy_spline.degree,
        fit_input_points=legacy_spline.fit_points,
        source_control_point_hints=legacy_spline.control_points,
        backend_input_source="source_control_point_hints",
    )
    composite = CompositeRegionRepresentation("composite", (line, circle))
    for representation in (line, circle, ellipse, legacy_spline, spline, composite):
        assert representation_from_mapping(representation.to_mapping()) == representation
        assert representation.parameter_count > 0
        assert len(representation.sample()) >= 2

    legacy_mapping = legacy_spline.to_mapping()
    assert representation_from_mapping(legacy_mapping).to_mapping() == legacy_mapping
    assert spline.to_mapping() == {
        "schema_version": "boundary_representation.v1",
        "representation_type": "SplineApprox",
        "representation_id": "spline.canonical",
        "representation_family": "spline",
        "fidelity": "approximate",
        "fit_input_points": [point.to_mapping() for point in legacy_spline.fit_points],
        "source_control_point_hints": [
            point.to_mapping() for point in legacy_spline.control_points
        ],
        "max_degree": 3,
        "backend_input_source": "source_control_point_hints",
        "backend_contract": "cadquery.splineApprox.v0",
        "approximation_tolerance_mm": 1.0e-3,
        "optimization_ready": True,
        "exact_nurbs": False,
    }
    assert spline.sample() == legacy_spline.sample()
    assert spline.start_tangent() == legacy_spline.start_tangent()
    assert spline.end_tangent() == legacy_spline.end_tangent()
    legacy_patch = GeometryPatch(
        patch_id="legacy.patch",
        owner_region_id="region",
        region_order=0,
        patch_order=0,
        global_order=0,
        representation=legacy_spline,
        start_landmark_id="landmark.start",
        end_landmark_id="landmark.end",
        source_native_segment_ref="native.curve",
        source_parameter_interval=(0.0, 1.0),
    )
    canonical_patch = GeometryPatch(
        patch_id="canonical.patch",
        owner_region_id="region",
        region_order=0,
        patch_order=0,
        global_order=0,
        representation=spline,
        start_landmark_id="landmark.start",
        end_landmark_id="landmark.end",
        source_native_segment_ref="native.curve",
        source_parameter_interval=(0.0, 1.0),
    )
    legacy_backend = compiler_core._backend_segment(legacy_patch)
    canonical_backend = compiler_core._backend_segment(canonical_patch)
    assert legacy_backend["curve"]["control_points"] == canonical_backend["curve"][
        "control_points"
    ]
    assert legacy_backend["curve"]["degree_max"] == canonical_backend["curve"][
        "degree_max"
    ]
    assert legacy_backend["curve"]["tolerance_mm"] == canonical_backend["curve"][
        "tolerance_mm"
    ] == 1.0e-3
    optimized = replace(
        spline,
        fit_input_points=(
            spline.fit_input_points[0],
            Point2D(0.5, 1.25),
            spline.fit_input_points[-1],
        ),
    )
    assert optimized.fit_input_points[1].r_mm == 1.25
    assert optimized.parameter_count == spline.parameter_count
    assert representation_from_mapping(optimized.to_mapping()) == optimized

    left = trim_representation(
        ellipse, start_fraction=0.0, end_fraction=0.5, representation_id="ellipse.left"
    )
    right = trim_representation(
        ellipse, start_fraction=0.5, end_fraction=1.0, representation_id="ellipse.right"
    )
    assert left.end.distance_to(right.start) < 1.0e-12
    assert left.end_tangent() == pytest.approx(right.start_tangent())
    assert left.end_curvature_per_mm() == pytest.approx(
        right.start_curvature_per_mm()
    )
    with pytest.raises(RepresentationContractError):
        Point2D(math.nan, 1.0)


def test_region_geometry_rejects_patch_owner_or_component_mismatch() -> None:
    representation = LineRepresentation(
        "line", Point2D(0.0, 1.0), Point2D(1.0, 1.0)
    )
    composite = CompositeRegionRepresentation("composite", (representation,))
    patch = GeometryPatch(
        patch_id="patch",
        owner_region_id="region.other",
        region_order=0,
        patch_order=0,
        global_order=0,
        representation=representation,
        start_landmark_id="left",
        end_landmark_id="right",
        source_native_segment_ref="seg.0",
        source_parameter_interval=(0.0, 1.0),
    )
    with pytest.raises(RepresentationContractError, match="owner"):
        RegionGeometry("geometry", "region.expected", 0, composite, (patch,))


def test_one_compiler_entry_handles_two_topologies_and_records_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        compiler_core, "validate_graph_against_grammar", lambda grammar, graph: None
    )
    compiler = ProfileCompiler(_FakeKernel())
    results = []
    for instance_id, region_count in (("fixture.simple", 2), ("fixture.composite", 3)):
        request, source_points = _compile_request(instance_id, region_count)
        result = compiler.compile(
            request,
            bundle_root=tmp_path / instance_id,
            source_profile_points=source_points,
        )
        results.append(result)
        assert result.record.status == "pass"
        assert len(result.record.region_geometries) == region_count
        assert result.record.patch_count == region_count + (1 if region_count == 3 else 0)
        assert all(
            patch.owner_region_id == region.owner_region_id
            for region in result.record.region_geometries
            for patch in region.patches
        )
        assert all(check.required_pass for check in result.record.continuity_checks)
        assert result.record.geometry_validation["brep_valid"] is True
        assert result.record.baseline_comparison["source_profile_max_deviation_mm"] == 0.0
        assert CompileRecord.from_mapping(result.record.to_mapping()) == result.record
        header = result.step_path.read_text(encoding="ascii")
        assert "1970-01-01T00:00:00" in header

    assert type(results[0].record.region_geometries[0].representation.components[0]) is (
        type(results[1].record.region_geometries[0].representation.components[0])
    )


def test_continuity_policy_selects_g1_c0_and_g2_without_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        compiler_core, "validate_graph_against_grammar", lambda grammar, graph: None
    )
    request, _ = _compile_request("fixture.continuity", 2)
    first, second = request.region_bindings
    line = LineRepresentation(
        "fixture.line", Point2D(0.0, 1.0), Point2D(1.0, 1.0)
    )
    arc = CircularArcRepresentation(
        "fixture.arc",
        center=Point2D(1.0, 2.0),
        radius_mm=1.0,
        start_angle_rad=-math.pi / 2.0,
        end_angle_rad=0.0,
        sample_count=9,
    )
    vertical = LineRepresentation(
        "fixture.vertical", Point2D(2.0, 2.0), Point2D(2.0, 3.0)
    )
    internal_landmark = "fixture.continuity.landmark.internal"
    first = replace(
        first,
        representation=CompositeRegionRepresentation(
            "fixture.composite.line-arc", (line, arc)
        ),
        source_native_segment_refs=("source.same", "source.same"),
        source_parameter_intervals=((0.0, 0.5), (0.5, 1.0)),
        internal_landmark_ids=(internal_landmark,),
    )
    second = replace(
        second,
        representation=CompositeRegionRepresentation(
            "fixture.composite.vertical", (vertical,)
        ),
    )
    tangent_request = replace(request, region_bindings=(first, second))
    tangent_patches = tuple(
        patch
        for geometry in compiler_core._build_region_geometries(tangent_request)
        for patch in geometry.patches
    )
    tangent_checks = compiler_core._continuity_requirement_plan(
        tangent_request, tangent_patches
    )
    internal = tangent_checks[0]
    ordinary_interface = tangent_checks[1]
    assert internal.join_scope == "within_region"
    assert internal.required_level == "G1"
    assert internal.requirement_source == "internal_patch_policy"
    assert internal.pre_kernel_tangent_angle_deg == pytest.approx(0.0)
    assert internal.pre_kernel_curvature_delta_per_mm > (
        compiler_core.G2_TOLERANCE_PER_MM
    )
    assert ordinary_interface.required_level == "G1"
    assert ordinary_interface.requirement_source == "semantic_interface_default"
    assert ordinary_interface.pre_kernel_tangent_angle_deg == pytest.approx(0.0)

    changed_refs = replace(
        first,
        source_native_segment_refs=("source.left", "source.right"),
    )
    changed_request = replace(
        tangent_request, region_bindings=(changed_refs, second)
    )
    changed_patches = tuple(
        patch
        for geometry in compiler_core._build_region_geometries(changed_request)
        for patch in geometry.patches
    )
    assert [item.required_level for item in compiler_core._continuity_requirement_plan(
        changed_request, changed_patches
    )] == [item.required_level for item in tangent_checks]

    corner_request, _ = _compile_request("fixture.corner", 2)
    corner_first, corner_second = corner_request.region_bindings
    corner_second = replace(
        corner_second,
        representation=CompositeRegionRepresentation(
            "fixture.corner.vertical",
            (
                LineRepresentation(
                    "fixture.corner.vertical.line",
                    Point2D(1.0, 1.0),
                    Point2D(1.0, 2.0),
                ),
            ),
        ),
    )
    corner_interface_id = corner_request.instance_graph.interfaces[0].interface_id
    corner_policy = default_boundary_continuity_policy(
        corner_request.family_id,
        overrides=(
            ContinuityInterfaceOverride(
                interface_id=corner_interface_id,
                requirement=ContinuityRequirement("C0"),
                intentional_corner=True,
                rationale="Synthetic reviewed intentional corner.",
            ),
        ),
    )
    corner_request = replace(
        corner_request,
        region_bindings=(corner_first, corner_second),
        continuity_policy=corner_policy,
    )
    corner_patches = tuple(
        patch
        for geometry in compiler_core._build_region_geometries(corner_request)
        for patch in geometry.patches
    )
    corner = compiler_core._continuity_requirement_plan(
        corner_request, corner_patches
    )[0]
    assert corner.pre_kernel_tangent_angle_deg > compiler_core.G1_TOLERANCE_DEG
    assert corner.required_level == "C0"
    assert corner.intentional_corner is True
    assert corner.requirement_source == "semantic_interface_override"
    corner_result = ProfileCompiler(_FakeKernel()).compile(
        corner_request,
        bundle_root=tmp_path / "explicit-c0",
        source_profile_points=(
            Point2D(0.0, 1.0),
            Point2D(1.0, 1.0),
            Point2D(1.0, 2.0),
        ),
    )
    realized_corner = corner_result.record.continuity_checks[0]
    assert realized_corner.g1_pass is False
    assert realized_corner.required_level == "C0"
    assert realized_corner.required_pass is True
    assert corner_result.record.status == "pass"

    g2_request, _ = _compile_request("fixture.g2", 2)
    g2_first, g2_second = g2_request.region_bindings
    g2_second = replace(
        g2_second,
        representation=CompositeRegionRepresentation(
            "fixture.g2.arc", (arc,)
        ),
    )
    g2_interface_id = g2_request.instance_graph.interfaces[0].interface_id
    g2_policy = default_boundary_continuity_policy(
        g2_request.family_id,
        overrides=(
            ContinuityInterfaceOverride(
                interface_id=g2_interface_id,
                requirement=ContinuityRequirement("G2"),
                intentional_corner=False,
                rationale="Synthetic explicit curvature-continuity extension.",
            ),
        ),
    )
    g2_request = replace(
        g2_request,
        region_bindings=(g2_first, g2_second),
        continuity_policy=g2_policy,
    )
    g2_patches = tuple(
        patch
        for geometry in compiler_core._build_region_geometries(g2_request)
        for patch in geometry.patches
    )
    g2 = compiler_core._continuity_requirement_plan(g2_request, g2_patches)[0]
    assert g2.pre_kernel_tangent_angle_deg <= compiler_core.G1_TOLERANCE_DEG
    assert g2.pre_kernel_curvature_delta_per_mm > (
        compiler_core.G2_TOLERANCE_PER_MM
    )
    assert g2.required_level == "G2"


def test_profile_endpoints_are_explicit_and_not_two_sided_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        compiler_core, "validate_graph_against_grammar", lambda grammar, graph: None
    )
    request, source_points = _compile_request("fixture.endpoints", 2)
    result = ProfileCompiler(_FakeKernel()).compile(
        request,
        bundle_root=tmp_path,
        source_profile_points=source_points,
    )
    assert {item.endpoint_role for item in result.record.endpoint_constraints} == {
        "profile_start",
        "profile_end",
    }
    endpoint_landmarks = {
        item.landmark_id for item in result.record.endpoint_constraints
    }
    assert endpoint_landmarks.isdisjoint(
        item.landmark_id for item in result.record.continuity_checks
    )
    assert all(
        item.two_sided_continuity_applicable is False
        for item in result.record.endpoint_constraints
    )


def test_generic_spline_constraint_plan_supports_start_end_and_both() -> None:
    start_request, _ = _line_to_spline_request("fixture.start-only")
    start_patches = tuple(
        patch
        for geometry in compiler_core._build_region_geometries(start_request)
        for patch in geometry.patches
    )
    start_plan = compiler_core._continuity_requirement_plan(
        start_request, start_patches
    )
    start_constraints = compiler_core._curve_realization_constraints(
        start_patches, start_plan
    )
    assert len(start_constraints) == 1
    assert start_constraints[0].endpoint_role == "start"
    assert start_constraints[0].start_tangent_unit == pytest.approx((1.0, 0.0))
    assert start_constraints[0].end_tangent_unit is None

    end_request, _ = _compile_request("fixture.end-only", 2)
    end_first, end_second = end_request.region_bindings
    end_first = replace(
        end_first,
        representation=CompositeRegionRepresentation(
            "fixture.end-only.spline.composite",
            (
                SplineApproxRepresentation(
                    "fixture.end-only.spline",
                    max_degree=2,
                    fit_input_points=(
                        Point2D(0.0, 1.0),
                        Point2D(0.5, 1.0),
                        Point2D(1.0, 1.0),
                    ),
                ),
            ),
        ),
    )
    end_request = replace(
        end_request, region_bindings=(end_first, end_second)
    )
    end_patches = tuple(
        patch
        for geometry in compiler_core._build_region_geometries(end_request)
        for patch in geometry.patches
    )
    end_constraints = compiler_core._curve_realization_constraints(
        end_patches,
        compiler_core._continuity_requirement_plan(end_request, end_patches),
    )
    assert len(end_constraints) == 1
    assert end_constraints[0].endpoint_role == "end"
    assert end_constraints[0].start_tangent_unit is None
    assert end_constraints[0].end_tangent_unit == pytest.approx((1.0, 0.0))

    both_request, _ = _compile_request("fixture.both", 3)
    first, middle, last = both_request.region_bindings
    middle = replace(
        middle,
        representation=CompositeRegionRepresentation(
            "fixture.both.spline.composite",
            (
                SplineApproxRepresentation(
                    "fixture.both.spline",
                    max_degree=2,
                    fit_input_points=(
                        Point2D(1.0, 1.0),
                        Point2D(1.5, 1.2),
                        Point2D(2.0, 1.0),
                    ),
                ),
            ),
        ),
        source_native_segment_refs=("seg.1",),
        source_parameter_intervals=((0.0, 1.0),),
        internal_landmark_ids=(),
    )
    both_request = replace(
        both_request, region_bindings=(first, middle, last)
    )
    both_patches = tuple(
        patch
        for geometry in compiler_core._build_region_geometries(both_request)
        for patch in geometry.patches
    )
    both_constraints = compiler_core._curve_realization_constraints(
        both_patches,
        compiler_core._continuity_requirement_plan(both_request, both_patches),
    )
    assert len(both_constraints) == 2
    assert {item.endpoint_role for item in both_constraints} == {"start", "end"}


def test_incomplete_source_partition_and_kernel_fallback_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        compiler_core, "validate_graph_against_grammar", lambda grammar, graph: None
    )
    request, source_points = _compile_request("fixture.invalid", 2)
    first = request.region_bindings[0]
    incomplete = replace(
        first,
        source_parameter_intervals=((0.1, 1.0),),
    )
    bad_request = replace(
        request, region_bindings=(incomplete, *request.region_bindings[1:])
    )
    with pytest.raises(CompileContractError, match="partition is incomplete"):
        ProfileCompiler(_FakeKernel()).compile(
            bad_request,
            bundle_root=tmp_path / "partition",
            source_profile_points=source_points,
        )

    fallback_result = ProfileCompiler(_FakeKernel(fallback=True)).compile(
        request,
        bundle_root=tmp_path / "fallback",
        source_profile_points=source_points,
    )
    assert fallback_result.record.status == "failed"
    assert fallback_result.record.geometry_validation["pass"] is False
    assert any(
        "curve-segment" in item
        for item in fallback_result.record.geometry_validation["blocking_errors"]
    )


def test_kernel_realized_tangent_mismatch_defeats_pre_kernel_g1_estimate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        compiler_core, "validate_graph_against_grammar", lambda grammar, graph: None
    )
    request, source_points = _line_to_spline_request("fixture.kernel-mismatch")
    patches = tuple(
        patch
        for geometry in compiler_core._build_region_geometries(request)
        for patch in geometry.patches
    )
    plan = compiler_core._continuity_requirement_plan(request, patches)[0]
    assert plan.pre_kernel_tangent_angle_deg == pytest.approx(0.0)
    spline_patch = patches[1]
    result = ProfileCompiler(
        _FakeKernel(
            tangent_overrides={spline_patch.patch_id: {"start": (0.0, 1.0)}}
        )
    ).compile(
        request,
        bundle_root=tmp_path,
        source_profile_points=source_points,
    )
    check = result.record.continuity_checks[0]
    assert check.measurement_basis == "kernel_realized_edge"
    assert check.pre_kernel_tangent_angle_deg == pytest.approx(0.0)
    assert check.tangent_angle_deg == pytest.approx(90.0)
    assert check.g1_pass is False
    assert check.required_pass is False
    assert result.record.status == "failed"
    assert result.record.geometry_validation["pass"] is False


def test_backend_that_ignores_planned_tangent_constraint_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        compiler_core, "validate_graph_against_grammar", lambda grammar, graph: None
    )
    request, source_points = _line_to_spline_request("fixture.constraint-ignored")
    result = ProfileCompiler(_FakeKernel(ignore_constraints=True)).compile(
        request,
        bundle_root=tmp_path,
        source_profile_points=source_points,
    )
    check = result.record.continuity_checks[0]
    assert check.g1_pass is True
    assert check.constraint_enforcement_verified is False
    assert check.required_pass is False
    assert result.record.status == "failed"
    assert any(
        "tangent constraint" in item
        for item in result.record.geometry_validation["blocking_errors"]
    )


def test_real_kernel_applies_constrained_spline_and_reports_fidelity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if importlib.util.find_spec("cadquery") is None or importlib.util.find_spec(
        "OCP"
    ) is None:
        pytest.skip("CadQuery/OCP backend is not installed")
    monkeypatch.setattr(
        compiler_core, "validate_graph_against_grammar", lambda grammar, graph: None
    )
    request, source_points = _line_to_spline_request("fixture.real-kernel")
    result = ProfileCompiler().compile(
        request,
        bundle_root=tmp_path,
        source_profile_points=source_points,
    )
    check = result.record.continuity_checks[0]
    assert result.record.status == "pass"
    assert check.measurement_basis == "kernel_realized_edge"
    assert check.g1_pass and check.required_pass
    assert check.constraint_enforcement_verified is True
    constraints = result.record.curve_realization_constraints
    assert len(constraints) == 1
    assert constraints[0].start_tangent_unit == pytest.approx((1.0, 0.0))
    assert constraints[0].end_tangent_unit is None
    fidelity = result.record.baseline_comparison["realized_spline_fidelity"]
    assert fidelity["maximum_deviation_mm"] <= fidelity["tolerance_mm"] == 0.001
    realized = result.record.geometry_validation["kernel"]["curve_generation"][
        "realized_segments"
    ]
    spline = next(item for item in realized if item["patch_id"].endswith("patch.01"))
    assert spline["construction_contract"] == (
        "cadquery.spline.tangent_constrained.v0"
    )
    assert spline["tangent_constraints_applied"] is True
    assert spline["applied_endpoint_constraints"] == {
        "start": True,
        "end": False,
    }


def test_validate_cli_detects_output_artifact_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        compiler_core, "validate_graph_against_grammar", lambda grammar, graph: None
    )
    request, source_points = _compile_request("fixture.cli", 2)
    result = ProfileCompiler(_FakeKernel()).compile(
        request,
        bundle_root=tmp_path,
        source_profile_points=source_points,
    )
    record_path = tmp_path / "record.json"
    record_path.write_bytes(canonical_json_bytes(result.record.to_mapping()) + b"\n")
    assert compiler_main(
        ["validate", "--record", str(record_path), "--bundle-root", str(tmp_path)]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pass"
    result.profile_path.write_text("tampered", encoding="utf-8")
    assert compiler_main(
        ["validate", "--record", str(record_path), "--bundle-root", str(tmp_path)]
    ) == 2
    assert "hash mismatch" in capsys.readouterr().err


def test_real_r2_bundle_is_reproducible_and_loadable(tmp_path: Path) -> None:
    sources = _real_source_set()
    if sources is None:
        pytest.skip("ignored canonical R1/Stage C/SLS-2 proof sources are not materialized")
    first = write_r2_bundle(sources, tmp_path / "first")
    second = write_r2_bundle(sources, tmp_path / "second")
    assert first.bundle_id == second.bundle_id
    assert first.input_sha256 == second.input_sha256
    first_files = {
        path.relative_to(first.path).as_posix(): path.read_bytes()
        for path in first.path.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second.path).as_posix(): path.read_bytes()
        for path in second.path.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    assert len(first.records) == 2
    assert all(record.status == "pass" for record in first.records)
    assert [len(record.region_geometries) for record in first.records] == [9, 11]
    assert [record.patch_count for record in first.records] == [10, 12]
    assert all(record.schema_version == "compile_record.v2" for record in first.records)
    assert all(record.continuity_policy is not None for record in first.records)
    assert all(len(record.endpoint_constraints) == 2 for record in first.records)
    assert all(
        check.measurement_basis == "kernel_realized_edge"
        for record in first.records
        for check in record.continuity_checks
    )
    compiled_primitives = tuple(
        patch.representation
        for record in first.records
        for region in record.region_geometries
        for patch in region.patches
    )
    assert any(
        isinstance(representation, SplineApproxRepresentation)
        for representation in compiled_primitives
    )
    assert not any(
        isinstance(representation, SplineNurbsRepresentation)
        for representation in compiled_primitives
    )
    assert all(
        check.required_level == "G1"
        for record in first.records
        for check in record.continuity_checks
        if check.requirement_source
        in {"internal_patch_policy", "semantic_interface_default"}
    )
    rf500 = next(record for record in first.records if record.instance_id.startswith("rf500"))
    assert not any(check.intentional_corner for check in rf500.continuity_checks)
    rf500_request = next(
        item.request
        for item in prepare_r2_cases(sources)
        if item.request.instance_id == rf500.instance_id
    )
    region_types = {
        item.region_id: item.region_type for item in rf500_request.instance_graph.regions
    }
    nose_interface_ids = {
        item.interface_id
        for item in rf500_request.instance_graph.interfaces
        if {
            region_types[item.left_region_id],
            region_types[item.right_region_id],
        }
        == {"IrisRegion", "NoseRegion"}
    }
    nose_checks = [
        check
        for check in rf500.continuity_checks
        if check.interface_id in nose_interface_ids
    ]
    assert len(nose_interface_ids) == len(nose_checks) == 2
    assert all(check.required_level == "G1" for check in nose_checks)
    assert all(check.requirement_source == "semantic_interface_default" for check in nose_checks)
    assert all(check.g1_pass and check.required_pass for check in nose_checks)
    assert all(check.constraint_enforcement_verified for check in nose_checks)
    assert all(check.measurement_basis == "kernel_realized_edge" for check in nose_checks)
    assert all(
        check.pre_kernel_tangent_angle_deg > check.g1_tolerance_deg
        for check in nose_checks
    )
    assert all(check.tangent_angle_deg <= 2.0 for check in nose_checks)
    rf500_patches = {
        patch.patch_id: patch
        for geometry in rf500.region_geometries
        for patch in geometry.patches
    }
    nose_spline_patch_ids = {
        check.right_patch_id
        if isinstance(
            rf500_patches[check.right_patch_id].representation,
            SplineApproxRepresentation,
        )
        else check.left_patch_id
        for check in nose_checks
    }
    assert {
        len(rf500_patches[patch_id].representation.fit_input_points)
        for patch_id in nose_spline_patch_ids
    } == {12}
    nose_constraints = [
        item
        for item in rf500.curve_realization_constraints
        if item.source_interface_id in nose_interface_ids
    ]
    assert len(nose_constraints) == 2
    assert {item.endpoint_role for item in nose_constraints} == {"start", "end"}
    realized = {
        item["patch_id"]: item
        for item in rf500.geometry_validation["kernel"]["curve_generation"][
            "realized_segments"
        ]
    }
    assert all(
        realized[item.patch_id]["tangent_constraints_applied"] is True
        and realized[item.patch_id]["construction_contract"]
        == "cadquery.spline.tangent_constrained.v0"
        for item in nose_constraints
    )
    fidelity = rf500.baseline_comparison["realized_spline_fidelity"]
    assert fidelity["maximum_deviation_mm"] <= fidelity["tolerance_mm"] == 0.001
    loaded = tuple(
        load_compile_record(path)
        for path in sorted((first.path / "records").glob("*.json"))
    )
    assert {record.compile_id for record in loaded} == {
        record.compile_id for record in first.records
    }
    assert any(
        record.baseline.accepted_step_materialized for record in first.records
    )
    assert any(
        not record.baseline.accepted_step_materialized for record in first.records
    )

    scratch = ROOT / ".codex_tmp"
    scratch.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="r2-w2-", dir=scratch) as value:
            _assert_real_w2_integration(sources, Path(value))
    finally:
        try:
            scratch.rmdir()
        except OSError:
            pass
    with pytest.raises(FileExistsError):
        write_r2_bundle(sources, tmp_path / "first")


def _assert_real_w2_integration(sources: R2SourceSet, workdir: Path) -> None:
    bundle = write_r2_bundle(sources, workdir / "proofs")
    record_paths = tuple(sorted((bundle.path / "records").glob("*.json")))
    workbench_sources = WorkbenchSourceSet(
        repo_root=ROOT,
        family_profile=sources.family_profile,
        family_grammar=sources.family_grammar,
        instance_boundary_graphs=sources.instance_graphs,
        instance_graph_diff=(
            sources.family_grammar.parent / "instance_graph_diff.v0.json"
        ),
        compile_records=record_paths,
    )
    database = workdir / "workbench.sqlite"
    first_workbench = rebuild_workbench(database, workbench_sources)
    first_snapshot = RegistryReader(database).snapshot()
    second_workbench = rebuild_workbench(database, workbench_sources)
    assert first_workbench.input_set_sha256 == second_workbench.input_set_sha256
    assert first_snapshot == RegistryReader(database).snapshot()
    reader = RegistryReader(database)
    counts = reader.entity_counts()
    assert counts["region_geometry"] == 20
    assert counts["geometry_patch"] == 22
    assert counts["baseline_comparison"] == 2
    assert counts["geometry_validation"] == 2
    assert counts["geometry_artifact"] == 4
    entities = {
        (item["entity_kind"], item["entity_id"]): item
        for item in reader.snapshot()["entities"]
    }
    assert entities[("validation", "w2.boundary-compiler-hard-gate")][
        "status"
    ] == "pass"
    assert reader.metadata()["indexer_version"] == "r4.w4.v0"

    with WorkbenchServer(
        database,
        source_root=ROOT,
        token="r2-workbench-test-token",
    ) as server:
        connection = HTTPConnection(server.host, server.port, timeout=5)
        connection.request(
            "GET", "/compile-records?token=r2-workbench-test-token"
        )
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        representation_connection = HTTPConnection(server.host, server.port, timeout=5)
        representation_connection.request(
            "GET", "/representations?token=r2-workbench-test-token"
        )
        representation_response = representation_connection.getresponse()
        representation_body = representation_response.read().decode("utf-8")
        representation_connection.close()
    assert response.status == 200
    assert "Compile Records / W2" in body
    assert "Region → representation → patches" in body
    assert "BRep valid" in body
    assert "Boundary continuity policies" in body
    assert "requirement_source" in body
    assert "measurement_basis" in body
    assert "kernel_realized_edge" in body
    assert "cadquery.spline.tangent_constrained.v0" in body
    assert "constraint_enforcement_verified" in body
    assert "Kernel-realized edge endpoints, tangents, contracts, and fidelity" in body
    assert "semantic_interface_default" in body
    assert "rf500.2c27faee.b1r3.interface.01" in body
    assert "rf500.2c27faee.b1r3.interface.08" in body
    assert "&quot;semantic_interface_overrides&quot;: []" in body
    assert "&quot;intentional_corner&quot;: true" not in body
    assert "One-sided profile endpoint constraints" in body
    assert "No live CST" in body
    assert "RF physical acceptance" in body
    assert representation_response.status == 200
    assert "SplineApproxRepresentation" in representation_body
    assert "Approximate" in representation_body
    assert "CadQuery/OCCT splineApprox" in representation_body
    assert "0.001 mm (1 micrometre)" in representation_body
    assert "optimization_ready" in representation_body
    assert "ExactNurbsRepresentation" in representation_body
    assert "planned_not_implemented" in representation_body
    assert "implemented exact NURBS" not in representation_body

    tampered_artifact = bundle.path / bundle.records[0].output_artifacts[0].path
    tampered_artifact.write_bytes(tampered_artifact.read_bytes() + b"tampered")
    with pytest.raises(WorkbenchIndexError, match="SHA-256 mismatch"):
        rebuild_workbench(workdir / "tampered.sqlite", workbench_sources)


def test_legacy_compile_record_v0_proof_remains_readable() -> None:
    proof = (
        ROOT
        / "analysis_outputs"
        / "rf_cem_boundary_compiler"
        / "r2_boundary_compiler.aa66a3e90125437b"
    )
    records = tuple(sorted((proof / "records").glob("*.compile_record.v0.json")))
    if len(records) != 2:
        pytest.skip("ignored canonical R2 v0 proof is not materialized")
    loaded = tuple(load_compile_record(path) for path in records)
    assert all(record.schema_version == "compile_record.v0" for record in loaded)
    assert all(record.continuity_policy is None for record in loaded)
    assert all(not record.endpoint_constraints for record in loaded)
    assert {
        record.compile_id for record in loaded
    } == {
        "rf500.2c27faee.b1r3.compile.40891d70493951aa",
        "sls2.r149.6593e02e.compile.ebe8e2827948ff96",
    }


def test_previous_compile_record_v1_proof_remains_readable() -> None:
    proof = (
        ROOT
        / "analysis_outputs"
        / "rf_cem_boundary_compiler_td1_td2"
        / "r2_boundary_compiler.8f47ca735db8ce8a"
    )
    records = tuple(sorted((proof / "records").glob("*.compile_record.v1.json")))
    if len(records) != 2:
        pytest.skip("ignored previous R2 v1 proof is not materialized")
    loaded = tuple(load_compile_record(path) for path in records)
    assert all(record.schema_version == "compile_record.v1" for record in loaded)
    assert all(record.continuity_policy is not None for record in loaded)
    assert {
        record.compile_id for record in loaded
    } == {
        "rf500.2c27faee.b1r3.compile.8f1a01d4fcd31ffb",
        "sls2.r149.6593e02e.compile.a22fd5f932c1ffff",
    }


def test_anchor_workaround_compile_record_v1_proof_remains_readable() -> None:
    proof = (
        ROOT
        / "analysis_outputs"
        / "rf_cem_boundary_compiler_td1_td2"
        / "r2_boundary_compiler.2980548dcdd5a85e"
    )
    records = tuple(sorted((proof / "records").glob("*.compile_record.v1.json")))
    if len(records) != 2:
        pytest.skip("ignored anchor-era R2 v1 proof is not materialized")
    loaded = tuple(load_compile_record(path) for path in records)
    assert all(record.schema_version == "compile_record.v1" for record in loaded)
    assert all(
        check.measurement_basis == "representation_estimate"
        for record in loaded
        for check in record.continuity_checks
    )


@dataclass(frozen=True)
class _FakeRegion:
    region_id: str


@dataclass(frozen=True)
class _FakeLandmark:
    landmark_id: str
    landmark_type: str
    side: str


@dataclass(frozen=True)
class _FakeInterface:
    interface_id: str
    left_region_id: str
    right_region_id: str
    landmark_id: str


@dataclass(frozen=True)
class _FakeGraph:
    family_id: str
    instance_id: str
    regions: tuple[_FakeRegion, ...]
    landmarks: tuple[_FakeLandmark, ...]
    interfaces: tuple[_FakeInterface, ...]


@dataclass(frozen=True)
class _FakeGrammar:
    family_id: str
    grammar_id: str


class _FakeKernel:
    def __init__(
        self,
        *,
        fallback: bool = False,
        ignore_constraints: bool = False,
        tangent_overrides: Mapping[str, Mapping[str, tuple[float, float]]] | None = None,
    ) -> None:
        self.fallback = fallback
        self.ignore_constraints = ignore_constraints
        self.tangent_overrides = tangent_overrides or {}

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        output = Path(kwargs["output_step"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "ISO-10303-21;\nHEADER;\n"
            "FILE_NAME('Mock Shape','2026-08-20T00:00:00',('Author'),('Mock'),'Mock','Mock','');\n"
            "ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
            encoding="ascii",
        )
        return {
            "schema_version": "fake_kernel.v0",
            "reader": {"backend": "fixture", "version": "0"},
            "body_selection": {
                "mode": "generated_without_seed",
                "body_index": None,
                "solid_count": 1,
            },
            "baseline": None,
            "generated": {
                "bbox_mm": {
                    "xmin": -1.0,
                    "xmax": 1.0,
                    "ymin": -1.0,
                    "ymax": 1.0,
                    "zmin": 0.0,
                    "zmax": 4.0,
                },
                "volume_mm3": 1.0,
                "surface_area_mm2": 1.0,
                "brep_valid": True,
            },
            "tessellation": {
                "source": "generated",
                "deflection_mm": 0.25,
                "vertex_count": 4,
                "triangle_count": 2,
                "radial_envelope_point_count": 2,
            },
            "curve_generation": {
                "mode": (
                    "dense_polyline_fallback"
                    if self.fallback
                    else "cadquery_curve_segments"
                ),
                "fallbacks": ["fixture fallback"] if self.fallback else [],
                "approximations": [],
                "realized_segments": self._realized_segments(
                    kwargs["profile_segments"]
                ),
            },
        }

    def _realized_segments(
        self, segments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        values = []
        for segment in segments:
            patch_id = str(segment["id"])
            start = segment["start"]
            end = segment["end"]
            curve = segment.get("curve", {})
            points = (
                curve.get("fit_input_points")
                or curve.get("sampled_points")
                or curve.get("control_points")
                or [start, end]
            )
            start_tangent = _unit_tangent(points[0], points[1])
            end_tangent = _unit_tangent(points[-2], points[-1])
            constraints = curve.get("endpoint_tangent_constraints") or {}
            applied = bool(constraints) and not self.ignore_constraints
            if applied and constraints.get("start_tangent_unit") is not None:
                start_tangent = tuple(constraints["start_tangent_unit"])
            if applied and constraints.get("end_tangent_unit") is not None:
                end_tangent = tuple(constraints["end_tangent_unit"])
            overrides = self.tangent_overrides.get(patch_id, {})
            start_tangent = overrides.get("start", start_tangent)
            end_tangent = overrides.get("end", end_tangent)
            constrained_endpoints = {
                "start": applied
                and constraints.get("start_tangent_unit") is not None,
                "end": applied and constraints.get("end_tangent_unit") is not None,
            }
            value = {
                "patch_id": patch_id,
                "actual_start_point": {
                    "z_mm": float(start["z"]),
                    "r_mm": float(start["r"]),
                },
                "actual_end_point": {
                    "z_mm": float(end["z"]),
                    "r_mm": float(end["r"]),
                },
                "actual_start_tangent_unit": list(start_tangent),
                "actual_end_tangent_unit": list(end_tangent),
                "edge_kind": str(segment.get("kind")),
                "orientation": "left_to_right",
                "construction_contract": curve.get(
                    "realized_backend_contract"
                )
                or (
                    "cadquery.threePointArc.v0"
                    if segment.get("kind") == "arc"
                    else "cadquery.lineTo.v0"
                ),
                "source_representation_contract": curve.get(
                    "source_representation_contract"
                )
                or curve.get("backend_contract"),
                "tangent_constraints_applied": applied,
                "applied_endpoint_constraints": constrained_endpoints,
            }
            if segment.get("kind") == "nurbs":
                value["geometry_fidelity"] = {
                    "maximum_deviation_mm": 0.0,
                    "sampling_policy": (
                        "all_backend_input_trace_points_projected_to_realized_edge"
                    ),
                    "comparison_source": curve.get("comparison_source")
                    or "fixture_trace",
                    "sample_count": len(points),
                    "tolerance_mm": float(curve.get("tolerance_mm") or 0.001),
                    "pass": True,
                }
            values.append(value)
        return values

    def recover(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("fixture requests do not use a baseline STEP")


def _unit_tangent(
    start: Mapping[str, Any], end: Mapping[str, Any]
) -> tuple[float, float]:
    dz = float(end["z"]) - float(start["z"])
    dr = float(end["r"]) - float(start["r"])
    length = math.hypot(dz, dr)
    return (dz / length, dr / length)


def _compile_request(
    instance_id: str, region_count: int
) -> tuple[CompileRequest, tuple[Point2D, ...]]:
    if region_count not in {2, 3}:
        raise AssertionError("fixture supports two or three regions")
    family_id = "fixture.family"
    region_ids = tuple(f"{instance_id}.region.{index}" for index in range(region_count))
    junction_ids = tuple(
        f"{instance_id}.landmark.junction.{index}" for index in range(region_count - 1)
    )
    landmarks = (
        _FakeLandmark(f"{instance_id}.landmark.left", "AxialApertureLandmark", "left"),
        *(
            _FakeLandmark(value, "RegionJunctionLandmark", "center")
            for value in junction_ids
        ),
        _FakeLandmark(f"{instance_id}.landmark.right", "AxialApertureLandmark", "right"),
    )
    graph = _FakeGraph(
        family_id=family_id,
        instance_id=instance_id,
        regions=tuple(_FakeRegion(value) for value in region_ids),
        landmarks=landmarks,
        interfaces=tuple(
            _FakeInterface(
                f"{instance_id}.interface.{index}",
                region_ids[index],
                region_ids[index + 1],
                junction_ids[index],
            )
            for index in range(region_count - 1)
        ),
    )
    grammar = _FakeGrammar(family_id=family_id, grammar_id="fixture.grammar")
    evidence = EvidenceRef(
        source_kind="fixture",
        source_path="fixtures/source.json",
        source_raw_sha256="a" * 64,
        locator="#/",
        relation="test_fixture",
    )
    grammar_ref = ContractSourceRef(
        "family_grammar", "family_grammar.v0", grammar.grammar_id, "b" * 64, evidence
    )
    graph_ref = ContractSourceRef(
        "instance_boundary_graph", "instance_boundary_graph.v0", instance_id, "c" * 64, evidence
    )
    provenance = SourceNativeProvenance(
        family_profile=ContractSourceRef(
            "family_profile", "family_profile.v0", family_id, "d" * 64, evidence
        ),
        adapter_id="fixture.adapter.v0",
        native_schema_version="fixture.native.v0",
        native_payload_locator="#/payload",
        native_payload_canonical_sha256="e" * 64,
        native_artifacts=(NativeArtifactRef("rf_vacuum_step", "source.step", "f" * 64),),
    )
    bindings = []
    source_points = [Point2D(0.0, 1.0)]
    for index, region_id in enumerate(region_ids):
        start = float(index)
        end = float(index + 1)
        if region_count == 3 and index == 1:
            components = (
                LineRepresentation(
                    f"{region_id}.line.0", Point2D(start, 1.0), Point2D(1.5, 1.0)
                ),
                LineRepresentation(
                    f"{region_id}.line.1", Point2D(1.5, 1.0), Point2D(end, 1.0)
                ),
            )
            source_refs = (f"seg.{index}", f"seg.{index}")
            intervals = ((0.0, 0.5), (0.5, 1.0))
            internal = (f"{instance_id}.landmark.internal",)
            source_points.extend((Point2D(1.5, 1.0), Point2D(end, 1.0)))
        else:
            components = (
                LineRepresentation(
                    f"{region_id}.line", Point2D(start, 1.0), Point2D(end, 1.0)
                ),
            )
            source_refs = (f"seg.{index}",)
            intervals = ((0.0, 1.0),)
            internal = ()
            source_points.append(Point2D(end, 1.0))
        bindings.append(
            RegionRepresentationBinding(
                region_id=region_id,
                region_order=index,
                representation=CompositeRegionRepresentation(
                    f"{region_id}.composite", components
                ),
                source_native_segment_refs=source_refs,
                source_parameter_intervals=intervals,
                start_landmark_id=(
                    f"{instance_id}.landmark.left"
                    if index == 0
                    else junction_ids[index - 1]
                ),
                end_landmark_id=(
                    f"{instance_id}.landmark.right"
                    if index == region_count - 1
                    else junction_ids[index]
                ),
                internal_landmark_ids=internal,
                evidence=(evidence,),
            )
        )
    request = CompileRequest(
        family_grammar=grammar,  # type: ignore[arg-type]
        instance_graph=graph,  # type: ignore[arg-type]
        family_grammar_ref=grammar_ref,
        instance_graph_ref=graph_ref,
        source_native_provenance=provenance,
        baseline=BaselineContract(
            "source_native_profile_with_unmaterialized_step",
            accepted_step_raw_sha256="f" * 64,
            accepted_step_materialized=False,
        ),
        region_bindings=tuple(bindings),
    )
    return request, tuple(source_points)


def _line_to_spline_request(
    instance_id: str,
) -> tuple[CompileRequest, tuple[Point2D, ...]]:
    request, _ = _compile_request(instance_id, 2)
    first, second = request.region_bindings
    fit_points = (
        Point2D(1.0, 1.0),
        Point2D(1.5, 1.0),
        Point2D(2.0, 1.2),
    )
    second = replace(
        second,
        representation=CompositeRegionRepresentation(
            f"{instance_id}.spline.composite",
            (
                SplineApproxRepresentation(
                    f"{instance_id}.spline",
                    max_degree=2,
                    fit_input_points=fit_points,
                ),
            ),
        ),
    )
    return replace(request, region_bindings=(first, second)), (
        Point2D(0.0, 1.0),
        *fit_points,
    )


def _real_source_set() -> R2SourceSet | None:
    semantic = (
        ROOT
        / "analysis_outputs"
        / "rf_cem_semantic_core"
        / "r1_semantic_core.28e8d6fa9efa221f"
    )
    sls2 = (
        ROOT
        / "analysis_outputs"
        / "rf_cem_literature_pilot_20260710"
        / "frozen_baselines"
        / "sls2.r149.6593e02e"
    )
    source = R2SourceSet(
        repo_root=ROOT,
        family_profile=(
            ROOT
            / "analysis_outputs"
            / "rf_cem_family_profiles"
            / "nc_axisymmetric_single_cell_rf_vacuum.00414d4f"
            / "family_profile.v0.json"
        ),
        family_grammar=semantic / "family_grammar.v0.json",
        instance_graphs=(
            semantic
            / "instances"
            / "sls2.r149.6593e02e.instance_boundary_graph.v0.json",
            semantic
            / "instances"
            / "rf500.2c27faee.b1r3.instance_boundary_graph.v0.json",
        ),
        sls2_generation=sls2 / "generation.core.json",
        sls2_baseline_step=sls2 / "cavity.step",
    )
    paths = (
        source.family_profile,
        source.family_grammar,
        *source.instance_graphs,
        source.sls2_generation,
        source.sls2_baseline_step,
    )
    return source if all(path.is_file() for path in paths) else None
