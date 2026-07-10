"""Integrity-bound literature geometry candidates and no-CST previews.

The v0 generator reconstructs the symmetric SLS-2 ellipse parameterization
from a coherent ``L, l, r, R, a, b`` tuple.  All dimensions are millimetres.
The reconstructed second-ellipse axes are a declared geometry hypothesis;
the output is suitable for human review, not RF-performance reproduction.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from rf_cem.parametric_geometry.core.backend_cadquery import CadQueryGeometryBackend

from .types import (
    MUTABLE_REVIEW_FIELDS,
    REVIEW_STATUSES,
    LiteratureSemanticsError,
    canonical_sha256,
    write_json,
)
from .validator import assert_valid_semantic_package


GEOMETRY_CANDIDATE_SCHEMA_VERSION = "literature_geometry_candidate.v0"
GEOMETRY_GENERATION_SCHEMA_VERSION = "literature_geometry_generation.v0"
GEOMETRY_PREVIEW_SCHEMA_VERSION = "literature_geometry_preview.v0"
SLS2_GENERATOR_VERSION = "symmetric_elliptical_four_quarter_arcs.v0"
_SLS2_PUBLISHED_SOURCE_ROLES = {
    "paper_figure_3_symmetric_parameterization": "sls2_p8_spline",
    "published_candidate_row": "sls2_p9_material_table",
}


class LiteratureGeometryCandidateError(ValueError):
    """Raised when a literature geometry candidate is unsafe or inconsistent."""


@dataclass(frozen=True)
class Sls2GeometryParameters:
    """Symmetric SLS-2 cavity dimensions in millimetres.

    ``L`` is total axial length, ``l`` is each straight beam-pipe length,
    ``r`` is beam-pipe radius, ``R`` is equator radius, and ``a``/``b`` are
    the axial/radial semi-axes of the equator-side quarter ellipse.
    """

    L: float
    l: float
    r: float
    R: float
    a: float
    b: float

    def __post_init__(self) -> None:
        raw_values = {"L": self.L, "l": self.l, "r": self.r, "R": self.R, "a": self.a, "b": self.b}
        for name, raw_value in raw_values.items():
            if isinstance(raw_value, bool):
                raise LiteratureGeometryCandidateError(f"{name} must be a finite number in mm")
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise LiteratureGeometryCandidateError(f"{name} must be a finite number in mm") from exc
            if not math.isfinite(value):
                raise LiteratureGeometryCandidateError(f"{name} must be a finite number in mm")
            object.__setattr__(self, name, value)
        if self.l < 0.0:
            raise LiteratureGeometryCandidateError("l must be non-negative")
        if self.r <= 0.0:
            raise LiteratureGeometryCandidateError("r must be greater than zero")
        if self.L <= 2.0 * self.l:
            raise LiteratureGeometryCandidateError("L must be greater than 2*l")
        if not 0.0 < self.a < self.h:
            raise LiteratureGeometryCandidateError("a must satisfy 0 < a < h, where h = L/2 - l")
        if not 0.0 < self.b < self.R - self.r:
            raise LiteratureGeometryCandidateError("b must satisfy 0 < b < R-r")

    @property
    def h(self) -> float:
        """Return the curved half-cell axial span in millimetres."""
        return float(self.L) / 2.0 - float(self.l)

    def as_values(self) -> dict[str, float]:
        """Return the coherent six-parameter tuple as JSON-safe floats."""
        return {
            "L": float(self.L),
            "l": float(self.l),
            "r": float(self.r),
            "R": float(self.R),
            "a": float(self.a),
            "b": float(self.b),
        }

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "Sls2GeometryParameters":
        """Build parameters from a mapping with exactly ``L,l,r,R,a,b``."""
        required = {"L", "l", "r", "R", "a", "b"}
        missing = sorted(required - set(values))
        extra = sorted(set(values) - required)
        if missing or extra:
            detail = []
            if missing:
                detail.append(f"missing={missing}")
            if extra:
                detail.append(f"extra={extra}")
            raise LiteratureGeometryCandidateError("invalid parameter tuple: " + ", ".join(detail))
        converted: dict[str, float] = {}
        for name in required:
            if isinstance(values[name], bool):
                raise LiteratureGeometryCandidateError("all geometry parameters must be numeric in mm")
            try:
                converted[name] = float(values[name])
            except (TypeError, ValueError) as exc:
                raise LiteratureGeometryCandidateError("all geometry parameters must be numeric in mm") from exc
        return cls(**converted)


def build_sls2_geometry_candidate(
    semantic_package: Mapping[str, Any],
    *,
    candidate_id: str,
    parameters: Sls2GeometryParameters | Mapping[str, Any],
    evidence_refs: Sequence[str],
    semantic_paths: Sequence[str],
    review_status: str = "pending",
    review_note: str = "",
    reviewer: str | None = None,
    reviewed_at: str | None = None,
    samples_per_quarter: int = 25,
) -> dict[str, Any]:
    """Build a deterministic, semantic-package-bound SLS-2 candidate.

    The six dimensions are intentionally indivisible: callers cannot accept
    or regenerate one dimension independently of the evidence-bound tuple.
    Review fields remain mutable without invalidating the immutable hash.
    """
    _assert_semantic_package(semantic_package)
    _assert_sls2_scope(semantic_package)
    if not candidate_id or not candidate_id.strip():
        raise LiteratureGeometryCandidateError("candidate_id must be non-empty")
    params = (
        parameters
        if isinstance(parameters, Sls2GeometryParameters)
        else Sls2GeometryParameters.from_mapping(parameters)
    )
    refs = _validated_evidence_refs(evidence_refs, semantic_package)
    required_role_refs = set(_SLS2_PUBLISHED_SOURCE_ROLES.values())
    if not required_role_refs.issubset(set(refs)):
        raise LiteratureGeometryCandidateError(
            "SLS-2 candidate requires sls2_p8_spline for Figure 3 and sls2_p9_material_table for the candidate row"
        )
    paths = _validated_semantic_paths(semantic_paths, semantic_package)
    _validate_review_status(review_status)
    samples = _validate_sample_count(samples_per_quarter)

    candidate: dict[str, Any] = {
        "schema_version": GEOMETRY_CANDIDATE_SCHEMA_VERSION,
        "candidate_id": candidate_id.strip(),
        "generator": {
            "id": SLS2_GENERATOR_VERSION,
            "axis": "z",
            "model_type": "axisymmetric_rf_vacuum_single_cell",
            "samples_per_quarter": samples,
        },
        "parameter_tuple": {
            "tuple_id": f"{candidate_id.strip()}.published_parameter_tuple",
            "origin": "published_candidate",
            "unit": "mm",
            "values": params.as_values(),
            "derived": {
                "h": params.h,
                "lower_ellipse_axial_semi_axis": params.h - params.a,
                "lower_ellipse_radial_semi_axis": params.R - params.r - params.b,
            },
            "coherence_policy": "fixed_study_dimensions_plus_one_published_candidate_row",
            "source_refs": refs,
            "source_roles": copy.deepcopy(_SLS2_PUBLISHED_SOURCE_ROLES),
        },
        "semantic_binding": {
            "semantic_package_sha256": canonical_sha256(dict(semantic_package)),
            "semantic_paths": paths,
        },
        "approximation": {
            "paper_curve_model": "four_90_degree_ellipse_arcs",
            "paper_definition": (
                "Paper Figure 3 defines the symmetric L,l,r,R,a,b section; the existing "
                "sls2_p8_spline evidence record is used as its bundle-level provenance anchor."
            ),
            "reconstruction_hypothesis": (
                "The lower quarter-ellipse semi-axes are h-a and R-r-b so the four arcs "
                "meet the equator and beam pipe with source-model G1 tangency. This derivation "
                "is a reconstruction hypothesis, not a claim that Figure 1 supplies the exact symmetric candidate."
            ),
            "kernel_representation": "cadquery.Workplane.splineApprox_degree_at_most_5_from_analytic_samples",
            "analytic_samples_lie_on_source_ellipses": True,
            "exact_conic_in_step": False,
        },
        "execution_policy": {
            "mode": "preview_only",
            "production_merge_allowed": False,
            "live_cst_allowed": False,
        },
        "review": {
            "human_review_status": review_status,
            "review_note": review_note,
            "review_note_language": "zh-CN",
            **({"reviewer": reviewer} if reviewer is not None else {}),
            **({"reviewed_at": reviewed_at} if reviewed_at is not None else {}),
        },
        "integrity": {
            "algorithm": "sha256",
            "semantic_package_sha256": canonical_sha256(dict(semantic_package)),
        },
    }
    candidate["integrity"]["candidate_content_sha256"] = candidate_content_sha256(candidate)
    candidate["integrity"]["immutable_candidate_sha256"] = immutable_candidate_sha256(candidate)
    return candidate


def build_sls2_preview_variant(
    parent_candidate: Mapping[str, Any],
    semantic_package: Mapping[str, Any],
    *,
    candidate_id: str,
    parameters: Sls2GeometryParameters | Mapping[str, Any],
    review_status: str = "pending",
    review_note: str = "",
    reviewer: str | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    """Build a human-edited preview while preserving paper provenance.

    Edited dimensions are never attributed to the paper.  The original
    published tuple is retained under ``paper_baseline`` and the new immutable
    candidate binds the immediate parent's id and content hashes.
    """
    validate_geometry_candidate(parent_candidate, semantic_package)
    if parent_candidate["review"]["human_review_status"] == "rejected":
        raise LiteratureGeometryCandidateError("cannot iterate from a rejected parent candidate")
    if candidate_id.strip() == str(parent_candidate["candidate_id"]):
        raise LiteratureGeometryCandidateError("preview variant candidate_id must differ from its parent")
    parent_tuple = parent_candidate["parameter_tuple"]
    if parent_tuple["origin"] == "published_candidate":
        paper_baseline = {
            "candidate_id": parent_candidate["candidate_id"],
            "immutable_candidate_sha256": parent_candidate["integrity"]["immutable_candidate_sha256"],
            "candidate_content_sha256": parent_candidate["integrity"]["candidate_content_sha256"],
            "parameter_tuple": copy.deepcopy(parent_tuple),
        }
    else:
        paper_baseline = copy.deepcopy(parent_candidate["paper_baseline"])
    baseline_tuple = paper_baseline["parameter_tuple"]
    candidate = build_sls2_geometry_candidate(
        semantic_package,
        candidate_id=candidate_id,
        parameters=parameters,
        evidence_refs=baseline_tuple["source_refs"],
        semantic_paths=parent_candidate["semantic_binding"]["semantic_paths"],
        review_status=review_status,
        review_note=review_note,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        samples_per_quarter=int(parent_candidate["generator"]["samples_per_quarter"]),
    )
    edited_tuple = candidate["parameter_tuple"]
    edited_tuple["tuple_id"] = f"{candidate_id.strip()}.human_preview_parameter_tuple"
    edited_tuple["origin"] = "human_preview_edit"
    edited_tuple["coherence_policy"] = "human_edit_of_one_coherent_parent_tuple"
    edited_tuple["source_refs"] = []
    edited_tuple.pop("source_roles", None)
    edited_tuple["value_provenance"] = {
        "kind": "human_preview_edit",
        "published_value_claim": False,
    }
    candidate["lineage"] = {
        "parent_candidate_id": parent_candidate["candidate_id"],
        "parent_immutable_candidate_sha256": parent_candidate["integrity"]["immutable_candidate_sha256"],
        "parent_candidate_content_sha256": parent_candidate["integrity"]["candidate_content_sha256"],
    }
    candidate["paper_baseline"] = paper_baseline
    candidate["integrity"] = {
        "algorithm": "sha256",
        "semantic_package_sha256": canonical_sha256(dict(semantic_package)),
    }
    candidate["integrity"]["candidate_content_sha256"] = candidate_content_sha256(candidate)
    candidate["integrity"]["immutable_candidate_sha256"] = immutable_candidate_sha256(candidate)
    validate_geometry_candidate(candidate, semantic_package, parent_candidate=parent_candidate)
    return candidate


def immutable_candidate_sha256(candidate: Mapping[str, Any]) -> str:
    """Hash the candidate while excluding only mutable human-review fields."""
    projected = copy.deepcopy(dict(candidate))
    integrity = projected.get("integrity")
    if isinstance(integrity, dict):
        integrity.pop("immutable_candidate_sha256", None)
    review = projected.get("review")
    if isinstance(review, dict):
        for key in MUTABLE_REVIEW_FIELDS:
            review.pop(key, None)
    return canonical_sha256(projected)


def candidate_content_sha256(candidate: Mapping[str, Any]) -> str:
    """Hash the candidate id and geometry-defining immutable content."""
    fields = (
        "schema_version",
        "candidate_id",
        "generator",
        "parameter_tuple",
        "semantic_binding",
        "approximation",
        "execution_policy",
        "lineage",
        "paper_baseline",
    )
    return canonical_sha256({key: copy.deepcopy(candidate[key]) for key in fields if key in candidate})


def candidate_snapshot_sha256(candidate: Mapping[str, Any]) -> str:
    """Hash the complete current candidate, including mutable review fields."""
    return canonical_sha256(dict(candidate))


def validate_geometry_candidate(
    candidate: Mapping[str, Any],
    semantic_package: Mapping[str, Any],
    *,
    parent_candidate: Mapping[str, Any] | None = None,
) -> None:
    """Validate candidate structure, tuple guards, provenance, and hashes."""
    _assert_semantic_package(semantic_package)
    _assert_sls2_scope(semantic_package)
    if candidate.get("schema_version") != GEOMETRY_CANDIDATE_SCHEMA_VERSION:
        raise LiteratureGeometryCandidateError(f"expected schema_version {GEOMETRY_CANDIDATE_SCHEMA_VERSION!r}")
    if not str(candidate.get("candidate_id", "")).strip():
        raise LiteratureGeometryCandidateError("candidate_id must be non-empty")

    generator = candidate.get("generator")
    if not isinstance(generator, Mapping) or generator.get("id") != SLS2_GENERATOR_VERSION:
        raise LiteratureGeometryCandidateError(f"unsupported generator; expected {SLS2_GENERATOR_VERSION!r}")
    if generator.get("axis") != "z":
        raise LiteratureGeometryCandidateError("SLS-2 v0 generator supports only the z axis")
    _validate_sample_count(generator.get("samples_per_quarter"))

    parameter_tuple = candidate.get("parameter_tuple")
    if not isinstance(parameter_tuple, Mapping):
        raise LiteratureGeometryCandidateError("parameter_tuple must be a mapping")
    _validate_parameter_tuple_geometry(parameter_tuple)
    origin = parameter_tuple.get("origin")
    if origin == "published_candidate":
        _validate_published_tuple_provenance(parameter_tuple, semantic_package)
        if "lineage" in candidate or "paper_baseline" in candidate:
            raise LiteratureGeometryCandidateError("published candidate cannot carry human-edit lineage")
    elif origin == "human_preview_edit":
        if parameter_tuple.get("source_refs") != [] or "source_roles" in parameter_tuple:
            raise LiteratureGeometryCandidateError("human_preview_edit tuple cannot claim paper source_refs")
        provenance = parameter_tuple.get("value_provenance")
        if not isinstance(provenance, Mapping) or provenance.get("kind") != "human_preview_edit":
            raise LiteratureGeometryCandidateError("human_preview_edit tuple is missing value_provenance")
        if provenance.get("published_value_claim") is not False:
            raise LiteratureGeometryCandidateError("human_preview_edit cannot make a published value claim")
        _validate_variant_lineage(candidate, semantic_package, parent_candidate)
    else:
        raise LiteratureGeometryCandidateError(
            "parameter_tuple.origin must be published_candidate or human_preview_edit"
        )

    binding = candidate.get("semantic_binding")
    if not isinstance(binding, Mapping):
        raise LiteratureGeometryCandidateError("semantic_binding must be a mapping")
    expected_semantic_hash = canonical_sha256(dict(semantic_package))
    if binding.get("semantic_package_sha256") != expected_semantic_hash:
        raise LiteratureGeometryCandidateError("semantic_binding.semantic_package_sha256 mismatch")
    _validated_semantic_paths(binding.get("semantic_paths", []), semantic_package)

    policy = candidate.get("execution_policy")
    if not isinstance(policy, Mapping) or policy.get("mode") != "preview_only":
        raise LiteratureGeometryCandidateError("geometry candidates must remain preview_only")
    if policy.get("production_merge_allowed") is not False or policy.get("live_cst_allowed") is not False:
        raise LiteratureGeometryCandidateError("preview candidate cannot enable production merge or live CST")
    review = candidate.get("review")
    if not isinstance(review, Mapping):
        raise LiteratureGeometryCandidateError("review must be a mapping")
    _validate_review_status(review.get("human_review_status"))

    integrity = candidate.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("algorithm") != "sha256":
        raise LiteratureGeometryCandidateError("candidate is missing supported integrity metadata")
    if integrity.get("semantic_package_sha256") != expected_semantic_hash:
        raise LiteratureGeometryCandidateError("integrity semantic_package_sha256 mismatch")
    if integrity.get("candidate_content_sha256") != candidate_content_sha256(candidate):
        raise LiteratureGeometryCandidateError("candidate_content_sha256 mismatch")
    if integrity.get("immutable_candidate_sha256") != immutable_candidate_sha256(candidate):
        raise LiteratureGeometryCandidateError("immutable_candidate_sha256 mismatch")


def build_sls2_profile(
    parameters: Sls2GeometryParameters | Mapping[str, Any],
    *,
    samples_per_quarter: int = 25,
) -> dict[str, Any]:
    """Return a pure symmetric r-z profile for fast GUI preview.

    The analytic quarter-ellipse samples are passed to CadQuery as NURBS-like
    ``splineApprox`` input.  The resulting STEP therefore approximates, rather
    than encodes, exact conics.
    """
    params = (
        parameters
        if isinstance(parameters, Sls2GeometryParameters)
        else Sls2GeometryParameters.from_mapping(parameters)
    )
    samples = _validate_sample_count(samples_per_quarter)
    right_upper = _sample_quarter_ellipse(
        center_z=0.0,
        center_r=params.R - params.b,
        semi_z=params.a,
        semi_r=params.b,
        start_angle=math.pi / 2.0,
        end_angle=0.0,
        count=samples,
    )
    right_lower = _sample_quarter_ellipse(
        center_z=params.h,
        center_r=params.R - params.b,
        semi_z=params.h - params.a,
        semi_r=params.R - params.r - params.b,
        start_angle=math.pi,
        end_angle=3.0 * math.pi / 2.0,
        count=samples,
    )
    left_lower = [(-z, radius) for z, radius in reversed(right_lower)]
    left_upper = [(-z, radius) for z, radius in reversed(right_upper)]
    refs = {
        "left_lower": ["feature.beam_pipe_left", "feature.ellipse_wall_left"],
        "left_upper": ["feature.ellipse_wall_left", "feature.equator"],
        "right_upper": ["feature.equator", "feature.ellipse_wall_right"],
        "right_lower": ["feature.ellipse_wall_right", "feature.beam_pipe_right"],
    }
    segments = [
        _line_segment(
            "seg_beam_pipe_left",
            (-params.L / 2.0, params.r),
            (-params.h, params.r),
            ["feature.beam_pipe_left"],
        ),
        _ellipse_approximation_segment("seg_ellipse_left_lower", left_lower, refs["left_lower"]),
        _ellipse_approximation_segment("seg_ellipse_left_upper", left_upper, refs["left_upper"]),
        _ellipse_approximation_segment("seg_ellipse_right_upper", right_upper, refs["right_upper"]),
        _ellipse_approximation_segment("seg_ellipse_right_lower", right_lower, refs["right_lower"]),
        _line_segment(
            "seg_beam_pipe_right",
            (params.h, params.r),
            (params.L / 2.0, params.r),
            ["feature.beam_pipe_right"],
        ),
    ]
    profile_points: list[tuple[float, float]] = []
    for segment in segments:
        sampled = segment.get("sampled_points") or [segment["start"], segment["end"]]
        points = [(float(point["z"]), float(point["r"])) for point in sampled]
        if profile_points and points:
            points = points[1:]
        profile_points.extend(points)
    return {
        "axis": "z",
        "unit": "mm",
        "points": [{"z_mm": z, "r_mm": radius} for z, radius in profile_points],
        "segments": segments,
        "symmetry": {"plane": "z=0", "left_right_mirrored": True},
        "approximation": {
            "source": "analytic_four_quarter_ellipses",
            "kernel": "cadquery.Workplane.splineApprox",
            "degree_max": 5,
            "samples_per_quarter": samples,
            "exact_conic_in_step": False,
        },
    }


def build_sls2_preview(
    candidate: Mapping[str, Any],
    semantic_package: Mapping[str, Any],
    *,
    parent_candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the pure, no-kernel payload used for immediate GUI rendering."""
    validate_geometry_candidate(candidate, semantic_package, parent_candidate=parent_candidate)
    parameter_tuple = candidate["parameter_tuple"]
    parameters = Sls2GeometryParameters.from_mapping(parameter_tuple["values"])
    profile = build_sls2_profile(parameters, samples_per_quarter=int(candidate["generator"]["samples_per_quarter"]))
    origin = str(parameter_tuple["origin"])
    if origin == "published_candidate":
        evidence_refs = list(parameter_tuple["source_refs"])
        evidence_relation = "published_value_provenance"
    else:
        evidence_refs = list(candidate["paper_baseline"]["parameter_tuple"]["source_refs"])
        evidence_relation = "paper_baseline_context_only"
    payload = {
        "schema_version": GEOMETRY_PREVIEW_SCHEMA_VERSION,
        "candidate_id": candidate["candidate_id"],
        "generator_id": SLS2_GENERATOR_VERSION,
        "parameter_tuple": copy.deepcopy(parameter_tuple),
        "guards": {
            "L_gt_2l": parameters.L > 2.0 * parameters.l,
            "h_mm": parameters.h,
            "a_between_0_and_h": 0.0 < parameters.a < parameters.h,
            "b_between_0_and_R_minus_r": 0.0 < parameters.b < parameters.R - parameters.r,
            "r_gt_0": parameters.r > 0.0,
        },
        "profile": profile,
        "features": _preview_features(evidence_refs, evidence_relation),
        "udsg": _preview_udsg(evidence_refs, origin),
        "review": copy.deepcopy(candidate["review"]),
        "policy": copy.deepcopy(candidate["execution_policy"]),
    }
    if origin == "human_preview_edit":
        payload["lineage"] = copy.deepcopy(candidate["lineage"])
        payload["paper_baseline"] = copy.deepcopy(candidate["paper_baseline"])
    return payload


def generate_sls2_step(
    candidate: Mapping[str, Any],
    semantic_package: Mapping[str, Any],
    *,
    output_step: Path,
    output_report: Path | None = None,
    backend: CadQueryGeometryBackend | None = None,
    parent_candidate: Mapping[str, Any] | None = None,
    deflection_mm: float = 0.5,
) -> dict[str, Any]:
    """Generate and validate an SLS-2 preview STEP without CST or a seed STEP."""
    preview = build_sls2_preview(candidate, semantic_package, parent_candidate=parent_candidate)
    if candidate["review"]["human_review_status"] == "rejected":
        raise LiteratureGeometryCandidateError("rejected geometry candidates cannot be generated")
    if isinstance(deflection_mm, bool) or not math.isfinite(float(deflection_mm)) or float(deflection_mm) <= 0.0:
        raise LiteratureGeometryCandidateError("deflection_mm must be a positive finite value")
    profile = preview["profile"]
    profile_points = [(float(point["z_mm"]), float(point["r_mm"])) for point in profile["points"]]
    output_step = Path(output_step)
    kernel = (backend or CadQueryGeometryBackend()).generate(
        output_step=output_step,
        axis="z",
        profile_points=profile_points,
        profile_segments=profile["segments"],
        deflection_mm=float(deflection_mm),
    )
    validation = _generation_validation(kernel, output_step, preview)
    mesh = copy.deepcopy(kernel.get("generated_mesh", {}))
    report: dict[str, Any] = {
        "schema_version": GEOMETRY_GENERATION_SCHEMA_VERSION,
        "mode": "preview_only",
        "candidate_id": candidate["candidate_id"],
        "review_status": candidate["review"]["human_review_status"],
        "integrity": {
            "semantic_package_sha256": candidate["integrity"]["semantic_package_sha256"],
            "candidate_content_sha256": candidate["integrity"]["candidate_content_sha256"],
            "immutable_candidate_sha256": candidate["integrity"]["immutable_candidate_sha256"],
            "candidate_snapshot_sha256": candidate_snapshot_sha256(candidate),
        },
        "parameter_tuple": copy.deepcopy(candidate["parameter_tuple"]),
        "profile": profile,
        "preview": {
            "baseline": None,
            "previous": None,
            "current": {
                "label": str(candidate["candidate_id"]),
                "candidate_id": candidate["candidate_id"],
                "profile_points": [[z, radius] for z, radius in profile_points],
                "mesh": mesh,
                "step_path": str(output_step),
            },
        },
        "geometry": {
            "model_type": "axisymmetric_rf_vacuum_single_cell",
            "axis": "z",
            "unit": "mm",
            "step_path": str(output_step),
            "kernel_metrics": copy.deepcopy(kernel.get("generated", {})),
        },
        "features": preview["features"],
        "udsg": preview["udsg"],
        "validation": validation,
        "kernel_report": kernel,
    }
    if candidate["parameter_tuple"]["origin"] == "human_preview_edit":
        report["lineage"] = copy.deepcopy(candidate["lineage"])
        report["paper_baseline"] = copy.deepcopy(candidate["paper_baseline"])
        baseline_tuple = candidate["paper_baseline"]["parameter_tuple"]
        baseline_profile = build_sls2_profile(
            baseline_tuple["values"],
            samples_per_quarter=int(candidate["generator"]["samples_per_quarter"]),
        )
        report["preview"]["baseline"] = _profile_trace(
            candidate["paper_baseline"]["candidate_id"],
            baseline_profile,
            provenance="published_candidate",
        )
        if parent_candidate is not None:
            parent_profile = build_sls2_profile(
                parent_candidate["parameter_tuple"]["values"],
                samples_per_quarter=int(parent_candidate["generator"]["samples_per_quarter"]),
            )
            report["preview"]["previous"] = _profile_trace(
                parent_candidate["candidate_id"],
                parent_profile,
                provenance=str(parent_candidate["parameter_tuple"]["origin"]),
            )
    if output_report is not None:
        write_json(Path(output_report), report)
    return report


def _generation_validation(kernel: Mapping[str, Any], output_step: Path, preview: Mapping[str, Any]) -> dict[str, Any]:
    blocking: list[str] = []
    warnings = [
        "STEP curves are splineApprox fits (degree at most 5) through analytic "
        "ellipse samples, not exact conic entities.",
        "Geometry validity and visual similarity do not reproduce RF performance.",
    ]
    if preview.get("review", {}).get("human_review_status") == "pending":
        warnings.append("Candidate is pending human review and remains preview-only.")
    generated = kernel.get("generated")
    if not isinstance(generated, Mapping):
        blocking.append("kernel report is missing generated metrics")
        generated = {}
    elif generated.get("brep_valid") is not True:
        blocking.append("generated BRep is invalid")
    if not output_step.exists() or output_step.stat().st_size <= 0:
        blocking.append("generated STEP file is missing or empty")
    mesh = kernel.get("generated_mesh")
    if not isinstance(mesh, Mapping) or not mesh.get("vertices") or not mesh.get("triangles"):
        blocking.append("generated mesh is empty")
    curve_generation = kernel.get("curve_generation")
    if not isinstance(curve_generation, Mapping) or curve_generation.get("mode") != "cadquery_curve_segments":
        blocking.append("quarter-ellipse splineApprox generation fell back from curve segments")
    else:
        approximations = curve_generation.get("approximations") or []
        sampled = [item for item in approximations if item.get("input_source") == "sampled_points"]
        if len(sampled) != 4:
            blocking.append("kernel did not confirm four sampled-point spline approximations")
        for fallback in curve_generation.get("fallbacks") or []:
            warnings.append(str(fallback))
    if generated:
        _check_generated_bounds(generated, preview, blocking)
        if float(generated.get("volume_mm3") or 0.0) <= 0.0:
            blocking.append("generated solid has non-positive volume")
    return {
        "pass": not blocking,
        "blocking_errors": blocking,
        "warnings": warnings,
        "generated": copy.deepcopy(generated),
        "curve_generation": copy.deepcopy(curve_generation),
        "step_path": str(output_step),
    }


def _check_generated_bounds(
    generated: Mapping[str, Any],
    preview: Mapping[str, Any],
    blocking: list[str],
    tolerance_mm: float = 0.5,
) -> None:
    bbox = generated.get("bbox_mm")
    values = preview["parameter_tuple"]["values"]
    if not isinstance(bbox, Mapping):
        blocking.append("generated metrics are missing bbox_mm")
        return
    axial = (float(bbox.get("zmin", math.nan)), float(bbox.get("zmax", math.nan)))
    expected_axial = (-float(values["L"]) / 2.0, float(values["L"]) / 2.0)
    radial = max(
        abs(float(bbox.get("xmin", math.nan))),
        abs(float(bbox.get("xmax", math.nan))),
        abs(float(bbox.get("ymin", math.nan))),
        abs(float(bbox.get("ymax", math.nan))),
    )
    if any(not math.isfinite(value) for value in (*axial, radial)):
        blocking.append("generated bounding box contains non-finite values")
        return
    if max(abs(axial[0] - expected_axial[0]), abs(axial[1] - expected_axial[1])) > tolerance_mm:
        blocking.append("generated axial extent does not match L")
    if abs(radial - float(values["R"])) > tolerance_mm:
        blocking.append("generated radial extent does not match R")


def _line_segment(
    segment_id: str,
    start: tuple[float, float],
    end: tuple[float, float],
    feature_refs: list[str],
) -> dict[str, Any]:
    points = [{"z": float(start[0]), "r": float(start[1])}, {"z": float(end[0]), "r": float(end[1])}]
    return {
        "id": segment_id,
        "kind": "line",
        "start": points[0],
        "end": points[-1],
        "curve": {"type": "line"},
        "sampled_points": points,
        "feature_refs": feature_refs,
        "continuity_start": "G1_source",
        "continuity_end": "G1_source",
    }


def _ellipse_approximation_segment(
    segment_id: str,
    points: list[tuple[float, float]],
    feature_refs: list[str],
) -> dict[str, Any]:
    sampled = [{"z": float(z), "r": float(radius)} for z, radius in points]
    return {
        "id": segment_id,
        "kind": "nurbs",
        "start": sampled[0],
        "end": sampled[-1],
        "curve": {
            "type": "nurbs_approximation",
            "degree_max": 5,
            "source_curve": "analytic_90_degree_ellipse_arc",
            "sampled_points": sampled,
            "approximation_method": "cadquery.Workplane.splineApprox",
            "exact_conic": False,
        },
        "sampled_points": sampled,
        "feature_refs": feature_refs,
        "continuity_start": "G1_source_spline_approximated",
        "continuity_end": "G1_source_spline_approximated",
    }


def _sample_quarter_ellipse(
    *,
    center_z: float,
    center_r: float,
    semi_z: float,
    semi_r: float,
    start_angle: float,
    end_angle: float,
    count: int,
) -> list[tuple[float, float]]:
    return [
        (
            center_z + semi_z * math.cos(start_angle + (end_angle - start_angle) * index / (count - 1)),
            center_r + semi_r * math.sin(start_angle + (end_angle - start_angle) * index / (count - 1)),
        )
        for index in range(count)
    ]


def _preview_features(evidence_refs: list[str], evidence_relation: str) -> list[dict[str, Any]]:
    features = [
        {
            "id": "feature.beam_pipe_left",
            "type": "beam_pipe",
            "segment_refs": ["seg_beam_pipe_left"],
            "parameter_refs": ["l", "r"],
            "evidence_refs": evidence_refs,
        },
        {
            "id": "feature.ellipse_wall_left",
            "type": "two_quarter_ellipse_wall",
            "segment_refs": ["seg_ellipse_left_lower", "seg_ellipse_left_upper"],
            "parameter_refs": ["L", "l", "r", "R", "a", "b"],
            "evidence_refs": evidence_refs,
        },
        {
            "id": "feature.equator",
            "type": "equator",
            "segment_refs": ["seg_ellipse_left_upper", "seg_ellipse_right_upper"],
            "parameter_refs": ["R", "a", "b"],
            "evidence_refs": evidence_refs,
        },
        {
            "id": "feature.ellipse_wall_right",
            "type": "two_quarter_ellipse_wall",
            "segment_refs": ["seg_ellipse_right_upper", "seg_ellipse_right_lower"],
            "parameter_refs": ["L", "l", "r", "R", "a", "b"],
            "evidence_refs": evidence_refs,
        },
        {
            "id": "feature.beam_pipe_right",
            "type": "beam_pipe",
            "segment_refs": ["seg_beam_pipe_right"],
            "parameter_refs": ["l", "r"],
            "evidence_refs": evidence_refs,
        },
    ]
    for feature in features:
        feature["evidence_relation"] = evidence_relation
    return features


def _preview_udsg(evidence_refs: list[str], origin: str) -> dict[str, Any]:
    if origin == "human_preview_edit":
        return {
            "schema_version": "literature_geometry_udsg.preview.v0",
            "nodes": [
                {"id": "evidence", "kind": "literature_evidence", "refs": evidence_refs},
                {"id": "paper_baseline", "kind": "published_parameter_tuple"},
                {"id": "parameter_tuple", "kind": "human_preview_edit"},
                {"id": "profile", "kind": "symmetric_rz_profile"},
                {"id": "step", "kind": "preview_step"},
            ],
            "edges": [
                {"source": "evidence", "target": "paper_baseline", "relation": "supports_published_baseline"},
                {"source": "paper_baseline", "target": "parameter_tuple", "relation": "human_edit_from"},
                {"source": "parameter_tuple", "target": "profile", "relation": "generates"},
                {"source": "profile", "target": "step", "relation": "revolves_about_z"},
            ],
        }
    return {
        "schema_version": "literature_geometry_udsg.preview.v0",
        "nodes": [
            {"id": "evidence", "kind": "literature_evidence", "refs": evidence_refs},
            {"id": "parameter_tuple", "kind": "coherent_parameter_tuple"},
            {"id": "profile", "kind": "symmetric_rz_profile"},
            {"id": "step", "kind": "preview_step"},
        ],
        "edges": [
            {"source": "evidence", "target": "parameter_tuple", "relation": "supports"},
            {"source": "parameter_tuple", "target": "profile", "relation": "generates"},
            {"source": "profile", "target": "step", "relation": "revolves_about_z"},
        ],
    }


def _profile_trace(candidate_id: object, profile: Mapping[str, Any], *, provenance: str) -> dict[str, Any]:
    return {
        "label": str(candidate_id),
        "candidate_id": str(candidate_id),
        "profile_points": [
            [float(point["z_mm"]), float(point["r_mm"])]
            for point in profile.get("points", [])
        ],
        "mesh": None,
        "step_path": None,
        "provenance": provenance,
    }


def _validate_parameter_tuple_geometry(parameter_tuple: Mapping[str, Any]) -> Sls2GeometryParameters:
    if parameter_tuple.get("unit") != "mm":
        raise LiteratureGeometryCandidateError("parameter_tuple.unit must be 'mm'")
    if not str(parameter_tuple.get("tuple_id", "")).strip():
        raise LiteratureGeometryCandidateError("parameter_tuple.tuple_id must be non-empty")
    values = parameter_tuple.get("values")
    if not isinstance(values, Mapping):
        raise LiteratureGeometryCandidateError("parameter_tuple.values must be a mapping")
    parameters = Sls2GeometryParameters.from_mapping(values)
    derived = parameter_tuple.get("derived")
    if not isinstance(derived, Mapping):
        raise LiteratureGeometryCandidateError("parameter_tuple.derived must be a mapping")
    expected_derived = {
        "h": parameters.h,
        "lower_ellipse_axial_semi_axis": parameters.h - parameters.a,
        "lower_ellipse_radial_semi_axis": parameters.R - parameters.r - parameters.b,
    }
    for key, expected in expected_derived.items():
        if not _same_number(derived.get(key), expected):
            raise LiteratureGeometryCandidateError(f"parameter_tuple.derived.{key} is inconsistent")
    return parameters


def _validate_published_tuple_provenance(
    parameter_tuple: Mapping[str, Any],
    semantic_package: Mapping[str, Any],
) -> None:
    refs = _validated_evidence_refs(parameter_tuple.get("source_refs", []), semantic_package)
    source_roles = parameter_tuple.get("source_roles")
    if not isinstance(source_roles, Mapping) or dict(source_roles) != _SLS2_PUBLISHED_SOURCE_ROLES:
        raise LiteratureGeometryCandidateError(
            "parameter_tuple.source_roles must preserve Figure 3 and candidate-row provenance"
        )
    if not set(_SLS2_PUBLISHED_SOURCE_ROLES.values()).issubset(set(refs)):
        raise LiteratureGeometryCandidateError("parameter_tuple.source_refs are missing required role evidence")


def _validate_variant_lineage(
    candidate: Mapping[str, Any],
    semantic_package: Mapping[str, Any],
    parent_candidate: Mapping[str, Any] | None,
) -> None:
    lineage = candidate.get("lineage")
    if not isinstance(lineage, Mapping):
        raise LiteratureGeometryCandidateError("human_preview_edit requires lineage")
    parent_id = str(lineage.get("parent_candidate_id", "")).strip()
    if not parent_id or parent_id == str(candidate.get("candidate_id", "")):
        raise LiteratureGeometryCandidateError("lineage.parent_candidate_id must name a distinct parent")
    for key in ("parent_immutable_candidate_sha256", "parent_candidate_content_sha256"):
        if not _is_sha256(lineage.get(key)):
            raise LiteratureGeometryCandidateError(f"lineage.{key} must be a SHA-256 digest")

    baseline = candidate.get("paper_baseline")
    if not isinstance(baseline, Mapping):
        raise LiteratureGeometryCandidateError("human_preview_edit requires paper_baseline")
    if not str(baseline.get("candidate_id", "")).strip():
        raise LiteratureGeometryCandidateError("paper_baseline.candidate_id must be non-empty")
    for key in ("immutable_candidate_sha256", "candidate_content_sha256"):
        if not _is_sha256(baseline.get(key)):
            raise LiteratureGeometryCandidateError(f"paper_baseline.{key} must be a SHA-256 digest")
    baseline_tuple = baseline.get("parameter_tuple")
    if not isinstance(baseline_tuple, Mapping) or baseline_tuple.get("origin") != "published_candidate":
        raise LiteratureGeometryCandidateError("paper_baseline must retain a published_candidate parameter tuple")
    _validate_parameter_tuple_geometry(baseline_tuple)
    _validate_published_tuple_provenance(baseline_tuple, semantic_package)

    if parent_candidate is None:
        return
    if parent_candidate is candidate:
        raise LiteratureGeometryCandidateError("candidate cannot be its own parent")
    validate_geometry_candidate(parent_candidate, semantic_package)
    expected_lineage = {
        "parent_candidate_id": parent_candidate["candidate_id"],
        "parent_immutable_candidate_sha256": parent_candidate["integrity"]["immutable_candidate_sha256"],
        "parent_candidate_content_sha256": parent_candidate["integrity"]["candidate_content_sha256"],
    }
    if dict(lineage) != expected_lineage:
        raise LiteratureGeometryCandidateError("lineage does not match the supplied parent candidate")
    if parent_candidate["parameter_tuple"]["origin"] == "published_candidate":
        expected_baseline = {
            "candidate_id": parent_candidate["candidate_id"],
            "immutable_candidate_sha256": parent_candidate["integrity"]["immutable_candidate_sha256"],
            "candidate_content_sha256": parent_candidate["integrity"]["candidate_content_sha256"],
            "parameter_tuple": copy.deepcopy(parent_candidate["parameter_tuple"]),
        }
    else:
        expected_baseline = parent_candidate["paper_baseline"]
    if dict(baseline) != dict(expected_baseline):
        raise LiteratureGeometryCandidateError("paper_baseline does not match the supplied parent lineage")


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)))


def _assert_semantic_package(package: Mapping[str, Any]) -> None:
    try:
        assert_valid_semantic_package(package)
    except LiteratureSemanticsError as exc:
        raise LiteratureGeometryCandidateError(f"invalid semantic package: {exc}") from exc


def _assert_sls2_scope(package: Mapping[str, Any]) -> None:
    context = package.get("request_context", {})
    classification = package.get("classification", {})
    observed = (
        context.get("operating_regime") if isinstance(context, Mapping) else None,
        classification.get("cavity_family") if isinstance(classification, Mapping) else None,
        classification.get("cell_count") if isinstance(classification, Mapping) else None,
        context.get("geometry_scope") if isinstance(context, Mapping) else None,
    )
    expected = ("normal_conducting", "elliptical", "single", "axisymmetric_single_cell_rf_vacuum")
    if observed != expected:
        raise LiteratureGeometryCandidateError(
            "SLS-2 v0 generator requires normal_conducting/elliptical/single/"
            "axisymmetric_single_cell_rf_vacuum semantics"
        )


def _validated_evidence_refs(refs: object, package: Mapping[str, Any]) -> list[str]:
    if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
        raise LiteratureGeometryCandidateError("evidence_refs must be a non-empty sequence")
    normalized = sorted({str(ref).strip() for ref in refs if str(ref).strip()})
    if not normalized:
        raise LiteratureGeometryCandidateError("evidence_refs must be non-empty")
    known = {
        str(item.get("id"))
        for section in ("evidence_sources", "text_evidence", "image_evidence")
        for item in (package.get(section, []) or [])
        if isinstance(item, Mapping) and item.get("id")
    }
    unknown = sorted(set(normalized) - known)
    if unknown:
        raise LiteratureGeometryCandidateError(f"unknown evidence_refs: {unknown}")
    return normalized


def _validated_semantic_paths(paths: object, package: Mapping[str, Any]) -> list[str]:
    if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)):
        raise LiteratureGeometryCandidateError("semantic_paths must be a non-empty sequence")
    normalized = sorted({str(path).strip() for path in paths if str(path).strip()})
    if not normalized:
        raise LiteratureGeometryCandidateError("semantic_paths must be non-empty")
    for path in normalized:
        _resolve_semantic_path(package, path)
    return normalized


_PATH_PART = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<index>[0-9]+)\])?$")


def _resolve_semantic_path(package: Mapping[str, Any], path: str) -> object:
    current: object = package
    for part in path.split("."):
        match = _PATH_PART.fullmatch(part)
        if match is None or not isinstance(current, Mapping) or match.group("key") not in current:
            raise LiteratureGeometryCandidateError(f"unknown semantic path: {path!r}")
        current = current[match.group("key")]
        index = match.group("index")
        if index is not None:
            if not isinstance(current, list) or int(index) >= len(current):
                raise LiteratureGeometryCandidateError(f"unknown semantic path: {path!r}")
            current = current[int(index)]
    return current


def _validate_review_status(status: object) -> None:
    if status not in REVIEW_STATUSES:
        raise LiteratureGeometryCandidateError(f"unsupported review status {status!r}")


def _validate_sample_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 5 <= value <= 257:
        raise LiteratureGeometryCandidateError("samples_per_quarter must be an integer between 5 and 257")
    return value


def _same_number(value: object, expected: float, tolerance: float = 1e-9) -> bool:
    try:
        return math.isfinite(float(value)) and abs(float(value) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


__all__ = [
    "GEOMETRY_CANDIDATE_SCHEMA_VERSION",
    "GEOMETRY_GENERATION_SCHEMA_VERSION",
    "GEOMETRY_PREVIEW_SCHEMA_VERSION",
    "SLS2_GENERATOR_VERSION",
    "LiteratureGeometryCandidateError",
    "Sls2GeometryParameters",
    "build_sls2_geometry_candidate",
    "build_sls2_preview_variant",
    "build_sls2_preview",
    "build_sls2_profile",
    "candidate_content_sha256",
    "candidate_snapshot_sha256",
    "generate_sls2_step",
    "immutable_candidate_sha256",
    "validate_geometry_candidate",
]
