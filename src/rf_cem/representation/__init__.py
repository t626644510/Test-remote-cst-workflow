"""Family-agnostic mathematical boundary-representation layer."""

from .core import (
    BOUNDARY_REPRESENTATION_SCHEMA_VERSION,
    BoundaryRepresentation,
    CircularArcRepresentation,
    CompositeRegionRepresentation,
    DEFAULT_JOIN_TOLERANCE_MM,
    EllipseArcRepresentation,
    GEOMETRY_PATCH_SCHEMA_VERSION,
    GeometryPatch,
    LineRepresentation,
    Point2D,
    PrimitiveRepresentation,
    REGION_GEOMETRY_SCHEMA_VERSION,
    RegionGeometry,
    Representation,
    RepresentationContractError,
    SplineNurbsRepresentation,
    representation_from_mapping,
    trim_representation,
)

ARCHITECTURE_LAYER = "representation"

__all__ = [
    "ARCHITECTURE_LAYER",
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
