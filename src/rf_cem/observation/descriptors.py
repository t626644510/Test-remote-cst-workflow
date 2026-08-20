"""R4 scalar descriptor registry and deterministic axisymmetric extraction."""

from __future__ import annotations

import math

from rf_cem.semantic import EvidenceRef

from .common import ObservationContractError
from .contracts import (
    ObservationBundle,
    ScalarDescriptorDefinition,
    ScalarDescriptorRegistry,
    ScalarDescriptorValue,
    SemanticShapeObservation,
)


DESCRIPTOR_ALGORITHM_VERSION = "rf_cem.axisymmetric_shape_descriptors.v0"

GLOBAL_TOTAL_CAVITY_LENGTH = "global.total_cavity_length"
GLOBAL_MAXIMUM_RADIUS = "global.maximum_radius"
GLOBAL_MINIMUM_APERTURE_RADIUS = "global.minimum_aperture_radius"
GLOBAL_VACUUM_VOLUME = "global.vacuum_volume"
GLOBAL_SURFACE_AREA = "global.surface_area"
GLOBAL_SEMANTIC_REGION_COUNT = "global.semantic_region_count"
GLOBAL_NOSE_PRESENT = "global.nose_present"
GLOBAL_MINIMUM_RADIUS_OF_CURVATURE = "global.minimum_radius_of_curvature"
REGION_AXIAL_EXTENT = "region.axial_extent"
REGION_ARC_LENGTH = "region.arc_length"
REGION_MAXIMUM_RADIUS = "region.maximum_radius"
REGION_MINIMUM_RADIUS = "region.minimum_radius"
REGION_MINIMUM_RADIUS_OF_CURVATURE = "region.minimum_radius_of_curvature"
REGION_START_TANGENT_Z = "region.start_tangent_z"
REGION_START_TANGENT_R = "region.start_tangent_r"
REGION_END_TANGENT_Z = "region.end_tangent_z"
REGION_END_TANGENT_R = "region.end_tangent_r"
REGION_START_CURVATURE = "region.start_curvature"
REGION_END_CURVATURE = "region.end_curvature"
REGION_NOSE_TIP_RADIUS = "region.nose_tip_radius"
REGION_EQUATOR_CREST_RADIUS = "region.equator_crest_radius"

REQUIRED_DESCRIPTOR_IDS = frozenset(
    {
        GLOBAL_TOTAL_CAVITY_LENGTH,
        GLOBAL_MAXIMUM_RADIUS,
        GLOBAL_MINIMUM_APERTURE_RADIUS,
        GLOBAL_VACUUM_VOLUME,
        GLOBAL_SURFACE_AREA,
        GLOBAL_SEMANTIC_REGION_COUNT,
        GLOBAL_NOSE_PRESENT,
        GLOBAL_MINIMUM_RADIUS_OF_CURVATURE,
        REGION_AXIAL_EXTENT,
        REGION_ARC_LENGTH,
        REGION_MAXIMUM_RADIUS,
        REGION_MINIMUM_RADIUS,
        REGION_MINIMUM_RADIUS_OF_CURVATURE,
        REGION_START_TANGENT_Z,
        REGION_START_TANGENT_R,
        REGION_END_TANGENT_Z,
        REGION_END_TANGENT_R,
        REGION_START_CURVATURE,
        REGION_END_CURVATURE,
        REGION_NOSE_TIP_RADIUS,
        REGION_EQUATOR_CREST_RADIUS,
    }
)


def build_default_descriptor_registry(
    provenance: tuple[EvidenceRef, ...],
) -> ScalarDescriptorRegistry:
    """Build the first R4 registry with explicit units and algorithms."""

    definitions = (
        _definition(
            GLOBAL_TOTAL_CAVITY_LENGTH,
            "Total cavity length",
            "global",
            "continuous",
            "mm",
            "Axial span max(z)-min(z) of the normalized compiled RF-vacuum wall.",
            1.0e-6,
            provenance,
        ),
        _definition(
            GLOBAL_MAXIMUM_RADIUS,
            "Maximum radius",
            "global",
            "continuous",
            "mm",
            "Maximum radial coordinate over all normalized semantic-region samples.",
            1.0e-6,
            provenance,
        ),
        _definition(
            GLOBAL_MINIMUM_APERTURE_RADIUS,
            "Minimum aperture radius",
            "global",
            "continuous",
            "mm",
            "Minimum radius among semantic AxialApertureLandmark observations.",
            1.0e-6,
            provenance,
        ),
        _definition(
            GLOBAL_VACUUM_VOLUME,
            "Axisymmetric vacuum volume",
            "global",
            "continuous",
            "mm^3",
            "Signed conical-frustum integral pi*integral(r^2 dz) over the left-to-right normalized wall with implicit axis closure.",
            1.0e-2,
            provenance,
        ),
        _definition(
            GLOBAL_SURFACE_AREA,
            "Axisymmetric boundary surface area",
            "global",
            "continuous",
            "mm^2",
            "Surface of revolution of the normalized wall plus both planar aperture-to-axis closure disks.",
            1.0e-2,
            provenance,
        ),
        _definition(
            GLOBAL_SEMANTIC_REGION_COUNT,
            "Semantic region count",
            "global",
            "integer",
            "count",
            "Number of ordered semantic regions in the shape observation.",
            0.0,
            provenance,
        ),
        _definition(
            GLOBAL_NOSE_PRESENT,
            "Nose present",
            "global",
            "boolean",
            "bool",
            "True when at least one reviewed semantic region has type NoseRegion.",
            0.0,
            provenance,
        ),
        _definition(
            GLOBAL_MINIMUM_RADIUS_OF_CURVATURE,
            "Global minimum radius of curvature",
            "global",
            "continuous",
            "mm",
            "Minimum finite sampled radius of curvature across all curved semantic regions; straight regions are explicitly non-applicable.",
            1.0e-5,
            provenance,
        ),
        _definition(
            REGION_AXIAL_EXTENT,
            "Region axial extent",
            "semantic_region",
            "continuous",
            "mm",
            "Per-region axial span max(z)-min(z).",
            1.0e-6,
            provenance,
        ),
        _definition(
            REGION_ARC_LENGTH,
            "Region arc length",
            "semantic_region",
            "continuous",
            "mm",
            "Polyline arc length of the fixed normalized semantic-region samples.",
            1.0e-6,
            provenance,
        ),
        _definition(
            REGION_MAXIMUM_RADIUS,
            "Region maximum radius",
            "semantic_region",
            "continuous",
            "mm",
            "Maximum radial coordinate in one semantic region.",
            1.0e-6,
            provenance,
        ),
        _definition(
            REGION_MINIMUM_RADIUS,
            "Region minimum radius",
            "semantic_region",
            "continuous",
            "mm",
            "Minimum radial coordinate in one semantic region.",
            1.0e-6,
            provenance,
        ),
        _definition(
            REGION_MINIMUM_RADIUS_OF_CURVATURE,
            "Region minimum radius of curvature",
            "semantic_region",
            "continuous",
            "mm",
            "Inverse of the maximum non-zero absolute sampled curvature in one region; a fully straight region is explicitly non-applicable.",
            1.0e-5,
            provenance,
        ),
        _definition(
            REGION_START_TANGENT_Z,
            "Region start tangent z component",
            "semantic_region",
            "continuous",
            "1",
            "Z component of the oriented unit tangent at the region start landmark.",
            1.0e-9,
            provenance,
        ),
        _definition(
            REGION_START_TANGENT_R,
            "Region start tangent r component",
            "semantic_region",
            "continuous",
            "1",
            "R component of the oriented unit tangent at the region start landmark.",
            1.0e-9,
            provenance,
        ),
        _definition(
            REGION_END_TANGENT_Z,
            "Region end tangent z component",
            "semantic_region",
            "continuous",
            "1",
            "Z component of the oriented unit tangent at the region end landmark.",
            1.0e-9,
            provenance,
        ),
        _definition(
            REGION_END_TANGENT_R,
            "Region end tangent r component",
            "semantic_region",
            "continuous",
            "1",
            "R component of the oriented unit tangent at the region end landmark.",
            1.0e-9,
            provenance,
        ),
        _definition(
            REGION_START_CURVATURE,
            "Region start curvature",
            "semantic_region",
            "continuous",
            "1/mm",
            "Absolute oriented-curve curvature at the region start landmark.",
            1.0e-9,
            provenance,
        ),
        _definition(
            REGION_END_CURVATURE,
            "Region end curvature",
            "semantic_region",
            "continuous",
            "1/mm",
            "Absolute oriented-curve curvature at the region end landmark.",
            1.0e-9,
            provenance,
        ),
        _definition(
            REGION_NOSE_TIP_RADIUS,
            "Nose tip radius",
            "semantic_region",
            "continuous",
            "mm",
            "Local osculating radius at the minimum-r sampled point of a NoseRegion.",
            1.0e-5,
            provenance,
            applicable_region_types=("NoseRegion",),
        ),
        _definition(
            REGION_EQUATOR_CREST_RADIUS,
            "Equator crest radius",
            "semantic_region",
            "continuous",
            "mm",
            "Maximum radial coordinate in an EquatorRegion.",
            1.0e-6,
            provenance,
            applicable_region_types=("EquatorRegion",),
        ),
    )
    return ScalarDescriptorRegistry(tuple(sorted(definitions, key=lambda item: item.descriptor_id)))


def extract_scalar_descriptors(
    observation: SemanticShapeObservation,
    registry: ScalarDescriptorRegistry,
) -> tuple[ScalarDescriptorValue, ...]:
    """Evaluate the complete first R4 descriptor registry on one shape."""

    definitions = registry.by_id
    if set(definitions) != REQUIRED_DESCRIPTOR_IDS:
        missing = sorted(REQUIRED_DESCRIPTOR_IDS - set(definitions))
        extra = sorted(set(definitions) - REQUIRED_DESCRIPTOR_IDS)
        raise ObservationContractError(
            f"R4 descriptor registry mismatch; missing={missing}, extra={extra}"
        )
    profile = _global_profile(observation)
    z_values = [item[0] for item in profile]
    r_values = [item[1] for item in profile]
    aperture_radii = [
        item.r_mm
        for item in observation.landmarks
        if item.landmark_type == "AxialApertureLandmark"
    ]
    if len(aperture_radii) != 2:
        raise ObservationContractError(
            "minimum aperture descriptor requires exactly two axial aperture landmarks"
        )
    finite_curvature_radii = [
        item.minimum_radius_of_curvature_mm
        for item in observation.regions
        if item.minimum_radius_of_curvature_mm is not None
    ]
    if not finite_curvature_radii:
        raise ObservationContractError(
            "global curvature descriptor requires at least one curved region"
        )
    values: list[ScalarDescriptorValue] = []

    global_values: dict[str, float | int | bool] = {
        GLOBAL_TOTAL_CAVITY_LENGTH: max(z_values) - min(z_values),
        GLOBAL_MAXIMUM_RADIUS: max(r_values),
        GLOBAL_MINIMUM_APERTURE_RADIUS: min(aperture_radii),
        GLOBAL_VACUUM_VOLUME: _axisymmetric_volume(profile),
        GLOBAL_SURFACE_AREA: _axisymmetric_surface_area(profile),
        GLOBAL_SEMANTIC_REGION_COUNT: len(observation.regions),
        GLOBAL_NOSE_PRESENT: any(
            item.region_type == "NoseRegion" for item in observation.regions
        ),
        GLOBAL_MINIMUM_RADIUS_OF_CURVATURE: min(finite_curvature_radii),
    }
    for descriptor_id, value in global_values.items():
        values.append(
            _value(
                definitions[descriptor_id],
                observation=observation,
                scope_id=observation.instance_id,
                value=value,
            )
        )

    for region in observation.regions:
        regional_values: dict[str, float] = {
            REGION_AXIAL_EXTENT: region.axial_extent_mm,
            REGION_ARC_LENGTH: region.arc_length_mm,
            REGION_MAXIMUM_RADIUS: region.maximum_radius_mm,
            REGION_MINIMUM_RADIUS: region.minimum_radius_mm,
            REGION_START_TANGENT_Z: region.start_tangent[0],
            REGION_START_TANGENT_R: region.start_tangent[1],
            REGION_END_TANGENT_Z: region.end_tangent[0],
            REGION_END_TANGENT_R: region.end_tangent[1],
            REGION_START_CURVATURE: region.start_curvature_per_mm,
            REGION_END_CURVATURE: region.end_curvature_per_mm,
        }
        for descriptor_id, value in regional_values.items():
            values.append(
                _value(
                    definitions[descriptor_id],
                    observation=observation,
                    scope_id=region.region_id,
                    region_type=region.region_type,
                    side=region.side,
                    value=value,
                )
            )
        curvature_definition = definitions[REGION_MINIMUM_RADIUS_OF_CURVATURE]
        if region.minimum_radius_of_curvature_mm is None:
            values.append(
                _value(
                    curvature_definition,
                    observation=observation,
                    scope_id=region.region_id,
                    region_type=region.region_type,
                    side=region.side,
                    value=None,
                    not_applicable_reason="region is straight within observer curvature tolerance",
                )
            )
        else:
            values.append(
                _value(
                    curvature_definition,
                    observation=observation,
                    scope_id=region.region_id,
                    region_type=region.region_type,
                    side=region.side,
                    value=region.minimum_radius_of_curvature_mm,
                )
            )
        if region.region_type == "NoseRegion":
            tip_sample = min(region.samples, key=lambda item: (item.r_mm, item.s_normalized))
            curvature = abs(tip_sample.curvature_per_mm)
            if curvature <= 1.0e-12:
                values.append(
                    _value(
                        definitions[REGION_NOSE_TIP_RADIUS],
                        observation=observation,
                        scope_id=region.region_id,
                        region_type=region.region_type,
                        side=region.side,
                        value=None,
                        not_applicable_reason="nose minimum-r point has zero observed curvature",
                    )
                )
            else:
                values.append(
                    _value(
                        definitions[REGION_NOSE_TIP_RADIUS],
                        observation=observation,
                        scope_id=region.region_id,
                        region_type=region.region_type,
                        side=region.side,
                        value=1.0 / curvature,
                    )
                )
        if region.region_type == "EquatorRegion":
            values.append(
                _value(
                    definitions[REGION_EQUATOR_CREST_RADIUS],
                    observation=observation,
                    scope_id=region.region_id,
                    region_type=region.region_type,
                    side=region.side,
                    value=region.maximum_radius_mm,
                )
            )
    return tuple(sorted(values, key=lambda item: item.value_id))


def build_observation_bundle(
    exact_geometry_ref: object,
    observation: SemanticShapeObservation,
    registry: ScalarDescriptorRegistry,
) -> ObservationBundle:
    """Link separate exact, shape, and scalar layers into one R4 bundle."""

    if not hasattr(exact_geometry_ref, "identity_ref"):
        raise ObservationContractError("exact geometry object lacks an identity reference")
    exact_ref = exact_geometry_ref.identity_ref()
    if observation.exact_geometry_ref != exact_ref:
        raise ObservationContractError("shape observation exact geometry binding mismatch")
    return ObservationBundle(
        family_id=observation.family_id,
        instance_id=observation.instance_id,
        exact_geometry_ref=exact_ref,
        shape_observation_ref=observation.identity_ref(),
        descriptor_registry_ref=registry.identity_ref(),
        descriptor_values=extract_scalar_descriptors(observation, registry),
    )


def _definition(
    descriptor_id: str,
    label: str,
    scope_kind: str,
    value_kind: str,
    unit: str,
    definition: str,
    tolerance: float,
    provenance: tuple[EvidenceRef, ...],
    *,
    applicable_region_types: tuple[str, ...] = (),
) -> ScalarDescriptorDefinition:
    return ScalarDescriptorDefinition(
        descriptor_id=descriptor_id,
        label=label,
        scope_kind=scope_kind,
        value_kind=value_kind,
        unit=unit,
        definition=definition,
        algorithm_version=DESCRIPTOR_ALGORITHM_VERSION,
        equivalence_absolute_tolerance=tolerance,
        applicable_region_types=applicable_region_types,
        provenance=provenance,
    )


def _value(
    definition: ScalarDescriptorDefinition,
    *,
    observation: SemanticShapeObservation,
    scope_id: str,
    value: float | int | bool | None,
    region_type: str | None = None,
    side: str | None = None,
    not_applicable_reason: str | None = None,
) -> ScalarDescriptorValue:
    scope_kind = "global" if region_type is None else "semantic_region"
    if definition.scope_kind != scope_kind:
        raise ObservationContractError("descriptor definition/value scope mismatch")
    if definition.applicable_region_types and region_type not in definition.applicable_region_types:
        raise ObservationContractError("descriptor used outside applicable semantic region")
    return ScalarDescriptorValue(
        descriptor_id=definition.descriptor_id,
        descriptor_version=definition.descriptor_version,
        source_observation_id=observation.shape_observation_id,
        scope_kind=scope_kind,
        scope_id=scope_id,
        region_type=region_type,
        side=side,
        value_kind=definition.value_kind,
        unit=definition.unit,
        status="not_applicable" if value is None else "observed",
        value=value,
        not_applicable_reason=not_applicable_reason,
    )


def _global_profile(observation: SemanticShapeObservation) -> tuple[tuple[float, float], ...]:
    result: list[tuple[float, float]] = []
    for region in observation.regions:
        points = [(item.z_mm, item.r_mm) for item in region.samples]
        if result and points:
            gap = math.hypot(result[-1][0] - points[0][0], result[-1][1] - points[0][1])
            if gap > 1.0e-6:
                raise ObservationContractError("shape regions do not form one global profile")
            points = points[1:]
        result.extend(points)
    if len(result) < 2:
        raise ObservationContractError("global descriptor profile is empty")
    return tuple(result)


def _axisymmetric_volume(profile: tuple[tuple[float, float], ...]) -> float:
    value = sum(
        math.pi
        * (right_z - left_z)
        * (left_r * left_r + left_r * right_r + right_r * right_r)
        / 3.0
        for (left_z, left_r), (right_z, right_r) in zip(profile, profile[1:])
    )
    if not math.isfinite(value) or value <= 0.0:
        raise ObservationContractError(
            "axisymmetric volume must be finite and positive for left-to-right geometry"
        )
    return value


def _axisymmetric_surface_area(profile: tuple[tuple[float, float], ...]) -> float:
    wall = sum(
        math.pi
        * (left_r + right_r)
        * math.hypot(right_z - left_z, right_r - left_r)
        for (left_z, left_r), (right_z, right_r) in zip(profile, profile[1:])
    )
    closures = math.pi * (profile[0][1] ** 2 + profile[-1][1] ** 2)
    value = wall + closures
    if not math.isfinite(value) or value <= 0.0:
        raise ObservationContractError("axisymmetric surface area must be finite and positive")
    return value


__all__ = [
    "DESCRIPTOR_ALGORITHM_VERSION",
    "GLOBAL_MAXIMUM_RADIUS",
    "GLOBAL_MINIMUM_APERTURE_RADIUS",
    "GLOBAL_MINIMUM_RADIUS_OF_CURVATURE",
    "GLOBAL_NOSE_PRESENT",
    "GLOBAL_SEMANTIC_REGION_COUNT",
    "GLOBAL_SURFACE_AREA",
    "GLOBAL_TOTAL_CAVITY_LENGTH",
    "GLOBAL_VACUUM_VOLUME",
    "REGION_ARC_LENGTH",
    "REGION_AXIAL_EXTENT",
    "REGION_END_CURVATURE",
    "REGION_END_TANGENT_R",
    "REGION_END_TANGENT_Z",
    "REGION_EQUATOR_CREST_RADIUS",
    "REGION_MAXIMUM_RADIUS",
    "REGION_MINIMUM_RADIUS",
    "REGION_MINIMUM_RADIUS_OF_CURVATURE",
    "REGION_NOSE_TIP_RADIUS",
    "REGION_START_CURVATURE",
    "REGION_START_TANGENT_R",
    "REGION_START_TANGENT_Z",
    "REQUIRED_DESCRIPTOR_IDS",
    "build_default_descriptor_registry",
    "build_observation_bundle",
    "extract_scalar_descriptors",
]
