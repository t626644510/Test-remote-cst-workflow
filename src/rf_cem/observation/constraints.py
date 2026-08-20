"""Auditable, non-mutating R4 engineering constraints and evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from rf_cem.semantic import EvidenceRef
from rf_cem.semantic.contracts import canonical_sha256

from .common import (
    ConstraintContractError,
    boolean,
    exact_keys,
    mapping,
    non_negative,
    normalized_hash,
    number,
    optional_string,
    read_json_mapping,
    sequence,
    string,
    string_tuple,
    unit,
)
from .contracts import (
    OBSERVATION_BUNDLE_SCHEMA_VERSION,
    SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION,
    ContractIdentityRef,
    DescriptorScalar,
    ObservationBundle,
    ScalarDescriptorRegistry,
    ScalarDescriptorValue,
)
from .descriptors import (
    GLOBAL_MAXIMUM_RADIUS,
    GLOBAL_MINIMUM_APERTURE_RADIUS,
    GLOBAL_MINIMUM_RADIUS_OF_CURVATURE,
    GLOBAL_NOSE_PRESENT,
    GLOBAL_TOTAL_CAVITY_LENGTH,
    REGION_EQUATOR_CREST_RADIUS,
)


ENGINEERING_CONSTRAINT_SCHEMA_VERSION = "engineering_constraint.v0"
CONSTRAINT_EVALUATION_SCHEMA_VERSION = "constraint_evaluation.v0"
CONSTRAINT_EVALUATOR_VERSION = "rf_cem.engineering_constraint_evaluator.v0"
CONSTRAINT_KINDS = frozenset({"hard", "soft", "advisory", "diagnostic"})
OPERATORS = frozenset(
    {"between", "greater_or_equal", "less_or_equal", "approximately_equal", "equal"}
)


@dataclass(frozen=True)
class EngineeringConstraint:
    """One unit-aware human engineering constraint over an R4 descriptor."""

    label: str
    constraint_kind: str
    descriptor_registry_ref: ContractIdentityRef
    descriptor_id: str
    descriptor_version: str
    scope_kind: str
    region_type: str | None
    side: str | None
    operator: str
    unit: str
    lower_limit: float | None
    upper_limit: float | None
    target_value: DescriptorScalar | None
    tolerance: float
    rationale: str
    authored_by: str
    provenance: tuple[EvidenceRef, ...]
    review_status: str = "reviewed_contract_demonstration"
    physical_acceptance_status: str = "not_established"
    constraint_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        string(self.label, "constraint.label")
        if self.constraint_kind not in CONSTRAINT_KINDS:
            raise ConstraintContractError("unsupported constraint kind")
        if self.descriptor_registry_ref.contract_kind != "scalar_descriptor_registry":
            raise ConstraintContractError("constraint requires descriptor registry ref")
        if (
            self.descriptor_registry_ref.schema_version
            != SCALAR_DESCRIPTOR_REGISTRY_SCHEMA_VERSION
        ):
            raise ConstraintContractError("constraint descriptor registry schema mismatch")
        string(self.descriptor_id, "constraint.descriptor_id")
        string(self.descriptor_version, "constraint.descriptor_version")
        if self.scope_kind not in {"global", "semantic_region"}:
            raise ConstraintContractError("unsupported constraint scope")
        optional_string(self.region_type, "constraint.region_type")
        optional_string(self.side, "constraint.side")
        if self.scope_kind == "global":
            if self.region_type is not None or self.side is not None:
                raise ConstraintContractError("global constraint cannot select regions")
        else:
            if self.region_type is None:
                raise ConstraintContractError("regional constraint requires region_type")
            if self.side is not None and self.side not in {"left", "center", "right"}:
                raise ConstraintContractError("unsupported regional constraint side")
        if self.operator not in OPERATORS:
            raise ConstraintContractError("unsupported constraint operator")
        declared_unit = unit(self.unit, "constraint.unit")
        tolerance = non_negative(self.tolerance, "constraint.tolerance")
        lower = (
            number(self.lower_limit, "constraint.lower_limit")
            if self.lower_limit is not None
            else None
        )
        upper = (
            number(self.upper_limit, "constraint.upper_limit")
            if self.upper_limit is not None
            else None
        )
        target = self.target_value
        if self.operator == "between":
            if lower is None or upper is None or target is not None or lower > upper:
                raise ConstraintContractError("between requires ordered lower/upper limits only")
        elif self.operator == "greater_or_equal":
            if lower is None or upper is not None or target is not None:
                raise ConstraintContractError("greater_or_equal requires only lower_limit")
        elif self.operator == "less_or_equal":
            if upper is None or lower is not None or target is not None:
                raise ConstraintContractError("less_or_equal requires only upper_limit")
        elif self.operator == "approximately_equal":
            if lower is not None or upper is not None:
                raise ConstraintContractError("approximately_equal requires only target/tolerance")
            number(target, "constraint.target_value")
            if tolerance <= 0.0:
                raise ConstraintContractError("approximately_equal requires positive tolerance")
        else:
            if lower is not None or upper is not None or target is None:
                raise ConstraintContractError("equal requires only target_value")
            if declared_unit == "bool":
                boolean(target, "constraint.target_value")
            else:
                number(target, "constraint.target_value")
        string(self.rationale, "constraint.rationale")
        string(self.authored_by, "constraint.authored_by")
        if not self.provenance:
            raise ConstraintContractError("constraint requires provenance")
        if self.review_status != "reviewed_contract_demonstration":
            raise ConstraintContractError("unsupported R4 constraint review status")
        if self.physical_acceptance_status != "not_established":
            raise ConstraintContractError("R4 constraints cannot establish physical acceptance")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"engineering_constraint.{content[:16]}"
        _set_or_check_identity(self, content, expected_id, "engineering constraint")

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": ENGINEERING_CONSTRAINT_SCHEMA_VERSION,
            "label": self.label,
            "constraint_kind": self.constraint_kind,
            "descriptor_registry_ref": self.descriptor_registry_ref.to_mapping(),
            "descriptor_id": self.descriptor_id,
            "descriptor_version": self.descriptor_version,
            "scope_kind": self.scope_kind,
            "region_type": self.region_type,
            "side": self.side,
            "operator": self.operator,
            "unit": self.unit,
            "lower_limit": self.lower_limit,
            "upper_limit": self.upper_limit,
            "target_value": self.target_value,
            "tolerance": self.tolerance,
            "rationale": self.rationale,
            "authored_by": self.authored_by,
            "provenance": [item.to_mapping() for item in self.provenance],
            "review_status": self.review_status,
            "geometry_mutation_authority": "none",
            "physical_acceptance_status": self.physical_acceptance_status,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "constraint_id": self.constraint_id,
            "content_sha256": self.content_sha256,
        }

    def identity_ref(self) -> ContractIdentityRef:
        return ContractIdentityRef(
            "engineering_constraint",
            ENGINEERING_CONSTRAINT_SCHEMA_VERSION,
            self.constraint_id,
            self.content_sha256,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringConstraint":
        value = mapping(value, "constraint")
        required = {
            "schema_version",
            "label",
            "constraint_kind",
            "descriptor_registry_ref",
            "descriptor_id",
            "descriptor_version",
            "scope_kind",
            "region_type",
            "side",
            "operator",
            "unit",
            "lower_limit",
            "upper_limit",
            "target_value",
            "tolerance",
            "rationale",
            "authored_by",
            "provenance",
            "review_status",
            "geometry_mutation_authority",
            "physical_acceptance_status",
            "constraint_id",
            "content_sha256",
        }
        exact_keys(value, required, "constraint")
        if value["schema_version"] != ENGINEERING_CONSTRAINT_SCHEMA_VERSION:
            raise ConstraintContractError("unsupported engineering constraint schema")
        if value["geometry_mutation_authority"] != "none":
            raise ConstraintContractError("constraints cannot have geometry mutation authority")
        target = value["target_value"]
        if target is not None and not isinstance(target, (bool, int, float)):
            raise ConstraintContractError("constraint target must be scalar or null")
        return cls(
            label=string(value["label"], "constraint.label"),
            constraint_kind=string(
                value["constraint_kind"], "constraint.constraint_kind"
            ),
            descriptor_registry_ref=ContractIdentityRef.from_mapping(
                mapping(value["descriptor_registry_ref"], "constraint.descriptor_registry_ref")
            ),
            descriptor_id=string(value["descriptor_id"], "constraint.descriptor_id"),
            descriptor_version=string(
                value["descriptor_version"], "constraint.descriptor_version"
            ),
            scope_kind=string(value["scope_kind"], "constraint.scope_kind"),
            region_type=optional_string(value["region_type"], "constraint.region_type"),
            side=optional_string(value["side"], "constraint.side"),
            operator=string(value["operator"], "constraint.operator"),
            unit=unit(value["unit"], "constraint.unit"),
            lower_limit=(
                number(value["lower_limit"], "constraint.lower_limit")
                if value["lower_limit"] is not None
                else None
            ),
            upper_limit=(
                number(value["upper_limit"], "constraint.upper_limit")
                if value["upper_limit"] is not None
                else None
            ),
            target_value=target,
            tolerance=non_negative(value["tolerance"], "constraint.tolerance"),
            rationale=string(value["rationale"], "constraint.rationale"),
            authored_by=string(value["authored_by"], "constraint.authored_by"),
            provenance=tuple(
                EvidenceRef.from_mapping(mapping(item, "constraint.provenance"))
                for item in sequence(value["provenance"], "constraint.provenance")
            ),
            review_status=string(value["review_status"], "constraint.review_status"),
            physical_acceptance_status=string(
                value["physical_acceptance_status"],
                "constraint.physical_acceptance_status",
            ),
            constraint_id=string(value["constraint_id"], "constraint.constraint_id"),
            content_sha256=normalized_hash(
                value["content_sha256"], "constraint.content_sha256"
            ),
        )


@dataclass(frozen=True)
class ConstraintFinding:
    """One constraint result at a global or semantic-region location."""

    descriptor_value_id: str
    scope_id: str
    region_type: str | None
    side: str | None
    measured_value: DescriptorScalar
    unit: str
    passed: bool
    margin: float | None
    detail: str

    def __post_init__(self) -> None:
        string(self.descriptor_value_id, "constraint_finding.descriptor_value_id")
        string(self.scope_id, "constraint_finding.scope_id")
        optional_string(self.region_type, "constraint_finding.region_type")
        optional_string(self.side, "constraint_finding.side")
        declared_unit = unit(self.unit, "constraint_finding.unit")
        if declared_unit == "bool":
            boolean(self.measured_value, "constraint_finding.measured_value")
        else:
            number(self.measured_value, "constraint_finding.measured_value")
        boolean(self.passed, "constraint_finding.passed")
        if self.margin is not None:
            number(self.margin, "constraint_finding.margin")
        string(self.detail, "constraint_finding.detail")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "descriptor_value_id": self.descriptor_value_id,
            "scope_id": self.scope_id,
            "region_type": self.region_type,
            "side": self.side,
            "measured_value": self.measured_value,
            "unit": self.unit,
            "passed": self.passed,
            "margin": self.margin,
            "detail": self.detail,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConstraintFinding":
        value = mapping(value, "constraint_finding")
        required = {
            "descriptor_value_id",
            "scope_id",
            "region_type",
            "side",
            "measured_value",
            "unit",
            "passed",
            "margin",
            "detail",
        }
        exact_keys(value, required, "constraint_finding")
        measured = value["measured_value"]
        if not isinstance(measured, (bool, int, float)):
            raise ConstraintContractError("constraint finding measured value must be scalar")
        return cls(
            descriptor_value_id=string(
                value["descriptor_value_id"],
                "constraint_finding.descriptor_value_id",
            ),
            scope_id=string(value["scope_id"], "constraint_finding.scope_id"),
            region_type=optional_string(
                value["region_type"], "constraint_finding.region_type"
            ),
            side=optional_string(value["side"], "constraint_finding.side"),
            measured_value=measured,
            unit=unit(value["unit"], "constraint_finding.unit"),
            passed=boolean(value["passed"], "constraint_finding.passed"),
            margin=(
                number(value["margin"], "constraint_finding.margin")
                if value["margin"] is not None
                else None
            ),
            detail=string(value["detail"], "constraint_finding.detail"),
        )


@dataclass(frozen=True)
class ConstraintEvaluation:
    """Immutable evaluation linked to one constraint and observation bundle."""

    constraint_ref: ContractIdentityRef
    observation_bundle_ref: ContractIdentityRef
    instance_id: str
    constraint_kind: str
    evaluator_version: str
    findings: tuple[ConstraintFinding, ...]
    result: str
    violation_locations: tuple[str, ...]
    disposition: str
    geometry_mutation_status: str = "not_performed"
    live_cst_status: str = "not_run"
    physical_acceptance_status: str = "not_established"
    evaluation_id: str = ""
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if self.constraint_ref.contract_kind != "engineering_constraint":
            raise ConstraintContractError("evaluation requires engineering constraint ref")
        if self.constraint_ref.schema_version != ENGINEERING_CONSTRAINT_SCHEMA_VERSION:
            raise ConstraintContractError("evaluation constraint schema mismatch")
        if self.observation_bundle_ref.contract_kind != "observation_bundle":
            raise ConstraintContractError("evaluation requires observation bundle ref")
        if self.observation_bundle_ref.schema_version != OBSERVATION_BUNDLE_SCHEMA_VERSION:
            raise ConstraintContractError("evaluation observation bundle schema mismatch")
        string(self.instance_id, "constraint_evaluation.instance_id")
        if self.constraint_kind not in CONSTRAINT_KINDS:
            raise ConstraintContractError("unsupported evaluation constraint kind")
        if self.evaluator_version != CONSTRAINT_EVALUATOR_VERSION:
            raise ConstraintContractError("unsupported constraint evaluator version")
        if not self.findings:
            raise ConstraintContractError("constraint evaluation requires findings")
        if self.result not in {"pass", "violation"}:
            raise ConstraintContractError("unsupported constraint evaluation result")
        expected_violations = tuple(
            sorted(item.scope_id for item in self.findings if not item.passed)
        )
        if self.violation_locations != expected_violations:
            raise ConstraintContractError("constraint violation location mismatch")
        if (self.result == "pass") != (not self.violation_locations):
            raise ConstraintContractError("constraint result/violation mismatch")
        expected_disposition = _disposition(self.constraint_kind, self.result)
        if self.disposition != expected_disposition:
            raise ConstraintContractError("constraint disposition mismatch")
        if self.geometry_mutation_status != "not_performed":
            raise ConstraintContractError("constraint evaluation cannot mutate geometry")
        if self.live_cst_status != "not_run":
            raise ConstraintContractError("R4 constraint evaluation must remain no-CST")
        if self.physical_acceptance_status != "not_established":
            raise ConstraintContractError("R4 evaluation cannot claim physical acceptance")
        content = canonical_sha256(self._content_mapping())
        expected_id = f"{self.instance_id}.constraint_evaluation.{content[:16]}"
        _set_or_check_identity(self, content, expected_id, "constraint evaluation")

    @property
    def blocks_progression(self) -> bool:
        return self.constraint_kind == "hard" and self.result == "violation"

    def _content_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": CONSTRAINT_EVALUATION_SCHEMA_VERSION,
            "constraint_ref": self.constraint_ref.to_mapping(),
            "observation_bundle_ref": self.observation_bundle_ref.to_mapping(),
            "instance_id": self.instance_id,
            "constraint_kind": self.constraint_kind,
            "evaluator_version": self.evaluator_version,
            "findings": [item.to_mapping() for item in self.findings],
            "finding_count": len(self.findings),
            "result": self.result,
            "violation_locations": list(self.violation_locations),
            "disposition": self.disposition,
            "blocks_progression": self.blocks_progression,
            "geometry_mutation_status": self.geometry_mutation_status,
            "live_cst_status": self.live_cst_status,
            "physical_acceptance_status": self.physical_acceptance_status,
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            **self._content_mapping(),
            "evaluation_id": self.evaluation_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConstraintEvaluation":
        value = mapping(value, "constraint_evaluation")
        required = {
            "schema_version",
            "constraint_ref",
            "observation_bundle_ref",
            "instance_id",
            "constraint_kind",
            "evaluator_version",
            "findings",
            "finding_count",
            "result",
            "violation_locations",
            "disposition",
            "blocks_progression",
            "geometry_mutation_status",
            "live_cst_status",
            "physical_acceptance_status",
            "evaluation_id",
            "content_sha256",
        }
        exact_keys(value, required, "constraint_evaluation")
        if value["schema_version"] != CONSTRAINT_EVALUATION_SCHEMA_VERSION:
            raise ConstraintContractError("unsupported constraint evaluation schema")
        findings = tuple(
            ConstraintFinding.from_mapping(
                mapping(item, "constraint_evaluation.finding")
            )
            for item in sequence(value["findings"], "constraint_evaluation.findings")
        )
        if not isinstance(value["finding_count"], int) or isinstance(
            value["finding_count"], bool
        ):
            raise ConstraintContractError("constraint finding_count must be integer")
        if value["finding_count"] != len(findings):
            raise ConstraintContractError("constraint finding_count mismatch")
        result = cls(
            constraint_ref=ContractIdentityRef.from_mapping(
                mapping(value["constraint_ref"], "constraint_evaluation.constraint_ref")
            ),
            observation_bundle_ref=ContractIdentityRef.from_mapping(
                mapping(
                    value["observation_bundle_ref"],
                    "constraint_evaluation.observation_bundle_ref",
                )
            ),
            instance_id=string(
                value["instance_id"], "constraint_evaluation.instance_id"
            ),
            constraint_kind=string(
                value["constraint_kind"],
                "constraint_evaluation.constraint_kind",
            ),
            evaluator_version=string(
                value["evaluator_version"],
                "constraint_evaluation.evaluator_version",
            ),
            findings=findings,
            result=string(value["result"], "constraint_evaluation.result"),
            violation_locations=string_tuple(
                value["violation_locations"],
                "constraint_evaluation.violation_locations",
            ),
            disposition=string(
                value["disposition"], "constraint_evaluation.disposition"
            ),
            geometry_mutation_status=string(
                value["geometry_mutation_status"],
                "constraint_evaluation.geometry_mutation_status",
            ),
            live_cst_status=string(
                value["live_cst_status"], "constraint_evaluation.live_cst_status"
            ),
            physical_acceptance_status=string(
                value["physical_acceptance_status"],
                "constraint_evaluation.physical_acceptance_status",
            ),
            evaluation_id=string(
                value["evaluation_id"], "constraint_evaluation.evaluation_id"
            ),
            content_sha256=normalized_hash(
                value["content_sha256"], "constraint_evaluation.content_sha256"
            ),
        )
        if boolean(
            value["blocks_progression"],
            "constraint_evaluation.blocks_progression",
        ) != result.blocks_progression:
            raise ConstraintContractError("constraint blocks_progression mismatch")
        return result


def evaluate_constraint(
    constraint: EngineeringConstraint,
    bundle: ObservationBundle,
    registry: ScalarDescriptorRegistry,
) -> ConstraintEvaluation:
    """Evaluate one constraint without changing the bundle or geometry."""

    if constraint.descriptor_registry_ref != registry.identity_ref():
        raise ConstraintContractError("constraint descriptor registry identity mismatch")
    if bundle.descriptor_registry_ref != registry.identity_ref():
        raise ConstraintContractError("observation bundle descriptor registry mismatch")
    definition = registry.by_id.get(constraint.descriptor_id)
    if definition is None:
        raise ConstraintContractError("constraint references unknown descriptor")
    if (
        definition.descriptor_version != constraint.descriptor_version
        or definition.scope_kind != constraint.scope_kind
        or definition.unit != constraint.unit
    ):
        raise ConstraintContractError("constraint/descriptor definition mismatch")
    selected = [
        item
        for item in bundle.descriptor_values
        if item.descriptor_id == constraint.descriptor_id
        and item.scope_kind == constraint.scope_kind
        and (constraint.region_type is None or item.region_type == constraint.region_type)
        and (constraint.side is None or item.side == constraint.side)
    ]
    if not selected:
        raise ConstraintContractError("constraint selector matched no descriptor values")
    if any(item.status != "observed" or item.value is None for item in selected):
        raise ConstraintContractError(
            "constraint selector includes a non-applicable descriptor value"
        )
    findings = tuple(
        sorted(
            (_evaluate_value(constraint, item) for item in selected),
            key=lambda item: item.scope_id,
        )
    )
    violations = tuple(sorted(item.scope_id for item in findings if not item.passed))
    result = "violation" if violations else "pass"
    return ConstraintEvaluation(
        constraint_ref=constraint.identity_ref(),
        observation_bundle_ref=bundle.identity_ref(),
        instance_id=bundle.instance_id,
        constraint_kind=constraint.constraint_kind,
        evaluator_version=CONSTRAINT_EVALUATOR_VERSION,
        findings=findings,
        result=result,
        violation_locations=violations,
        disposition=_disposition(constraint.constraint_kind, result),
    )


def evaluate_constraints(
    constraints: tuple[EngineeringConstraint, ...],
    bundle: ObservationBundle,
    registry: ScalarDescriptorRegistry,
) -> tuple[ConstraintEvaluation, ...]:
    """Evaluate an ordered set and return evaluations sorted by identity."""

    evaluations = tuple(
        evaluate_constraint(item, bundle, registry) for item in constraints
    )
    return tuple(sorted(evaluations, key=lambda item: item.evaluation_id))


def build_demonstration_constraints(
    registry: ScalarDescriptorRegistry,
    provenance: tuple[EvidenceRef, ...],
    *,
    authored_by: str = "rf-cem-r4-contract-review",
) -> tuple[EngineeringConstraint, ...]:
    """Create reviewed R4 contract demonstrations, not physical design limits."""

    rationale = (
        "R4 contract demonstration only; this threshold exercises unit-aware "
        "evaluation and does not establish manufacturing or RF acceptance."
    )
    specs = (
        {
            "label": "Demonstration total cavity length window",
            "constraint_kind": "hard",
            "descriptor_id": GLOBAL_TOTAL_CAVITY_LENGTH,
            "scope_kind": "global",
            "operator": "between",
            "unit": "mm",
            "lower_limit": 450.0,
            "upper_limit": 650.0,
        },
        {
            "label": "Demonstration maximum radius target",
            "constraint_kind": "soft",
            "descriptor_id": GLOBAL_MAXIMUM_RADIUS,
            "scope_kind": "global",
            "operator": "approximately_equal",
            "unit": "mm",
            "target_value": 240.0,
            "tolerance": 15.0,
        },
        {
            "label": "Demonstration minimum aperture",
            "constraint_kind": "hard",
            "descriptor_id": GLOBAL_MINIMUM_APERTURE_RADIUS,
            "scope_kind": "global",
            "operator": "greater_or_equal",
            "unit": "mm",
            "lower_limit": 45.0,
        },
        {
            "label": "Demonstration minimum curvature radius",
            "constraint_kind": "advisory",
            "descriptor_id": GLOBAL_MINIMUM_RADIUS_OF_CURVATURE,
            "scope_kind": "global",
            "operator": "greater_or_equal",
            "unit": "mm",
            "lower_limit": 2.0,
        },
        {
            "label": "Diagnostic paired nose presence",
            "constraint_kind": "diagnostic",
            "descriptor_id": GLOBAL_NOSE_PRESENT,
            "scope_kind": "global",
            "operator": "equal",
            "unit": "bool",
            "target_value": True,
        },
        {
            "label": "Demonstration equator crest radius",
            "constraint_kind": "soft",
            "descriptor_id": REGION_EQUATOR_CREST_RADIUS,
            "scope_kind": "semantic_region",
            "region_type": "EquatorRegion",
            "operator": "greater_or_equal",
            "unit": "mm",
            "lower_limit": 225.0,
        },
    )
    definitions = registry.by_id
    constraints = []
    for spec in specs:
        descriptor_id = str(spec["descriptor_id"])
        definition = definitions[descriptor_id]
        constraints.append(
            EngineeringConstraint(
                label=str(spec["label"]),
                constraint_kind=str(spec["constraint_kind"]),
                descriptor_registry_ref=registry.identity_ref(),
                descriptor_id=descriptor_id,
                descriptor_version=definition.descriptor_version,
                scope_kind=str(spec["scope_kind"]),
                region_type=(
                    str(spec["region_type"])
                    if spec.get("region_type") is not None
                    else None
                ),
                side=None,
                operator=str(spec["operator"]),
                unit=str(spec["unit"]),
                lower_limit=(
                    float(spec["lower_limit"])
                    if spec.get("lower_limit") is not None
                    else None
                ),
                upper_limit=(
                    float(spec["upper_limit"])
                    if spec.get("upper_limit") is not None
                    else None
                ),
                target_value=spec.get("target_value"),
                tolerance=float(spec.get("tolerance", 1.0e-6)),
                rationale=rationale,
                authored_by=authored_by,
                provenance=provenance,
            )
        )
    return tuple(sorted(constraints, key=lambda item: item.constraint_id))


def load_engineering_constraint(path: Path) -> EngineeringConstraint:
    """Load one strict ``engineering_constraint.v0`` artifact."""

    return EngineeringConstraint.from_mapping(
        read_json_mapping(path, "engineering constraint")
    )


def load_constraint_evaluation(path: Path) -> ConstraintEvaluation:
    """Load one strict ``constraint_evaluation.v0`` artifact."""

    return ConstraintEvaluation.from_mapping(
        read_json_mapping(path, "constraint evaluation")
    )


def _evaluate_value(
    constraint: EngineeringConstraint, value: ScalarDescriptorValue
) -> ConstraintFinding:
    assert value.value is not None
    measured = value.value
    passed: bool
    margin: float | None
    if constraint.operator == "between":
        assert constraint.lower_limit is not None and constraint.upper_limit is not None
        numeric = number(measured, "constraint measured value")
        lower = constraint.lower_limit - constraint.tolerance
        upper = constraint.upper_limit + constraint.tolerance
        passed = lower <= numeric <= upper
        margin = min(numeric - lower, upper - numeric)
    elif constraint.operator == "greater_or_equal":
        assert constraint.lower_limit is not None
        numeric = number(measured, "constraint measured value")
        threshold = constraint.lower_limit - constraint.tolerance
        passed = numeric >= threshold
        margin = numeric - threshold
    elif constraint.operator == "less_or_equal":
        assert constraint.upper_limit is not None
        numeric = number(measured, "constraint measured value")
        threshold = constraint.upper_limit + constraint.tolerance
        passed = numeric <= threshold
        margin = threshold - numeric
    elif constraint.operator == "approximately_equal":
        assert constraint.target_value is not None
        numeric = number(measured, "constraint measured value")
        target = number(constraint.target_value, "constraint target")
        margin = constraint.tolerance - abs(numeric - target)
        passed = margin >= 0.0
    else:
        assert constraint.target_value is not None
        if constraint.unit == "bool":
            passed = boolean(measured, "constraint measured value") == boolean(
                constraint.target_value, "constraint target"
            )
            margin = None
        else:
            numeric = number(measured, "constraint measured value")
            target = number(constraint.target_value, "constraint target")
            margin = constraint.tolerance - abs(numeric - target)
            passed = margin >= 0.0
    detail = (
        f"{constraint.descriptor_id} {constraint.operator} at {value.scope_id}: "
        f"measured={measured} {constraint.unit}; result={'pass' if passed else 'violation'}"
    )
    return ConstraintFinding(
        descriptor_value_id=value.value_id,
        scope_id=value.scope_id,
        region_type=value.region_type,
        side=value.side,
        measured_value=measured,
        unit=value.unit,
        passed=passed,
        margin=margin,
        detail=detail,
    )


def _disposition(constraint_kind: str, result: str) -> str:
    if result == "pass":
        return "pass"
    return {
        "hard": "hard_violation",
        "soft": "soft_violation",
        "advisory": "advisory_violation",
        "diagnostic": "diagnostic_finding",
    }[constraint_kind]


def _set_or_check_identity(
    target: object, content: str, expected_id: str, label: str
) -> None:
    current_hash = getattr(target, "content_sha256")
    current_id_field = (
        "constraint_id" if hasattr(target, "constraint_id") else "evaluation_id"
    )
    current_id = getattr(target, current_id_field)
    if current_hash:
        if current_hash != content:
            raise ConstraintContractError(f"{label} content SHA-256 mismatch")
    else:
        object.__setattr__(target, "content_sha256", content)
    if current_id:
        if current_id != expected_id:
            raise ConstraintContractError(f"{label} ID mismatch")
    else:
        object.__setattr__(target, current_id_field, expected_id)


__all__ = [
    "CONSTRAINT_EVALUATION_SCHEMA_VERSION",
    "CONSTRAINT_EVALUATOR_VERSION",
    "CONSTRAINT_KINDS",
    "ConstraintEvaluation",
    "ConstraintFinding",
    "ENGINEERING_CONSTRAINT_SCHEMA_VERSION",
    "EngineeringConstraint",
    "OPERATORS",
    "build_demonstration_constraints",
    "evaluate_constraint",
    "evaluate_constraints",
    "load_constraint_evaluation",
    "load_engineering_constraint",
]
