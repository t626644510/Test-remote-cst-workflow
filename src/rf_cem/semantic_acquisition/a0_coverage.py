"""Truth loading, coverage evaluation, and immutable A0 proof bundles."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from rf_cem.compiler import CompileRecord, load_compile_record
from rf_cem.semantic import InstanceBoundaryGraph, load_instance_boundary_graph
from rf_cem.semantic.contracts import (
    canonical_json_bytes,
    canonical_sha256,
    canonicalization_contract,
    file_sha256,
)
from rf_cem.semantic.ontology import REGION_JUNCTION_LANDMARK

from .boundary_signals import (
    BOUNDARY_SIGNAL_ALGORITHM_VERSION,
    BoundaryJoin,
    BoundaryPoint,
    BoundarySegment,
    BoundarySignalError,
    BoundaryTrace,
    CandidateExtraction,
    LandmarkCandidate,
    SignalParameters,
    extract_landmark_candidates,
)


A0_ALGORITHM_VERSION = "rf_cem.semantic_acquisition.a0_coverage.v0"
A0_BUNDLE_SCHEMA_VERSION = "rf_cem_acquisition_a0_bundle.v0"
A0_REPORT_SCHEMA_VERSION = "a0_landmark_coverage_report.v0"
A0_MANIFEST_SCHEMA_VERSION = "a0_source_binding_manifest.v0"
A0_BUNDLE_PREFIX = "a0_landmark_coverage"
REPORT_JSON_FILE = "a0_coverage_report.v0.json"
REPORT_MARKDOWN_FILE = "a0_coverage_report.md"
PLOT_FILE = "landmark_coverage.png"
MANIFEST_FILE = "source_binding_manifest.v0.json"
_POINT_TOLERANCE_MM = 1.0e-10


@dataclass(frozen=True)
class A0SourceSet:
    """Repository-bound inputs for one A0 coverage build."""

    repo_root: Path
    compile_record: Path
    instance_graph: Path


@dataclass(frozen=True)
class TruthJunction:
    """One independently reviewed RegionJunctionLandmark binding."""

    landmark_id: str
    interface_id: str
    point: BoundaryPoint
    u: float
    projection_residual_mm: float
    incident_region_ids: tuple[str, ...]
    incident_region_types: tuple[str, ...]
    coordinate_source_path: str
    coordinate_source_locator: str
    semantic_source_path: str
    semantic_source_locator: str

    def to_mapping(self) -> dict[str, object]:
        """Return a canonical JSON-compatible truth record."""

        return {
            "landmark_id": self.landmark_id,
            "interface_id": self.interface_id,
            "point_mm": {"z": self.point.z_mm, "r": self.point.r_mm},
            "u": self.u,
            "projection_residual_mm": self.projection_residual_mm,
            "incident_region_ids": list(self.incident_region_ids),
            "incident_region_types": list(self.incident_region_types),
            "coordinate_source": {
                "path": self.coordinate_source_path,
                "locator": self.coordinate_source_locator,
                "relation": "compile_record_v2_reviewed_landmark_coordinate_binding",
            },
            "semantic_source": {
                "path": self.semantic_source_path,
                "locator": self.semantic_source_locator,
                "relation": "reviewed_region_junction_type_and_incidence",
            },
        }


@dataclass(frozen=True)
class TruthData:
    """Validated real inputs and independently normalized junction truth."""

    record: CompileRecord
    graph: InstanceBoundaryGraph
    profile_path: Path
    profile_points: tuple[BoundaryPoint, ...]
    total_arc_length_mm: float
    junctions: tuple[TruthJunction, ...]


@dataclass(frozen=True)
class CoverageMatch:
    """Nearest stable candidate for one truth junction."""

    landmark_id: str
    truth_u: float
    candidate_index: int
    candidate_u: float
    delta_u: float
    absolute_deviation_mm: float
    signals: tuple[str, ...]
    hit: bool

    def to_mapping(self, diagnosis: str | None = None) -> dict[str, object]:
        """Return a canonical JSON-compatible nearest-candidate record."""

        result: dict[str, object] = {
            "landmark_id": self.landmark_id,
            "truth_u": self.truth_u,
            "nearest_candidate_id": f"candidate.{self.candidate_index:03d}",
            "nearest_candidate_u": self.candidate_u,
            "delta_u": self.delta_u,
            "absolute_deviation_mm": self.absolute_deviation_mm,
            "signals": list(self.signals),
            "hit": self.hit,
        }
        if diagnosis is not None:
            result["miss_diagnosis"] = diagnosis
        return result


@dataclass(frozen=True)
class CoverageEvaluation:
    """Forward coverage plus reverse candidate accounting."""

    tolerance_u: float
    matches: tuple[CoverageMatch, ...]
    candidate_count: int
    hit_truth_count: int
    candidates_hitting_truth_count: int
    extra_candidate_count: int
    unstable_candidate_count: int

    @property
    def all_truth_hit(self) -> bool:
        """Whether every reviewed junction is covered within tolerance."""

        return all(match.hit for match in self.matches)


@dataclass(frozen=True)
class PrimaryAvailabilityAudit:
    """Deterministic filename/JSON audit for the preferred LEReC instance."""

    searched_paths: tuple[str, ...]
    found_artifacts: tuple[Mapping[str, Any], ...]
    consumed_json_paths: tuple[Path, ...]
    usable: bool
    reason: str

    def to_mapping(self) -> dict[str, object]:
        """Return the portable selection decision without absolute paths."""

        return {
            "preferred_instance": "LEReC 704 MHz",
            "searched_paths": list(self.searched_paths),
            "found_artifacts": [dict(item) for item in self.found_artifacts],
            "usable": self.usable,
            "reason": self.reason,
            "pdf_content_read_or_parsed": False,
        }


@dataclass(frozen=True)
class A0Bundle:
    """Location and canonical identities for one immutable A0 result."""

    path: Path
    bundle_id: str
    input_sha256: str
    report: Mapping[str, Any]
    manifest: Mapping[str, Any]


def load_truth_junctions(
    repo_root: Path, compile_record_path: Path, instance_graph_path: Path
) -> TruthData:
    """Load v2 coordinate bindings and independently map them to profile arc length."""

    root = repo_root.resolve()
    record_path = _inside_repo(root, compile_record_path, "compile record")
    graph_path = _inside_repo(root, instance_graph_path, "instance graph")
    record = load_compile_record(record_path)
    graph = load_instance_boundary_graph(graph_path)
    if record.schema_version != "compile_record.v2":
        raise BoundarySignalError("A0 truth requires compile_record.v2")
    if record.instance_id != graph.instance_id:
        raise BoundarySignalError("compile record and graph instance IDs differ")
    if record.instance_graph_ref.canonical_sha256 != canonical_sha256(graph.to_mapping()):
        raise BoundarySignalError("compile record does not bind the supplied graph content")
    if record.instance_graph_ref.source.source_raw_sha256 != file_sha256(graph_path):
        raise BoundarySignalError("compile record does not bind the supplied graph bytes")

    profile_path = _compiled_profile_path(record_path, record)
    profile = _read_json_mapping(profile_path, "compiled profile")
    if profile.get("schema_version") != "compiled_profile.v0":
        raise BoundarySignalError("A0 requires compiled_profile.v0")
    if profile.get("instance_id") != record.instance_id:
        raise BoundarySignalError("compiled profile instance ID mismatch")
    if profile.get("units") != {"r": "mm", "z": "mm"}:
        raise BoundarySignalError("compiled profile must declare z/r in mm")
    profile_points = _profile_points(profile)
    total_arc_length_mm = _polyline_length(profile_points)
    if total_arc_length_mm <= _POINT_TOLERANCE_MM:
        raise BoundarySignalError("compiled profile has zero arc length")

    binding_by_id = {binding.landmark_id: binding for binding in record.landmark_bindings}
    binding_indices = {
        binding.landmark_id: index for index, binding in enumerate(record.landmark_bindings)
    }
    region_type_by_id = {region.region_id: region.region_type for region in graph.regions}
    interface_by_landmark = {
        interface.landmark_id: interface.interface_id for interface in graph.interfaces
    }
    record_relative = record_path.relative_to(root).as_posix()
    graph_relative = graph_path.relative_to(root).as_posix()
    junctions: list[TruthJunction] = []
    for graph_index, landmark in enumerate(graph.landmarks):
        if landmark.landmark_type != REGION_JUNCTION_LANDMARK:
            continue
        binding = binding_by_id.get(landmark.landmark_id)
        if binding is None:
            raise BoundarySignalError(
                f"missing compile binding for reviewed junction {landmark.landmark_id}"
            )
        point = BoundaryPoint(binding.point.z_mm, binding.point.r_mm)
        u_value, residual = _truth_projection_to_profile(point, profile_points)
        if residual > 1.0e-6:
            raise BoundarySignalError(
                f"junction is not on compiled profile within 1e-6 mm: {landmark.landmark_id}"
            )
        try:
            region_types = tuple(
                region_type_by_id[region_id] for region_id in landmark.incident_region_ids
            )
        except KeyError as exc:
            raise BoundarySignalError("junction references an unknown semantic region") from exc
        interface_id = interface_by_landmark.get(landmark.landmark_id)
        if interface_id is None:
            raise BoundarySignalError("junction lacks its reviewed interface binding")
        junctions.append(
            TruthJunction(
                landmark_id=landmark.landmark_id,
                interface_id=interface_id,
                point=point,
                u=u_value,
                projection_residual_mm=residual,
                incident_region_ids=tuple(landmark.incident_region_ids),
                incident_region_types=region_types,
                coordinate_source_path=record_relative,
                coordinate_source_locator=(
                    f"#/landmark_bindings/{binding_indices[landmark.landmark_id]}"
                ),
                semantic_source_path=graph_relative,
                semantic_source_locator=f"#/landmarks/{graph_index}",
            )
        )
    if not junctions:
        raise BoundarySignalError("reviewed graph contains no RegionJunctionLandmark")
    return TruthData(
        record=record,
        graph=graph,
        profile_path=profile_path,
        profile_points=profile_points,
        total_arc_length_mm=total_arc_length_mm,
        junctions=tuple(junctions),
    )


def boundary_trace_from_compile_record(record: CompileRecord) -> BoundaryTrace:
    """Strip semantics and return native geometric traces plus numeric joins."""

    patches = sorted(
        (patch for geometry in record.region_geometries for patch in geometry.patches),
        key=lambda item: item.global_order,
    )
    if [patch.global_order for patch in patches] != list(range(len(patches))):
        raise BoundarySignalError("compiled patch global order is not contiguous")
    if any(patch.orientation != "left_to_right" for patch in patches):
        raise BoundarySignalError("A0 requires one left-to-right compiled contour")

    numeric_patches: list[
        tuple[str, tuple[BoundaryPoint, ...], tuple[float, float], tuple[float, float]]
    ] = []
    for patch in patches:
        sampled = tuple(
            BoundaryPoint(point.z_mm, point.r_mm)
            for point in patch.representation.sample()
        )
        numeric_patches.append(
            (
                patch.source_native_segment_ref,
                sampled,
                tuple(patch.representation.start_tangent()),
                tuple(patch.representation.end_tangent()),
            )
        )

    joins = tuple(
        BoundaryJoin(
            left_end=left[1][-1],
            right_start=right[1][0],
            left_tangent=left[3],
            right_tangent=right[2],
        )
        for left, right in zip(numeric_patches, numeric_patches[1:])
    )

    grouped: list[
        tuple[str, list[BoundaryPoint], tuple[float, float], tuple[float, float]]
    ] = []
    for native_ref, points, start_tangent, end_tangent in numeric_patches:
        if grouped and grouped[-1][0] == native_ref:
            previous_ref, previous_points, previous_start, _ = grouped[-1]
            if previous_points[-1].distance_to(points[0]) <= _POINT_TOLERANCE_MM:
                previous_points.extend(points[1:])
            else:
                previous_points.extend(points)
            grouped[-1] = (
                previous_ref,
                previous_points,
                previous_start,
                end_tangent,
            )
        else:
            grouped.append((native_ref, list(points), start_tangent, end_tangent))
    segments = tuple(
        BoundarySegment(
            points=tuple(points),
            start_tangent=start_tangent,
            end_tangent=end_tangent,
        )
        for _, points, start_tangent, end_tangent in grouped
    )
    return BoundaryTrace(segments=segments, joins=joins)


def evaluate_coverage(
    truth_junctions: Sequence[TruthJunction],
    candidates: Sequence[LandmarkCandidate],
    *,
    total_arc_length_mm: float,
    tolerance_u: float = 0.02,
    unstable_candidate_count: int = 0,
) -> CoverageEvaluation:
    """Evaluate nearest-candidate truth coverage and reverse candidate counts."""

    if not truth_junctions:
        raise BoundarySignalError("coverage requires at least one truth junction")
    if not candidates:
        raise BoundarySignalError("coverage requires at least one stable candidate")
    if not math.isfinite(total_arc_length_mm) or total_arc_length_mm <= 0.0:
        raise BoundarySignalError("total arc length must be finite and positive")
    if not math.isfinite(tolerance_u) or tolerance_u <= 0.0:
        raise BoundarySignalError("coverage tolerance must be finite and positive")
    ordered_candidates = tuple(sorted(candidates, key=lambda item: item.u))
    matches: list[CoverageMatch] = []
    for truth in truth_junctions:
        candidate_index, candidate = min(
            enumerate(ordered_candidates),
            key=lambda item: (abs(item[1].u - truth.u), item[1].u, item[0]),
        )
        delta_u = abs(candidate.u - truth.u)
        matches.append(
            CoverageMatch(
                landmark_id=truth.landmark_id,
                truth_u=truth.u,
                candidate_index=candidate_index,
                candidate_u=candidate.u,
                delta_u=delta_u,
                absolute_deviation_mm=delta_u * total_arc_length_mm,
                signals=candidate.signals,
                hit=delta_u <= tolerance_u,
            )
        )
    hit_candidate_indices = {
        candidate_index
        for candidate_index, candidate in enumerate(ordered_candidates)
        if any(abs(candidate.u - truth.u) <= tolerance_u for truth in truth_junctions)
    }
    return CoverageEvaluation(
        tolerance_u=tolerance_u,
        matches=tuple(matches),
        candidate_count=len(ordered_candidates),
        hit_truth_count=sum(match.hit for match in matches),
        candidates_hitting_truth_count=len(hit_candidate_indices),
        extra_candidate_count=len(ordered_candidates) - len(hit_candidate_indices),
        unstable_candidate_count=unstable_candidate_count,
    )


def audit_lerec_availability(repo_root: Path) -> PrimaryAvailabilityAudit:
    """Audit path names and reviewed JSON only; never open or parse PDFs."""

    root = repo_root.resolve()
    analysis_root = root / "analysis_outputs"
    searched_paths = (
        "analysis_outputs/rf_cem_family_induction_ablation/"
        "r3_family_induction_ablation.59db0a7b5f8e158c/",
        "analysis_outputs/rf_cem_family_induction/"
        "r3_family_induction.2f6c02557798e606/",
        "analysis_outputs/** (case-insensitive path search for 'lerec')",
    )
    matching = (
        sorted(
            path
            for path in analysis_root.rglob("*")
            if path.is_file() and "lerec" in path.as_posix().lower()
        )
        if analysis_root.is_dir()
        else []
    )
    found: list[Mapping[str, Any]] = []
    consumed: list[Path] = []
    geometry_found = False
    coordinate_truth_found = False
    for path in matching:
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".pdf":
            found.append(
                {
                    "path": relative,
                    "kind": "literature_pdf",
                    "status": "not_read_or_parsed_scope_exclusion",
                }
            )
            continue
        if path.suffix.lower() != ".json":
            found.append(
                {"path": relative, "kind": "other", "status": "filename_only"}
            )
            continue
        mapping = _read_json_mapping(path, "LEReC selection evidence")
        consumed.append(path)
        schema = mapping.get("schema_version")
        landmarks = mapping.get("landmarks")
        junctions = [
            item
            for item in landmarks
            if isinstance(item, dict)
            and item.get("landmark_type") == REGION_JUNCTION_LANDMARK
        ] if isinstance(landmarks, list) else []
        has_coordinates = bool(junctions) and all(
            isinstance(item.get("point"), dict)
            or ("z_mm" in item and "r_mm" in item)
            for item in junctions
        )
        has_geometry = (
            isinstance(mapping.get("profile_points"), list)
            or isinstance(mapping.get("kernel_segments"), list)
            or str(schema).startswith("compile_record.")
            or str(schema).startswith("compiled_profile.")
        )
        geometry_found = geometry_found or has_geometry
        coordinate_truth_found = coordinate_truth_found or has_coordinates
        found.append(
            {
                "path": relative,
                "kind": str(schema),
                "raw_sha256": file_sha256(path),
                "reviewed_region_junctions": len(junctions),
                "junction_coordinates_present": has_coordinates,
                "resample_geometry_present": has_geometry,
            }
        )
    usable = geometry_found and coordinate_truth_found
    if usable:
        reason = "reviewed junction coordinates and resampleable geometry are both present"
    else:
        missing = []
        if not geometry_found:
            missing.append("resampleable compiled/profile geometry")
        if not coordinate_truth_found:
            missing.append("coordinate-bearing reviewed junction truth")
        reason = (
            "LEReC is unavailable for A0 because the searched local evidence lacks "
            + " and ".join(missing)
            + "; reviewed topology alone is insufficient"
        )
    return PrimaryAvailabilityAudit(
        searched_paths=searched_paths,
        found_artifacts=tuple(found),
        consumed_json_paths=tuple(consumed),
        usable=usable,
        reason=reason,
    )


def write_a0_bundle(
    sources: A0SourceSet,
    output_root: Path,
    *,
    parameters: SignalParameters | None = None,
    coverage_tolerance_u: float = 0.02,
) -> A0Bundle:
    """Build one atomic content-addressed A0 proof and refuse overwrite."""

    root = sources.repo_root.resolve()
    params = parameters or SignalParameters()
    truth_data = load_truth_junctions(
        root, sources.compile_record, sources.instance_graph
    )
    primary_audit = audit_lerec_availability(root)
    if truth_data.record.instance_id.startswith("lerec") and not primary_audit.usable:
        raise BoundarySignalError("selected LEReC input failed its availability audit")
    if not truth_data.record.instance_id.startswith("lerec") and primary_audit.usable:
        raise BoundarySignalError(
            "preferred LEReC input is usable; A0 may not silently select a fallback"
        )
    trace = boundary_trace_from_compile_record(truth_data.record)
    extraction = extract_landmark_candidates(trace, params)
    coverage = evaluate_coverage(
        truth_data.junctions,
        extraction.candidates,
        total_arc_length_mm=truth_data.total_arc_length_mm,
        tolerance_u=coverage_tolerance_u,
        unstable_candidate_count=len(extraction.unstable_candidates),
    )
    continuity = _continuity_corroboration(
        truth_data.record, extraction, params
    )
    if not all(item["threshold_classification_agrees"] for item in continuity):
        raise BoundarySignalError(
            "independent continuity signals do not corroborate compiler diagnostics"
        )

    source_entries, source_paths = _source_inventory(
        root, sources, truth_data, primary_audit
    )
    selection = {
        "selected_instance": truth_data.record.instance_id,
        "selected_label": "SLS-2" if truth_data.record.instance_id.startswith("sls2") else truth_data.record.instance_id,
        "selection_reason": (
            primary_audit.reason
            if not truth_data.record.instance_id.startswith("lerec")
            else "preferred LEReC instance satisfied both availability conditions"
        ),
        "preferred_instance_audit": primary_audit.to_mapping(),
    }
    input_preimage = {
        "schema_version": A0_BUNDLE_SCHEMA_VERSION,
        "canonicalization_contract": canonicalization_contract(),
        "algorithm_version": A0_ALGORITHM_VERSION,
        "boundary_signal_algorithm_version": BOUNDARY_SIGNAL_ALGORITHM_VERSION,
        "parameters": {
            **params.to_mapping(),
            "coverage_tolerance_u": coverage_tolerance_u,
        },
        "selection": selection,
        "sources": source_entries,
    }
    input_sha256 = canonical_sha256(input_preimage)
    bundle_id = f"{A0_BUNDLE_PREFIX}.{input_sha256[:16]}"
    output = output_root if output_root.is_absolute() else root / output_root
    resolved_output = output.resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    target = resolved_output / bundle_id
    if target.exists():
        raise FileExistsError(f"A0 proof bundle already exists: {target}")
    prebuild_hashes = {path: file_sha256(path) for path in source_paths}
    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle_id}.tmp-", dir=resolved_output))
    try:
        report = _report_mapping(
            bundle_id=bundle_id,
            input_sha256=input_sha256,
            truth=truth_data,
            extraction=extraction,
            coverage=coverage,
            continuity=continuity,
            parameters=params,
            coverage_tolerance_u=coverage_tolerance_u,
            selection=selection,
        )
        _write_json(temporary / REPORT_JSON_FILE, report)
        (temporary / REPORT_MARKDOWN_FILE).write_bytes(
            _markdown_report(report).encode("utf-8")
        )
        _write_plot(
            temporary / PLOT_FILE,
            truth_data.profile_points,
            truth_data.junctions,
            extraction.candidates,
        )
        artifacts = _artifact_inventory(temporary)
        manifest = {
            "schema_version": A0_MANIFEST_SCHEMA_VERSION,
            "bundle_id": bundle_id,
            "input_sha256": input_sha256,
            "canonicalization_contract": canonicalization_contract(),
            "validation_mode": "deterministic_no_cst_read_only_existing_proofs",
            "status": report["status"],
            "live_cst_status": "not_run",
            "physical_acceptance_status": "not_established",
            "sources": source_entries,
            "artifacts": artifacts,
            "checks": [
                "preferred_instance_availability_audited_without_pdf_parsing",
                "truth_coordinates_loaded_from_compile_record_v2_bindings",
                "truth_semantics_loaded_from_reviewed_instance_graph",
                "candidate_extractor_received_no_region_or_landmark_identifiers",
                "two_scale_stability_required",
                "minimum_candidate_spacing_applied",
                "continuity_thresholds_corroborated_against_compiler_diagnostics",
                "existing_input_hashes_unchanged",
                "canonical_content_has_no_timestamp_or_absolute_path",
                "live_cst_not_run",
            ],
        }
        _write_json(temporary / MANIFEST_FILE, manifest)
        postbuild_hashes = {path: file_sha256(path) for path in source_paths}
        if postbuild_hashes != prebuild_hashes:
            raise BoundarySignalError("A0 build mutated an input source")
        if target.exists():
            raise FileExistsError(f"A0 proof bundle already exists: {target}")
        os.replace(temporary, target)
    except BaseException:
        if temporary.exists() and temporary.parent == resolved_output:
            shutil.rmtree(temporary)
        raise
    return A0Bundle(
        path=target,
        bundle_id=bundle_id,
        input_sha256=input_sha256,
        report=report,
        manifest=manifest,
    )


def _compiled_profile_path(record_path: Path, record: CompileRecord) -> Path:
    artifacts = [item for item in record.output_artifacts if item.role == "compiled_profile"]
    if len(artifacts) != 1:
        raise BoundarySignalError("compile record must bind exactly one compiled profile")
    artifact = artifacts[0]
    bundle_root = record_path.parent.parent.resolve()
    profile_path = (bundle_root / artifact.path).resolve()
    try:
        profile_path.relative_to(bundle_root)
    except ValueError as exc:
        raise BoundarySignalError("compiled profile escapes its proof bundle") from exc
    if not profile_path.is_file():
        raise BoundarySignalError("compiled profile is missing")
    if file_sha256(profile_path) != artifact.raw_sha256:
        raise BoundarySignalError("compiled profile hash mismatch")
    if profile_path.stat().st_size != artifact.size_bytes:
        raise BoundarySignalError("compiled profile size mismatch")
    return profile_path


def _profile_points(profile: Mapping[str, Any]) -> tuple[BoundaryPoint, ...]:
    raw_points = profile.get("profile_points")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise BoundarySignalError("compiled profile requires at least two points")
    try:
        return tuple(
            BoundaryPoint(float(item["z_mm"]), float(item["r_mm"]))
            for item in raw_points
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BoundarySignalError("compiled profile point schema is invalid") from exc


def _truth_projection_to_profile(
    target: BoundaryPoint, points: Sequence[BoundaryPoint]
) -> tuple[float, float]:
    """Independent truth-only projection; candidate helpers are not called."""

    cumulative = [0.0]
    for left, right in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + left.distance_to(right))
    best_distance = math.inf
    best_s = 0.0
    for index, (left, right) in enumerate(zip(points, points[1:])):
        dz = right.z_mm - left.z_mm
        dr = right.r_mm - left.r_mm
        denominator = dz * dz + dr * dr
        fraction = 0.0
        if denominator > _POINT_TOLERANCE_MM**2:
            fraction = max(
                0.0,
                min(
                    1.0,
                    ((target.z_mm - left.z_mm) * dz + (target.r_mm - left.r_mm) * dr)
                    / denominator,
                ),
            )
        projected = BoundaryPoint(
            left.z_mm + fraction * dz, left.r_mm + fraction * dr
        )
        distance = target.distance_to(projected)
        if distance < best_distance:
            best_distance = distance
            best_s = cumulative[index] + fraction * math.sqrt(denominator)
    return best_s / cumulative[-1], best_distance


def _continuity_corroboration(
    record: CompileRecord,
    extraction: CandidateExtraction,
    parameters: SignalParameters,
) -> tuple[Mapping[str, Any], ...]:
    checks = sorted(record.continuity_checks, key=lambda item: item.check_id)
    if len(checks) != len(extraction.continuity):
        raise BoundarySignalError("numeric and compiler continuity join counts differ")
    result: list[Mapping[str, Any]] = []
    for numeric, compiler in zip(extraction.continuity, checks):
        compiler_c0_detected = compiler.c0_gap_mm > parameters.c0_gap_threshold_mm
        compiler_g1_detected = (
            compiler.tangent_angle_deg > parameters.g1_angle_threshold_deg
        )
        agreement = (
            numeric.c0_gap_detected == compiler_c0_detected
            and numeric.g1_jump_detected == compiler_g1_detected
        )
        result.append(
            {
                "join_index": numeric.join_index,
                "landmark_id": compiler.landmark_id,
                "u_by_scale": [
                    {"sample_count": count, "u": position}
                    for count, position in numeric.u_by_scale
                ],
                "independent_numeric": {
                    "c0_gap_mm": numeric.gap_mm,
                    "g1_tangent_angle_deg": numeric.tangent_angle_deg,
                    "c0_gap_detected": numeric.c0_gap_detected,
                    "g1_jump_detected": numeric.g1_jump_detected,
                },
                "compiler_diagnostic": {
                    "check_id": compiler.check_id,
                    "measurement_basis": compiler.measurement_basis,
                    "c0_gap_mm": compiler.c0_gap_mm,
                    "g1_tangent_angle_deg": compiler.tangent_angle_deg,
                    "c0_pass": compiler.c0_pass,
                    "g1_pass": compiler.g1_pass,
                    "required_level": compiler.required_level,
                    "required_pass": compiler.required_pass,
                },
                "threshold_classification_agrees": agreement,
            }
        )
    return tuple(result)


def _report_mapping(
    *,
    bundle_id: str,
    input_sha256: str,
    truth: TruthData,
    extraction: CandidateExtraction,
    coverage: CoverageEvaluation,
    continuity: tuple[Mapping[str, Any], ...],
    parameters: SignalParameters,
    coverage_tolerance_u: float,
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    truth_by_id = {item.landmark_id: item for item in truth.junctions}
    continuity_by_landmark = {
        str(item["landmark_id"]): item for item in continuity
    }
    matches = []
    for match in coverage.matches:
        diagnosis = None
        if not match.hit:
            junction = truth_by_id[match.landmark_id]
            check = continuity_by_landmark.get(match.landmark_id)
            continuity_text = "no compiler continuity record"
            if check is not None:
                compiler = check["compiler_diagnostic"]
                continuity_text = (
                    f"compiler {compiler['required_level']} join passes with "
                    f"C0 gap {compiler['c0_gap_mm']:.12g} mm and tangent angle "
                    f"{compiler['g1_tangent_angle_deg']:.12g} deg"
                )
            diagnosis = (
                f"{junction.incident_region_types[0]} to "
                f"{junction.incident_region_types[-1]} is a reviewed semantic partition; "
                f"{continuity_text}. No endpoint, radius extremum, signed-curvature "
                "zero/extremum, C0/G1 discontinuity, or z=0 symmetry signal occurs "
                "within the configured coverage tolerance."
            )
        matches.append(match.to_mapping(diagnosis))
    candidate_mappings = []
    for index, candidate in enumerate(sorted(extraction.candidates, key=lambda item: item.u)):
        candidate_mappings.append(
            {"candidate_id": f"candidate.{index:03d}", **candidate.to_mapping()}
        )
    unstable_mappings = [
        {"unstable_id": f"unstable.{index:03d}", **candidate.to_mapping()}
        for index, candidate in enumerate(
            sorted(extraction.unstable_candidates, key=lambda item: item.u)
        )
    ]
    return {
        "schema_version": A0_REPORT_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "input_sha256": input_sha256,
        "algorithm_version": A0_ALGORITHM_VERSION,
        "boundary_signal_algorithm_version": BOUNDARY_SIGNAL_ALGORITHM_VERSION,
        "probe_question": (
            "Do deterministic geometry signals cover every reviewed region junction?"
        ),
        "status": (
            "pass_full_coverage"
            if coverage.all_truth_hit
            else "pass_with_explicit_diagnosed_misses"
        ),
        "selection": dict(selection),
        "instance": {
            "instance_id": truth.record.instance_id,
            "compile_id": truth.record.compile_id,
            "graph_id": truth.graph.graph_id,
            "profile_axis": "z",
            "orientation": "negative_to_positive_z",
            "length_unit": "mm",
            "curvature_unit": "1/mm",
            "total_arc_length_mm": truth.total_arc_length_mm,
        },
        "parameters": {
            **parameters.to_mapping(),
            "coverage_tolerance_u": coverage_tolerance_u,
        },
        "truth_independence": {
            "coordinate_authority": "compile_record.v2 reviewed landmark bindings",
            "semantic_authority": "reviewed instance_boundary_graph.v0",
            "candidate_input": (
                "numeric native-curve traces and tangents after removal of region, "
                "landmark, and patch identifiers"
            ),
            "candidate_reads_truth_landmarks": False,
            "normalization": "u=s/L along complete compiled RF-vacuum profile",
        },
        "truth_junctions": [item.to_mapping() for item in truth.junctions],
        "candidates": candidate_mappings,
        "unstable_candidates": unstable_mappings,
        "per_scale_candidate_counts": [
            {"sample_count": count, "candidate_count": len(candidates)}
            for count, candidates in extraction.per_scale
        ],
        "continuity_corroboration": list(continuity),
        "coverage": {
            "all_truth_hit": coverage.all_truth_hit,
            "truth_junction_count": len(truth.junctions),
            "hit_truth_count": coverage.hit_truth_count,
            "missed_truth_count": len(truth.junctions) - coverage.hit_truth_count,
            "candidate_count": coverage.candidate_count,
            "candidates_hitting_truth_count": coverage.candidates_hitting_truth_count,
            "extra_candidate_count": coverage.extra_candidate_count,
            "unstable_candidate_count": coverage.unstable_candidate_count,
            "matches": matches,
        },
        "visualization": PLOT_FILE,
        "known_limitations": [
            (
                "A0 tests only the declared deterministic signal and threshold set; "
                "it does not classify regions or assemble a semantic graph."
            ),
            (
                "Native curve grouping uses compiler source-native geometry provenance "
                "only to prevent semantic patch partitions from becoming artificial peaks."
            ),
            (
                "Extra candidates are quantified but are not a failure criterion at A0."
            ),
        ],
        "known_duplicate_debt": [
            (
                "Arc-length resampling and signed-curvature numerics locally duplicate "
                "private R4 observer helpers; keep local until a stable two-consumer "
                "public contract is justified."
            )
        ],
        "exclusions": [
            "llm_or_vision_api",
            "pdf_content_read_or_parse",
            "region_classification",
            "semantic_graph_assembly",
            "grammar_acceptance",
            "cst_import_or_execution",
            "rf_physical_acceptance",
        ],
        "live_cst_status": "not_run",
        "physical_acceptance_status": "not_established",
    }


def _markdown_report(report: Mapping[str, Any]) -> str:
    coverage = report["coverage"]
    parameters = report["parameters"]
    selection = report["selection"]
    preferred = selection["preferred_instance_audit"]
    lines = [
        "# Semantic Acquisition A0 landmark coverage",
        "",
        f"- Bundle: `{report['bundle_id']}`",
        f"- Selected instance: `{report['instance']['instance_id']}` ({selection['selected_label']})",
        f"- Status: `{report['status']}`",
        "- Validation: deterministic no-CST; no PDF content, LLM, vision API, or CST was used.",
        "",
        "## Instance selection",
        "",
        f"Preferred LEReC usable: `{str(preferred['usable']).lower()}`.",
        f"Reason: {preferred['reason']}.",
        "",
        "Searched paths:",
        "",
    ]
    lines.extend(f"- `{path}`" for path in preferred["searched_paths"])
    lines.extend(
        [
            "",
            "Discovered LEReC artifacts:",
            "",
        ]
    )
    lines.extend(
        f"- `{item['path']}`: {item['status'] if 'status' in item else item['kind']}"
        for item in preferred["found_artifacts"]
    )
    lines.extend(
        [
            "",
            "## Truth independence",
            "",
            "Junction type/incidence comes from the reviewed `instance_boundary_graph.v0`; "
            "coordinates come from `compile_record.v2` landmark bindings. Candidate extraction "
            "receives only numeric geometry and tangents after all region/landmark identifiers "
            "are removed.",
            "",
            "| Landmark | u | z (mm) | r (mm) | Coordinate binding |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for truth in report["truth_junctions"]:
        source = truth["coordinate_source"]
        lines.append(
            f"| `{truth['landmark_id']}` | {truth['u']:.9f} | "
            f"{truth['point_mm']['z']:.9f} | {truth['point_mm']['r']:.9f} | "
            f"`{source['path']}{source['locator']}` |"
        )
    lines.extend(
        [
            "",
            "## Thresholds and candidate statistics",
            "",
            f"Sampling densities are `{parameters['sample_counts']}`. Stable matching tolerance "
            f"is `{parameters['stability_tolerance_u']}` in normalized arc length; candidates "
            f"closer than `{parameters['merge_distance_u']}` are merged. Radius prominence is "
            f"`{parameters['radius_prominence_mm']} mm`; curvature prominence is "
            f"`{parameters['curvature_prominence_per_mm']} 1/mm`; curvature zero threshold is "
            f"`{parameters['curvature_zero_per_mm']} 1/mm`. C0 gap threshold is "
            f"`{parameters['c0_gap_threshold_mm']} mm`; G1 tangent-jump threshold is "
            f"`{parameters['g1_angle_threshold_deg']} deg`.",
            "",
            f"Coverage tolerance is `Delta u <= {parameters['coverage_tolerance_u']}`. "
            f"Stable candidates: **{coverage['candidate_count']}**; truth hits: "
            f"**{coverage['hit_truth_count']}/{coverage['truth_junction_count']}**; candidates "
            f"hitting truth: **{coverage['candidates_hitting_truth_count']}**; extra candidates: "
            f"**{coverage['extra_candidate_count']}**; unstable candidates: "
            f"**{coverage['unstable_candidate_count']}**.",
            "",
            "## Per-junction coverage",
            "",
            "| Landmark | Truth u | Candidate u | Delta u | Deviation (mm) | Signals | Hit |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    missed_matches = []
    for match in coverage["matches"]:
        lines.append(
            f"| `{match['landmark_id']}` | {match['truth_u']:.9f} | "
            f"{match['nearest_candidate_u']:.9f} | {match['delta_u']:.9f} | "
            f"{match['absolute_deviation_mm']:.6f} | "
            f"{', '.join(match['signals'])} | {'yes' if match['hit'] else 'no'} |"
        )
        if not match["hit"]:
            missed_matches.append(match)
    if missed_matches:
        lines.extend(["", "### Miss diagnoses", ""])
        lines.extend(
            f"- `{match['landmark_id']}`: {match['miss_diagnosis']}"
            for match in missed_matches
        )
    lines.extend(
        [
            "",
            "## Continuity corroboration",
            "",
            "All original patch joins were measured independently for C0 gap and G1 tangent "
            "angle, then compared only afterward with the compiler diagnostics. Threshold "
            "classifications agree for every join.",
            "",
            "## Conclusion",
            "",
            (
                "The deterministic candidate set covers all reviewed junctions at the declared "
                "tolerance."
                if coverage["all_truth_hit"]
                else "The deterministic candidate set does not cover every reviewed junction. "
                "Each miss is disclosed above; smooth semantic partitions are not guaranteed "
                "to produce a deterministic geometric landmark."
            ),
            "",
            f"Visualization: `{report['visualization']}`",
            "",
            "Known duplicate debt: arc-length resampling and signed-curvature numerics are a "
            "local equivalent of private R4 observer helpers and must remain local until a "
            "stable public two-consumer contract exists.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_plot(
    path: Path,
    profile_points: Sequence[BoundaryPoint],
    truth: Sequence[TruthJunction],
    candidates: Sequence[LandmarkCandidate],
) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(11.0, 5.2), dpi=140, constrained_layout=True)
    FigureCanvasAgg(figure)
    axes = figure.add_subplot(1, 1, 1)
    axes.plot(
        [point.z_mm for point in profile_points],
        [point.r_mm for point in profile_points],
        color="#222222",
        linewidth=1.8,
        label="compiled RF-vacuum contour",
    )
    candidate_points = [_point_at_u(profile_points, item.u) for item in candidates]
    axes.scatter(
        [point.z_mm for point in candidate_points],
        [point.r_mm for point in candidate_points],
        marker="x",
        s=46,
        linewidths=1.4,
        color="#d62728",
        label="stable deterministic candidate",
        zorder=3,
    )
    axes.scatter(
        [item.point.z_mm for item in truth],
        [item.point.r_mm for item in truth],
        marker="o",
        s=58,
        facecolors="none",
        edgecolors="#1f77b4",
        linewidths=1.5,
        label="reviewed region junction truth",
        zorder=4,
    )
    for item in truth:
        axes.annotate(
            item.landmark_id.rsplit(".", 1)[-1],
            (item.point.z_mm, item.point.r_mm),
            xytext=(3, 5),
            textcoords="offset points",
            fontsize=7,
            color="#1f77b4",
        )
    axes.set_xlabel("z (mm)")
    axes.set_ylabel("r (mm)")
    axes.set_title("Semantic Acquisition A0: deterministic candidates vs reviewed junctions")
    axes.grid(True, linewidth=0.4, alpha=0.35)
    axes.legend(loc="lower center", fontsize=8, ncol=3)
    axes.set_aspect("equal", adjustable="datalim")
    figure.canvas.print_png(
        str(path), metadata={"Software": BOUNDARY_SIGNAL_ALGORITHM_VERSION}
    )


def _point_at_u(points: Sequence[BoundaryPoint], u_value: float) -> BoundaryPoint:
    cumulative = [0.0]
    for left, right in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + left.distance_to(right))
    target = min(1.0, max(0.0, u_value)) * cumulative[-1]
    index = 0
    while index < len(cumulative) - 2 and target > cumulative[index + 1]:
        index += 1
    width = cumulative[index + 1] - cumulative[index]
    fraction = 0.0 if width <= _POINT_TOLERANCE_MM else (target - cumulative[index]) / width
    left, right = points[index], points[index + 1]
    return BoundaryPoint(
        left.z_mm + fraction * (right.z_mm - left.z_mm),
        left.r_mm + fraction * (right.r_mm - left.r_mm),
    )


def _source_inventory(
    root: Path,
    sources: A0SourceSet,
    truth: TruthData,
    primary_audit: PrimaryAvailabilityAudit,
) -> tuple[list[dict[str, object]], tuple[Path, ...]]:
    record_path = _inside_repo(root, sources.compile_record, "compile record")
    graph_path = _inside_repo(root, sources.instance_graph, "instance graph")
    implementation_paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("boundary_signals.py").resolve(),
    )
    roles: dict[Path, str] = {
        record_path: "selected_compile_record",
        graph_path: "selected_reviewed_instance_graph",
        truth.profile_path: "selected_compiled_profile",
        implementation_paths[0]: "a0_coverage_implementation",
        implementation_paths[1]: "boundary_signal_implementation",
    }
    for path in primary_audit.consumed_json_paths:
        roles.setdefault(path.resolve(), "preferred_instance_selection_evidence")
    paths = tuple(sorted(roles, key=lambda item: item.relative_to(root).as_posix()))
    entries = []
    for path in paths:
        schema_version = None
        if path.suffix.lower() == ".json":
            mapping = _read_json_mapping(path, "input source")
            value = mapping.get("schema_version")
            schema_version = value if isinstance(value, str) else None
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "role": roles[path],
                "raw_sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
                "schema_version": schema_version,
            }
        )
    return entries, paths


def _artifact_inventory(bundle_root: Path) -> list[dict[str, object]]:
    schema_by_name = {
        REPORT_JSON_FILE: A0_REPORT_SCHEMA_VERSION,
        REPORT_MARKDOWN_FILE: None,
        PLOT_FILE: None,
    }
    return [
        {
            "path": path.relative_to(bundle_root).as_posix(),
            "raw_sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
            "schema_version": schema_by_name[path.name],
        }
        for path in sorted(bundle_root.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != MANIFEST_FILE
    ]


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _read_json_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundarySignalError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise BoundarySignalError(f"{label} must be a JSON object")
    return value


def _inside_repo(root: Path, value: Path, label: str) -> Path:
    path = (value if value.is_absolute() else root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise BoundarySignalError(f"{label} must stay inside the repository") from exc
    if not path.is_file():
        raise BoundarySignalError(f"{label} is missing: {path}")
    return path


def _polyline_length(points: Sequence[BoundaryPoint]) -> float:
    return sum(left.distance_to(right) for left, right in zip(points, points[1:]))


__all__ = [
    "A0_ALGORITHM_VERSION",
    "A0_BUNDLE_PREFIX",
    "A0_BUNDLE_SCHEMA_VERSION",
    "A0_MANIFEST_SCHEMA_VERSION",
    "A0_REPORT_SCHEMA_VERSION",
    "A0Bundle",
    "A0SourceSet",
    "CoverageEvaluation",
    "CoverageMatch",
    "MANIFEST_FILE",
    "PLOT_FILE",
    "PrimaryAvailabilityAudit",
    "REPORT_JSON_FILE",
    "REPORT_MARKDOWN_FILE",
    "TruthData",
    "TruthJunction",
    "audit_lerec_availability",
    "boundary_trace_from_compile_record",
    "evaluate_coverage",
    "load_truth_junctions",
    "write_a0_bundle",
]
