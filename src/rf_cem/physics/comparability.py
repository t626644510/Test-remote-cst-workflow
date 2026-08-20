"""Fail-closed RF metric comparability policy for W5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .cases import PhysicsCase
from .common import PhysicsContractError, enum, exact_keys, mapping, sequence, string, string_tuple
from .identity import bind_identity, identity_ref
from .metrics import METRIC_OBSERVATION_SCHEMA_VERSION, MetricContract, MetricObservation
from .modes import ModeFingerprint, ModeIdentity
from .references import ContractRef, content_fingerprint


COMPARABILITY_SCHEMA_VERSION = "result_comparability.v0"
COMPARABILITY_DECISIONS = frozenset({"comparable", "not_comparable"})
COMPARISON_PURPOSES = frozenset({"direct", "mesh_convergence"})


@dataclass(frozen=True)
class ComparabilityAssessment:
    """Auditable decision with every incompatibility made explicit."""

    left_observation_ref: ContractRef
    right_observation_ref: ContractRef
    comparison_purpose: str
    decision: str
    reason_codes: tuple[str, ...]
    assessment_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        for reference in (self.left_observation_ref, self.right_observation_ref):
            if (
                reference.contract_kind != "metric_observation"
                or reference.schema_version != METRIC_OBSERVATION_SCHEMA_VERSION
            ):
                raise PhysicsContractError(
                    "comparability assessment requires metric_observation.v0"
                )
        if self.left_observation_ref == self.right_observation_ref:
            raise PhysicsContractError("comparability requires two distinct observations")
        enum(
            self.comparison_purpose,
            COMPARISON_PURPOSES,
            "comparability.comparison_purpose",
        )
        enum(self.decision, COMPARABILITY_DECISIONS, "comparability.decision")
        string_tuple(self.reason_codes, "comparability.reason_codes")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise PhysicsContractError("comparability reason codes must be unique")
        if self.decision == "comparable" and self.reason_codes:
            raise PhysicsContractError("comparable assessment cannot have failure reasons")
        if self.decision == "not_comparable" and not self.reason_codes:
            raise PhysicsContractError("not-comparable assessment requires reasons")
        bind_identity(
            self,
            content_mapping=self._content_mapping(),
            id_attribute="assessment_id",
            id_prefix="rf_result.comparability",
            label="comparability assessment",
        )

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": COMPARABILITY_SCHEMA_VERSION,
            "left_observation_ref": self.left_observation_ref.to_mapping(),
            "right_observation_ref": self.right_observation_ref.to_mapping(),
            "comparison_purpose": self.comparison_purpose,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "assessment_id": self.assessment_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractRef:
        return identity_ref(
            contract_kind="result_comparability",
            schema_version=COMPARABILITY_SCHEMA_VERSION,
            object_id=self.assessment_id,
            content_sha256=self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ComparabilityAssessment":
        value = mapping(value, "comparability")
        exact_keys(
            value,
            {
                "schema_version",
                "left_observation_ref",
                "right_observation_ref",
                "comparison_purpose",
                "decision",
                "reason_codes",
                "assessment_id",
                "content_sha256",
            },
            "comparability",
        )
        if value["schema_version"] != COMPARABILITY_SCHEMA_VERSION:
            raise PhysicsContractError("unsupported comparability schema")
        return cls(
            left_observation_ref=ContractRef.from_mapping(
                mapping(value["left_observation_ref"], "left_observation_ref")
            ),
            right_observation_ref=ContractRef.from_mapping(
                mapping(value["right_observation_ref"], "right_observation_ref")
            ),
            comparison_purpose=enum(
                value["comparison_purpose"],
                COMPARISON_PURPOSES,
                "comparability.comparison_purpose",
            ),
            decision=enum(
                value["decision"], COMPARABILITY_DECISIONS, "comparability.decision"
            ),
            reason_codes=string_tuple(value["reason_codes"], "comparability.reason_codes"),
            assessment_id=string(value["assessment_id"], "comparability.assessment_id"),
            content_sha256=string(value["content_sha256"], "comparability.content_sha256"),
        )


def assess_comparability(
    *,
    left_observation: MetricObservation,
    right_observation: MetricObservation,
    left_case: PhysicsCase,
    right_case: PhysicsCase,
    left_mode: ModeIdentity,
    right_mode: ModeIdentity,
    left_fingerprint: ModeFingerprint,
    right_fingerprint: ModeFingerprint,
    left_metric: MetricContract,
    right_metric: MetricContract,
    comparison_purpose: str = "direct",
) -> ComparabilityAssessment:
    """Apply the R5 default-deny material/boundary/mesh/normalization/mode policy."""

    enum(comparison_purpose, COMPARISON_PURPOSES, "comparison_purpose")
    reasons: list[str] = []
    for side, observation, case, mode, fingerprint, metric in (
        (
            "left",
            left_observation,
            left_case,
            left_mode,
            left_fingerprint,
            left_metric,
        ),
        (
            "right",
            right_observation,
            right_case,
            right_mode,
            right_fingerprint,
            right_metric,
        ),
    ):
        if not _contract_chain_matches(
            observation=observation,
            case=case,
            mode=mode,
            fingerprint=fingerprint,
            metric=metric,
        ):
            reasons.append(f"{side}_contract_chain_mismatch")
    if left_observation.geometry.to_mapping() != right_observation.geometry.to_mapping():
        reasons.append("geometry_identity_differs")
    if left_case.solver.to_mapping() != right_case.solver.to_mapping():
        reasons.append("solver_or_version_differs")
    if _fingerprint([item.to_mapping() for item in left_case.materials]) != _fingerprint(
        [item.to_mapping() for item in right_case.materials]
    ):
        reasons.append("material_assignment_differs")
    if _fingerprint([item.to_mapping() for item in left_case.boundaries]) != _fingerprint(
        [item.to_mapping() for item in right_case.boundaries]
    ):
        reasons.append("boundary_assignment_differs")
    if left_case.mesh.to_mapping() != right_case.mesh.to_mapping():
        if comparison_purpose != "mesh_convergence":
            reasons.append("mesh_definition_differs")
    elif comparison_purpose == "mesh_convergence":
        reasons.append("mesh_levels_not_distinct")
    if left_metric.content_sha256 != right_metric.content_sha256:
        reasons.append("metric_contract_differs")
    if left_observation.unit != right_observation.unit:
        reasons.append("unit_differs")
    if left_observation.normalization != right_observation.normalization:
        reasons.append("normalization_differs")
    if left_observation.validation_status not in {"extracted", "replayed"} or (
        right_observation.validation_status not in {"extracted", "replayed"}
    ):
        reasons.append("result_not_established")
    if left_fingerprint.fingerprint_status != "established" or (
        right_fingerprint.fingerprint_status != "established"
    ):
        reasons.append("mode_fingerprint_not_established")
    if left_mode.determination_status == "not_established" or (
        right_mode.determination_status == "not_established"
    ):
        reasons.append("mode_identity_not_established")
    if comparison_purpose == "direct":
        if left_mode.content_sha256 != right_mode.content_sha256:
            reasons.append("mode_identity_differs")
    else:
        if (left_mode.mode_family, left_mode.mode_role) != (
            right_mode.mode_family,
            right_mode.mode_role,
        ):
            reasons.append("mode_role_differs")
    reasons = sorted(set(reasons))
    return ComparabilityAssessment(
        left_observation_ref=left_observation.identity_ref(),
        right_observation_ref=right_observation.identity_ref(),
        comparison_purpose=comparison_purpose,
        decision="not_comparable" if reasons else "comparable",
        reason_codes=tuple(reasons),
    )


def _fingerprint(value: object) -> str:
    return content_fingerprint(value)


def _contract_chain_matches(
    *,
    observation: MetricObservation,
    case: PhysicsCase,
    mode: ModeIdentity,
    fingerprint: ModeFingerprint,
    metric: MetricContract,
) -> bool:
    """Confirm the objects supplied to a comparison are the referenced objects."""

    if (
        observation.geometry != case.geometry
        or observation.physics_case_ref != case.identity_ref()
        or observation.mode_identity_ref != mode.identity_ref()
        or observation.metric_contract_ref != metric.identity_ref()
        or mode.geometry != case.geometry
        or mode.physics_case_ref != case.identity_ref()
        or mode.fingerprint_ref != fingerprint.identity_ref()
        or fingerprint.geometry != case.geometry
        or fingerprint.physics_case_ref != case.identity_ref()
        or observation.unit != metric.unit
        or observation.extraction_method != metric.extraction_method
        or observation.normalization != metric.normalization
    ):
        return False
    if (
        observation.validation_status in {"extracted", "replayed"}
        and metric.extraction_support == "not_established"
    ):
        return False
    if (
        observation.validation_status in {"extracted", "replayed"}
        and mode.solver_mode_index is not None
        and metric.result_locator_template != "not_established"
        and observation.result_locator
        != metric.result_locator_template.format(mode_index=mode.solver_mode_index)
    ):
        return False
    return True


__all__ = [
    "COMPARABILITY_DECISIONS",
    "COMPARABILITY_SCHEMA_VERSION",
    "COMPARISON_PURPOSES",
    "ComparabilityAssessment",
    "assess_comparability",
]
