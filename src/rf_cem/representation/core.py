"""Family-independent mathematical boundary representations for RF-CEM R2.

The objects in this module describe oriented curves in the meridional ``z-r``
plane.  They deliberately contain no cavity-family or semantic-region types.
Semantic ownership is carried only as opaque string identifiers on compiled
patches, so the representation layer remains reusable outside RF-CEM families.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, ClassVar, Mapping, Protocol, Sequence, Union, runtime_checkable


BOUNDARY_REPRESENTATION_SCHEMA_VERSION = "boundary_representation.v0"
GEOMETRY_PATCH_SCHEMA_VERSION = "geometry_patch.v0"
REGION_GEOMETRY_SCHEMA_VERSION = "region_geometry.v0"
DEFAULT_JOIN_TOLERANCE_MM = 1.0e-6


class RepresentationContractError(ValueError):
    """Raised when a representation or ownership contract is invalid."""


@dataclass(frozen=True)
class Point2D:
    """One finite point in the axisymmetric meridional plane, in millimetres."""

    z_mm: float
    r_mm: float

    def __post_init__(self) -> None:
        _finite(self.z_mm, "point.z_mm")
        _finite(self.r_mm, "point.r_mm")
        if self.r_mm < 0.0:
            raise RepresentationContractError("point.r_mm must be non-negative")

    def to_mapping(self) -> dict[str, float]:
        return {"z_mm": float(self.z_mm), "r_mm": float(self.r_mm)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Point2D":
        mapping = _mapping(value, "point")
        _exact_keys(mapping, {"z_mm", "r_mm"}, "point")
        return cls(
            z_mm=_number(mapping["z_mm"], "point.z_mm"),
            r_mm=_number(mapping["r_mm"], "point.r_mm"),
        )

    def distance_to(self, other: "Point2D") -> float:
        return math.hypot(self.z_mm - other.z_mm, self.r_mm - other.r_mm)


@runtime_checkable
class BoundaryRepresentation(Protocol):
    """Protocol implemented by every oriented family-independent curve."""

    representation_id: str
    representation_type: ClassVar[str]

    @property
    def start(self) -> Point2D: ...

    @property
    def end(self) -> Point2D: ...

    @property
    def parameter_count(self) -> int: ...

    def sample(self) -> tuple[Point2D, ...]: ...

    def start_tangent(self) -> tuple[float, float]: ...

    def end_tangent(self) -> tuple[float, float]: ...

    def start_curvature_per_mm(self) -> float: ...

    def end_curvature_per_mm(self) -> float: ...

    def to_mapping(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class LineRepresentation:
    """An oriented straight line segment."""

    representation_type: ClassVar[str] = "Line"
    representation_id: str
    start_point: Point2D
    end_point: Point2D

    def __post_init__(self) -> None:
        _non_empty(self.representation_id, "line.representation_id")
        if self.start_point.distance_to(self.end_point) <= 1.0e-12:
            raise RepresentationContractError("line endpoints must be distinct")

    @property
    def start(self) -> Point2D:
        return self.start_point

    @property
    def end(self) -> Point2D:
        return self.end_point

    @property
    def parameter_count(self) -> int:
        return 4

    def sample(self) -> tuple[Point2D, ...]:
        return (self.start, self.end)

    def start_tangent(self) -> tuple[float, float]:
        return _unit(
            self.end.z_mm - self.start.z_mm,
            self.end.r_mm - self.start.r_mm,
            "line tangent",
        )

    def end_tangent(self) -> tuple[float, float]:
        return self.start_tangent()

    def start_curvature_per_mm(self) -> float:
        return 0.0

    def end_curvature_per_mm(self) -> float:
        return 0.0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": BOUNDARY_REPRESENTATION_SCHEMA_VERSION,
            "representation_type": self.representation_type,
            "representation_id": self.representation_id,
            "start": self.start.to_mapping(),
            "end": self.end.to_mapping(),
        }


@dataclass(frozen=True)
class CircularArcRepresentation:
    """An oriented circular arc parameterised by an angle interval."""

    representation_type: ClassVar[str] = "CircularArc"
    representation_id: str
    center: Point2D
    radius_mm: float
    start_angle_rad: float
    end_angle_rad: float
    sample_count: int = 12

    def __post_init__(self) -> None:
        _non_empty(self.representation_id, "circular_arc.representation_id")
        _positive(self.radius_mm, "circular_arc.radius_mm")
        _angle_interval(self.start_angle_rad, self.end_angle_rad, "circular_arc")
        _sample_count(self.sample_count, "circular_arc.sample_count")
        for point in (self.start, self.end):
            if point.r_mm < 0.0:
                raise RepresentationContractError("circular arc crosses negative radius")

    @property
    def start(self) -> Point2D:
        return self._point(self.start_angle_rad)

    @property
    def end(self) -> Point2D:
        return self._point(self.end_angle_rad)

    @property
    def parameter_count(self) -> int:
        return 5

    def _point(self, angle: float) -> Point2D:
        return Point2D(
            z_mm=self.center.z_mm + self.radius_mm * math.cos(angle),
            r_mm=self.center.r_mm + self.radius_mm * math.sin(angle),
        )

    def sample(self) -> tuple[Point2D, ...]:
        return tuple(
            self._point(_lerp(self.start_angle_rad, self.end_angle_rad, index / (self.sample_count - 1)))
            for index in range(self.sample_count)
        )

    def _tangent(self, angle: float) -> tuple[float, float]:
        direction = 1.0 if self.end_angle_rad > self.start_angle_rad else -1.0
        return _unit(
            direction * -self.radius_mm * math.sin(angle),
            direction * self.radius_mm * math.cos(angle),
            "circular arc tangent",
        )

    def start_tangent(self) -> tuple[float, float]:
        return self._tangent(self.start_angle_rad)

    def end_tangent(self) -> tuple[float, float]:
        return self._tangent(self.end_angle_rad)

    def start_curvature_per_mm(self) -> float:
        return 1.0 / self.radius_mm

    def end_curvature_per_mm(self) -> float:
        return 1.0 / self.radius_mm

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": BOUNDARY_REPRESENTATION_SCHEMA_VERSION,
            "representation_type": self.representation_type,
            "representation_id": self.representation_id,
            "center": self.center.to_mapping(),
            "radius_mm": float(self.radius_mm),
            "start_angle_rad": float(self.start_angle_rad),
            "end_angle_rad": float(self.end_angle_rad),
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class EllipseArcRepresentation:
    """An oriented exact ellipse arc in the meridional plane."""

    representation_type: ClassVar[str] = "EllipseArc"
    representation_id: str
    center: Point2D
    semi_axis_z_mm: float
    semi_axis_r_mm: float
    start_angle_rad: float
    end_angle_rad: float
    sample_count: int = 13

    def __post_init__(self) -> None:
        _non_empty(self.representation_id, "ellipse_arc.representation_id")
        _positive(self.semi_axis_z_mm, "ellipse_arc.semi_axis_z_mm")
        _positive(self.semi_axis_r_mm, "ellipse_arc.semi_axis_r_mm")
        _angle_interval(self.start_angle_rad, self.end_angle_rad, "ellipse_arc")
        _sample_count(self.sample_count, "ellipse_arc.sample_count")
        if min(point.r_mm for point in self.sample()) < 0.0:
            raise RepresentationContractError("ellipse arc crosses negative radius")

    @property
    def start(self) -> Point2D:
        return self._point(self.start_angle_rad)

    @property
    def end(self) -> Point2D:
        return self._point(self.end_angle_rad)

    @property
    def parameter_count(self) -> int:
        return 6

    def _point(self, angle: float) -> Point2D:
        return Point2D(
            z_mm=self.center.z_mm + self.semi_axis_z_mm * math.cos(angle),
            r_mm=self.center.r_mm + self.semi_axis_r_mm * math.sin(angle),
        )

    def sample(self) -> tuple[Point2D, ...]:
        return tuple(
            self._point(_lerp(self.start_angle_rad, self.end_angle_rad, index / (self.sample_count - 1)))
            for index in range(self.sample_count)
        )

    def _tangent(self, angle: float) -> tuple[float, float]:
        direction = 1.0 if self.end_angle_rad > self.start_angle_rad else -1.0
        return _unit(
            direction * -self.semi_axis_z_mm * math.sin(angle),
            direction * self.semi_axis_r_mm * math.cos(angle),
            "ellipse arc tangent",
        )

    def _curvature(self, angle: float) -> float:
        denominator = (
            self.semi_axis_z_mm**2 * math.sin(angle) ** 2
            + self.semi_axis_r_mm**2 * math.cos(angle) ** 2
        ) ** 1.5
        return self.semi_axis_z_mm * self.semi_axis_r_mm / denominator

    def start_tangent(self) -> tuple[float, float]:
        return self._tangent(self.start_angle_rad)

    def end_tangent(self) -> tuple[float, float]:
        return self._tangent(self.end_angle_rad)

    def start_curvature_per_mm(self) -> float:
        return self._curvature(self.start_angle_rad)

    def end_curvature_per_mm(self) -> float:
        return self._curvature(self.end_angle_rad)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": BOUNDARY_REPRESENTATION_SCHEMA_VERSION,
            "representation_type": self.representation_type,
            "representation_id": self.representation_id,
            "center": self.center.to_mapping(),
            "semi_axis_z_mm": float(self.semi_axis_z_mm),
            "semi_axis_r_mm": float(self.semi_axis_r_mm),
            "start_angle_rad": float(self.start_angle_rad),
            "end_angle_rad": float(self.end_angle_rad),
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class SplineNurbsRepresentation:
    """A source-native spline/NURBS fit contract.

    ``fit_points`` are the deterministic validation trace.  The explicit
    ``backend_point_source`` preserves whether the legacy CadQuery adapter used
    those fit points or the source control-point list; the two are never
    silently interchanged.
    """

    representation_type: ClassVar[str] = "SplineNURBS"
    representation_id: str
    degree: int
    fit_points: tuple[Point2D, ...]
    control_points: tuple[Point2D, ...] = ()
    backend_point_source: str = "fit_points"
    fitting_contract: str = "cadquery_spline_approximation.v0"
    approximation_tolerance_mm: float = 1.0e-3

    def __post_init__(self) -> None:
        _non_empty(self.representation_id, "spline.representation_id")
        if isinstance(self.degree, bool) or not isinstance(self.degree, int) or not 1 <= self.degree <= 5:
            raise RepresentationContractError("spline.degree must be an integer from 1 through 5")
        _point_sequence(self.fit_points, "spline.fit_points")
        if self.control_points:
            _point_sequence(self.control_points, "spline.control_points")
        if self.backend_point_source not in {"fit_points", "control_points"}:
            raise RepresentationContractError("unsupported spline backend_point_source")
        if self.backend_point_source == "control_points" and not self.control_points:
            raise RepresentationContractError("control-point spline source requires control_points")
        if self.fitting_contract != "cadquery_spline_approximation.v0":
            raise RepresentationContractError("unsupported spline fitting_contract")
        _positive(self.approximation_tolerance_mm, "spline.approximation_tolerance_mm")

    @property
    def start(self) -> Point2D:
        return self.fit_points[0]

    @property
    def end(self) -> Point2D:
        return self.fit_points[-1]

    @property
    def parameter_count(self) -> int:
        return 2 * len(self.fit_points) + 2 * len(self.control_points) + 2

    def sample(self) -> tuple[Point2D, ...]:
        return self.fit_points

    def start_tangent(self) -> tuple[float, float]:
        return _secant(self.fit_points[0], self.fit_points[1], "spline start tangent")

    def end_tangent(self) -> tuple[float, float]:
        return _secant(self.fit_points[-2], self.fit_points[-1], "spline end tangent")

    def start_curvature_per_mm(self) -> float:
        return _three_point_curvature(self.fit_points[:3])

    def end_curvature_per_mm(self) -> float:
        return _three_point_curvature(self.fit_points[-3:])

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": BOUNDARY_REPRESENTATION_SCHEMA_VERSION,
            "representation_type": self.representation_type,
            "representation_id": self.representation_id,
            "degree": self.degree,
            "fit_points": [point.to_mapping() for point in self.fit_points],
            "control_points": [point.to_mapping() for point in self.control_points],
            "backend_point_source": self.backend_point_source,
            "fitting_contract": self.fitting_contract,
            "approximation_tolerance_mm": float(self.approximation_tolerance_mm),
        }


PrimitiveRepresentation = Union[
    LineRepresentation,
    CircularArcRepresentation,
    EllipseArcRepresentation,
    SplineNurbsRepresentation,
]


@dataclass(frozen=True)
class CompositeRegionRepresentation:
    """An ordered 1..N collection of primitive representations for one region."""

    representation_type: ClassVar[str] = "CompositeRegionRepresentation"
    representation_id: str
    components: tuple[PrimitiveRepresentation, ...]
    join_tolerance_mm: float = DEFAULT_JOIN_TOLERANCE_MM

    def __post_init__(self) -> None:
        _non_empty(self.representation_id, "composite.representation_id")
        if not self.components:
            raise RepresentationContractError("composite requires at least one component")
        _positive(self.join_tolerance_mm, "composite.join_tolerance_mm")
        component_ids = [item.representation_id for item in self.components]
        if len(component_ids) != len(set(component_ids)):
            raise RepresentationContractError("composite component IDs must be unique")
        for left, right in zip(self.components, self.components[1:]):
            if left.end.distance_to(right.start) > self.join_tolerance_mm:
                raise RepresentationContractError(
                    f"composite components are not C0: {left.representation_id} -> {right.representation_id}"
                )

    @property
    def start(self) -> Point2D:
        return self.components[0].start

    @property
    def end(self) -> Point2D:
        return self.components[-1].end

    @property
    def parameter_count(self) -> int:
        return sum(item.parameter_count for item in self.components)

    def sample(self) -> tuple[Point2D, ...]:
        values: list[Point2D] = []
        for component in self.components:
            points = list(component.sample())
            if values and points and values[-1].distance_to(points[0]) <= self.join_tolerance_mm:
                points = points[1:]
            values.extend(points)
        return tuple(values)

    def start_tangent(self) -> tuple[float, float]:
        return self.components[0].start_tangent()

    def end_tangent(self) -> tuple[float, float]:
        return self.components[-1].end_tangent()

    def start_curvature_per_mm(self) -> float:
        return self.components[0].start_curvature_per_mm()

    def end_curvature_per_mm(self) -> float:
        return self.components[-1].end_curvature_per_mm()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": BOUNDARY_REPRESENTATION_SCHEMA_VERSION,
            "representation_type": self.representation_type,
            "representation_id": self.representation_id,
            "components": [item.to_mapping() for item in self.components],
            "join_tolerance_mm": float(self.join_tolerance_mm),
        }


@dataclass(frozen=True)
class GeometryPatch:
    """One oriented primitive curve patch with exactly one opaque owner ID."""

    patch_id: str
    owner_region_id: str
    region_order: int
    patch_order: int
    global_order: int
    representation: PrimitiveRepresentation
    start_landmark_id: str
    end_landmark_id: str
    source_native_segment_ref: str
    source_parameter_interval: tuple[float, float]
    orientation: str = "left_to_right"

    def __post_init__(self) -> None:
        for value, path in (
            (self.patch_id, "patch.patch_id"),
            (self.owner_region_id, "patch.owner_region_id"),
            (self.start_landmark_id, "patch.start_landmark_id"),
            (self.end_landmark_id, "patch.end_landmark_id"),
            (self.source_native_segment_ref, "patch.source_native_segment_ref"),
        ):
            _non_empty(value, path)
        for value, path in (
            (self.region_order, "patch.region_order"),
            (self.patch_order, "patch.patch_order"),
            (self.global_order, "patch.global_order"),
        ):
            _non_negative_integer(value, path)
        if self.orientation != "left_to_right":
            raise RepresentationContractError("patch orientation must be left_to_right")
        if self.start_landmark_id == self.end_landmark_id:
            raise RepresentationContractError("patch endpoints require distinct landmarks")
        start, end = self.source_parameter_interval
        _finite(start, "patch.source_parameter_interval[0]")
        _finite(end, "patch.source_parameter_interval[1]")
        if not 0.0 <= start < end <= 1.0:
            raise RepresentationContractError("patch source parameter interval must satisfy 0 <= start < end <= 1")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": GEOMETRY_PATCH_SCHEMA_VERSION,
            "patch_id": self.patch_id,
            "owner_region_id": self.owner_region_id,
            "region_order": self.region_order,
            "patch_order": self.patch_order,
            "global_order": self.global_order,
            "representation": self.representation.to_mapping(),
            "start_landmark_id": self.start_landmark_id,
            "end_landmark_id": self.end_landmark_id,
            "source_native_segment_ref": self.source_native_segment_ref,
            "source_parameter_interval": [
                float(self.source_parameter_interval[0]),
                float(self.source_parameter_interval[1]),
            ],
            "orientation": self.orientation,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GeometryPatch":
        mapping = _mapping(value, "patch")
        _exact_keys(
            mapping,
            {
                "schema_version",
                "patch_id",
                "owner_region_id",
                "region_order",
                "patch_order",
                "global_order",
                "representation",
                "start_landmark_id",
                "end_landmark_id",
                "source_native_segment_ref",
                "source_parameter_interval",
                "orientation",
            },
            "patch",
        )
        if mapping["schema_version"] != GEOMETRY_PATCH_SCHEMA_VERSION:
            raise RepresentationContractError("unsupported geometry patch schema")
        interval = _sequence(mapping["source_parameter_interval"], "patch.source_parameter_interval")
        if len(interval) != 2:
            raise RepresentationContractError("patch source parameter interval requires two values")
        representation = representation_from_mapping(_mapping(mapping["representation"], "patch.representation"))
        if isinstance(representation, CompositeRegionRepresentation):
            raise RepresentationContractError("one patch cannot contain a composite representation")
        return cls(
            patch_id=_string(mapping["patch_id"], "patch.patch_id"),
            owner_region_id=_string(mapping["owner_region_id"], "patch.owner_region_id"),
            region_order=_integer(mapping["region_order"], "patch.region_order"),
            patch_order=_integer(mapping["patch_order"], "patch.patch_order"),
            global_order=_integer(mapping["global_order"], "patch.global_order"),
            representation=representation,
            start_landmark_id=_string(mapping["start_landmark_id"], "patch.start_landmark_id"),
            end_landmark_id=_string(mapping["end_landmark_id"], "patch.end_landmark_id"),
            source_native_segment_ref=_string(
                mapping["source_native_segment_ref"], "patch.source_native_segment_ref"
            ),
            source_parameter_interval=(
                _number(interval[0], "patch.source_parameter_interval[0]"),
                _number(interval[1], "patch.source_parameter_interval[1]"),
            ),
            orientation=_string(mapping["orientation"], "patch.orientation"),
        )


@dataclass(frozen=True)
class RegionGeometry:
    """The unique compiled geometry owned by one opaque semantic-region ID."""

    region_geometry_id: str
    owner_region_id: str
    region_order: int
    representation: CompositeRegionRepresentation
    patches: tuple[GeometryPatch, ...]

    def __post_init__(self) -> None:
        _non_empty(self.region_geometry_id, "region_geometry.region_geometry_id")
        _non_empty(self.owner_region_id, "region_geometry.owner_region_id")
        _non_negative_integer(self.region_order, "region_geometry.region_order")
        if not self.patches:
            raise RepresentationContractError("RegionGeometry must own 1..N patches")
        if len(self.patches) != len(self.representation.components):
            raise RepresentationContractError("RegionGeometry patch/component cardinality mismatch")
        for index, (patch, component) in enumerate(zip(self.patches, self.representation.components)):
            if patch.owner_region_id != self.owner_region_id:
                raise RepresentationContractError("patch owner does not match RegionGeometry owner")
            if patch.region_order != self.region_order or patch.patch_order != index:
                raise RepresentationContractError("RegionGeometry patch order is not deterministic")
            if patch.representation.to_mapping() != component.to_mapping():
                raise RepresentationContractError("patch representation differs from composite component")

    @property
    def patch_count(self) -> int:
        return len(self.patches)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": REGION_GEOMETRY_SCHEMA_VERSION,
            "region_geometry_id": self.region_geometry_id,
            "owner_region_id": self.owner_region_id,
            "region_order": self.region_order,
            "representation": self.representation.to_mapping(),
            "patches": [patch.to_mapping() for patch in self.patches],
            "patch_count": self.patch_count,
            "parameter_count": self.representation.parameter_count,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RegionGeometry":
        mapping = _mapping(value, "region_geometry")
        _exact_keys(
            mapping,
            {
                "schema_version",
                "region_geometry_id",
                "owner_region_id",
                "region_order",
                "representation",
                "patches",
                "patch_count",
                "parameter_count",
            },
            "region_geometry",
        )
        if mapping["schema_version"] != REGION_GEOMETRY_SCHEMA_VERSION:
            raise RepresentationContractError("unsupported RegionGeometry schema")
        representation = representation_from_mapping(
            _mapping(mapping["representation"], "region_geometry.representation")
        )
        if not isinstance(representation, CompositeRegionRepresentation):
            raise RepresentationContractError("RegionGeometry requires a composite representation")
        patches = tuple(
            GeometryPatch.from_mapping(_mapping(item, "region_geometry.patch"))
            for item in _sequence(mapping["patches"], "region_geometry.patches")
        )
        result = cls(
            region_geometry_id=_string(
                mapping["region_geometry_id"], "region_geometry.region_geometry_id"
            ),
            owner_region_id=_string(mapping["owner_region_id"], "region_geometry.owner_region_id"),
            region_order=_integer(mapping["region_order"], "region_geometry.region_order"),
            representation=representation,
            patches=patches,
        )
        if mapping["patch_count"] != result.patch_count:
            raise RepresentationContractError("RegionGeometry patch_count mismatch")
        if mapping["parameter_count"] != result.representation.parameter_count:
            raise RepresentationContractError("RegionGeometry parameter_count mismatch")
        return result


Representation = Union[PrimitiveRepresentation, CompositeRegionRepresentation]


def representation_from_mapping(value: Mapping[str, Any]) -> Representation:
    """Parse one strict versioned representation mapping."""

    mapping = _mapping(value, "representation")
    if mapping.get("schema_version") != BOUNDARY_REPRESENTATION_SCHEMA_VERSION:
        raise RepresentationContractError("unsupported boundary representation schema")
    kind = _string(mapping.get("representation_type"), "representation.representation_type")
    representation_id = _string(mapping.get("representation_id"), "representation.representation_id")
    if kind == LineRepresentation.representation_type:
        _exact_keys(mapping, {"schema_version", "representation_type", "representation_id", "start", "end"}, "line")
        return LineRepresentation(
            representation_id=representation_id,
            start_point=Point2D.from_mapping(_mapping(mapping["start"], "line.start")),
            end_point=Point2D.from_mapping(_mapping(mapping["end"], "line.end")),
        )
    if kind == CircularArcRepresentation.representation_type:
        _exact_keys(
            mapping,
            {
                "schema_version",
                "representation_type",
                "representation_id",
                "center",
                "radius_mm",
                "start_angle_rad",
                "end_angle_rad",
                "sample_count",
            },
            "circular_arc",
        )
        return CircularArcRepresentation(
            representation_id=representation_id,
            center=Point2D.from_mapping(_mapping(mapping["center"], "circular_arc.center")),
            radius_mm=_number(mapping["radius_mm"], "circular_arc.radius_mm"),
            start_angle_rad=_number(mapping["start_angle_rad"], "circular_arc.start_angle_rad"),
            end_angle_rad=_number(mapping["end_angle_rad"], "circular_arc.end_angle_rad"),
            sample_count=_integer(mapping["sample_count"], "circular_arc.sample_count"),
        )
    if kind == EllipseArcRepresentation.representation_type:
        _exact_keys(
            mapping,
            {
                "schema_version",
                "representation_type",
                "representation_id",
                "center",
                "semi_axis_z_mm",
                "semi_axis_r_mm",
                "start_angle_rad",
                "end_angle_rad",
                "sample_count",
            },
            "ellipse_arc",
        )
        return EllipseArcRepresentation(
            representation_id=representation_id,
            center=Point2D.from_mapping(_mapping(mapping["center"], "ellipse_arc.center")),
            semi_axis_z_mm=_number(mapping["semi_axis_z_mm"], "ellipse_arc.semi_axis_z_mm"),
            semi_axis_r_mm=_number(mapping["semi_axis_r_mm"], "ellipse_arc.semi_axis_r_mm"),
            start_angle_rad=_number(mapping["start_angle_rad"], "ellipse_arc.start_angle_rad"),
            end_angle_rad=_number(mapping["end_angle_rad"], "ellipse_arc.end_angle_rad"),
            sample_count=_integer(mapping["sample_count"], "ellipse_arc.sample_count"),
        )
    if kind == SplineNurbsRepresentation.representation_type:
        _exact_keys(
            mapping,
            {
                "schema_version",
                "representation_type",
                "representation_id",
                "degree",
                "fit_points",
                "control_points",
                "backend_point_source",
                "fitting_contract",
                "approximation_tolerance_mm",
            },
            "spline",
        )
        return SplineNurbsRepresentation(
            representation_id=representation_id,
            degree=_integer(mapping["degree"], "spline.degree"),
            fit_points=_points(mapping["fit_points"], "spline.fit_points"),
            control_points=_points(mapping["control_points"], "spline.control_points"),
            backend_point_source=_string(
                mapping["backend_point_source"], "spline.backend_point_source"
            ),
            fitting_contract=_string(mapping["fitting_contract"], "spline.fitting_contract"),
            approximation_tolerance_mm=_number(
                mapping["approximation_tolerance_mm"], "spline.approximation_tolerance_mm"
            ),
        )
    if kind == CompositeRegionRepresentation.representation_type:
        _exact_keys(
            mapping,
            {
                "schema_version",
                "representation_type",
                "representation_id",
                "components",
                "join_tolerance_mm",
            },
            "composite",
        )
        components: list[PrimitiveRepresentation] = []
        for item in _sequence(mapping["components"], "composite.components"):
            parsed = representation_from_mapping(_mapping(item, "composite.component"))
            if isinstance(parsed, CompositeRegionRepresentation):
                raise RepresentationContractError("nested composite representations are not supported")
            components.append(parsed)
        return CompositeRegionRepresentation(
            representation_id=representation_id,
            components=tuple(components),
            join_tolerance_mm=_number(mapping["join_tolerance_mm"], "composite.join_tolerance_mm"),
        )
    raise RepresentationContractError(f"unsupported representation type: {kind}")


def trim_representation(
    representation: PrimitiveRepresentation,
    *,
    start_fraction: float,
    end_fraction: float,
    representation_id: str,
    sample_count: int | None = None,
) -> PrimitiveRepresentation:
    """Return an oriented sub-domain without introducing family semantics."""

    _non_empty(representation_id, "trim.representation_id")
    _finite(start_fraction, "trim.start_fraction")
    _finite(end_fraction, "trim.end_fraction")
    if not 0.0 <= start_fraction < end_fraction <= 1.0:
        raise RepresentationContractError("trim fractions must satisfy 0 <= start < end <= 1")
    if isinstance(representation, LineRepresentation):
        return LineRepresentation(
            representation_id=representation_id,
            start_point=_point_lerp(representation.start, representation.end, start_fraction),
            end_point=_point_lerp(representation.start, representation.end, end_fraction),
        )
    if isinstance(representation, CircularArcRepresentation):
        return CircularArcRepresentation(
            representation_id=representation_id,
            center=representation.center,
            radius_mm=representation.radius_mm,
            start_angle_rad=_lerp(
                representation.start_angle_rad, representation.end_angle_rad, start_fraction
            ),
            end_angle_rad=_lerp(
                representation.start_angle_rad, representation.end_angle_rad, end_fraction
            ),
            sample_count=sample_count or representation.sample_count,
        )
    if isinstance(representation, EllipseArcRepresentation):
        return EllipseArcRepresentation(
            representation_id=representation_id,
            center=representation.center,
            semi_axis_z_mm=representation.semi_axis_z_mm,
            semi_axis_r_mm=representation.semi_axis_r_mm,
            start_angle_rad=_lerp(
                representation.start_angle_rad, representation.end_angle_rad, start_fraction
            ),
            end_angle_rad=_lerp(
                representation.start_angle_rad, representation.end_angle_rad, end_fraction
            ),
            sample_count=sample_count or representation.sample_count,
        )
    fit_points = _trim_trace(representation.fit_points, start_fraction, end_fraction)
    return SplineNurbsRepresentation(
        representation_id=representation_id,
        degree=min(representation.degree, max(1, len(fit_points) - 1)),
        fit_points=fit_points,
        control_points=(),
        backend_point_source="fit_points",
        fitting_contract=representation.fitting_contract,
        approximation_tolerance_mm=representation.approximation_tolerance_mm,
    )


def _trim_trace(
    points: tuple[Point2D, ...], start_fraction: float, end_fraction: float
) -> tuple[Point2D, ...]:
    lengths = [0.0]
    for left, right in zip(points, points[1:]):
        lengths.append(lengths[-1] + left.distance_to(right))
    total = lengths[-1]
    if total <= 1.0e-12:
        raise RepresentationContractError("cannot trim a zero-length spline trace")
    start_length = start_fraction * total
    end_length = end_fraction * total
    result = [_point_at_length(points, lengths, start_length)]
    result.extend(point for point, length in zip(points[1:-1], lengths[1:-1]) if start_length < length < end_length)
    result.append(_point_at_length(points, lengths, end_length))
    return tuple(result)


def _point_at_length(
    points: tuple[Point2D, ...], lengths: list[float], target: float
) -> Point2D:
    for index, (left_length, right_length) in enumerate(zip(lengths, lengths[1:])):
        if target <= right_length or index == len(points) - 2:
            width = right_length - left_length
            fraction = 0.0 if width <= 1.0e-15 else (target - left_length) / width
            return _point_lerp(points[index], points[index + 1], fraction)
    return points[-1]


def _three_point_curvature(points: Sequence[Point2D]) -> float:
    if len(points) < 3:
        return 0.0
    a, b, c = points[0], points[1], points[2]
    ab = a.distance_to(b)
    bc = b.distance_to(c)
    ca = c.distance_to(a)
    denominator = ab * bc * ca
    if denominator <= 1.0e-15:
        return 0.0
    twice_area = abs(
        (b.z_mm - a.z_mm) * (c.r_mm - a.r_mm)
        - (b.r_mm - a.r_mm) * (c.z_mm - a.z_mm)
    )
    return 2.0 * twice_area / denominator


def _point_lerp(left: Point2D, right: Point2D, fraction: float) -> Point2D:
    return Point2D(
        z_mm=_lerp(left.z_mm, right.z_mm, fraction),
        r_mm=_lerp(left.r_mm, right.r_mm, fraction),
    )


def _lerp(left: float, right: float, fraction: float) -> float:
    return left + (right - left) * fraction


def _secant(left: Point2D, right: Point2D, path: str) -> tuple[float, float]:
    return _unit(right.z_mm - left.z_mm, right.r_mm - left.r_mm, path)


def _unit(z_value: float, r_value: float, path: str) -> tuple[float, float]:
    norm = math.hypot(z_value, r_value)
    if norm <= 1.0e-15:
        raise RepresentationContractError(f"{path} is undefined")
    return z_value / norm, r_value / norm


def _point_sequence(values: Sequence[Point2D], path: str) -> None:
    if len(values) < 2:
        raise RepresentationContractError(f"{path} must contain at least two points")
    if all(left.distance_to(right) <= 1.0e-12 for left, right in zip(values, values[1:])):
        raise RepresentationContractError(f"{path} is a zero-length trace")


def _points(value: object, path: str) -> tuple[Point2D, ...]:
    return tuple(
        Point2D.from_mapping(_mapping(item, f"{path}[]"))
        for item in _sequence(value, path)
    )


def _angle_interval(start: object, end: object, path: str) -> None:
    start_value = _number(start, f"{path}.start_angle_rad")
    end_value = _number(end, f"{path}.end_angle_rad")
    sweep = abs(end_value - start_value)
    if sweep <= 1.0e-12 or sweep > 2.0 * math.pi + 1.0e-12:
        raise RepresentationContractError(f"{path} angle interval must be non-zero and at most 2*pi")


def _sample_count(value: object, path: str) -> None:
    count = _integer(value, path)
    if count < 2 or count > 10_000:
        raise RepresentationContractError(f"{path} must be from 2 through 10000")


def _positive(value: object, path: str) -> None:
    if _number(value, path) <= 0.0:
        raise RepresentationContractError(f"{path} must be positive")


def _non_negative_integer(value: object, path: str) -> None:
    if _integer(value, path) < 0:
        raise RepresentationContractError(f"{path} must be non-negative")


def _finite(value: object, path: str) -> None:
    _number(value, path)


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RepresentationContractError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RepresentationContractError(f"{path} must be finite")
    return result


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RepresentationContractError(f"{path} must be an integer")
    return value


def _non_empty(value: object, path: str) -> str:
    result = _string(value, path)
    if not result.strip():
        raise RepresentationContractError(f"{path} must not be empty")
    return result


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise RepresentationContractError(f"{path} must be a string")
    return value


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RepresentationContractError(f"{path} must be an object")
    return value


def _sequence(value: object, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RepresentationContractError(f"{path} must be an array")
    return value


def _exact_keys(mapping: Mapping[str, Any], required: set[str], path: str) -> None:
    actual = set(mapping)
    if actual != required:
        missing = sorted(required - actual)
        unexpected = sorted(actual - required)
        raise RepresentationContractError(
            f"{path} keys mismatch; missing={missing}, unexpected={unexpected}"
        )


__all__ = [
    "BOUNDARY_REPRESENTATION_SCHEMA_VERSION",
    "BoundaryRepresentation",
    "CircularArcRepresentation",
    "CompositeRegionRepresentation",
    "DEFAULT_JOIN_TOLERANCE_MM",
    "EllipseArcRepresentation",
    "GEOMETRY_PATCH_SCHEMA_VERSION",
    "GeometryPatch",
    "LineRepresentation",
    "Point2D",
    "PrimitiveRepresentation",
    "REGION_GEOMETRY_SCHEMA_VERSION",
    "RegionGeometry",
    "Representation",
    "RepresentationContractError",
    "SplineNurbsRepresentation",
    "representation_from_mapping",
    "trim_representation",
]
