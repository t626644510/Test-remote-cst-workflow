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
    SplineApproxRepresentation,
    SplineNurbsRepresentation,
)
from rf_cem.semantic import validate_graph_against_grammar
from rf_cem.semantic.contracts import canonical_json_bytes, file_sha256

from .contracts import (
    CompileContractError,
    CompileRecord,
    CompileRequest,
    ContinuityCheck,
    CurveRealizationConstraint,
    EndpointConstraint,
    LandmarkGeometryBinding,
    OutputArtifactRef,
)


PROFILE_SCHEMA_VERSION = "compiled_profile.v0"
GEOMETRY_VALIDATION_VERSION = "r2_geometry_validation.v0"
BASELINE_COMPARISON_VERSION = "r2_baseline_comparison.v0"
C0_TOLERANCE_MM = 1.0e-6
G1_TOLERANCE_DEG = 2.0
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


@dataclass(frozen=True)
class _ContinuityPlan:
    """Pre-kernel requirement plus non-authoritative representation estimate."""

    check_id: str
    landmark_id: str
    left_patch_id: str
    right_patch_id: str
    join_scope: str
    required_level: str
    requirement_source: str
    policy_ref: str
    intentional_corner: bool
    enforcement: str
    interface_id: str | None
    pre_kernel_c0_gap_mm: float
    pre_kernel_tangent_angle_deg: float
    pre_kernel_curvature_delta_per_mm: float


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
        endpoint_constraints = _endpoint_constraints(
            request, patches, landmark_bindings
        )
        continuity_plan = _continuity_requirement_plan(request, patches)
        curve_realization_constraints = _curve_realization_constraints(
            patches, continuity_plan
        )
        profile_points = _profile_points(patches)
        backend_segments = tuple(
            _backend_segment(
                patch,
                tuple(
                    item
                    for item in curve_realization_constraints
                    if item.patch_id == patch.patch_id
                ),
            )
            for patch in patches
        )

        kernel_report = self._run_kernel(
            output_step=step_path,
            baseline_step=baseline_step,
            profile_points=profile_points,
            backend_segments=backend_segments,
            deflection_mm=deflection_mm,
        )
        _normalize_step_header(step_path)
        realized_segments = _realized_segment_map(kernel_report, patches)
        continuity_checks = _continuity_checks(
            continuity_plan,
            realized_segments=realized_segments,
            curve_realization_constraints=curve_realization_constraints,
        )
        geometry_validation = _geometry_validation(
            request,
            profile_points=profile_points,
            continuity_checks=continuity_checks,
            curve_realization_constraints=curve_realization_constraints,
            kernel_report=kernel_report,
            step_path=step_path,
        )
        baseline_comparison = _baseline_comparison(
            request,
            source_profile_points=source_profile_points,
            patches=patches,
            curve_realization_constraints=curve_realization_constraints,
            kernel_report=kernel_report,
        )
        profile_mapping = _compiled_profile_mapping(
            request,
            region_geometries=region_geometries,
            landmark_bindings=landmark_bindings,
            endpoint_constraints=endpoint_constraints,
            curve_realization_constraints=curve_realization_constraints,
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
            continuity_policy=request.continuity_policy,
            endpoint_constraints=endpoint_constraints,
            curve_realization_constraints=curve_realization_constraints,
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


def _endpoint_constraints(
    request: CompileRequest,
    patches: tuple[GeometryPatch, ...],
    landmark_bindings: tuple[LandmarkGeometryBinding, ...],
) -> tuple[EndpointConstraint, ...]:
    """Classify the two one-sided profile termini outside continuity checks."""

    if not patches:
        raise CompileContractError("compiled profile has no patches")
    bindings = {item.landmark_id: item for item in landmark_bindings}
    values: list[EndpointConstraint] = []
    for role, patch, landmark_id, point, tangent in (
        (
            "profile_start",
            patches[0],
            patches[0].start_landmark_id,
            patches[0].representation.start,
            patches[0].representation.start_tangent(),
        ),
        (
            "profile_end",
            patches[-1],
            patches[-1].end_landmark_id,
            patches[-1].representation.end,
            patches[-1].representation.end_tangent(),
        ),
    ):
        binding = bindings.get(landmark_id)
        if binding is None or binding.binding_role != "profile_endpoint":
            raise CompileContractError(
                f"profile endpoint lacks endpoint landmark classification: {landmark_id}"
            )
        if binding.incident_patch_ids != (patch.patch_id,):
            raise CompileContractError(
                f"profile endpoint must have exactly one incident patch: {landmark_id}"
            )
        normal = (-tangent[1], tangent[0])
        values.append(
            EndpointConstraint(
                constraint_id=f"{request.instance_id}.endpoint_constraint.{role}",
                landmark_id=landmark_id,
                endpoint_role=role,
                incident_patch_id=patch.patch_id,
                position=point,
                tangent=tangent,
                normal=normal,
                termination_plane="constant_z",
                classification_source=(
                    "instance_boundary_graph.landmark_type:AxialApertureLandmark"
                ),
            )
        )
    return tuple(values)


def _continuity_requirement_plan(
    request: CompileRequest, patches: tuple[GeometryPatch, ...]
) -> tuple[_ContinuityPlan, ...]:
    values: list[_ContinuityPlan] = []
    policy = request.continuity_policy
    if policy is None:
        raise CompileContractError("compile request lacks a continuity policy")
    overrides = {
        item.interface_id: item for item in policy.semantic_interface_overrides
    }
    interfaces = {
        (
            item.left_region_id,
            item.right_region_id,
            item.landmark_id,
        ): item
        for item in request.instance_graph.interfaces
    }
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
        within_region = left.owner_region_id == right.owner_region_id
        interface_id: str | None = None
        intentional_corner = False
        if within_region:
            requirement = policy.internal_patch_policy
            requirement_source = "internal_patch_policy"
        else:
            interface = interfaces.get(
                (
                    left.owner_region_id,
                    right.owner_region_id,
                    left.end_landmark_id,
                )
            )
            if interface is None:
                raise CompileContractError(
                    "cross-region patch join lacks a matching semantic interface"
                )
            interface_id = interface.interface_id
            override = overrides.get(interface_id)
            if override is None:
                requirement = policy.semantic_interface_default
                requirement_source = "semantic_interface_default"
            else:
                requirement = override.requirement
                requirement_source = "semantic_interface_override"
                intentional_corner = override.intentional_corner
        required_level = requirement.required_level
        values.append(
            _ContinuityPlan(
                check_id=f"continuity.{index:02d}",
                landmark_id=left.end_landmark_id,
                left_patch_id=left.patch_id,
                right_patch_id=right.patch_id,
                join_scope="within_region" if within_region else "cross_region",
                required_level=required_level,
                requirement_source=requirement_source,
                policy_ref=policy.policy_id,
                intentional_corner=intentional_corner,
                enforcement=requirement.enforcement,
                interface_id=interface_id,
                pre_kernel_c0_gap_mm=gap,
                pre_kernel_tangent_angle_deg=tangent_angle,
                pre_kernel_curvature_delta_per_mm=curvature_delta,
            )
        )
    return tuple(values)


def _curve_realization_constraints(
    patches: tuple[GeometryPatch, ...],
    continuity_plan: tuple[_ContinuityPlan, ...],
) -> tuple[CurveRealizationConstraint, ...]:
    """Translate required G1 joins into family-independent spline directions."""

    by_id = {patch.patch_id: patch for patch in patches}
    values: list[CurveRealizationConstraint] = []
    for plan in continuity_plan:
        if plan.required_level == "C0":
            continue
        left = by_id[plan.left_patch_id]
        right = by_id[plan.right_patch_id]
        left_is_spline = isinstance(
            left.representation, SplineApproxRepresentation
        )
        right_is_spline = isinstance(
            right.representation, SplineApproxRepresentation
        )
        if left_is_spline and right_is_spline:
            target = _average_unit_tangent(
                left.representation.end_tangent(),
                right.representation.start_tangent(),
            )
            values.append(
                _curve_constraint(left, "end", target, plan)
            )
            values.append(
                _curve_constraint(right, "start", target, plan)
            )
        elif left_is_spline:
            values.append(
                _curve_constraint(
                    left,
                    "end",
                    right.representation.start_tangent(),
                    plan,
                )
            )
        elif right_is_spline:
            values.append(
                _curve_constraint(
                    right,
                    "start",
                    left.representation.end_tangent(),
                    plan,
                )
            )
    return tuple(values)


def _curve_constraint(
    patch: GeometryPatch,
    endpoint_role: str,
    tangent: tuple[float, float],
    plan: _ContinuityPlan,
) -> CurveRealizationConstraint:
    representation = patch.representation
    if not isinstance(representation, SplineApproxRepresentation):
        raise CompileContractError("curve tangent constraint requires a spline patch")
    return CurveRealizationConstraint(
        constraint_id=f"{patch.patch_id}.endpoint_tangent.{endpoint_role}",
        patch_id=patch.patch_id,
        endpoint_role=endpoint_role,
        start_tangent_unit=tangent if endpoint_role == "start" else None,
        end_tangent_unit=tangent if endpoint_role == "end" else None,
        source_join_id=plan.check_id,
        source_interface_id=plan.interface_id,
        required_continuity=plan.required_level,
        source_representation_contract=representation.backend_contract,
    )


def _average_unit_tangent(
    left: tuple[float, float], right: tuple[float, float]
) -> tuple[float, float]:
    dz = left[0] + right[0]
    dr = left[1] + right[1]
    length = math.hypot(dz, dr)
    if length <= 1.0e-12:
        raise CompileContractError(
            "adjacent spline tangents cannot define one oriented G1 direction"
        )
    return (dz / length, dr / length)


def _continuity_checks(
    continuity_plan: tuple[_ContinuityPlan, ...],
    *,
    realized_segments: Mapping[str, Mapping[str, Any]],
    curve_realization_constraints: tuple[CurveRealizationConstraint, ...],
) -> tuple[ContinuityCheck, ...]:
    """Measure authoritative C0/G1 on realized kernel edges."""

    values: list[ContinuityCheck] = []
    constraints_by_join: dict[str, list[CurveRealizationConstraint]] = {}
    for constraint in curve_realization_constraints:
        constraints_by_join.setdefault(constraint.source_join_id, []).append(
            constraint
        )
    for plan in continuity_plan:
        left = realized_segments[plan.left_patch_id]
        right = realized_segments[plan.right_patch_id]
        gap = _realized_point(left, "actual_end_point").distance_to(
            _realized_point(right, "actual_start_point")
        )
        tangent_angle = _tangent_angle_deg(
            _realized_tangent(left, "actual_end_tangent_unit"),
            _realized_tangent(right, "actual_start_tangent_unit"),
        )
        curvature_delta = plan.pre_kernel_curvature_delta_per_mm
        c0_pass = gap <= C0_TOLERANCE_MM
        g1_pass = c0_pass and tangent_angle <= G1_TOLERANCE_DEG
        g2_pass = g1_pass and curvature_delta <= G2_TOLERANCE_PER_MM
        constraint_verified = all(
            _constraint_was_applied(item, realized_segments[item.patch_id])
            for item in constraints_by_join.get(plan.check_id, [])
        )
        level_pass = {
            "C0": c0_pass,
            "G1": g1_pass,
            "G2": g2_pass,
        }[plan.required_level]
        values.append(
            ContinuityCheck(
                check_id=plan.check_id,
                landmark_id=plan.landmark_id,
                left_patch_id=plan.left_patch_id,
                right_patch_id=plan.right_patch_id,
                join_scope=plan.join_scope,
                required_level=plan.required_level,
                c0_gap_mm=gap,
                tangent_angle_deg=tangent_angle,
                curvature_delta_per_mm=curvature_delta,
                c0_tolerance_mm=C0_TOLERANCE_MM,
                g1_tolerance_deg=G1_TOLERANCE_DEG,
                g2_tolerance_per_mm=G2_TOLERANCE_PER_MM,
                c0_pass=c0_pass,
                g1_pass=g1_pass,
                g2_pass=g2_pass,
                required_pass=level_pass and constraint_verified,
                requirement_source=plan.requirement_source,
                policy_ref=plan.policy_ref,
                intentional_corner=plan.intentional_corner,
                enforcement=plan.enforcement,
                interface_id=plan.interface_id,
                requirement_basis="boundary_continuity_policy.v0",
                measurement_basis="kernel_realized_edge",
                g2_measurement_basis="representation_estimate",
                pre_kernel_c0_gap_mm=plan.pre_kernel_c0_gap_mm,
                pre_kernel_tangent_angle_deg=(
                    plan.pre_kernel_tangent_angle_deg
                ),
                constraint_enforcement_verified=constraint_verified,
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


def _backend_segment(
    patch: GeometryPatch,
    constraints: tuple[CurveRealizationConstraint, ...] = (),
) -> dict[str, Any]:
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
    if isinstance(representation, SplineApproxRepresentation):
        curve = {
            "type": "spline_approximation",
            "backend_contract": representation.backend_contract,
            "source_representation_contract": representation.backend_contract,
            "source_representation_backend_input_source": (
                representation.backend_input_source
            ),
            "fidelity": representation.fidelity,
            "degree_max": representation.max_degree,
            "tolerance_mm": representation.approximation_tolerance_mm,
            "optimization_ready": representation.optimization_ready,
            "exact_nurbs": representation.exact_nurbs,
        }
        if constraints:
            backends = {item.enforcement_backend for item in constraints}
            if len(backends) != 1:
                raise CompileContractError(
                    "one spline patch cannot use multiple realization backends"
                )
            start_constraint = next(
                (
                    item.start_tangent_unit
                    for item in constraints
                    if item.endpoint_role == "start"
                ),
                None,
            )
            end_constraint = next(
                (
                    item.end_tangent_unit
                    for item in constraints
                    if item.endpoint_role == "end"
                ),
                None,
            )
            curve.update(
                {
                    "fit_input_points": [
                        _kernel_point(point)
                        for point in representation.fit_input_points
                    ],
                    "source_control_point_hints": [
                        _kernel_point(point)
                        for point in representation.source_control_point_hints
                    ],
                    "input_source": "fit_input_points",
                    "comparison_source": (
                        "cadquery.splineApprox.v0 realization of "
                        "SplineApproxRepresentation.fit_input_points"
                    ),
                    "realized_backend_contract": next(iter(backends)),
                    "endpoint_tangent_constraints": {
                        "start_tangent_unit": (
                            None
                            if start_constraint is None
                            else list(start_constraint)
                        ),
                        "end_tangent_unit": (
                            None if end_constraint is None else list(end_constraint)
                        ),
                        "constraint_ids": [
                            item.constraint_id for item in constraints
                        ],
                        "constraint_kind": "geometric_direction",
                        "scale_tangent": True,
                    },
                }
            )
        elif representation.backend_input_source == "source_control_point_hints":
            curve["control_points"] = [
                _kernel_point(point)
                for point in representation.source_control_point_hints
            ]
            curve["input_source"] = "source_control_point_hints"
            curve["realized_backend_contract"] = representation.backend_contract
        else:
            curve["sampled_points"] = [
                _kernel_point(point) for point in representation.fit_input_points
            ]
            curve["input_source"] = "fit_input_points"
            curve["realized_backend_contract"] = representation.backend_contract
        return {**common, "kind": "nurbs", "curve": curve}
    if isinstance(representation, SplineNurbsRepresentation):
        curve: dict[str, Any] = {
            "type": "legacy_spline_approximation",
            "backend_contract": representation.fitting_contract,
            "degree_max": representation.degree,
            "tolerance_mm": representation.approximation_tolerance_mm,
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


def _realized_segment_map(
    kernel_report: Mapping[str, Any], patches: tuple[GeometryPatch, ...]
) -> dict[str, Mapping[str, Any]]:
    curve_generation = _mapping(
        kernel_report.get("curve_generation"), "kernel.curve_generation"
    )
    raw_segments = curve_generation.get("realized_segments")
    if not isinstance(raw_segments, list):
        raise CompileContractError(
            "geometry kernel did not return realized edge diagnostics"
        )
    expected = {patch.patch_id for patch in patches}
    values: dict[str, Mapping[str, Any]] = {}
    for raw in raw_segments:
        segment = _mapping(raw, "kernel.realized_segment")
        patch_id = segment.get("patch_id")
        if not isinstance(patch_id, str) or not patch_id:
            raise CompileContractError("realized edge diagnostic lacks a patch ID")
        if patch_id in values:
            raise CompileContractError("geometry kernel returned duplicate patch diagnostics")
        if segment.get("orientation") != "left_to_right":
            raise CompileContractError(
                f"realized edge orientation is not left-to-right: {patch_id}"
            )
        construction_contract = segment.get("construction_contract")
        if not isinstance(construction_contract, str) or not construction_contract:
            raise CompileContractError(
                f"realized edge lacks a construction contract: {patch_id}"
            )
        if not isinstance(segment.get("tangent_constraints_applied"), bool):
            raise CompileContractError(
                f"realized edge lacks constraint application provenance: {patch_id}"
            )
        _realized_point(segment, "actual_start_point")
        _realized_point(segment, "actual_end_point")
        _realized_tangent(segment, "actual_start_tangent_unit")
        _realized_tangent(segment, "actual_end_tangent_unit")
        values[patch_id] = segment
    if set(values) != expected:
        raise CompileContractError(
            "geometry kernel realized edge set does not match compiled patches"
        )
    return values


def _realized_point(segment: Mapping[str, Any], field: str) -> Point2D:
    value = _mapping(segment.get(field), f"kernel.realized_segment.{field}")
    try:
        z_mm = float(value["z_mm"])
        r_mm = float(value["r_mm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CompileContractError(
            f"kernel realized edge has invalid {field}"
        ) from exc
    if not math.isfinite(z_mm) or not math.isfinite(r_mm):
        raise CompileContractError(
            f"kernel realized edge has non-finite {field}"
        )
    return Point2D(z_mm=z_mm, r_mm=r_mm)


def _realized_tangent(
    segment: Mapping[str, Any], field: str
) -> tuple[float, float]:
    value = segment.get(field)
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(item, bool) for item in value)
    ):
        raise CompileContractError(
            f"kernel realized edge has invalid {field}"
        )
    try:
        tangent = (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise CompileContractError(
            f"kernel realized edge has invalid {field}"
        ) from exc
    length = math.hypot(*tangent)
    if (
        not all(math.isfinite(item) for item in tangent)
        or abs(length - 1.0) > 1.0e-6
    ):
        raise CompileContractError(
            f"kernel realized edge {field} is not a finite unit vector"
        )
    return tangent


def _constraint_was_applied(
    constraint: CurveRealizationConstraint,
    realized_segment: Mapping[str, Any],
) -> bool:
    endpoints = realized_segment.get("applied_endpoint_constraints")
    target = (
        constraint.start_tangent_unit
        if constraint.endpoint_role == "start"
        else constraint.end_tangent_unit
    )
    if target is None:
        return False
    actual = _realized_tangent(
        realized_segment,
        (
            "actual_start_tangent_unit"
            if constraint.endpoint_role == "start"
            else "actual_end_tangent_unit"
        ),
    )
    return (
        realized_segment.get("tangent_constraints_applied") is True
        and realized_segment.get("construction_contract")
        == constraint.enforcement_backend
        and isinstance(endpoints, Mapping)
        and endpoints.get(constraint.endpoint_role) is True
        and _tangent_angle_deg(target, actual) <= G1_TOLERANCE_DEG
    )


def _realized_fidelity_summary(
    kernel_report: Mapping[str, Any],
    curve_realization_constraints: tuple[CurveRealizationConstraint, ...],
) -> dict[str, Any]:
    curve_generation = _mapping(
        kernel_report.get("curve_generation"), "kernel.curve_generation"
    )
    raw_segments = curve_generation.get("realized_segments")
    if not isinstance(raw_segments, list):
        raise CompileContractError(
            "geometry kernel did not return realized edge diagnostics"
        )
    required_patch_ids = {
        item.patch_id for item in curve_realization_constraints
    }
    measured_patch_ids: set[str] = set()
    maximum_deviation = 0.0
    tolerances: list[float] = []
    sampling_policies: set[str] = set()
    comparison_sources: set[str] = set()
    measured_pass = True
    for raw in raw_segments:
        segment = _mapping(raw, "kernel.realized_segment")
        fidelity_value = segment.get("geometry_fidelity")
        if fidelity_value is None:
            continue
        fidelity = _mapping(
            fidelity_value, "kernel.realized_segment.geometry_fidelity"
        )
        patch_id = segment.get("patch_id")
        if not isinstance(patch_id, str):
            raise CompileContractError("realized fidelity lacks a patch ID")
        try:
            deviation = float(fidelity["maximum_deviation_mm"])
            tolerance = float(fidelity["tolerance_mm"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CompileContractError(
                "realized spline fidelity is incomplete"
            ) from exc
        if (
            not math.isfinite(deviation)
            or deviation < 0.0
            or not math.isfinite(tolerance)
            or tolerance <= 0.0
        ):
            raise CompileContractError(
                "realized spline fidelity has invalid numeric values"
            )
        policy = fidelity.get("sampling_policy")
        source = fidelity.get("comparison_source")
        if not isinstance(policy, str) or not policy:
            raise CompileContractError("realized spline fidelity lacks sampling policy")
        if not isinstance(source, str) or not source:
            raise CompileContractError("realized spline fidelity lacks comparison source")
        measured_patch_ids.add(patch_id)
        maximum_deviation = max(maximum_deviation, deviation)
        tolerances.append(tolerance)
        sampling_policies.add(policy)
        comparison_sources.add(source)
        measured_pass = measured_pass and fidelity.get("pass") is True
    missing = sorted(required_patch_ids - measured_patch_ids)
    return {
        "measurement_basis": "kernel_realized_edge",
        "measured_spline_count": len(measured_patch_ids),
        "required_constrained_spline_count": len(required_patch_ids),
        "maximum_deviation_mm": maximum_deviation,
        "sampling_policies": sorted(sampling_policies),
        "comparison_sources": sorted(comparison_sources),
        "tolerance_mm": max(tolerances, default=0.001),
        "missing_required_patch_ids": missing,
        "pass": measured_pass and not missing,
    }


def _geometry_validation(
    request: CompileRequest,
    *,
    profile_points: tuple[Point2D, ...],
    continuity_checks: tuple[ContinuityCheck, ...],
    curve_realization_constraints: tuple[CurveRealizationConstraint, ...],
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
    realized_fidelity = _realized_fidelity_summary(
        kernel_report, curve_realization_constraints
    )
    unverified_constraints = sum(
        not item.constraint_enforcement_verified for item in continuity_checks
    )
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
    if unverified_constraints:
        blocking.append(
            "planned endpoint tangent constraint was not applied by the geometry backend"
        )
    if realized_fidelity["pass"] is not True:
        blocking.append(
            "kernel-realized spline exceeds declared source-trace fidelity"
        )
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
            "measurement_basis": "kernel_realized_edge",
            "constraint_enforcement_verified": unverified_constraints == 0,
        },
        "realized_spline_fidelity": realized_fidelity,
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
    curve_realization_constraints: tuple[CurveRealizationConstraint, ...],
    kernel_report: Mapping[str, Any],
) -> dict[str, Any]:
    primitives = tuple(patch.representation for patch in patches)
    maximum = max(
        min(_point_to_representation_distance(point, item) for item in primitives)
        for point in source_profile_points
    )
    profile_pass = maximum <= request.baseline.profile_max_deviation_tolerance_mm
    realized_fidelity = _realized_fidelity_summary(
        kernel_report, curve_realization_constraints
    )
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
        "realized_spline_fidelity": realized_fidelity,
        "source_partition_coverage_pass": True,
        "accepted_step_comparison": kernel_comparison,
        "accepted_step_pass": step_pass,
        "pass": profile_pass and step_pass and realized_fidelity["pass"] is True,
        "warnings": warnings,
    }


def _compiled_profile_mapping(
    request: CompileRequest,
    *,
    region_geometries: tuple[RegionGeometry, ...],
    landmark_bindings: tuple[LandmarkGeometryBinding, ...],
    endpoint_constraints: tuple[EndpointConstraint, ...],
    curve_realization_constraints: tuple[CurveRealizationConstraint, ...],
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
        "continuity_policy": request.continuity_policy.to_mapping(),
        "endpoint_constraints": [item.to_mapping() for item in endpoint_constraints],
        "curve_realization_constraints": [
            item.to_mapping() for item in curve_realization_constraints
        ],
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
