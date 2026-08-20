"""Generic R2 profile compiler joining semantic topology and representations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from rf_cem.parametric_geometry.core.backend_cadquery import CadQueryGeometryBackend
from rf_cem.parametric_geometry.core.types import GeometryThresholds
from rf_cem.parametric_geometry.validation.geometry_metrics import compare_geometry
from rf_cem.parametric_geometry.validation.self_intersection import (
    all_r_nonnegative,
    profile_is_simple,
)
from rf_cem.representation import (
    CircularArcRepresentation,
    CompositeRegionRepresentation,
    EllipseArcRepresentation,
    GeometryPatch,
    LineRepresentation,
    Point2D,
    PrimitiveRepresentation,
    RegionGeometry,
    SplineNurbsRepresentation,
)
from rf_cem.semantic import validate_graph_against_grammar
from rf_cem.semantic.contracts import canonical_json_bytes, file_sha256

from .contracts import (
    CompileContractError,
    CompileRecord,
    CompileRequest,
    ContinuityCheck,
    LandmarkGeometryBinding,
    OutputArtifactRef,
)


PROFILE_SCHEMA_VERSION = "compiled_profile.v0"
GEOMETRY_VALIDATION_VERSION = "r2_geometry_validation.v0"
BASELINE_COMPARISON_VERSION = "r2_baseline_comparison.v0"
C0_TOLERANCE_MM = 1.0e-6
G1_TOLERANCE_DEG = 0.5
G2_TOLERANCE_PER_MM = 1.0e-3


class GeometryKernel(Protocol):
    """Minimal adapter implemented by the existing isolated geometry backend."""

    def recover(self, **kwargs: Any) -> dict[str, Any]: ...

    def generate(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CompileResult:
    """One in-memory R2 compile result plus its materialized no-CST artifacts."""

    record: CompileRecord
    step_path: Path
    profile_path: Path
    profile_points: tuple[Point2D, ...]
    backend_segments: tuple[dict[str, Any], ...]


class ProfileCompiler:
    """Compile any validated topology and region-representation binding set."""

    def __init__(self, kernel: GeometryKernel | None = None) -> None:
        self._kernel = kernel or CadQueryGeometryBackend()

    def compile(
        self,
        request: CompileRequest,
        *,
        bundle_root: Path,
        source_profile_points: tuple[Point2D, ...],
        baseline_step: Path | None = None,
        deflection_mm: float = 0.25,
    ) -> CompileResult:
        """Compile through the sole R2 entry and emit STEP/profile/record data.

        This method performs no CST action.  CadQuery/OCP executes only through
        the repository's existing isolated worker adapter.
        """

        validate_graph_against_grammar(request.family_grammar, request.instance_graph)
        if request.baseline.accepted_step_materialized != (baseline_step is not None):
            raise CompileContractError("baseline STEP materialization does not match request")
        if baseline_step is not None:
            if not baseline_step.is_file():
                raise CompileContractError("materialized baseline STEP is missing")
            if file_sha256(baseline_step) != request.baseline.accepted_step_raw_sha256:
                raise CompileContractError("materialized baseline STEP raw hash mismatch")
        if not source_profile_points:
            raise CompileContractError("source-native profile trace is empty")
        root = bundle_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        geometry_dir = root / "geometry"
        geometry_dir.mkdir(parents=True, exist_ok=True)
        step_relative = f"geometry/{request.instance_id}.step"
        profile_relative = f"geometry/{request.instance_id}.compiled_profile.v0.json"
        step_path = root / Path(step_relative)
        profile_path = root / Path(profile_relative)
        if step_path.exists() or profile_path.exists():
            raise CompileContractError("compiler refuses to overwrite an existing output artifact")

        region_geometries = _build_region_geometries(request)
        patches = tuple(
            patch for region_geometry in region_geometries for patch in region_geometry.patches
        )
        _validate_source_partition_coverage(patches)
        landmark_bindings = _resolve_landmarks(request, patches)
        continuity_checks = _continuity_checks(patches)
        profile_points = _profile_points(patches)
        backend_segments = tuple(_backend_segment(patch) for patch in patches)

        kernel_report = self._run_kernel(
            output_step=step_path,
            baseline_step=baseline_step,
            profile_points=profile_points,
            backend_segments=backend_segments,
            deflection_mm=deflection_mm,
        )
        _normalize_step_header(step_path)
        geometry_validation = _geometry_validation(
            request,
            profile_points=profile_points,
            continuity_checks=continuity_checks,
            kernel_report=kernel_report,
            step_path=step_path,
        )
        baseline_comparison = _baseline_comparison(
            request,
            source_profile_points=source_profile_points,
            patches=patches,
            kernel_report=kernel_report,
        )
        profile_mapping = _compiled_profile_mapping(
            request,
            region_geometries=region_geometries,
            landmark_bindings=landmark_bindings,
            profile_points=profile_points,
            backend_segments=backend_segments,
        )
        profile_path.write_bytes(canonical_json_bytes(profile_mapping) + b"\n")
        if not step_path.is_file() or step_path.stat().st_size <= 0:
            raise CompileContractError("geometry kernel did not materialize a STEP output")
        output_artifacts = (
            OutputArtifactRef(
                role="compiled_rf_vacuum_step",
                path=step_relative,
                media_type="model/step",
                raw_sha256=file_sha256(step_path),
                size_bytes=step_path.stat().st_size,
            ),
            OutputArtifactRef(
                role="compiled_profile",
                path=profile_relative,
                media_type="application/json",
                raw_sha256=file_sha256(profile_path),
                size_bytes=profile_path.stat().st_size,
            ),
        )
        warnings = tuple(
            str(item)
            for item in (
                list(geometry_validation.get("warnings", []))
                + list(baseline_comparison.get("warnings", []))
            )
        )
        passed = (
            all(item.required_pass for item in continuity_checks)
            and geometry_validation["pass"] is True
            and baseline_comparison["pass"] is True
        )
        record = CompileRecord(
            family_id=request.family_id,
            instance_id=request.instance_id,
            compiler_version=request.compiler_version,
            family_grammar_ref=request.family_grammar_ref,
            instance_graph_ref=request.instance_graph_ref,
            source_native_provenance=request.source_native_provenance,
            baseline=request.baseline,
            region_geometries=region_geometries,
            landmark_bindings=landmark_bindings,
            continuity_checks=continuity_checks,
            geometry_validation=geometry_validation,
            baseline_comparison=baseline_comparison,
            output_artifacts=output_artifacts,
            warnings=warnings,
            status="pass" if passed else "failed",
        )
        return CompileResult(
            record=record,
            step_path=step_path,
            profile_path=profile_path,
            profile_points=profile_points,
            backend_segments=backend_segments,
        )

    def _run_kernel(
        self,
        *,
        output_step: Path,
        baseline_step: Path | None,
        profile_points: tuple[Point2D, ...],
        backend_segments: tuple[dict[str, Any], ...],
        deflection_mm: float,
    ) -> dict[str, Any]:
        kwargs = {
            "output_step": output_step,
            "axis": "z",
            "profile_points": [(point.z_mm, point.r_mm) for point in profile_points],
            "profile_segments": list(backend_segments),
            "deflection_mm": deflection_mm,
        }
        if baseline_step is not None:
            return self._kernel.recover(
                step_file=baseline_step,
                body_index=0,
                **kwargs,
            )
        return self._kernel.generate(**kwargs)


def _build_region_geometries(request: CompileRequest) -> tuple[RegionGeometry, ...]:
    values: list[RegionGeometry] = []
    global_order = 0
    for binding in request.region_bindings:
        components = binding.representation.components
        patches: list[GeometryPatch] = []
        for patch_order, component in enumerate(components):
            start_landmark = (
                binding.start_landmark_id
                if patch_order == 0
                else binding.internal_landmark_ids[patch_order - 1]
            )
            end_landmark = (
                binding.end_landmark_id
                if patch_order == len(components) - 1
                else binding.internal_landmark_ids[patch_order]
            )
            patches.append(
                GeometryPatch(
                    patch_id=f"{request.instance_id}.patch.{global_order:02d}",
                    owner_region_id=binding.region_id,
                    region_order=binding.region_order,
                    patch_order=patch_order,
                    global_order=global_order,
                    representation=component,
                    start_landmark_id=start_landmark,
                    end_landmark_id=end_landmark,
                    source_native_segment_ref=binding.source_native_segment_refs[patch_order],
                    source_parameter_interval=binding.source_parameter_intervals[patch_order],
                )
            )
            global_order += 1
        values.append(
            RegionGeometry(
                region_geometry_id=f"{binding.region_id}.geometry.v0",
                owner_region_id=binding.region_id,
                region_order=binding.region_order,
                representation=binding.representation,
                patches=tuple(patches),
            )
        )
    return tuple(values)


def _validate_source_partition_coverage(patches: tuple[GeometryPatch, ...]) -> None:
    by_source: dict[str, list[tuple[float, float]]] = {}
    for patch in patches:
        by_source.setdefault(patch.source_native_segment_ref, []).append(
            patch.source_parameter_interval
        )
    for source_ref, intervals in by_source.items():
        ordered = sorted(intervals)
        if abs(ordered[0][0]) > 1.0e-12 or abs(ordered[-1][1] - 1.0) > 1.0e-12:
            raise CompileContractError(f"source segment partition is incomplete: {source_ref}")
        for left, right in zip(ordered, ordered[1:]):
            if abs(left[1] - right[0]) > 1.0e-12:
                raise CompileContractError(
                    f"source segment partition has a gap or overlap: {source_ref}"
                )


def _resolve_landmarks(
    request: CompileRequest, patches: tuple[GeometryPatch, ...]
) -> tuple[LandmarkGeometryBinding, ...]:
    endpoint_map: dict[str, list[tuple[str, Point2D]]] = {}
    for patch in patches:
        endpoint_map.setdefault(patch.start_landmark_id, []).append(
            (patch.patch_id, patch.representation.start)
        )
        endpoint_map.setdefault(patch.end_landmark_id, []).append(
            (patch.patch_id, patch.representation.end)
        )
    semantic_landmarks = {item.landmark_id: item for item in request.instance_graph.landmarks}
    missing = sorted(set(semantic_landmarks) - set(endpoint_map))
    if missing:
        raise CompileContractError(f"semantic landmarks were not bound: {missing}")
    values: list[LandmarkGeometryBinding] = []
    for landmark_id, incidents in endpoint_map.items():
        if len(incidents) > 2:
            raise CompileContractError(f"landmark has more than two incident patches: {landmark_id}")
        point = Point2D(
            z_mm=sum(item[1].z_mm for item in incidents) / len(incidents),
            r_mm=sum(item[1].r_mm for item in incidents) / len(incidents),
        )
        maximum_gap = max((left[1].distance_to(right[1]) for left in incidents for right in incidents), default=0.0)
        if maximum_gap > C0_TOLERANCE_MM:
            raise CompileContractError(f"landmark incident patches are not C0: {landmark_id}")
        semantic = semantic_landmarks.get(landmark_id)
        if semantic is None:
            role = "internal_patch_join"
        elif semantic.landmark_type == "AxialApertureLandmark":
            role = "profile_endpoint"
        elif semantic.landmark_type == "SymmetryLandmark":
            role = "symmetry"
        else:
            role = "region_interface"
        values.append(
            LandmarkGeometryBinding(
                landmark_id=landmark_id,
                point=point,
                incident_patch_ids=tuple(item[0] for item in incidents),
                binding_role=role,
                maximum_incident_gap_mm=maximum_gap,
            )
        )
    order = {patch.start_landmark_id: patch.global_order * 2 for patch in patches}
    order.update({patch.end_landmark_id: patch.global_order * 2 + 1 for patch in patches})
    return tuple(sorted(values, key=lambda item: (order.get(item.landmark_id, 10**9), item.landmark_id)))


def _continuity_checks(patches: tuple[GeometryPatch, ...]) -> tuple[ContinuityCheck, ...]:
    values: list[ContinuityCheck] = []
    for index, (left, right) in enumerate(zip(patches, patches[1:])):
        if left.end_landmark_id != right.start_landmark_id:
            raise CompileContractError(
                f"patch sequence does not share a landmark: {left.patch_id} -> {right.patch_id}"
            )
        gap = left.representation.end.distance_to(right.representation.start)
        tangent_angle = _tangent_angle_deg(
            left.representation.end_tangent(), right.representation.start_tangent()
        )
        curvature_delta = abs(
            left.representation.end_curvature_per_mm()
            - right.representation.start_curvature_per_mm()
        )
        c0_pass = gap <= C0_TOLERANCE_MM
        g1_pass = c0_pass and tangent_angle <= G1_TOLERANCE_DEG
        g2_pass = g1_pass and curvature_delta <= G2_TOLERANCE_PER_MM
        same_source = left.source_native_segment_ref == right.source_native_segment_ref
        required_level = "G2" if same_source else "C0"
        required_pass = g2_pass if required_level == "G2" else c0_pass
        values.append(
            ContinuityCheck(
                check_id=f"continuity.{index:02d}",
                landmark_id=left.end_landmark_id,
                left_patch_id=left.patch_id,
                right_patch_id=right.patch_id,
                join_scope=(
                    "within_region"
                    if left.owner_region_id == right.owner_region_id
                    else "cross_region"
                ),
                required_level=required_level,
                c0_gap_mm=gap,
                tangent_angle_deg=tangent_angle,
                curvature_delta_per_mm=curvature_delta,
                c0_tolerance_mm=C0_TOLERANCE_MM,
                g1_tolerance_deg=G1_TOLERANCE_DEG,
                g2_tolerance_per_mm=G2_TOLERANCE_PER_MM,
                c0_pass=c0_pass,
                g1_pass=g1_pass,
                g2_pass=g2_pass,
                required_pass=required_pass,
            )
        )
    return tuple(values)


def _profile_points(patches: tuple[GeometryPatch, ...]) -> tuple[Point2D, ...]:
    values: list[Point2D] = []
    for patch in patches:
        points = list(patch.representation.sample())
        if values and values[-1].distance_to(points[0]) <= C0_TOLERANCE_MM:
            points = points[1:]
        values.extend(points)
    if len(values) < 2:
        raise CompileContractError("compiled profile contains fewer than two points")
    return tuple(values)


def _backend_segment(patch: GeometryPatch) -> dict[str, Any]:
    representation = patch.representation
    common = {
        "id": patch.patch_id,
        "start": _kernel_point(representation.start),
        "end": _kernel_point(representation.end),
        "owner_region_id": patch.owner_region_id,
        "source_native_segment_ref": patch.source_native_segment_ref,
    }
    if isinstance(representation, LineRepresentation):
        return {**common, "kind": "line", "curve": {"type": "line"}}
    if isinstance(representation, CircularArcRepresentation):
        mid_angle = (representation.start_angle_rad + representation.end_angle_rad) / 2.0
        mid = Point2D(
            z_mm=representation.center.z_mm + representation.radius_mm * math.cos(mid_angle),
            r_mm=representation.center.r_mm + representation.radius_mm * math.sin(mid_angle),
        )
        return {
            **common,
            "kind": "arc",
            "curve": {
                "type": "arc",
                "center": _kernel_point(representation.center),
                "radius": representation.radius_mm,
                "start_angle_rad": representation.start_angle_rad,
                "end_angle_rad": representation.end_angle_rad,
                "mid": _kernel_point(mid),
            },
        }
    if isinstance(representation, EllipseArcRepresentation):
        sampled = [_kernel_point(point) for point in representation.sample()]
        return {
            **common,
            "kind": "nurbs",
            "curve": {
                "type": "nurbs_approximation",
                "source_curve": "analytic_ellipse_arc",
                "sampled_points": sampled,
                "degree_max": 5,
            },
        }
    if isinstance(representation, SplineNurbsRepresentation):
        curve: dict[str, Any] = {
            "type": "nurbs",
            "degree_max": representation.degree,
        }
        if representation.backend_point_source == "control_points":
            curve["control_points"] = [
                _kernel_point(point) for point in representation.control_points
            ]
        else:
            curve["sampled_points"] = [
                _kernel_point(point) for point in representation.fit_points
            ]
        return {**common, "kind": "nurbs", "curve": curve}
    raise CompileContractError("unsupported primitive representation")


def _geometry_validation(
    request: CompileRequest,
    *,
    profile_points: tuple[Point2D, ...],
    continuity_checks: tuple[ContinuityCheck, ...],
    kernel_report: Mapping[str, Any],
    step_path: Path,
) -> dict[str, Any]:
    plain_points = [(point.z_mm, point.r_mm) for point in profile_points]
    generated = _mapping(kernel_report.get("generated"), "kernel.generated")
    curve_generation = _mapping(kernel_report.get("curve_generation"), "kernel.curve_generation")
    fallbacks = [str(item) for item in curve_generation.get("fallbacks", [])]
    blocking: list[str] = []
    warnings: list[str] = []
    simple = profile_is_simple(plain_points)
    nonnegative = all_r_nonnegative(plain_points)
    brep_valid = generated.get("brep_valid") is True
    segment_mode = curve_generation.get("mode") == "cadquery_curve_segments"
    required_continuity = all(item.required_pass for item in continuity_checks)
    if not simple:
        blocking.append("compiled outer profile is self-intersecting")
    if not nonnegative:
        blocking.append("compiled outer profile crosses the rotation axis")
    if not brep_valid:
        blocking.append("generated B-Rep is invalid")
    if not step_path.is_file() or step_path.stat().st_size <= 0:
        blocking.append("STEP output is missing or empty")
    if not segment_mode or fallbacks:
        blocking.append("geometry kernel did not preserve curve-segment generation")
    if not required_continuity:
        blocking.append("required continuity failed")
    non_required_g1_failures = sum(1 for item in continuity_checks if not item.g1_pass)
    non_required_g2_failures = sum(1 for item in continuity_checks if not item.g2_pass)
    if non_required_g1_failures:
        warnings.append(
            f"{non_required_g1_failures} join(s) fail diagnostic G1; only declared required levels gate R2"
        )
    if non_required_g2_failures:
        warnings.append(
            f"{non_required_g2_failures} join(s) fail diagnostic G2; only declared required levels gate R2"
        )
    return {
        "schema_version": GEOMETRY_VALIDATION_VERSION,
        "validation_mode": "no_cst_profile_and_isolated_occt",
        "units": {"length": "mm", "angle": "deg", "curvature": "1/mm"},
        "profile_checks": {
            "point_count": len(profile_points),
            "profile_is_simple": simple,
            "all_r_nonnegative": nonnegative,
            "implicit_axis_closure_defined": True,
            "boundary_orientation": "left_to_right_outer_profile_then_axis_return",
        },
        "ownership_checks": {
            "region_count": len(request.region_bindings),
            "patch_count": sum(len(item.representation.components) for item in request.region_bindings),
            "one_owner_per_patch": True,
            "no_cross_region_patch": True,
        },
        "continuity_summary": {
            "check_count": len(continuity_checks),
            "required_pass": required_continuity,
            "c0_pass_count": sum(item.c0_pass for item in continuity_checks),
            "g1_pass_count": sum(item.g1_pass for item in continuity_checks),
            "g2_pass_count": sum(item.g2_pass for item in continuity_checks),
        },
        "kernel": _kernel_summary(kernel_report),
        "step_exported": step_path.is_file() and step_path.stat().st_size > 0,
        "step_header_timestamp_policy": "normalized_1970_epoch_for_reproducible_artifact",
        "brep_valid": brep_valid,
        "pass": not blocking,
        "blocking_errors": blocking,
        "warnings": warnings,
    }


def _baseline_comparison(
    request: CompileRequest,
    *,
    source_profile_points: tuple[Point2D, ...],
    patches: tuple[GeometryPatch, ...],
    kernel_report: Mapping[str, Any],
) -> dict[str, Any]:
    primitives = tuple(patch.representation for patch in patches)
    maximum = max(
        min(_point_to_representation_distance(point, item) for item in primitives)
        for point in source_profile_points
    )
    profile_pass = maximum <= request.baseline.profile_max_deviation_tolerance_mm
    warnings: list[str] = []
    kernel_comparison: dict[str, Any]
    baseline_metrics = kernel_report.get("baseline")
    if request.baseline.accepted_step_materialized:
        thresholds = GeometryThresholds(
            bbox_abs_mm=request.baseline.bbox_absolute_tolerance_mm,
            bbox_rel=0.0,
            volume_rel=request.baseline.volume_relative_tolerance,
            surface_area_rel=request.baseline.surface_area_relative_tolerance,
        )
        kernel_comparison = compare_geometry(dict(kernel_report), thresholds)
        step_pass = not kernel_comparison["blocking_errors"]
    else:
        if baseline_metrics is not None:
            raise CompileContractError("unmaterialized baseline unexpectedly produced kernel metrics")
        kernel_comparison = {
            "status": "not_compared_accepted_step_unmaterialized",
            "accepted_step_raw_sha256": request.baseline.accepted_step_raw_sha256,
        }
        warnings.append(
            "accepted RF500 STEP is hash-bound but not materialized locally; source-native profile equivalence and new B-Rep validity are the R2 baseline"
        )
        step_pass = True
    return {
        "schema_version": BASELINE_COMPARISON_VERSION,
        "comparison_mode": request.baseline.baseline_kind,
        "source_profile_contract": request.baseline.source_profile_contract,
        "source_profile_point_count": len(source_profile_points),
        "source_profile_max_deviation_mm": maximum,
        "source_profile_tolerance_mm": request.baseline.profile_max_deviation_tolerance_mm,
        "source_profile_pass": profile_pass,
        "source_partition_coverage_pass": True,
        "accepted_step_comparison": kernel_comparison,
        "accepted_step_pass": step_pass,
        "pass": profile_pass and step_pass,
        "warnings": warnings,
    }


def _compiled_profile_mapping(
    request: CompileRequest,
    *,
    region_geometries: tuple[RegionGeometry, ...],
    landmark_bindings: tuple[LandmarkGeometryBinding, ...],
    profile_points: tuple[Point2D, ...],
    backend_segments: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "family_id": request.family_id,
        "instance_id": request.instance_id,
        "compiler_version": request.compiler_version,
        "units": {"z": "mm", "r": "mm"},
        "axis": "z",
        "orientation": "left_to_right",
        "implicit_axis_closure": True,
        "region_geometries": [item.to_mapping() for item in region_geometries],
        "landmark_bindings": [item.to_mapping() for item in landmark_bindings],
        "profile_points": [point.to_mapping() for point in profile_points],
        "kernel_segments": list(backend_segments),
    }


def _kernel_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    reader = _mapping(value.get("reader"), "kernel.reader")
    body_selection = _mapping(value.get("body_selection"), "kernel.body_selection")
    generated = _mapping(value.get("generated"), "kernel.generated")
    tessellation = _mapping(value.get("tessellation"), "kernel.tessellation")
    curve_generation = _mapping(value.get("curve_generation"), "kernel.curve_generation")
    return {
        "schema_version": value.get("schema_version"),
        "reader": dict(reader),
        "body_selection": dict(body_selection),
        "generated_metrics": dict(generated),
        "tessellation": dict(tessellation),
        "curve_generation": dict(curve_generation),
    }


def _point_to_representation_distance(
    point: Point2D, representation: PrimitiveRepresentation
) -> float:
    if isinstance(representation, LineRepresentation):
        return _point_to_segment_distance(point, representation.start, representation.end)
    if isinstance(representation, CircularArcRepresentation):
        return abs(point.distance_to(representation.center) - representation.radius_mm)
    if isinstance(representation, EllipseArcRepresentation):
        angle = math.atan2(
            (point.r_mm - representation.center.r_mm) / representation.semi_axis_r_mm,
            (point.z_mm - representation.center.z_mm) / representation.semi_axis_z_mm,
        )
        candidate = Point2D(
            z_mm=representation.center.z_mm
            + representation.semi_axis_z_mm * math.cos(angle),
            r_mm=representation.center.r_mm
            + representation.semi_axis_r_mm * math.sin(angle),
        )
        return point.distance_to(candidate)
    return min(
        _point_to_segment_distance(point, left, right)
        for left, right in zip(representation.fit_points, representation.fit_points[1:])
    )


def _point_to_segment_distance(point: Point2D, left: Point2D, right: Point2D) -> float:
    dz = right.z_mm - left.z_mm
    dr = right.r_mm - left.r_mm
    denominator = dz * dz + dr * dr
    if denominator <= 1.0e-30:
        return point.distance_to(left)
    fraction = (
        (point.z_mm - left.z_mm) * dz + (point.r_mm - left.r_mm) * dr
    ) / denominator
    fraction = min(1.0, max(0.0, fraction))
    candidate = Point2D(
        z_mm=left.z_mm + fraction * dz,
        r_mm=left.r_mm + fraction * dr,
    )
    return point.distance_to(candidate)


def _tangent_angle_deg(
    left: tuple[float, float], right: tuple[float, float]
) -> float:
    dot = min(1.0, max(-1.0, left[0] * right[0] + left[1] * right[1]))
    return math.degrees(math.acos(dot))


def _kernel_point(point: Point2D) -> dict[str, float]:
    return {"z": point.z_mm, "r": point.r_mm}


def _normalize_step_header(path: Path) -> None:
    """Normalize the non-geometric OCCT export timestamp for byte stability."""

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CompileContractError("cannot read generated STEP for header normalization") from exc
    pattern = re.compile(rb"(FILE_NAME\('[^']*',)'[^']*'")
    normalized, count = pattern.subn(
        rb"\1'1970-01-01T00:00:00'", data, count=1
    )
    if count != 1:
        raise CompileContractError("generated STEP lacks one normalizable FILE_NAME timestamp")
    path.write_bytes(normalized)


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompileContractError(f"{path} must be an object")
    return value


__all__ = [
    "BASELINE_COMPARISON_VERSION",
    "C0_TOLERANCE_MM",
    "CompileResult",
    "G1_TOLERANCE_DEG",
    "G2_TOLERANCE_PER_MM",
    "GEOMETRY_VALIDATION_VERSION",
    "GeometryKernel",
    "PROFILE_SCHEMA_VERSION",
    "ProfileCompiler",
]
