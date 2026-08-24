"""Source-lossless adapters preparing the two real R2 compile requests."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

from rf_cem.family_profile import (
    FAMILY_PROFILE_SCHEMA_VERSION,
    FamilyInstance,
    FamilyProfile,
    canonical_sha256 as family_canonical_sha256,
    load_profile,
)
from rf_cem.literature_semantics.geometry_candidate import build_sls2_profile
from rf_cem.representation import (
    CircularArcRepresentation,
    CompositeRegionRepresentation,
    EllipseArcRepresentation,
    LineRepresentation,
    Point2D,
    PrimitiveRepresentation,
    SplineApproxRepresentation,
    trim_representation,
)
from rf_cem.semantic import (
    EvidenceRef,
    FamilyGrammar,
    InstanceBoundaryGraph,
    RF500_INSTANCE_ID,
    SLS2_INSTANCE_ID,
    load_family_grammar,
    load_instance_boundary_graph,
    validate_graph_against_grammar,
)
from rf_cem.semantic.contracts import canonical_sha256, file_sha256

from .contracts import (
    BaselineContract,
    BoundaryContinuityPolicy,
    CompileContractError,
    CompileRequest,
    ContinuityInterfaceOverride,
    ContinuityRequirement,
    ContractSourceRef,
    NativeArtifactRef,
    RegionRepresentationBinding,
    SourceNativeProvenance,
    default_boundary_continuity_policy,
)


@dataclass(frozen=True)
class R2SourceSet:
    """Explicit immutable inputs required for the two real R2 compiles."""

    repo_root: Path
    family_profile: Path
    family_grammar: Path
    instance_graphs: tuple[Path, ...]
    sls2_generation: Path
    sls2_baseline_step: Path


@dataclass(frozen=True)
class PreparedCompileCase:
    """One validated compile request with its source-native comparison trace."""

    request: CompileRequest
    source_profile_points: tuple[Point2D, ...]
    baseline_step: Path | None


@dataclass(frozen=True)
class _SourceCurve:
    source_segment_ref: str
    representation: PrimitiveRepresentation


@dataclass(frozen=True)
class _ComponentPlan:
    region_id: str
    source_segment_ref: str
    source_interval: tuple[float, float]
    representation: PrimitiveRepresentation


def prepare_r2_cases(sources: R2SourceSet) -> tuple[PreparedCompileCase, ...]:
    """Load and fail-closed validate both canonical instance compile requests."""

    root = sources.repo_root.resolve()
    profile_path = _inside(root, sources.family_profile, "family profile")
    grammar_path = _inside(root, sources.family_grammar, "family grammar")
    generation_path = _inside(root, sources.sls2_generation, "SLS-2 generation")
    baseline_step = _inside(root, sources.sls2_baseline_step, "SLS-2 baseline STEP")
    graph_paths = tuple(
        _inside(root, path, "instance graph") for path in sources.instance_graphs
    )
    if len(graph_paths) != 2:
        raise CompileContractError("R2 requires exactly two canonical instance graphs")
    profile = load_profile(profile_path)
    grammar = load_family_grammar(grammar_path)
    graphs = tuple(load_instance_boundary_graph(path) for path in graph_paths)
    by_id = {graph.instance_id: (graph, path) for graph, path in zip(graphs, graph_paths)}
    if set(by_id) != {SLS2_INSTANCE_ID, RF500_INSTANCE_ID}:
        raise CompileContractError("R2 graphs must be the canonical SLS-2 and RF500 instances")
    if profile.family_id != grammar.family_id:
        raise CompileContractError("Stage C profile and R1 grammar family mismatch")
    for graph in graphs:
        validate_graph_against_grammar(grammar, graph)
    generation = _read_json(generation_path)
    grammar_ref = _contract_ref(
        root,
        grammar_path,
        contract_kind="family_grammar",
        schema_version=grammar.schema_version,
        object_id=grammar.grammar_id,
        value=grammar.to_mapping(),
    )
    profile_ref = _contract_ref(
        root,
        profile_path,
        contract_kind="family_profile",
        schema_version=profile.schema_version,
        object_id=profile.family_id,
        value=profile.to_mapping(),
        canonicalizer=family_canonical_sha256,
    )
    instances = {instance.instance_id: instance for instance in profile.instances}
    if set(instances) != {SLS2_INSTANCE_ID, RF500_INSTANCE_ID}:
        raise CompileContractError("Stage C profile no longer contains exactly both R2 instances")
    _verify_sls2_sources(
        root=root,
        instance=instances[SLS2_INSTANCE_ID],
        generation_path=generation_path,
        generation=generation,
        baseline_step=baseline_step,
    )
    cases: list[PreparedCompileCase] = []
    for instance_id in (SLS2_INSTANCE_ID, RF500_INSTANCE_ID):
        graph, graph_path = by_id[instance_id]
        instance = instances[instance_id]
        graph_ref = _contract_ref(
            root,
            graph_path,
            contract_kind="instance_boundary_graph",
            schema_version=graph.schema_version,
            object_id=graph.instance_id,
            value=graph.to_mapping(),
        )
        source_curves, source_points = (
            _sls2_source_curves(instance, generation)
            if instance_id == SLS2_INSTANCE_ID
            else _rf500_source_curves(instance)
        )
        bindings = _region_bindings(
            graph,
            source_curves=source_curves,
            family_profile_path=_repo_relative(root, profile_path),
            family_profile_raw_sha256=file_sha256(profile_path),
        )
        native_step = _native_step_artifact(instance)
        materialized = instance_id == SLS2_INSTANCE_ID
        baseline = BaselineContract(
            baseline_kind=(
                "frozen_step_and_source_native_profile"
                if materialized
                else "source_native_profile_with_unmaterialized_step"
            ),
            accepted_step_raw_sha256=native_step.raw_sha256,
            accepted_step_materialized=materialized,
        )
        request = CompileRequest(
            family_grammar=grammar,
            instance_graph=graph,
            family_grammar_ref=grammar_ref,
            instance_graph_ref=graph_ref,
            source_native_provenance=_source_native_provenance(instance, profile_ref),
            baseline=baseline,
            region_bindings=bindings,
            continuity_policy=_continuity_policy(graph),
        )
        cases.append(
            PreparedCompileCase(
                request=request,
                source_profile_points=source_points,
                baseline_step=baseline_step if materialized else None,
            )
        )
    return tuple(cases)


def _continuity_policy(graph: InstanceBoundaryGraph) -> BoundaryContinuityPolicy:
    """Declare RF-wall G1 defaults and reviewed RF500 sharp nose corners."""

    region_types = {item.region_id: item.region_type for item in graph.regions}
    overrides: list[ContinuityInterfaceOverride] = []
    for interface in graph.interfaces:
        pair = {
            region_types[interface.left_region_id],
            region_types[interface.right_region_id],
        }
        if pair == {"IrisRegion", "NoseRegion"}:
            overrides.append(
                ContinuityInterfaceOverride(
                    interface_id=interface.interface_id,
                    requirement=ContinuityRequirement("C0"),
                    intentional_corner=True,
                    rationale=(
                        "Reviewed RF500 iris-to-nose sharp transition is an "
                        "intentional geometric corner."
                    ),
                )
            )
    return default_boundary_continuity_policy(
        graph.family_id,
        overrides=tuple(overrides),
        policy_id=f"{graph.instance_id}.boundary_continuity_policy.v0",
    )


def _sls2_source_curves(
    instance: FamilyInstance, generation: Mapping[str, Any]
) -> tuple[tuple[_SourceCurve, ...], tuple[Point2D, ...]]:
    payload = instance.parameter_payload
    if payload.get("native_schema_version") != "literature_geometry_generation.v0":
        raise CompileContractError("SLS-2 native schema version changed")
    native = _mapping(payload.get("native_payload"), "SLS-2 native payload")
    expected = {"L", "R", "a", "b", "l", "r"}
    if set(native) != expected:
        raise CompileContractError("SLS-2 source-native six-parameter tuple changed")
    parameter_tuple = _mapping(generation.get("parameter_tuple"), "SLS-2 parameter tuple")
    values = _mapping(parameter_tuple.get("values"), "SLS-2 parameter values")
    if dict(values) != dict(native):
        raise CompileContractError("SLS-2 generation/profile native parameter mismatch")
    generation_profile = _mapping(generation.get("profile"), "SLS-2 generation profile")
    generator = _mapping(
        generation_profile.get("approximation"), "SLS-2 profile approximation"
    )
    sample_count = _integer(
        generator.get("samples_per_quarter"), "SLS-2 samples_per_quarter"
    )
    if sample_count < 5 or sample_count > 1001 or sample_count % 2 == 0:
        raise CompileContractError("SLS-2 samples_per_quarter must be odd and bounded")
    profile = build_sls2_profile(native, samples_per_quarter=sample_count)
    source_points = tuple(
        Point2D(z_mm=_number(item["z_mm"], "SLS-2 profile z"), r_mm=_number(item["r_mm"], "SLS-2 profile r"))
        for item in profile["points"]
    )
    length = _number(native["L"], "SLS-2 L")
    equator_radius = _number(native["R"], "SLS-2 R")
    upper_z = _number(native["a"], "SLS-2 a")
    upper_r = _number(native["b"], "SLS-2 b")
    beam_pipe_length = _number(native["l"], "SLS-2 l")
    half_cell = length / 2.0 - beam_pipe_length
    aperture = _number(native["r"], "SLS-2 r")
    lower_z = half_cell - upper_z
    lower_r = equator_radius - aperture - upper_r
    if min(
        length,
        equator_radius,
        upper_z,
        upper_r,
        beam_pipe_length,
        half_cell,
        aperture,
        lower_z,
        lower_r,
    ) <= 0.0:
        raise CompileContractError("SLS-2 source-native geometry is non-positive")
    center_r = equator_radius - upper_r
    curves = (
        _SourceCurve(
            "seg_beam_pipe_left",
            LineRepresentation(
                f"{instance.instance_id}.source.seg_beam_pipe_left",
                Point2D(-length / 2.0, aperture),
                Point2D(-half_cell, aperture),
            ),
        ),
        _SourceCurve(
            "seg_ellipse_left_lower",
            EllipseArcRepresentation(
                f"{instance.instance_id}.source.seg_ellipse_left_lower",
                center=Point2D(-half_cell, center_r),
                semi_axis_z_mm=lower_z,
                semi_axis_r_mm=lower_r,
                start_angle_rad=3.0 * math.pi / 2.0,
                end_angle_rad=2.0 * math.pi,
                sample_count=sample_count,
            ),
        ),
        _SourceCurve(
            "seg_ellipse_left_upper",
            EllipseArcRepresentation(
                f"{instance.instance_id}.source.seg_ellipse_left_upper",
                center=Point2D(0.0, center_r),
                semi_axis_z_mm=upper_z,
                semi_axis_r_mm=upper_r,
                start_angle_rad=math.pi,
                end_angle_rad=math.pi / 2.0,
                sample_count=sample_count,
            ),
        ),
        _SourceCurve(
            "seg_ellipse_right_upper",
            EllipseArcRepresentation(
                f"{instance.instance_id}.source.seg_ellipse_right_upper",
                center=Point2D(0.0, center_r),
                semi_axis_z_mm=upper_z,
                semi_axis_r_mm=upper_r,
                start_angle_rad=math.pi / 2.0,
                end_angle_rad=0.0,
                sample_count=sample_count,
            ),
        ),
        _SourceCurve(
            "seg_ellipse_right_lower",
            EllipseArcRepresentation(
                f"{instance.instance_id}.source.seg_ellipse_right_lower",
                center=Point2D(half_cell, center_r),
                semi_axis_z_mm=lower_z,
                semi_axis_r_mm=lower_r,
                start_angle_rad=math.pi,
                end_angle_rad=3.0 * math.pi / 2.0,
                sample_count=sample_count,
            ),
        ),
        _SourceCurve(
            "seg_beam_pipe_right",
            LineRepresentation(
                f"{instance.instance_id}.source.seg_beam_pipe_right",
                Point2D(half_cell, aperture),
                Point2D(length / 2.0, aperture),
            ),
        ),
    )
    return curves, source_points


def _rf500_source_curves(
    instance: FamilyInstance,
) -> tuple[tuple[_SourceCurve, ...], tuple[Point2D, ...]]:
    payload = instance.parameter_payload
    if payload.get("native_schema_version") != "parametric_geometry.v0":
        raise CompileContractError("RF500 native schema version changed")
    native = _mapping(payload.get("native_payload"), "RF500 native payload")
    profile = _mapping(native.get("profile"), "RF500 native profile")
    segments = _mapping_array(profile.get("segments"), "RF500 native segments")
    curves: list[_SourceCurve] = []
    source_points: list[Point2D] = []
    for segment in segments:
        source_ref = _string(segment.get("id"), "RF500 segment id")
        start = _native_point(segment.get("start"), f"{source_ref}.start")
        end = _native_point(segment.get("end"), f"{source_ref}.end")
        kind = _string(segment.get("kind"), f"{source_ref}.kind")
        curve = _mapping(segment.get("curve"), f"{source_ref}.curve")
        if kind == "line":
            representation: PrimitiveRepresentation = LineRepresentation(
                f"{instance.instance_id}.source.{source_ref}", start, end
            )
        elif kind == "arc":
            sampled = _native_points(segment.get("sampled_points"), f"{source_ref}.sampled_points")
            representation = CircularArcRepresentation(
                f"{instance.instance_id}.source.{source_ref}",
                center=_native_point(curve.get("center"), f"{source_ref}.center"),
                radius_mm=_number(curve.get("radius"), f"{source_ref}.radius"),
                start_angle_rad=_number(
                    curve.get("start_angle_rad"), f"{source_ref}.start_angle_rad"
                ),
                end_angle_rad=_number(
                    curve.get("end_angle_rad"), f"{source_ref}.end_angle_rad"
                ),
                sample_count=max(3, len(sampled)),
            )
        elif kind == "nurbs":
            fit_points = _native_points(
                segment.get("sampled_points"), f"{source_ref}.sampled_points"
            )
            control_points = _native_points(
                curve.get("control_points", []), f"{source_ref}.control_points"
            )
            if not control_points:
                raise CompileContractError(f"RF500 NURBS lacks source control points: {source_ref}")
            representation = SplineApproxRepresentation(
                f"{instance.instance_id}.source.{source_ref}",
                max_degree=_integer(curve.get("degree", 3), f"{source_ref}.degree"),
                fit_input_points=fit_points,
                source_control_point_hints=control_points,
                backend_input_source="source_control_point_hints",
            )
        else:
            raise CompileContractError(f"unsupported RF500 native segment kind: {kind}")
        curves.append(_SourceCurve(source_ref, representation))
        sampled = _native_points(segment.get("sampled_points", []), f"{source_ref}.sampled_points")
        points = list(sampled or (start, end))
        if source_points and source_points[-1].distance_to(points[0]) <= 1.0e-6:
            points = points[1:]
        source_points.extend(points)
    if not curves or len(source_points) < 2:
        raise CompileContractError("RF500 source-native profile is empty")
    return tuple(curves), tuple(source_points)


def _region_bindings(
    graph: InstanceBoundaryGraph,
    *,
    source_curves: tuple[_SourceCurve, ...],
    family_profile_path: str,
    family_profile_raw_sha256: str,
) -> tuple[RegionRepresentationBinding, ...]:
    source_ids = {item.source_segment_ref for item in source_curves}
    region_sources: dict[str, list[str]] = {}
    for region in graph.regions:
        refs = [value for value in region.source_feature_ids if value in source_ids]
        if not refs:
            raise CompileContractError(f"semantic region has no source-native segment: {region.region_id}")
        region_sources[region.region_id] = refs
    referenced = {value for values in region_sources.values() for value in values}
    if referenced != source_ids:
        raise CompileContractError(
            f"source-native segment coverage mismatch; missing={sorted(source_ids - referenced)}"
        )
    symmetry = next(
        (item for item in graph.landmarks if item.landmark_type == "SymmetryLandmark"),
        None,
    )
    component_plans: list[_ComponentPlan] = []
    for source_curve in source_curves:
        owners = [
            region.region_id
            for region in graph.regions
            if source_curve.source_segment_ref in region_sources[region.region_id]
        ]
        if not owners:
            raise CompileContractError(
                f"source-native segment has no semantic owner: {source_curve.source_segment_ref}"
            )
        if (
            len(owners) == 1
            and symmetry is not None
            and owners[0] in symmetry.incident_region_ids
            and source_curve.representation.start.z_mm < 0.0
            and source_curve.representation.end.z_mm > 0.0
        ):
            owners = [owners[0], owners[0]]
        part_count = len(owners)
        for index, owner in enumerate(owners):
            start_fraction = index / part_count
            end_fraction = (index + 1) / part_count
            native_samples = len(source_curve.representation.sample())
            sub_samples = max(2, round((native_samples - 1) / part_count) + 1)
            component_plans.append(
                _ComponentPlan(
                    region_id=owner,
                    source_segment_ref=source_curve.source_segment_ref,
                    source_interval=(start_fraction, end_fraction),
                    representation=trim_representation(
                        source_curve.representation,
                        start_fraction=start_fraction,
                        end_fraction=end_fraction,
                        representation_id=(
                            f"{graph.instance_id}.representation."
                            f"{source_curve.source_segment_ref}.{index:02d}"
                        ),
                        sample_count=sub_samples,
                    ),
                )
            )
    collapsed: list[str] = []
    for item in component_plans:
        if not collapsed or collapsed[-1] != item.region_id:
            collapsed.append(item.region_id)
    graph_order = [region.region_id for region in graph.regions]
    if collapsed != graph_order:
        raise CompileContractError(
            "source-native curve order does not realize the semantic graph order"
        )
    aperture_left = next(
        item.landmark_id
        for item in graph.landmarks
        if item.landmark_type == "AxialApertureLandmark" and item.side == "left"
    )
    aperture_right = next(
        item.landmark_id
        for item in graph.landmarks
        if item.landmark_type == "AxialApertureLandmark" and item.side == "right"
    )
    interface_by_pair = {
        (item.left_region_id, item.right_region_id): item.landmark_id
        for item in graph.interfaces
    }
    evidence = EvidenceRef(
        source_kind="family_profile",
        source_path=family_profile_path,
        source_raw_sha256=family_profile_raw_sha256,
        locator=f"#/instances[instance_id={graph.instance_id}]/parameter_payload/native_payload/profile",
        relation="binds_source_native_curve_to_region_representation",
    )
    values: list[RegionRepresentationBinding] = []
    for index, region in enumerate(graph.regions):
        plans = [item for item in component_plans if item.region_id == region.region_id]
        if not plans:
            raise CompileContractError(f"region has no component plan: {region.region_id}")
        start_landmark = (
            aperture_left
            if index == 0
            else interface_by_pair[(graph.regions[index - 1].region_id, region.region_id)]
        )
        end_landmark = (
            aperture_right
            if index == len(graph.regions) - 1
            else interface_by_pair[(region.region_id, graph.regions[index + 1].region_id)]
        )
        internal: list[str] = []
        for component_index, (left, right) in enumerate(zip(plans, plans[1:])):
            if (
                symmetry is not None
                and region.region_id in symmetry.incident_region_ids
                and left.representation.end.distance_to(right.representation.start) <= 1.0e-6
                and abs((left.representation.end.z_mm + right.representation.start.z_mm) / 2.0)
                <= 1.0e-6
            ):
                internal.append(symmetry.landmark_id)
            else:
                internal.append(
                    f"{graph.instance_id}.landmark.geometry_internal.{index:02d}.{component_index:02d}"
                )
        values.append(
            RegionRepresentationBinding(
                region_id=region.region_id,
                region_order=index,
                representation=CompositeRegionRepresentation(
                    representation_id=f"{region.region_id}.representation.v0",
                    components=tuple(item.representation for item in plans),
                ),
                source_native_segment_refs=tuple(item.source_segment_ref for item in plans),
                source_parameter_intervals=tuple(item.source_interval for item in plans),
                start_landmark_id=start_landmark,
                end_landmark_id=end_landmark,
                internal_landmark_ids=tuple(internal),
                evidence=tuple(region.evidence) + (evidence,),
            )
        )
    return tuple(values)


def _contract_ref(
    root: Path,
    path: Path,
    *,
    contract_kind: str,
    schema_version: str,
    object_id: str,
    value: object,
    canonicalizer: Any = canonical_sha256,
) -> ContractSourceRef:
    return ContractSourceRef(
        contract_kind=contract_kind,
        schema_version=schema_version,
        object_id=object_id,
        canonical_sha256=canonicalizer(value),
        source=EvidenceRef(
            source_kind=contract_kind,
            source_path=_repo_relative(root, path),
            source_raw_sha256=file_sha256(path),
            locator="#/",
            relation="compile_input_contract",
        ),
    )


def _source_native_provenance(
    instance: FamilyInstance, profile_ref: ContractSourceRef
) -> SourceNativeProvenance:
    payload = instance.parameter_payload
    artifacts = tuple(
        NativeArtifactRef(
            role=_string(item.get("role"), "geometry artifact role"),
            bundle_relative_path=_string(
                item.get("bundle_relative_path"), "geometry artifact path"
            ).replace("\\", "/"),
            raw_sha256=_string(
                item.get("raw_sha256") or item.get("source_file_sha256"),
                "geometry artifact raw hash",
            ).lower(),
        )
        for item in instance.geometry_artifacts
    )
    return SourceNativeProvenance(
        family_profile=profile_ref,
        adapter_id=_string(payload.get("adapter_id"), "native adapter_id"),
        native_schema_version=_string(
            payload.get("native_schema_version"), "native schema version"
        ),
        native_payload_locator=_string(
            payload.get("native_payload_locator"), "native payload locator"
        ),
        native_payload_canonical_sha256=_string(
            payload.get("native_payload_canonical_sha256"), "native payload hash"
        ).lower(),
        native_artifacts=artifacts,
    )


def _native_step_artifact(instance: FamilyInstance) -> NativeArtifactRef:
    candidates = [
        item
        for item in instance.geometry_artifacts
        if item.get("role") in {"rf_vacuum_geometry", "rf_vacuum_step"}
    ]
    if len(candidates) != 1:
        raise CompileContractError("instance requires exactly one accepted RF-vacuum STEP binding")
    item = candidates[0]
    return NativeArtifactRef(
        role=_string(item.get("role"), "native STEP role"),
        bundle_relative_path=_string(
            item.get("bundle_relative_path"), "native STEP path"
        ).replace("\\", "/"),
        raw_sha256=_string(
            item.get("raw_sha256") or item.get("source_file_sha256"),
            "native STEP raw hash",
        ).lower(),
    )


def _verify_sls2_sources(
    *,
    root: Path,
    instance: FamilyInstance,
    generation_path: Path,
    generation: Mapping[str, Any],
    baseline_step: Path,
) -> None:
    artifacts = {
        _string(item.get("role"), "SLS-2 artifact role"): item
        for item in instance.geometry_artifacts
    }
    generation_artifact = artifacts.get("geometry_generation_record")
    step_artifact = artifacts.get("rf_vacuum_geometry")
    if generation_artifact is None or step_artifact is None:
        raise CompileContractError("SLS-2 Stage C source bindings are incomplete")
    if file_sha256(generation_path) != _string(
        generation_artifact.get("raw_sha256"), "SLS-2 generation raw hash"
    ).lower():
        raise CompileContractError("SLS-2 generation raw hash mismatch")
    if file_sha256(baseline_step) != _string(
        step_artifact.get("raw_sha256"), "SLS-2 STEP raw hash"
    ).lower():
        raise CompileContractError("SLS-2 baseline STEP raw hash mismatch")
    if generation.get("schema_version") is None:
        raise CompileContractError("SLS-2 generation schema is missing")


def _inside(root: Path, value: Path, label: str) -> Path:
    path = value if value.is_absolute() else root / value
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CompileContractError(f"{label} must be inside the repository") from exc
    if not resolved.is_file():
        raise CompileContractError(f"{label} does not exist: {resolved}")
    return resolved


def _repo_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompileContractError(f"cannot read JSON source: {path}") from exc
    return _mapping(value, f"JSON source {path.name}")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _native_point(value: object, path: str) -> Point2D:
    mapping = _mapping(value, path)
    return Point2D(
        z_mm=_number(mapping.get("z"), f"{path}.z"),
        r_mm=_number(mapping.get("r"), f"{path}.r"),
    )


def _native_points(value: object, path: str) -> tuple[Point2D, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CompileContractError(f"{path} must be an array")
    return tuple(_native_point(item, f"{path}[]") for item in value)


def _mapping_array(value: object, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise CompileContractError(f"{path} must be an array")
    return [_mapping(item, f"{path}[]") for item in value]


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompileContractError(f"{path} must be an object")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompileContractError(f"{path} must be a non-empty string")
    return value


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CompileContractError(f"{path} must be an integer")
    return value


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CompileContractError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise CompileContractError(f"{path} must be finite")
    return result


__all__ = [
    "PreparedCompileCase",
    "R2SourceSet",
    "prepare_r2_cases",
]
