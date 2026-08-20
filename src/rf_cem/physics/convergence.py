"""Multi-level mesh convergence evidence for mode-identified scalar results."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from .cases import PHYSICS_CASE_SCHEMA_VERSION
from .common import (
    PhysicsContractError,
    enum,
    exact_keys,
    mapping,
    non_negative,
    number,
    positive,
    positive_integer,
    sequence,
    string,
    unit,
)
from .identity import bind_identity, identity_ref
from .metrics import METRIC_CONTRACT_SCHEMA_VERSION, METRIC_OBSERVATION_SCHEMA_VERSION
from .modes import MODE_IDENTITY_SCHEMA_VERSION
from .references import ContractRef, GeometryBinding


MESH_CONVERGENCE_SCHEMA_VERSION = "mesh_convergence.v0"
CONVERGENCE_STATUSES = frozenset(
    {"not_established", "converged", "not_converged"}
)


@dataclass(frozen=True)
class MeshConvergenceSample:
    """One scalar observation at one explicit mesh level."""

    mesh_level: str
    mesh_id: str
    mesh_cells: int
    physics_case_ref: ContractRef
    mode_identity_ref: ContractRef
    metric_observation_ref: ContractRef
    value: float
    unit: str

    def __post_init__(self) -> None:
        string(self.mesh_level, "mesh_sample.mesh_level")
        string(self.mesh_id, "mesh_sample.mesh_id")
        positive_integer(self.mesh_cells, "mesh_sample.mesh_cells")
        expected_refs = (
            (self.physics_case_ref, "physics_case", PHYSICS_CASE_SCHEMA_VERSION),
            (self.mode_identity_ref, "mode_identity", MODE_IDENTITY_SCHEMA_VERSION),
            (
                self.metric_observation_ref,
                "metric_observation",
                METRIC_OBSERVATION_SCHEMA_VERSION,
            ),
        )
        for reference, kind, schema in expected_refs:
            if reference.contract_kind != kind or reference.schema_version != schema:
                raise PhysicsContractError(f"mesh sample requires {schema}")
        number(self.value, "mesh_sample.value")
        unit(self.unit, "mesh_sample.unit")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "mesh_level": self.mesh_level,
            "mesh_id": self.mesh_id,
            "mesh_cells": self.mesh_cells,
            "physics_case_ref": self.physics_case_ref.to_mapping(),
            "mode_identity_ref": self.mode_identity_ref.to_mapping(),
            "metric_observation_ref": self.metric_observation_ref.to_mapping(),
            "value": self.value,
            "unit": self.unit,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MeshConvergenceSample":
        value = mapping(value, "mesh_sample")
        exact_keys(
            value,
            {
                "mesh_level",
                "mesh_id",
                "mesh_cells",
                "physics_case_ref",
                "mode_identity_ref",
                "metric_observation_ref",
                "value",
                "unit",
            },
            "mesh_sample",
        )
        return cls(
            mesh_level=string(value["mesh_level"], "mesh_sample.mesh_level"),
            mesh_id=string(value["mesh_id"], "mesh_sample.mesh_id"),
            mesh_cells=positive_integer(value["mesh_cells"], "mesh_sample.mesh_cells"),
            physics_case_ref=ContractRef.from_mapping(
                mapping(value["physics_case_ref"], "physics_case_ref")
            ),
            mode_identity_ref=ContractRef.from_mapping(
                mapping(value["mode_identity_ref"], "mode_identity_ref")
            ),
            metric_observation_ref=ContractRef.from_mapping(
                mapping(value["metric_observation_ref"], "metric_observation_ref")
            ),
            value=number(value["value"], "mesh_sample.value"),
            unit=unit(value["unit"], "mesh_sample.unit"),
        )


@dataclass(frozen=True)
class MeshConvergence:
    """A replayable convergence decision over three or more mesh levels."""

    geometry: GeometryBinding
    metric_contract_ref: ContractRef
    convergence_status: str
    relative_tolerance: float
    samples: tuple[MeshConvergenceSample, ...]
    relative_changes: tuple[float, ...]
    assessment: str
    convergence_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.metric_contract_ref.contract_kind != "metric_contract"
            or self.metric_contract_ref.schema_version != METRIC_CONTRACT_SCHEMA_VERSION
        ):
            raise PhysicsContractError("mesh convergence requires metric_contract.v0")
        enum(
            self.convergence_status,
            CONVERGENCE_STATUSES,
            "mesh_convergence.convergence_status",
        )
        positive(self.relative_tolerance, "mesh_convergence.relative_tolerance")
        string(self.assessment, "mesh_convergence.assessment")
        for index, change in enumerate(self.relative_changes):
            non_negative(change, f"mesh_convergence.relative_changes[{index}]")
        if self.convergence_status == "not_established":
            if self.samples or self.relative_changes:
                raise PhysicsContractError(
                    "not-established mesh convergence cannot contain partial samples"
                )
        else:
            if len(self.samples) < 3:
                raise PhysicsContractError(
                    "established mesh convergence requires at least three levels"
                )
            if len(self.relative_changes) != len(self.samples) - 1:
                raise PhysicsContractError("mesh relative-change count is inconsistent")
            cells = [item.mesh_cells for item in self.samples]
            if any(right <= left for left, right in zip(cells, cells[1:])):
                raise PhysicsContractError("mesh cell counts must increase strictly")
            levels = [item.mesh_level for item in self.samples]
            mesh_ids = [item.mesh_id for item in self.samples]
            case_refs = [item.physics_case_ref for item in self.samples]
            mode_refs = [item.mode_identity_ref for item in self.samples]
            if (
                len(levels) != len(set(levels))
                or len(mesh_ids) != len(set(mesh_ids))
                or len(case_refs) != len(set(case_refs))
                or len(mode_refs) != len(set(mode_refs))
            ):
                raise PhysicsContractError(
                    "mesh convergence levels, meshes, cases, and modes must be unique"
                )
            for sample in self.samples:
                for reference in (
                    sample.physics_case_ref,
                    sample.mode_identity_ref,
                    sample.metric_observation_ref,
                ):
                    if not reference.object_id.startswith(
                        self.geometry.instance_id + "."
                    ):
                        raise PhysicsContractError(
                            "mesh convergence sample does not bind its geometry"
                        )
            units = {item.unit for item in self.samples}
            if len(units) != 1:
                raise PhysicsContractError("mesh convergence samples must use one unit")
            ids = [item.metric_observation_ref.object_id for item in self.samples]
            if len(ids) != len(set(ids)):
                raise PhysicsContractError("mesh convergence observations must be unique")
            computed = _relative_changes([item.value for item in self.samples])
            if any(
                not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15)
                for actual, expected in zip(self.relative_changes, computed)
            ):
                raise PhysicsContractError(
                    "mesh convergence relative changes do not match sample values"
                )
            expected_status = (
                "converged"
                if self.relative_changes[-1] <= self.relative_tolerance
                else "not_converged"
            )
            if self.convergence_status != expected_status:
                raise PhysicsContractError(
                    "mesh convergence status does not match final relative change"
                )
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="convergence_id",
            id_prefix=f"{self.geometry.instance_id}.mesh_convergence",
            label="mesh convergence",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": MESH_CONVERGENCE_SCHEMA_VERSION,
            "geometry": self.geometry.to_mapping(),
            "metric_contract_ref": self.metric_contract_ref.to_mapping(),
            "convergence_status": self.convergence_status,
            "relative_tolerance": self.relative_tolerance,
            "samples": [item.to_mapping() for item in self.samples],
            "relative_changes": list(self.relative_changes),
            "assessment": self.assessment,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "convergence_id": self.convergence_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="mesh_convergence",
            schema_version=MESH_CONVERGENCE_SCHEMA_VERSION,
            object_id=self.convergence_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MeshConvergence":
        value = mapping(value, "mesh_convergence")
        exact_keys(
            value,
            {
                "schema_version",
                "geometry",
                "metric_contract_ref",
                "convergence_status",
                "relative_tolerance",
                "samples",
                "relative_changes",
                "assessment",
                "convergence_id",
                "content_sha256",
            },
            "mesh_convergence",
        )
        if value["schema_version"] != MESH_CONVERGENCE_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported mesh convergence schema")
        return cls(
            geometry=GeometryBinding.from_mapping(mapping(value["geometry"], "geometry")),
            metric_contract_ref=ContractRef.from_mapping(
                mapping(value["metric_contract_ref"], "metric_contract_ref")
            ),
            convergence_status=enum(
                value["convergence_status"],
                CONVERGENCE_STATUSES,
                "mesh_convergence.convergence_status",
            ),
            relative_tolerance=positive(
                value["relative_tolerance"], "mesh_convergence.relative_tolerance"
            ),
            samples=tuple(
                MeshConvergenceSample.from_mapping(mapping(item, "mesh_sample"))
                for item in sequence(value["samples"], "mesh_convergence.samples")
            ),
            relative_changes=tuple(
                non_negative(item, "mesh_convergence.relative_changes[]")
                for item in sequence(
                    value["relative_changes"], "mesh_convergence.relative_changes"
                )
            ),
            assessment=string(value["assessment"], "mesh_convergence.assessment"),
            convergence_id=string(
                value["convergence_id"], "mesh_convergence.convergence_id"
            ),
            content_sha256=string(
                value["content_sha256"], "mesh_convergence.content_sha256"
            ),
        )


def evaluate_mesh_convergence(
    *,
    geometry: GeometryBinding,
    metric_contract_ref: ContractRef,
    samples: Sequence[MeshConvergenceSample],
    relative_tolerance: float,
) -> MeshConvergence:
    """Derive a deterministic convergence status from ordered samples."""

    ordered = tuple(samples)
    changes = _relative_changes([item.value for item in ordered])
    tolerance = positive(relative_tolerance, "relative_tolerance")
    status = "converged" if changes and changes[-1] <= tolerance else "not_converged"
    return MeshConvergence(
        geometry=geometry,
        metric_contract_ref=metric_contract_ref,
        convergence_status=status,
        relative_tolerance=tolerance,
        samples=ordered,
        relative_changes=changes,
        assessment=(
            f"final relative change {changes[-1]:.12g} "
            f"{'<=' if status == 'converged' else '>'} tolerance {tolerance:.12g}"
            if changes
            else "insufficient mesh samples"
        ),
    )


def _relative_changes(values: Sequence[float]) -> tuple[float, ...]:
    result: list[float] = []
    for left, right in zip(values, values[1:]):
        denominator = max(abs(right), 1e-300)
        result.append(abs(right - left) / denominator)
    return tuple(result)


__all__ = [
    "CONVERGENCE_STATUSES",
    "MESH_CONVERGENCE_SCHEMA_VERSION",
    "MeshConvergence",
    "MeshConvergenceSample",
    "evaluate_mesh_convergence",
]
