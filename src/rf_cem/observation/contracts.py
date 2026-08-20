"""Versioned, finite contracts for RF-CEM R4 geometry observations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Union

from rf_cem.semantic import EvidenceRef
from rf_cem.semantic.contracts import canonical_sha256

from .common import (
    ObservationContractError,
    boolean,
    exact_keys,
    integer,
    mapping,
    non_negative,
    non_negative_integer,
    normalized_hash,
    number,
    optional_string,
    positive,
    read_json_mapping,
    relative_path,
    sequence,
    string,
    string_tuple,
    unit,
)


EXACT_GEOMETRY_REFERENCE_SCHEMA_VERSION = "exact_geometry_reference.v0"
SEMANTIC_SHAPE_OBSERVATION_SCHEMA_VERSION = "semantic_shape_observation.v0"
SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION = "scalar_descriptor_registry.v0"
OBSERVATION_BUNDLE_SCHEMA_VERSION = "observation_bundle.v0"


@dataclass(frozen=True)
class ContractIdentityRef:
    """Portable identity of one separate R4 contract artifact."""

    contract_kind: str
    schema_version: str
    object_id: str
    content_sha256: str

    def __post_init__(self) -> None:
        string(self.contract_kind, "contract_ref.contract_kind")
        string(self.schema_version, "contract_ref.schema_version")
        string(self.object_id, "contract_ref.object_id")
        normalized_hash(self.content_sha256, "contract_ref.content_sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "contract_kind": self.contract_kind,
            "schema_version": self.schema_version,
            "object_id": self.object_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ContractIdentityRef":
        value = mapping(value, "contract_ref")
        exact_keys(
            value,
            {"contract_kind", "schema_version", "object_id", "content_sha256"},
            "contract_ref",
        )
        return cls(
            contract_kind=string(value["contract_kind"], "contract_ref.contract_kind"),
            schema_version=string(value["schema_version"], "contract_ref.schema_version"),
            object_id=string(value["object_id"], "contract_ref.object_id"),
            content_sha256=normalized_hash(
                value["content_sha256"], "contract_ref.content_sha256"
            ),
        )


@dataclass(frozen=True)
class GeometryArtifactIdentity:
    """Hash-bound exact compiler artifact used without copying its payload."""

    role: str
    bundle_relative_path: str
    media_type: str
    raw_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        string(self.role, "geometry_artifact.role")
        relative_path(
            self.bundle_relative_path, "geometry_artifact.bundle_relative_path"
        )
        string(self.media_type, "geometry_artifact.media_type")
        normalized_hash(self.raw_sha256, "geometry_artifact.raw_sha256")
        non_negative_integer(self.size_bytes, "geometry_artifact.size_bytes")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "bundle_relative_path": self.bundle_relative_path,
            "media_type": self.media_type,
            "raw_sha256": self.raw_sha256,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GeometryArtifactIdentity":
        value = mapping(value, "geometry_artifact")
        exact_keys(
            value,
            {
                "role",
                "bundle_relative_path",
                "media_type",
                "raw_sha256",
                "size_bytes",
            },
            "geometry_artifact",
        )
        return cls(
            role=string(value["role"], "geometry_artifact.role"),
            bundle_relative_path=relative_path(
                value["bundle_relative_path"],
                "geometry_artifact.bundle_relative_path",
            ),
            media_type=string(value["media_type"], "geometry_artifact.media_type"),
            raw_sha256=normalized_hash(
                value["raw_sha256"], "geometry_artifact.raw_sha256"
            ),
            size_bytes=non_negative_integer(
                value["size_bytes"], "geometry_artifact.size_bytes"
            ),
        )


@dataclass(frozen=True)
class ExactGeometryReference:
    """R4 layer 1: exact compiled geometry identity and provenance.

    This contract references the exact STEP and lossless compiled-profile
    artifacts.  It deliberately contains no sampled replacement geometry.
    """

    family_id: str
    instance_id: str
    compile_id: str
    compile_content_sha256: str
    compiler_version: str
    compile_record_source: EvidenceRef
    geometry_artifacts: tuple[GeometryArtifactIdentity, ...]
    coordinate_system: str = "axisymmetric_z_r"
    length_unit: str = "mm"
    exact_geometry_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        string(self.family_id, "exact_geometry.family_id")
        string(self.instance_id, "exact_geometry.instance_id")
        string(self.compile_id, "exact_geometry.compile_id")
        normalized_hash(
            self.compile_content_sha256, "exact_geometry.compile_content_sha256"
        )
        string(self.compiler_version, "exact_geometry.compiler_version")
        if self.coordinate_system != "axisymmetric_z_r":
            raise ObservationContractError("unsupported exact geometry coordinate system")
        if unit(self.length_unit, "exact_geometry.length_unit") != "mm":
            raise ObservationContractError("exact geometry length unit must be mm")
        roles = [item.role for item in self.geometry_artifacts]
        if len(roles) != len(set(roles)):
            raise ObservationContractError("exact geometry artifact roles must be unique")
        if set(roles) != {"compiled_rf_vacuum_step", "compiled_profile"}:
            raise ObservationContractError(
                "exact geometry requires compiled_rf_vacuum_step and compiled_profile artifacts"
            )
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.instance_id}.exact_geometry.{content[:16]}"
        _set_or_check_identity(self, content, expected_id, "exact geometry")

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": EXACT_GEOMETRY_REFERENCE_SCHEMA_VERSION,
            "family_id": self.family_id,
            "instance_id": self.instance_id,
            "compile_id": self.compile_id,
            "compile_content_sha256": self.compile_content_sha256,
            "compiler_version": self.compiler_version,
            "compile_record_source": self.compile_record_source.to_mapping(),
            "geometry_artifacts": [item.to_mapping() for item in self.geometry_artifacts],
            "coordinate_system": self.coordinate_system,
            "length_unit": self.length_unit,
            "sampled_geometry_replacement": False,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "exact_geometry_id": self.exact_geometry_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractIdentityRef:
        return ContractIdentityRef(
            "exact_geometry_reference",
            EXACT_GEOMETRY_REFERENCE_SCHEMA_VERSION,
            self.exact_geometry_id,
            self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExactGeometryReference":
        value = mapping(value, "exact_geometry")
        required = {
            "schema_version",
            "family_id",
            "instance_id",
            "compile_id",
            "compile_content_sha256",
            "compiler_version",
            "compile_record_source",
            "geometry_artifacts",
            "coordinate_system",
            "length_unit",
            "sampled_geometry_replacement",
            "exact_geometry_id",
            "content_sha256",
        }
        exact_keys(value, required, "exact_geometry")
        if value["schema_version"] != EXACT_GEOMETRY_REFERENCE_SCHEMA_VERSION:
            raise ObservationContractError("unsupported exact geometry schema")
        if value["sampled_geometry_replacement"] is not False:
            raise ObservationContractError(
                "semantic sampling cannot replace exact compiled geometry"
            )
        return cls(
            family_id=string(value["family_id"], "exact_geometry.family_id"),
            instance_id=string(value["instance_id"], "exact_geometry.instance_id"),
            compile_id=string(value["compile_id"], "exact_geometry.compile_id"),
            compile_content_sha256=normalized_hash(
                value["compile_content_sha256"],
                "exact_geometry.compile_content_sha256",
            ),
            compiler_version=string(
                value["compiler_version"], "exact_geometry.compiler_version"
            ),
            compile_record_source=EvidenceRef.from_mapping(
                mapping(value["compile_record_source"], "exact_geometry.compile_record_source")
            ),
            geometry_artifacts=tuple(
                GeometryArtifactIdentity.from_mapping(
                    mapping(item, "exact_geometry.geometry_artifact")
                )
                for item in sequence(
                    value["geometry_artifacts"], "exact_geometry.geometry_artifacts"
                )
            ),
            coordinate_system=string(
                value["coordinate_system"], "exact_geometry.coordinate_system"
            ),
            length_unit=unit(value["length_unit"], "exact_geometry.length_unit"),
            exact_geometry_id=string(
                value["exact_geometry_id"], "exact_geometry.exact_geometry_id"
            ),
            content_sha256=normalized_hash(
                value["content_sha256"], "exact_geometry.content_sha256"
            ),
        )


@dataclass(frozen=True)
class ShapeSample:
    """One finite point and differential observation on normalized arc length."""

    s_normalized: float
    z_mm: float
    r_mm: float
    tangent_z: float
    tangent_r: float
    normal_z: float
    normal_r: float
    curvature_per_mm: float

    def __post_init__(self) -> None:
        s_value = number(self.s_normalized, "shape_sample.s_normalized")
        if not 0.0 <= s_value <= 1.0:
            raise ObservationContractError("shape sample arc coordinate must be in [0, 1]")
        number(self.z_mm, "shape_sample.z_mm")
        if number(self.r_mm, "shape_sample.r_mm") < 0.0:
            raise ObservationContractError("shape sample radius must be non-negative")
        for value, path in (
            (self.tangent_z, "shape_sample.tangent_z"),
            (self.tangent_r, "shape_sample.tangent_r"),
            (self.normal_z, "shape_sample.normal_z"),
            (self.normal_r, "shape_sample.normal_r"),
            (self.curvature_per_mm, "shape_sample.curvature_per_mm"),
        ):
            number(value, path)
        tangent_norm = (self.tangent_z**2 + self.tangent_r**2) ** 0.5
        normal_norm = (self.normal_z**2 + self.normal_r**2) ** 0.5
        if abs(tangent_norm - 1.0) > 1.0e-9 or abs(normal_norm - 1.0) > 1.0e-9:
            raise ObservationContractError("shape sample tangent and normal must be unit vectors")
        if abs(self.tangent_z * self.normal_z + self.tangent_r * self.normal_r) > 1.0e-9:
            raise ObservationContractError("shape sample tangent and normal must be orthogonal")

    def to_mapping(self) -> dict[str, float]:
        return {
            "s_normalized": self.s_normalized,
            "z_mm": self.z_mm,
            "r_mm": self.r_mm,
            "tangent_z": self.tangent_z,
            "tangent_r": self.tangent_r,
            "normal_z": self.normal_z,
            "normal_r": self.normal_r,
            "curvature_per_mm": self.curvature_per_mm,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ShapeSample":
        value = mapping(value, "shape_sample")
        required = {
            "s_normalized",
            "z_mm",
            "r_mm",
            "tangent_z",
            "tangent_r",
            "normal_z",
            "normal_r",
            "curvature_per_mm",
        }
        exact_keys(value, required, "shape_sample")
        return cls(**{key: number(value[key], f"shape_sample.{key}") for key in required})


@dataclass(frozen=True)
class LandmarkObservation:
    """Semantic landmark resolved to one finite compiled coordinate."""

    landmark_id: str
    landmark_type: str
    side: str
    z_mm: float
    r_mm: float
    incident_region_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        string(self.landmark_id, "landmark_observation.landmark_id")
        string(self.landmark_type, "landmark_observation.landmark_type")
        if self.side not in {"left", "center", "right"}:
            raise ObservationContractError("unsupported landmark side")
        number(self.z_mm, "landmark_observation.z_mm")
        if number(self.r_mm, "landmark_observation.r_mm") < 0.0:
            raise ObservationContractError("landmark radius must be non-negative")
        if not self.incident_region_ids:
            raise ObservationContractError("landmark observation requires an incident region")
        if len(set(self.incident_region_ids)) != len(self.incident_region_ids):
            raise ObservationContractError("landmark incident region IDs must be unique")
        for region_id in self.incident_region_ids:
            string(region_id, "landmark_observation.incident_region_id")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "landmark_id": self.landmark_id,
            "landmark_type": self.landmark_type,
            "side": self.side,
            "z_mm": self.z_mm,
            "r_mm": self.r_mm,
            "incident_region_ids": list(self.incident_region_ids),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LandmarkObservation":
        value = mapping(value, "landmark_observation")
        exact_keys(
            value,
            {
                "landmark_id",
                "landmark_type",
                "side",
                "z_mm",
                "r_mm",
                "incident_region_ids",
            },
            "landmark_observation",
        )
        return cls(
            landmark_id=string(
                value["landmark_id"], "landmark_observation.landmark_id"
            ),
            landmark_type=string(
                value["landmark_type"], "landmark_observation.landmark_type"
            ),
            side=string(value["side"], "landmark_observation.side"),
            z_mm=number(value["z_mm"], "landmark_observation.z_mm"),
            r_mm=number(value["r_mm"], "landmark_observation.r_mm"),
            incident_region_ids=string_tuple(
                value["incident_region_ids"],
                "landmark_observation.incident_region_ids",
            ),
        )


@dataclass(frozen=True)
class MonotonicInterval:
    """Maximal sampled interval with one coordinate direction."""

    coordinate: str
    start_s: float
    end_s: float
    direction: str

    def __post_init__(self) -> None:
        if self.coordinate not in {"z", "r"}:
            raise ObservationContractError("monotonic coordinate must be z or r")
        start = number(self.start_s, "monotonic_interval.start_s")
        end = number(self.end_s, "monotonic_interval.end_s")
        if not 0.0 <= start < end <= 1.0:
            raise ObservationContractError("invalid monotonic interval bounds")
        if self.direction not in {"increasing", "decreasing", "constant"}:
            raise ObservationContractError("unsupported monotonic interval direction")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "coordinate": self.coordinate,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "direction": self.direction,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MonotonicInterval":
        value = mapping(value, "monotonic_interval")
        exact_keys(
            value,
            {"coordinate", "start_s", "end_s", "direction"},
            "monotonic_interval",
        )
        return cls(
            coordinate=string(value["coordinate"], "monotonic_interval.coordinate"),
            start_s=number(value["start_s"], "monotonic_interval.start_s"),
            end_s=number(value["end_s"], "monotonic_interval.end_s"),
            direction=string(value["direction"], "monotonic_interval.direction"),
        )


@dataclass(frozen=True)
class RegionShapeObservation:
    """R4 semantic-region curve sampled independently of native parameters."""

    region_id: str
    region_order: int
    region_type: str
    side: str
    motif_id: str | None
    start_landmark_id: str
    end_landmark_id: str
    samples: tuple[ShapeSample, ...]
    arc_length_mm: float
    axial_extent_mm: float
    minimum_radius_mm: float
    maximum_radius_mm: float
    minimum_radius_of_curvature_mm: float | None
    curvature_status: str
    start_tangent: tuple[float, float]
    end_tangent: tuple[float, float]
    start_curvature_per_mm: float
    end_curvature_per_mm: float
    convexity: str
    monotonic_intervals: tuple[MonotonicInterval, ...]

    def __post_init__(self) -> None:
        string(self.region_id, "region_observation.region_id")
        non_negative_integer(self.region_order, "region_observation.region_order")
        string(self.region_type, "region_observation.region_type")
        if self.side not in {"left", "center", "right"}:
            raise ObservationContractError("unsupported semantic region side")
        optional_string(self.motif_id, "region_observation.motif_id")
        string(self.start_landmark_id, "region_observation.start_landmark_id")
        string(self.end_landmark_id, "region_observation.end_landmark_id")
        if self.start_landmark_id == self.end_landmark_id:
            raise ObservationContractError("region endpoints require distinct landmarks")
        if len(self.samples) < 3:
            raise ObservationContractError("region shape requires at least three samples")
        coordinates = [item.s_normalized for item in self.samples]
        if coordinates[0] != 0.0 or coordinates[-1] != 1.0:
            raise ObservationContractError("region samples must include normalized endpoints")
        if any(right <= left for left, right in zip(coordinates, coordinates[1:])):
            raise ObservationContractError("region sample coordinates must increase strictly")
        positive(self.arc_length_mm, "region_observation.arc_length_mm")
        non_negative(self.axial_extent_mm, "region_observation.axial_extent_mm")
        minimum = non_negative(
            self.minimum_radius_mm, "region_observation.minimum_radius_mm"
        )
        maximum = non_negative(
            self.maximum_radius_mm, "region_observation.maximum_radius_mm"
        )
        if minimum > maximum:
            raise ObservationContractError("region minimum radius exceeds maximum")
        if self.curvature_status not in {"finite", "unbounded_straight"}:
            raise ObservationContractError("unsupported region curvature status")
        if self.minimum_radius_of_curvature_mm is None:
            if self.curvature_status != "unbounded_straight":
                raise ObservationContractError("missing curvature radius requires straight status")
        else:
            positive(
                self.minimum_radius_of_curvature_mm,
                "region_observation.minimum_radius_of_curvature_mm",
            )
            if self.curvature_status != "finite":
                raise ObservationContractError("finite curvature radius requires finite status")
        _unit_vector(self.start_tangent, "region_observation.start_tangent")
        _unit_vector(self.end_tangent, "region_observation.end_tangent")
        non_negative(
            self.start_curvature_per_mm,
            "region_observation.start_curvature_per_mm",
        )
        non_negative(
            self.end_curvature_per_mm,
            "region_observation.end_curvature_per_mm",
        )
        if self.convexity not in {"positive", "negative", "flat", "mixed"}:
            raise ObservationContractError("unsupported convexity classification")
        if not self.monotonic_intervals:
            raise ObservationContractError("region observation requires monotonic intervals")
        for coordinate in ("z", "r"):
            intervals = [
                item for item in self.monotonic_intervals if item.coordinate == coordinate
            ]
            if not intervals or intervals[0].start_s != 0.0 or intervals[-1].end_s != 1.0:
                raise ObservationContractError(
                    f"region {coordinate} monotonic intervals must cover [0, 1]"
                )
            if any(
                abs(left.end_s - right.start_s) > 1.0e-12
                for left, right in zip(intervals, intervals[1:])
            ):
                raise ObservationContractError("monotonic intervals must be contiguous")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "region_order": self.region_order,
            "region_type": self.region_type,
            "side": self.side,
            "motif_id": self.motif_id,
            "start_landmark_id": self.start_landmark_id,
            "end_landmark_id": self.end_landmark_id,
            "samples": [item.to_mapping() for item in self.samples],
            "sample_count": len(self.samples),
            "arc_length_mm": self.arc_length_mm,
            "axial_extent_mm": self.axial_extent_mm,
            "minimum_radius_mm": self.minimum_radius_mm,
            "maximum_radius_mm": self.maximum_radius_mm,
            "minimum_radius_of_curvature_mm": self.minimum_radius_of_curvature_mm,
            "curvature_status": self.curvature_status,
            "start_tangent": list(self.start_tangent),
            "end_tangent": list(self.end_tangent),
            "start_curvature_per_mm": self.start_curvature_per_mm,
            "end_curvature_per_mm": self.end_curvature_per_mm,
            "convexity": self.convexity,
            "monotonic_intervals": [
                item.to_mapping() for item in self.monotonic_intervals
            ],
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RegionShapeObservation":
        value = mapping(value, "region_observation")
        required = {
            "region_id",
            "region_order",
            "region_type",
            "side",
            "motif_id",
            "start_landmark_id",
            "end_landmark_id",
            "samples",
            "sample_count",
            "arc_length_mm",
            "axial_extent_mm",
            "minimum_radius_mm",
            "maximum_radius_mm",
            "minimum_radius_of_curvature_mm",
            "curvature_status",
            "start_tangent",
            "end_tangent",
            "start_curvature_per_mm",
            "end_curvature_per_mm",
            "convexity",
            "monotonic_intervals",
        }
        exact_keys(value, required, "region_observation")
        samples = tuple(
            ShapeSample.from_mapping(mapping(item, "region_observation.sample"))
            for item in sequence(value["samples"], "region_observation.samples")
        )
        if integer(value["sample_count"], "region_observation.sample_count") != len(samples):
            raise ObservationContractError("region observation sample_count mismatch")
        curvature_radius = value["minimum_radius_of_curvature_mm"]
        return cls(
            region_id=string(value["region_id"], "region_observation.region_id"),
            region_order=non_negative_integer(
                value["region_order"], "region_observation.region_order"
            ),
            region_type=string(
                value["region_type"], "region_observation.region_type"
            ),
            side=string(value["side"], "region_observation.side"),
            motif_id=optional_string(value["motif_id"], "region_observation.motif_id"),
            start_landmark_id=string(
                value["start_landmark_id"], "region_observation.start_landmark_id"
            ),
            end_landmark_id=string(
                value["end_landmark_id"], "region_observation.end_landmark_id"
            ),
            samples=samples,
            arc_length_mm=positive(
                value["arc_length_mm"], "region_observation.arc_length_mm"
            ),
            axial_extent_mm=non_negative(
                value["axial_extent_mm"], "region_observation.axial_extent_mm"
            ),
            minimum_radius_mm=non_negative(
                value["minimum_radius_mm"], "region_observation.minimum_radius_mm"
            ),
            maximum_radius_mm=non_negative(
                value["maximum_radius_mm"], "region_observation.maximum_radius_mm"
            ),
            minimum_radius_of_curvature_mm=(
                positive(
                    curvature_radius,
                    "region_observation.minimum_radius_of_curvature_mm",
                )
                if curvature_radius is not None
                else None
            ),
            curvature_status=string(
                value["curvature_status"], "region_observation.curvature_status"
            ),
            start_tangent=_pair(value["start_tangent"], "region_observation.start_tangent"),
            end_tangent=_pair(value["end_tangent"], "region_observation.end_tangent"),
            start_curvature_per_mm=non_negative(
                value["start_curvature_per_mm"],
                "region_observation.start_curvature_per_mm",
            ),
            end_curvature_per_mm=non_negative(
                value["end_curvature_per_mm"],
                "region_observation.end_curvature_per_mm",
            ),
            convexity=string(value["convexity"], "region_observation.convexity"),
            monotonic_intervals=tuple(
                MonotonicInterval.from_mapping(
                    mapping(item, "region_observation.monotonic_interval")
                )
                for item in sequence(
                    value["monotonic_intervals"],
                    "region_observation.monotonic_intervals",
                )
            ),
        )


@dataclass(frozen=True)
class SemanticShapeObservation:
    """R4 layer 2: semantic-region shape observations from compiled curves."""

    family_id: str
    instance_id: str
    exact_geometry_ref: ContractIdentityRef
    algorithm_version: str
    samples_per_region: int
    regions: tuple[RegionShapeObservation, ...]
    landmarks: tuple[LandmarkObservation, ...]
    coordinate_system: str = "axisymmetric_z_r"
    length_unit: str = "mm"
    curvature_unit: str = "1/mm"
    observation_status: str = "pass_no_cst"
    shape_observation_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        string(self.family_id, "shape_observation.family_id")
        string(self.instance_id, "shape_observation.instance_id")
        if self.exact_geometry_ref.contract_kind != "exact_geometry_reference":
            raise ObservationContractError("shape observation requires exact geometry ref")
        if (
            self.exact_geometry_ref.schema_version
            != EXACT_GEOMETRY_REFERENCE_SCHEMA_VERSION
        ):
            raise ObservationContractError("shape observation exact geometry schema mismatch")
        string(self.algorithm_version, "shape_observation.algorithm_version")
        count = integer(self.samples_per_region, "shape_observation.samples_per_region")
        if count < 3:
            raise ObservationContractError("shape observer requires at least three samples")
        if self.coordinate_system != "axisymmetric_z_r":
            raise ObservationContractError("unsupported shape coordinate system")
        if unit(self.length_unit, "shape_observation.length_unit") != "mm":
            raise ObservationContractError("shape observation length unit must be mm")
        if unit(self.curvature_unit, "shape_observation.curvature_unit") != "1/mm":
            raise ObservationContractError("shape curvature unit must be 1/mm")
        if self.observation_status != "pass_no_cst":
            raise ObservationContractError("R4 shape observation must be pass_no_cst")
        if not self.regions or not self.landmarks:
            raise ObservationContractError("shape observation requires regions and landmarks")
        if [item.region_order for item in self.regions] != list(range(len(self.regions))):
            raise ObservationContractError("shape region order must be contiguous")
        region_ids = [item.region_id for item in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ObservationContractError("shape observation region IDs must be unique")
        if any(len(item.samples) != count for item in self.regions):
            raise ObservationContractError("all shape regions must use the declared sample count")
        landmark_ids = [item.landmark_id for item in self.landmarks]
        if len(landmark_ids) != len(set(landmark_ids)):
            raise ObservationContractError("shape observation landmark IDs must be unique")
        known_landmarks = set(landmark_ids)
        used_landmarks = {
            landmark_id
            for region in self.regions
            for landmark_id in (region.start_landmark_id, region.end_landmark_id)
        }
        if not used_landmarks.issubset(known_landmarks):
            raise ObservationContractError("shape region references an unknown landmark")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.instance_id}.shape_observation.{content[:16]}"
        _set_or_check_identity(self, content, expected_id, "shape observation")

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": SEMANTIC_SHAPE_OBSERVATION_SCHEMA_VERSION,
            "family_id": self.family_id,
            "instance_id": self.instance_id,
            "exact_geometry_ref": self.exact_geometry_ref.to_mapping(),
            "algorithm_version": self.algorithm_version,
            "samples_per_region": self.samples_per_region,
            "coordinate_system": self.coordinate_system,
            "length_unit": self.length_unit,
            "curvature_unit": self.curvature_unit,
            "regions": [item.to_mapping() for item in self.regions],
            "region_count": len(self.regions),
            "landmarks": [item.to_mapping() for item in self.landmarks],
            "landmark_count": len(self.landmarks),
            "native_parameter_names_read": False,
            "exact_geometry_replaced": False,
            "observation_status": self.observation_status,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "shape_observation_id": self.shape_observation_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractIdentityRef:
        return ContractIdentityRef(
            "semantic_shape_observation",
            SEMANTIC_SHAPE_OBSERVATION_SCHEMA_VERSION,
            self.shape_observation_id,
            self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SemanticShapeObservation":
        value = mapping(value, "shape_observation")
        required = {
            "schema_version",
            "family_id",
            "instance_id",
            "exact_geometry_ref",
            "algorithm_version",
            "samples_per_region",
            "coordinate_system",
            "length_unit",
            "curvature_unit",
            "regions",
            "region_count",
            "landmarks",
            "landmark_count",
            "native_parameter_names_read",
            "exact_geometry_replaced",
            "observation_status",
            "shape_observation_id",
            "content_sha256",
        }
        exact_keys(value, required, "shape_observation")
        if value["schema_version"] != SEMANTIC_SHAPE_OBSERVATION_SCHEMA_VERSION:
            raise ObservationContractError("unsupported semantic shape schema")
        if value["native_parameter_names_read"] is not False:
            raise ObservationContractError("shape observation cannot read native parameters")
        if value["exact_geometry_replaced"] is not False:
            raise ObservationContractError("shape observation cannot replace exact geometry")
        regions = tuple(
            RegionShapeObservation.from_mapping(
                mapping(item, "shape_observation.region")
            )
            for item in sequence(value["regions"], "shape_observation.regions")
        )
        landmarks = tuple(
            LandmarkObservation.from_mapping(
                mapping(item, "shape_observation.landmark")
            )
            for item in sequence(value["landmarks"], "shape_observation.landmarks")
        )
        if integer(value["region_count"], "shape_observation.region_count") != len(regions):
            raise ObservationContractError("shape observation region_count mismatch")
        if integer(value["landmark_count"], "shape_observation.landmark_count") != len(
            landmarks
        ):
            raise ObservationContractError("shape observation landmark_count mismatch")
        return cls(
            family_id=string(value["family_id"], "shape_observation.family_id"),
            instance_id=string(value["instance_id"], "shape_observation.instance_id"),
            exact_geometry_ref=ContractIdentityRef.from_mapping(
                mapping(value["exact_geometry_ref"], "shape_observation.exact_geometry_ref")
            ),
            algorithm_version=string(
                value["algorithm_version"], "shape_observation.algorithm_version"
            ),
            samples_per_region=integer(
                value["samples_per_region"], "shape_observation.samples_per_region"
            ),
            regions=regions,
            landmarks=landmarks,
            coordinate_system=string(
                value["coordinate_system"], "shape_observation.coordinate_system"
            ),
            length_unit=unit(value["length_unit"], "shape_observation.length_unit"),
            curvature_unit=unit(
                value["curvature_unit"], "shape_observation.curvature_unit"
            ),
            observation_status=string(
                value["observation_status"], "shape_observation.observation_status"
            ),
            shape_observation_id=string(
                value["shape_observation_id"],
                "shape_observation.shape_observation_id",
            ),
            content_sha256=normalized_hash(
                value["content_sha256"], "shape_observation.content_sha256"
            ),
        )


@dataclass(frozen=True)
class ScalarDescriptorDefinition:
    """Versioned definition and unit for one engineering scalar."""

    descriptor_id: str
    label: str
    scope_kind: str
    value_kind: str
    unit: str
    definition: str
    algorithm_version: str
    equivalence_absolute_tolerance: float
    applicable_region_types: tuple[str, ...]
    provenance: tuple[EvidenceRef, ...]
    descriptor_version: str = "v0"

    def __post_init__(self) -> None:
        string(self.descriptor_id, "descriptor_definition.descriptor_id")
        string(self.label, "descriptor_definition.label")
        if self.scope_kind not in {"global", "semantic_region"}:
            raise ObservationContractError("unsupported descriptor scope")
        if self.value_kind not in {"continuous", "integer", "boolean"}:
            raise ObservationContractError("unsupported descriptor value kind")
        validated_unit = unit(self.unit, "descriptor_definition.unit")
        if self.value_kind == "boolean" and validated_unit != "bool":
            raise ObservationContractError("boolean descriptor unit must be bool")
        if self.value_kind == "integer" and validated_unit != "count":
            raise ObservationContractError("integer descriptor unit must be count")
        if self.value_kind == "continuous" and validated_unit in {"bool", "count"}:
            raise ObservationContractError("continuous descriptor requires a numeric unit")
        string(self.definition, "descriptor_definition.definition")
        string(self.algorithm_version, "descriptor_definition.algorithm_version")
        non_negative(
            self.equivalence_absolute_tolerance,
            "descriptor_definition.equivalence_absolute_tolerance",
        )
        if self.scope_kind == "global" and self.applicable_region_types:
            raise ObservationContractError("global descriptor cannot select region types")
        if len(set(self.applicable_region_types)) != len(self.applicable_region_types):
            raise ObservationContractError("descriptor applicable region types must be unique")
        for region_type in self.applicable_region_types:
            string(region_type, "descriptor_definition.applicable_region_type")
        if not self.provenance:
            raise ObservationContractError("descriptor definition requires provenance")
        string(self.descriptor_version, "descriptor_definition.descriptor_version")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "descriptor_id": self.descriptor_id,
            "label": self.label,
            "scope_kind": self.scope_kind,
            "value_kind": self.value_kind,
            "unit": self.unit,
            "definition": self.definition,
            "algorithm_version": self.algorithm_version,
            "equivalence_absolute_tolerance": self.equivalence_absolute_tolerance,
            "applicable_region_types": list(self.applicable_region_types),
            "provenance": [item.to_mapping() for item in self.provenance],
            "descriptor_version": self.descriptor_version,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ScalarDescriptorDefinition":
        value = mapping(value, "descriptor_definition")
        required = set(cls.__dataclass_fields__)
        exact_keys(value, required, "descriptor_definition")
        return cls(
            descriptor_id=string(
                value["descriptor_id"], "descriptor_definition.descriptor_id"
            ),
            label=string(value["label"], "descriptor_definition.label"),
            scope_kind=string(
                value["scope_kind"], "descriptor_definition.scope_kind"
            ),
            value_kind=string(
                value["value_kind"], "descriptor_definition.value_kind"
            ),
            unit=unit(value["unit"], "descriptor_definition.unit"),
            definition=string(
                value["definition"], "descriptor_definition.definition"
            ),
            algorithm_version=string(
                value["algorithm_version"],
                "descriptor_definition.algorithm_version",
            ),
            equivalence_absolute_tolerance=non_negative(
                value["equivalence_absolute_tolerance"],
                "descriptor_definition.equivalence_absolute_tolerance",
            ),
            applicable_region_types=string_tuple(
                value["applicable_region_types"],
                "descriptor_definition.applicable_region_types",
            ),
            provenance=tuple(
                EvidenceRef.from_mapping(mapping(item, "descriptor_definition.provenance"))
                for item in sequence(
                    value["provenance"], "descriptor_definition.provenance"
                )
            ),
            descriptor_version=string(
                value["descriptor_version"], "descriptor_definition.descriptor_version"
            ),
        )


@dataclass(frozen=True)
class ScalarDescriptorRegistry:
    """R4 layer 3 vocabulary of scalar descriptors."""

    definitions: tuple[ScalarDescriptorDefinition, ...]
    registry_version: str = "rf_cem.r4.scalar_descriptors.v0"
    registry_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        string(self.registry_version, "descriptor_registry.registry_version")
        if not self.definitions:
            raise ObservationContractError("descriptor registry requires definitions")
        ids = [item.descriptor_id for item in self.definitions]
        if ids != sorted(ids):
            raise ObservationContractError("descriptor definitions must be sorted by ID")
        if len(ids) != len(set(ids)):
            raise ObservationContractError("descriptor IDs must be unique")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"scalar_descriptor_registry.{content[:16]}"
        _set_or_check_identity(self, content, expected_id, "descriptor registry")

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION,
            "registry_version": self.registry_version,
            "definitions": [item.to_mapping() for item in self.definitions],
            "definition_count": len(self.definitions),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "registry_id": self.registry_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractIdentityRef:
        return ContractIdentityRef(
            "scalar_descriptor_registry",
            SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION,
            self.registry_id,
            self.content_sha256,
        )

    @property
    def by_id(self) -> dict[str, ScalarDescriptorDefinition]:
        return {item.descriptor_id: item for item in self.definitions}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ScalarDescriptorRegistry":
        value = mapping(value, "descriptor_registry")
        required = {
            "schema_version",
            "registry_version",
            "definitions",
            "definition_count",
            "registry_id",
            "content_sha256",
        }
        exact_keys(value, required, "descriptor_registry")
        if value["schema_version"] != SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION:
            raise ObservationContractError("unsupported descriptor registry schema")
        definitions = tuple(
            ScalarDescriptorDefinition.from_mapping(
                mapping(item, "descriptor_registry.definition")
            )
            for item in sequence(value["definitions"], "descriptor_registry.definitions")
        )
        if integer(value["definition_count"], "descriptor_registry.definition_count") != len(
            definitions
        ):
            raise ObservationContractError("descriptor registry definition_count mismatch")
        return cls(
            definitions=definitions,
            registry_version=string(
                value["registry_version"], "descriptor_registry.registry_version"
            ),
            registry_id=string(value["registry_id"], "descriptor_registry.registry_id"),
            content_sha256=normalized_hash(
                value["content_sha256"], "descriptor_registry.content_sha256"
            ),
        )


DescriptorScalar = Union[float, int, bool]


@dataclass(frozen=True)
class ScalarDescriptorValue:
    """One observed scalar bound to a definition and semantic scope."""

    descriptor_id: str
    descriptor_version: str
    source_observation_id: str
    scope_kind: str
    scope_id: str
    region_type: str | None
    side: str | None
    value_kind: str
    unit: str
    status: str
    value: DescriptorScalar | None
    not_applicable_reason: str | None = None
    value_id: str = ""

    def __post_init__(self) -> None:
        string(self.descriptor_id, "descriptor_value.descriptor_id")
        string(self.descriptor_version, "descriptor_value.descriptor_version")
        string(self.source_observation_id, "descriptor_value.source_observation_id")
        if self.scope_kind not in {"global", "semantic_region"}:
            raise ObservationContractError("unsupported descriptor value scope")
        string(self.scope_id, "descriptor_value.scope_id")
        optional_string(self.region_type, "descriptor_value.region_type")
        optional_string(self.side, "descriptor_value.side")
        if self.scope_kind == "global":
            if self.region_type is not None or self.side is not None:
                raise ObservationContractError("global descriptor cannot have region tags")
        elif self.region_type is None or self.side not in {"left", "center", "right"}:
            raise ObservationContractError("regional descriptor requires region type and side")
        if self.value_kind not in {"continuous", "integer", "boolean"}:
            raise ObservationContractError("unsupported descriptor value kind")
        validated_unit = unit(self.unit, "descriptor_value.unit")
        if self.status not in {"observed", "not_applicable"}:
            raise ObservationContractError("unsupported descriptor value status")
        if self.status == "observed":
            if self.not_applicable_reason is not None:
                raise ObservationContractError("observed descriptor cannot have N/A reason")
            _validate_scalar(self.value, self.value_kind, validated_unit)
            if self.value_kind == "continuous" and validated_unit in {"bool", "count"}:
                raise ObservationContractError(
                    "continuous descriptor value requires a numeric unit"
                )
        else:
            if self.value is not None:
                raise ObservationContractError("not-applicable descriptor must have null value")
            string(
                self.not_applicable_reason,
                "descriptor_value.not_applicable_reason",
            )
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.scope_id}:{self.descriptor_id}:{content[:12]}"
        if self.value_id:
            if self.value_id != expected_id:
                raise ObservationContractError("descriptor value ID mismatch")
        else:
            object.__setattr__(self, "value_id", expected_id)

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "descriptor_id": self.descriptor_id,
            "descriptor_version": self.descriptor_version,
            "source_observation_id": self.source_observation_id,
            "scope_kind": self.scope_kind,
            "scope_id": self.scope_id,
            "region_type": self.region_type,
            "side": self.side,
            "value_kind": self.value_kind,
            "unit": self.unit,
            "status": self.status,
            "value": self.value,
            "not_applicable_reason": self.not_applicable_reason,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {**self._content_mapping(), "value_id": self.value_id}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ScalarDescriptorValue":
        value = mapping(value, "descriptor_value")
        required = {
            "descriptor_id",
            "descriptor_version",
            "source_observation_id",
            "scope_kind",
            "scope_id",
            "region_type",
            "side",
            "value_kind",
            "unit",
            "status",
            "value",
            "not_applicable_reason",
            "value_id",
        }
        exact_keys(value, required, "descriptor_value")
        scalar = value["value"]
        if scalar is not None and not isinstance(scalar, (bool, int, float)):
            raise ObservationContractError("descriptor value must be scalar or null")
        return cls(
            descriptor_id=string(value["descriptor_id"], "descriptor_value.descriptor_id"),
            descriptor_version=string(
                value["descriptor_version"], "descriptor_value.descriptor_version"
            ),
            source_observation_id=string(
                value["source_observation_id"],
                "descriptor_value.source_observation_id",
            ),
            scope_kind=string(value["scope_kind"], "descriptor_value.scope_kind"),
            scope_id=string(value["scope_id"], "descriptor_value.scope_id"),
            region_type=optional_string(
                value["region_type"], "descriptor_value.region_type"
            ),
            side=optional_string(value["side"], "descriptor_value.side"),
            value_kind=string(value["value_kind"], "descriptor_value.value_kind"),
            unit=unit(value["unit"], "descriptor_value.unit"),
            status=string(value["status"], "descriptor_value.status"),
            value=scalar,
            not_applicable_reason=optional_string(
                value["not_applicable_reason"],
                "descriptor_value.not_applicable_reason",
            ),
            value_id=string(value["value_id"], "descriptor_value.value_id"),
        )


@dataclass(frozen=True)
class ObservationBundle:
    """R4 bundle that links, but does not collapse, all three layers."""

    family_id: str
    instance_id: str
    exact_geometry_ref: ContractIdentityRef
    shape_observation_ref: ContractIdentityRef
    descriptor_registry_ref: ContractIdentityRef
    descriptor_values: tuple[ScalarDescriptorValue, ...]
    observation_status: str = "pass_no_cst"
    geometry_mutation_status: str = "not_performed"
    live_cst_status: str = "not_run"
    rf_metric_status: str = "not_defined_r4"
    physical_acceptance_status: str = "not_established"
    observation_bundle_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        string(self.family_id, "observation_bundle.family_id")
        string(self.instance_id, "observation_bundle.instance_id")
        if self.exact_geometry_ref.contract_kind != "exact_geometry_reference":
            raise ObservationContractError("observation bundle exact layer mismatch")
        if self.exact_geometry_ref.schema_version != EXACT_GEOMETRY_REFERENCE_SCHEMA_VERSION:
            raise ObservationContractError("observation bundle exact schema mismatch")
        if self.shape_observation_ref.contract_kind != "semantic_shape_observation":
            raise ObservationContractError("observation bundle shape layer mismatch")
        if (
            self.shape_observation_ref.schema_version
            != SEMANTIC_SHAPE_OBSERVATION_SCHEMA_VERSION
        ):
            raise ObservationContractError("observation bundle shape schema mismatch")
        if self.descriptor_registry_ref.contract_kind != "scalar_descriptor_registry":
            raise ObservationContractError("observation bundle registry layer mismatch")
        if (
            self.descriptor_registry_ref.schema_version
            != SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION
        ):
            raise ObservationContractError("observation bundle registry schema mismatch")
        if not self.descriptor_values:
            raise ObservationContractError("observation bundle requires descriptor values")
        value_ids = [item.value_id for item in self.descriptor_values]
        if value_ids != sorted(value_ids):
            raise ObservationContractError("descriptor values must be sorted by value ID")
        if len(value_ids) != len(set(value_ids)):
            raise ObservationContractError("descriptor value IDs must be unique")
        if any(
            item.source_observation_id != self.shape_observation_ref.object_id
            for item in self.descriptor_values
        ):
            raise ObservationContractError("descriptor value shape source mismatch")
        if self.observation_status != "pass_no_cst":
            raise ObservationContractError("R4 observation bundle must be pass_no_cst")
        if self.geometry_mutation_status != "not_performed":
            raise ObservationContractError("R4 observations cannot mutate geometry")
        if self.live_cst_status != "not_run":
            raise ObservationContractError("R4 observation bundle must remain no-CST")
        if self.rf_metric_status != "not_defined_r4":
            raise ObservationContractError("R4 cannot define RF metrics")
        if self.physical_acceptance_status != "not_established":
            raise ObservationContractError("R4 cannot claim physical acceptance")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.instance_id}.observation_bundle.{content[:16]}"
        _set_or_check_identity(self, content, expected_id, "observation bundle")

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": OBSERVATION_BUNDLE_SCHEMA_VERSION,
            "family_id": self.family_id,
            "instance_id": self.instance_id,
            "exact_geometry_ref": self.exact_geometry_ref.to_mapping(),
            "shape_observation_ref": self.shape_observation_ref.to_mapping(),
            "descriptor_registry_ref": self.descriptor_registry_ref.to_mapping(),
            "descriptor_values": [item.to_mapping() for item in self.descriptor_values],
            "descriptor_value_count": len(self.descriptor_values),
            "layer_separation": [
                "exact_native_geometry",
                "semantic_shape_observation",
                "scalar_engineering_descriptor",
            ],
            "observation_status": self.observation_status,
            "geometry_mutation_status": self.geometry_mutation_status,
            "live_cst_status": self.live_cst_status,
            "rf_metric_status": self.rf_metric_status,
            "physical_acceptance_status": self.physical_acceptance_status,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "observation_bundle_id": self.observation_bundle_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractIdentityRef:
        return ContractIdentityRef(
            "observation_bundle",
            OBSERVATION_BUNDLE_SCHEMA_VERSION,
            self.observation_bundle_id,
            self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ObservationBundle":
        value = mapping(value, "observation_bundle")
        required = {
            "schema_version",
            "family_id",
            "instance_id",
            "exact_geometry_ref",
            "shape_observation_ref",
            "descriptor_registry_ref",
            "descriptor_values",
            "descriptor_value_count",
            "layer_separation",
            "observation_status",
            "geometry_mutation_status",
            "live_cst_status",
            "rf_metric_status",
            "physical_acceptance_status",
            "observation_bundle_id",
            "content_sha256",
        }
        exact_keys(value, required, "observation_bundle")
        if value["schema_version"] != OBSERVATION_BUNDLE_SCHEMA_VERSION:
            raise ObservationContractError("unsupported observation bundle schema")
        expected_layers = (
            "exact_native_geometry",
            "semantic_shape_observation",
            "scalar_engineering_descriptor",
        )
        if string_tuple(value["layer_separation"], "observation_bundle.layer_separation") != expected_layers:
            raise ObservationContractError("observation bundle layer separation mismatch")
        descriptor_values = tuple(
            ScalarDescriptorValue.from_mapping(
                mapping(item, "observation_bundle.descriptor_value")
            )
            for item in sequence(
                value["descriptor_values"], "observation_bundle.descriptor_values"
            )
        )
        if integer(
            value["descriptor_value_count"],
            "observation_bundle.descriptor_value_count",
        ) != len(descriptor_values):
            raise ObservationContractError("observation bundle descriptor count mismatch")
        return cls(
            family_id=string(value["family_id"], "observation_bundle.family_id"),
            instance_id=string(
                value["instance_id"], "observation_bundle.instance_id"
            ),
            exact_geometry_ref=ContractIdentityRef.from_mapping(
                mapping(value["exact_geometry_ref"], "observation_bundle.exact_geometry_ref")
            ),
            shape_observation_ref=ContractIdentityRef.from_mapping(
                mapping(
                    value["shape_observation_ref"],
                    "observation_bundle.shape_observation_ref",
                )
            ),
            descriptor_registry_ref=ContractIdentityRef.from_mapping(
                mapping(
                    value["descriptor_registry_ref"],
                    "observation_bundle.descriptor_registry_ref",
                )
            ),
            descriptor_values=descriptor_values,
            observation_status=string(
                value["observation_status"], "observation_bundle.observation_status"
            ),
            geometry_mutation_status=string(
                value["geometry_mutation_status"],
                "observation_bundle.geometry_mutation_status",
            ),
            live_cst_status=string(
                value["live_cst_status"], "observation_bundle.live_cst_status"
            ),
            rf_metric_status=string(
                value["rf_metric_status"], "observation_bundle.rf_metric_status"
            ),
            physical_acceptance_status=string(
                value["physical_acceptance_status"],
                "observation_bundle.physical_acceptance_status",
            ),
            observation_bundle_id=string(
                value["observation_bundle_id"],
                "observation_bundle.observation_bundle_id",
            ),
            content_sha256=normalized_hash(
                value["content_sha256"], "observation_bundle.content_sha256"
            ),
        )


def load_exact_geometry_reference(path: Path) -> ExactGeometryReference:
    """Load a strict ``exact_geometry_reference.v0`` artifact."""

    return ExactGeometryReference.from_mapping(read_json_mapping(path, "exact geometry"))


def load_semantic_shape_observation(path: Path) -> SemanticShapeObservation:
    """Load a strict ``semantic_shape_observation.v0`` artifact."""

    return SemanticShapeObservation.from_mapping(
        read_json_mapping(path, "semantic shape observation")
    )


def load_scalar_descriptor_registry(path: Path) -> ScalarDescriptorRegistry:
    """Load a strict ``scalar_descriptor_registry.v0`` artifact."""

    return ScalarDescriptorRegistry.from_mapping(
        read_json_mapping(path, "scalar descriptor registry")
    )


def load_observation_bundle(path: Path) -> ObservationBundle:
    """Load a strict ``observation_bundle.v0`` artifact."""

    return ObservationBundle.from_mapping(read_json_mapping(path, "observation bundle"))


def _set_or_check_identity(
    target: object, content: str, expected_id: str, label: str
) -> None:
    current_hash = getattr(target, "content_sha256")
    current_id_field = next(
        name
        for name in (
            "exact_geometry_id",
            "shape_observation_id",
            "registry_id",
            "observation_bundle_id",
        )
        if hasattr(target, name)
    )
    current_id = getattr(target, current_id_field)
    if current_hash:
        if current_hash != content:
            raise ObservationContractError(f"{label} content SHA-256 mismatch")
    else:
        object.__setattr__(target, "content_sha256", content)
    if current_id:
        if current_id != expected_id:
            raise ObservationContractError(f"{label} ID mismatch")
    else:
        object.__setattr__(target, current_id_field, expected_id)


def _pair(value: object, path: str) -> tuple[float, float]:
    values = sequence(value, path)
    if len(values) != 2:
        raise ObservationContractError(f"{path} must contain exactly two numbers")
    return (number(values[0], f"{path}[0]"), number(values[1], f"{path}[1]"))


def _unit_vector(value: tuple[float, float], path: str) -> None:
    if len(value) != 2:
        raise ObservationContractError(f"{path} must contain exactly two numbers")
    first = number(value[0], f"{path}[0]")
    second = number(value[1], f"{path}[1]")
    if abs((first * first + second * second) ** 0.5 - 1.0) > 1.0e-9:
        raise ObservationContractError(f"{path} must be a unit vector")


def _validate_scalar(value: object, value_kind: str, declared_unit: str) -> None:
    if value_kind == "boolean":
        boolean(value, "descriptor_value.value")
        if declared_unit != "bool":
            raise ObservationContractError("boolean descriptor value unit must be bool")
    elif value_kind == "integer":
        integer(value, "descriptor_value.value")
        if declared_unit != "count":
            raise ObservationContractError("integer descriptor value unit must be count")
    else:
        number(value, "descriptor_value.value")


__all__ = [
    "ContractIdentityRef",
    "DescriptorScalar",
    "EXACT_GEOMETRY_REFERENCE_SCHEMA_VERSION",
    "ExactGeometryReference",
    "GeometryArtifactIdentity",
    "LandmarkObservation",
    "MonotonicInterval",
    "OBSERVATION_BUNDLE_SCHEMA_VERSION",
    "ObservationBundle",
    "RegionShapeObservation",
    "SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION",
    "SEMANTIC_SHAPE_OBSERVATION_SCHEMA_VERSION",
    "ScalarDescriptorDefinition",
    "ScalarDescriptorRegistry",
    "ScalarDescriptorValue",
    "SemanticShapeObservation",
    "ShapeSample",
    "load_exact_geometry_reference",
    "load_observation_bundle",
    "load_scalar_descriptor_registry",
    "load_semantic_shape_observation",
]
