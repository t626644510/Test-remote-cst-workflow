"""Representation-independent R4 shape observer for compiled RF boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from rf_cem.compiler import CompileRecord, load_compile_record
from rf_cem.representation import Point2D, RegionGeometry
from rf_cem.semantic import InstanceBoundaryGraph
from rf_cem.semantic.contracts import canonical_sha256, file_sha256

from .common import ObservationContractError, non_negative, number, positive, string
from .contracts import (
    ExactGeometryReference,
    GeometryArtifactIdentity,
    LandmarkObservation,
    MonotonicInterval,
    RegionShapeObservation,
    SemanticShapeObservation,
    ShapeSample,
)


SHAPE_OBSERVER_VERSION = "rf_cem.semantic_arc_observer.v0"
DEFAULT_SAMPLES_PER_REGION = 65
_POINT_TOLERANCE_MM = 1.0e-10
_REGION_JOIN_TOLERANCE_MM = 1.0e-6
_CURVATURE_ZERO_PER_MM = 1.0e-12


@dataclass(frozen=True)
class RegionCurveInput:
    """Semantic metadata plus an ordered, generic finite curve trace.

    This is the observer's representation-neutral input seam.  Compiler
    adapters may create it from any concrete representation; no native
    parameter name is exposed to the observer.
    """

    region_id: str
    region_order: int
    region_type: str
    side: str
    motif_id: str | None
    start_landmark_id: str
    end_landmark_id: str
    points: tuple[Point2D, ...]
    start_tangent: tuple[float, float]
    end_tangent: tuple[float, float]
    start_curvature_per_mm: float
    end_curvature_per_mm: float

    def __post_init__(self) -> None:
        string(self.region_id, "region_curve.region_id")
        if not isinstance(self.region_order, int) or isinstance(self.region_order, bool):
            raise ObservationContractError("region curve order must be an integer")
        if self.region_order < 0:
            raise ObservationContractError("region curve order must be non-negative")
        string(self.region_type, "region_curve.region_type")
        if self.side not in {"left", "center", "right"}:
            raise ObservationContractError("unsupported region curve side")
        if self.motif_id is not None:
            string(self.motif_id, "region_curve.motif_id")
        string(self.start_landmark_id, "region_curve.start_landmark_id")
        string(self.end_landmark_id, "region_curve.end_landmark_id")
        if self.start_landmark_id == self.end_landmark_id:
            raise ObservationContractError("region curve endpoints require distinct landmarks")
        if len(self.points) < 2:
            raise ObservationContractError("region curve requires at least two points")
        if any(not isinstance(item, Point2D) for item in self.points):
            raise ObservationContractError("region curve points must be Point2D values")
        if _trace_length(self.points) <= _POINT_TOLERANCE_MM:
            raise ObservationContractError("region curve cannot have zero length")
        _unit_vector(self.start_tangent, "region_curve.start_tangent")
        _unit_vector(self.end_tangent, "region_curve.end_tangent")
        non_negative(
            self.start_curvature_per_mm, "region_curve.start_curvature_per_mm"
        )
        non_negative(self.end_curvature_per_mm, "region_curve.end_curvature_per_mm")


def build_exact_geometry_reference(
    repo_root: Path,
    compile_record_path: Path,
    *,
    record: CompileRecord | None = None,
) -> ExactGeometryReference:
    """Bind an R2 record to its exact STEP/profile artifacts and verify hashes."""

    root = repo_root.resolve()
    record_path = _inside(root, compile_record_path, "compile record")
    loaded = load_compile_record(record_path) if record is None else record
    if record is not None:
        disk_record = load_compile_record(record_path)
        if disk_record != record:
            raise ObservationContractError("in-memory and on-disk compile records differ")
    if record_path.parent.name != "records":
        raise ObservationContractError(
            "compile record must be supplied from an immutable records directory"
        )
    bundle_root = record_path.parent.parent.resolve()
    artifacts: list[GeometryArtifactIdentity] = []
    for artifact in sorted(loaded.output_artifacts, key=lambda item: item.role):
        artifact_path = (bundle_root / artifact.path).resolve()
        try:
            artifact_path.relative_to(bundle_root)
        except ValueError as exc:
            raise ObservationContractError("compiled geometry artifact escapes its bundle") from exc
        if not artifact_path.is_file():
            raise ObservationContractError(
                f"compiled geometry artifact is missing: {artifact.path}"
            )
        if file_sha256(artifact_path) != artifact.raw_sha256:
            raise ObservationContractError(
                f"compiled geometry artifact hash mismatch: {artifact.path}"
            )
        if artifact_path.stat().st_size != artifact.size_bytes:
            raise ObservationContractError(
                f"compiled geometry artifact size mismatch: {artifact.path}"
            )
        artifacts.append(
            GeometryArtifactIdentity(
                role=artifact.role,
                bundle_relative_path=artifact.path,
                media_type=artifact.media_type,
                raw_sha256=artifact.raw_sha256,
                size_bytes=artifact.size_bytes,
            )
        )
    from rf_cem.semantic import EvidenceRef

    return ExactGeometryReference(
        family_id=loaded.family_id,
        instance_id=loaded.instance_id,
        compile_id=loaded.compile_id,
        compile_content_sha256=loaded.content_sha256,
        compiler_version=loaded.compiler_version,
        compile_record_source=EvidenceRef(
            source_kind="compile_record.v0",
            source_path=record_path.relative_to(root).as_posix(),
            source_raw_sha256=file_sha256(record_path),
            locator="#",
            relation="defines_exact_compiled_geometry",
            subject_raw_sha256=loaded.content_sha256,
        ),
        geometry_artifacts=tuple(artifacts),
    )


def observe_compiled_geometry(
    exact_geometry: ExactGeometryReference,
    record: CompileRecord,
    graph: InstanceBoundaryGraph,
    *,
    samples_per_region: int = DEFAULT_SAMPLES_PER_REGION,
) -> SemanticShapeObservation:
    """Observe one R2 compiled geometry without reading native parameter names."""

    _validate_compile_bindings(exact_geometry, record, graph)
    curves = region_curves_from_compiled(record.region_geometries, graph)
    landmarks = landmark_observations_from_compiled(record, graph)
    return observe_region_curves(
        family_id=record.family_id,
        instance_id=record.instance_id,
        exact_geometry=exact_geometry,
        region_curves=curves,
        landmarks=landmarks,
        samples_per_region=samples_per_region,
    )


def region_curves_from_compiled(
    region_geometries: tuple[RegionGeometry, ...],
    graph: InstanceBoundaryGraph,
) -> tuple[RegionCurveInput, ...]:
    """Adapt generic R2 representations into the observer's neutral trace seam."""

    semantic_regions = {item.region_id: item for item in graph.regions}
    if [item.owner_region_id for item in region_geometries] != [
        item.region_id for item in graph.regions
    ]:
        raise ObservationContractError(
            "compiled region order must exactly follow the semantic graph"
        )
    result: list[RegionCurveInput] = []
    for geometry in region_geometries:
        semantic = semantic_regions.get(geometry.owner_region_id)
        if semantic is None:
            raise ObservationContractError("compiled geometry has an unknown semantic owner")
        patches = geometry.patches
        if not patches:
            raise ObservationContractError("compiled region has no geometry patches")
        result.append(
            RegionCurveInput(
                region_id=semantic.region_id,
                region_order=geometry.region_order,
                region_type=semantic.region_type,
                side=semantic.side,
                motif_id=semantic.motif_id,
                start_landmark_id=patches[0].start_landmark_id,
                end_landmark_id=patches[-1].end_landmark_id,
                points=_deduplicate_points(geometry.representation.sample()),
                start_tangent=geometry.representation.start_tangent(),
                end_tangent=geometry.representation.end_tangent(),
                start_curvature_per_mm=geometry.representation.start_curvature_per_mm(),
                end_curvature_per_mm=geometry.representation.end_curvature_per_mm(),
            )
        )
    return tuple(result)


def landmark_observations_from_compiled(
    record: CompileRecord,
    graph: InstanceBoundaryGraph,
) -> tuple[LandmarkObservation, ...]:
    """Resolve every reviewed semantic landmark against compiled coordinates."""

    semantic_landmarks = {item.landmark_id: item for item in graph.landmarks}
    bindings = {item.landmark_id: item for item in record.landmark_bindings}
    if set(bindings) != set(semantic_landmarks):
        missing = sorted(set(semantic_landmarks) - set(bindings))
        extra = sorted(set(bindings) - set(semantic_landmarks))
        raise ObservationContractError(
            f"compiled/semantic landmark mismatch; missing={missing}, extra={extra}"
        )
    result = []
    for semantic in graph.landmarks:
        binding = bindings[semantic.landmark_id]
        if set(binding.incident_patch_ids) == set():
            raise ObservationContractError("landmark binding has no incident geometry")
        result.append(
            LandmarkObservation(
                landmark_id=semantic.landmark_id,
                landmark_type=semantic.landmark_type,
                side=semantic.side,
                z_mm=binding.point.z_mm,
                r_mm=binding.point.r_mm,
                incident_region_ids=semantic.incident_region_ids,
            )
        )
    return tuple(result)


def observe_region_curves(
    *,
    family_id: str,
    instance_id: str,
    exact_geometry: ExactGeometryReference,
    region_curves: tuple[RegionCurveInput, ...],
    landmarks: tuple[LandmarkObservation, ...],
    samples_per_region: int = DEFAULT_SAMPLES_PER_REGION,
) -> SemanticShapeObservation:
    """Create a normalized shape observation from representation-neutral curves."""

    if exact_geometry.family_id != family_id or exact_geometry.instance_id != instance_id:
        raise ObservationContractError("exact geometry and shape target identity mismatch")
    if not isinstance(samples_per_region, int) or isinstance(samples_per_region, bool):
        raise ObservationContractError("samples_per_region must be an integer")
    if samples_per_region < 3:
        raise ObservationContractError("samples_per_region must be at least three")
    if [item.region_order for item in region_curves] != list(range(len(region_curves))):
        raise ObservationContractError("region curve order must be contiguous")
    landmark_ids = {item.landmark_id for item in landmarks}
    for curve in region_curves:
        if curve.start_landmark_id not in landmark_ids or curve.end_landmark_id not in landmark_ids:
            raise ObservationContractError(
                f"region curve references invalid landmark: {curve.region_id}"
            )
    regions = tuple(
        _observe_region(curve, samples_per_region=samples_per_region)
        for curve in region_curves
    )
    for left, right in zip(regions, regions[1:]):
        if left.end_landmark_id != right.start_landmark_id:
            raise ObservationContractError("semantic region chain is not contiguous")
        if _sample_point(left.samples[-1]).distance_to(
            _sample_point(right.samples[0])
        ) > _REGION_JOIN_TOLERANCE_MM:
            raise ObservationContractError("observed region chain has a coordinate gap")
    return SemanticShapeObservation(
        family_id=family_id,
        instance_id=instance_id,
        exact_geometry_ref=exact_geometry.identity_ref(),
        algorithm_version=SHAPE_OBSERVER_VERSION,
        samples_per_region=samples_per_region,
        regions=regions,
        landmarks=landmarks,
    )


def _observe_region(
    curve: RegionCurveInput, *, samples_per_region: int
) -> RegionShapeObservation:
    points = _resample_by_arc_length(curve.points, samples_per_region)
    tangents = [_numeric_tangent(points, index) for index in range(len(points))]
    tangents[0] = curve.start_tangent
    tangents[-1] = curve.end_tangent
    curvatures = [_signed_curvature(points, index) for index in range(len(points))]
    start_sign = _sign(curvatures[1] if len(curvatures) > 2 else curvatures[0])
    end_sign = _sign(curvatures[-2] if len(curvatures) > 2 else curvatures[-1])
    curvatures[0] = start_sign * curve.start_curvature_per_mm
    curvatures[-1] = end_sign * curve.end_curvature_per_mm
    samples = tuple(
        ShapeSample(
            s_normalized=index / (len(points) - 1),
            z_mm=point.z_mm,
            r_mm=point.r_mm,
            tangent_z=tangent[0],
            tangent_r=tangent[1],
            normal_z=-tangent[1],
            normal_r=tangent[0],
            curvature_per_mm=curvature,
        )
        for index, (point, tangent, curvature) in enumerate(
            zip(points, tangents, curvatures)
        )
    )
    nonzero_curvatures = [
        abs(value) for value in curvatures if abs(value) > _CURVATURE_ZERO_PER_MM
    ]
    minimum_curvature_radius = (
        1.0 / max(nonzero_curvatures) if nonzero_curvatures else None
    )
    z_values = [point.z_mm for point in points]
    r_values = [point.r_mm for point in points]
    return RegionShapeObservation(
        region_id=curve.region_id,
        region_order=curve.region_order,
        region_type=curve.region_type,
        side=curve.side,
        motif_id=curve.motif_id,
        start_landmark_id=curve.start_landmark_id,
        end_landmark_id=curve.end_landmark_id,
        samples=samples,
        arc_length_mm=_trace_length(points),
        axial_extent_mm=max(z_values) - min(z_values),
        minimum_radius_mm=min(r_values),
        maximum_radius_mm=max(r_values),
        minimum_radius_of_curvature_mm=minimum_curvature_radius,
        curvature_status=("finite" if minimum_curvature_radius is not None else "unbounded_straight"),
        start_tangent=curve.start_tangent,
        end_tangent=curve.end_tangent,
        start_curvature_per_mm=curve.start_curvature_per_mm,
        end_curvature_per_mm=curve.end_curvature_per_mm,
        convexity=_convexity(curvatures),
        monotonic_intervals=(
            *_monotonic_intervals(z_values, "z"),
            *_monotonic_intervals(r_values, "r"),
        ),
    )


def _validate_compile_bindings(
    exact_geometry: ExactGeometryReference,
    record: CompileRecord,
    graph: InstanceBoundaryGraph,
) -> None:
    if (
        exact_geometry.family_id != record.family_id
        or exact_geometry.instance_id != record.instance_id
        or exact_geometry.compile_id != record.compile_id
        or exact_geometry.compile_content_sha256 != record.content_sha256
    ):
        raise ObservationContractError("exact geometry and compile record mismatch")
    if graph.family_id != record.family_id or graph.instance_id != record.instance_id:
        raise ObservationContractError("semantic graph and compile record mismatch")
    if record.instance_graph_ref.object_id != graph.instance_id:
        raise ObservationContractError("compile record graph object identity mismatch")
    if record.instance_graph_ref.canonical_sha256 != canonical_sha256(graph.to_mapping()):
        raise ObservationContractError("compile record graph content identity mismatch")
    if record.status != "pass":
        raise ObservationContractError("R4 observes only passing compiled geometry")
    if record.live_cst_status != "not_run":
        raise ObservationContractError("R4 observation must remain no-CST")


def _inside(root: Path, value: Path, label: str) -> Path:
    path = (value if value.is_absolute() else root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ObservationContractError(f"{label} must remain inside repository") from exc
    if not path.is_file():
        raise ObservationContractError(f"{label} is missing: {path}")
    return path


def _deduplicate_points(points: tuple[Point2D, ...]) -> tuple[Point2D, ...]:
    result: list[Point2D] = []
    for point in points:
        if not result or result[-1].distance_to(point) > _POINT_TOLERANCE_MM:
            result.append(point)
    if len(result) < 2:
        raise ObservationContractError("curve trace collapses after duplicate removal")
    return tuple(result)


def _trace_length(points: tuple[Point2D, ...]) -> float:
    return sum(left.distance_to(right) for left, right in zip(points, points[1:]))


def _resample_by_arc_length(
    points: tuple[Point2D, ...], sample_count: int
) -> tuple[Point2D, ...]:
    points = _deduplicate_points(points)
    lengths = [0.0]
    for left, right in zip(points, points[1:]):
        lengths.append(lengths[-1] + left.distance_to(right))
    total = positive(lengths[-1], "curve total arc length")
    result = []
    segment_index = 0
    for index in range(sample_count):
        target = total * index / (sample_count - 1)
        while segment_index < len(lengths) - 2 and target > lengths[segment_index + 1]:
            segment_index += 1
        left_length = lengths[segment_index]
        right_length = lengths[segment_index + 1]
        width = right_length - left_length
        fraction = 0.0 if width <= _POINT_TOLERANCE_MM else (target - left_length) / width
        left = points[segment_index]
        right = points[segment_index + 1]
        result.append(
            Point2D(
                z_mm=left.z_mm + fraction * (right.z_mm - left.z_mm),
                r_mm=left.r_mm + fraction * (right.r_mm - left.r_mm),
            )
        )
    result[0] = points[0]
    result[-1] = points[-1]
    return tuple(result)


def _numeric_tangent(points: tuple[Point2D, ...], index: int) -> tuple[float, float]:
    if index == 0:
        left, right = points[0], points[1]
    elif index == len(points) - 1:
        left, right = points[-2], points[-1]
    else:
        left, right = points[index - 1], points[index + 1]
    return _normalized(right.z_mm - left.z_mm, right.r_mm - left.r_mm)


def _signed_curvature(points: tuple[Point2D, ...], index: int) -> float:
    if index == 0 or index == len(points) - 1:
        return 0.0
    first, middle, last = points[index - 1], points[index], points[index + 1]
    first_length = first.distance_to(middle)
    second_length = middle.distance_to(last)
    diagonal = last.distance_to(first)
    denominator = first_length * second_length * diagonal
    if denominator <= _POINT_TOLERANCE_MM**3:
        return 0.0
    twice_signed_area = (
        (middle.z_mm - first.z_mm) * (last.r_mm - first.r_mm)
        - (middle.r_mm - first.r_mm) * (last.z_mm - first.z_mm)
    )
    return 2.0 * twice_signed_area / denominator


def _convexity(curvatures: list[float]) -> str:
    signs = {_sign(value) for value in curvatures if abs(value) > _CURVATURE_ZERO_PER_MM}
    if not signs:
        return "flat"
    if signs == {1.0}:
        return "positive"
    if signs == {-1.0}:
        return "negative"
    return "mixed"


def _monotonic_intervals(
    values: list[float], coordinate: str
) -> tuple[MonotonicInterval, ...]:
    directions = [_direction(right - left) for left, right in zip(values, values[1:])]
    result = []
    start = 0
    current = directions[0]
    for index, direction in enumerate(directions[1:], start=1):
        if direction != current:
            result.append(
                MonotonicInterval(
                    coordinate=coordinate,
                    start_s=start / (len(values) - 1),
                    end_s=index / (len(values) - 1),
                    direction=current,
                )
            )
            start = index
            current = direction
    result.append(
        MonotonicInterval(
            coordinate=coordinate,
            start_s=start / (len(values) - 1),
            end_s=1.0,
            direction=current,
        )
    )
    return tuple(result)


def _direction(delta: float) -> str:
    if delta > _POINT_TOLERANCE_MM:
        return "increasing"
    if delta < -_POINT_TOLERANCE_MM:
        return "decreasing"
    return "constant"


def _sign(value: float) -> float:
    return -1.0 if value < 0.0 else 1.0


def _normalized(z_value: float, r_value: float) -> tuple[float, float]:
    norm = math.hypot(z_value, r_value)
    if norm <= _POINT_TOLERANCE_MM:
        raise ObservationContractError("cannot normalize a zero direction")
    return (z_value / norm, r_value / norm)


def _unit_vector(value: tuple[float, float], path: str) -> None:
    if len(value) != 2:
        raise ObservationContractError(f"{path} must contain two components")
    first = number(value[0], f"{path}[0]")
    second = number(value[1], f"{path}[1]")
    if abs(math.hypot(first, second) - 1.0) > 1.0e-9:
        raise ObservationContractError(f"{path} must be a unit vector")


def _sample_point(sample: ShapeSample) -> Point2D:
    return Point2D(sample.z_mm, sample.r_mm)


__all__ = [
    "DEFAULT_SAMPLES_PER_REGION",
    "RegionCurveInput",
    "SHAPE_OBSERVER_VERSION",
    "build_exact_geometry_reference",
    "landmark_observations_from_compiled",
    "observe_compiled_geometry",
    "observe_region_curves",
    "region_curves_from_compiled",
]
