"""Atomic input-addressed proof bundles for the two canonical R2 compiles."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from rf_cem.semantic.contracts import (
    canonical_json_bytes,
    canonical_sha256,
    canonicalization_contract,
    file_sha256,
)

from .adapters import R2SourceSet, prepare_r2_cases
from .contracts import COMPILE_RECORD_SCHEMA_VERSION, CompileContractError, CompileRecord
from .core import ProfileCompiler


R2_BUNDLE_SCHEMA_VERSION = "r2_boundary_compiler_bundle.v0"
R2_MANIFEST_SCHEMA_VERSION = "r2_compile_source_binding_manifest.v0"
R2_BUNDLE_PREFIX = "r2_boundary_compiler"


@dataclass(frozen=True)
class R2Bundle:
    """Location, input identity and records for one immutable R2 proof bundle."""

    path: Path
    bundle_id: str
    input_sha256: str
    records: tuple[CompileRecord, ...]
    manifest: Mapping[str, Any]


def write_r2_bundle(sources: R2SourceSet, output_root: Path) -> R2Bundle:
    """Compile both real cases into a new atomic bundle and refuse overwrite."""

    cases = prepare_r2_cases(sources)
    input_preimage = {
        "schema_version": R2_BUNDLE_SCHEMA_VERSION,
        "canonicalization_contract": canonicalization_contract(),
        "compile_requests": [case.request.to_mapping() for case in cases],
    }
    input_sha256 = canonical_sha256(input_preimage)
    bundle_id = f"{R2_BUNDLE_PREFIX}.{input_sha256[:16]}"
    root = output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / bundle_id
    if target.exists():
        raise FileExistsError(f"R2 compile proof bundle already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle_id}.tmp-", dir=root))
    try:
        compiler = ProfileCompiler()
        records: list[CompileRecord] = []
        for case in cases:
            result = compiler.compile(
                case.request,
                bundle_root=temporary,
                source_profile_points=case.source_profile_points,
                baseline_step=case.baseline_step,
            )
            if result.record.status != "pass":
                raise CompileContractError(
                    f"R2 compile failed hard gate: {result.record.instance_id}"
                )
            record_path = (
                temporary
                / "records"
                / f"{result.record.instance_id}.compile_record.v0.json"
            )
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_bytes(canonical_json_bytes(result.record.to_mapping()) + b"\n")
            records.append(result.record)
        manifest = _manifest_mapping(
            sources=sources,
            bundle_id=bundle_id,
            input_sha256=input_sha256,
            bundle_root=temporary,
            records=tuple(records),
        )
        (temporary / "source_binding_manifest.v0.json").write_bytes(
            canonical_json_bytes(manifest) + b"\n"
        )
        if target.exists():
            raise FileExistsError(f"R2 compile proof bundle already exists: {target}")
        os.replace(temporary, target)
    except BaseException:
        if temporary.exists() and temporary.parent == root:
            shutil.rmtree(temporary)
        raise
    return R2Bundle(
        path=target,
        bundle_id=bundle_id,
        input_sha256=input_sha256,
        records=tuple(records),
        manifest=manifest,
    )


def _manifest_mapping(
    *,
    sources: R2SourceSet,
    bundle_id: str,
    input_sha256: str,
    bundle_root: Path,
    records: tuple[CompileRecord, ...],
) -> dict[str, Any]:
    root = sources.repo_root.resolve()
    source_paths = (
        sources.family_profile,
        sources.family_grammar,
        *sources.instance_graphs,
        sources.sls2_generation,
        sources.sls2_baseline_step,
    )
    source_files = []
    for value in source_paths:
        path = (value if value.is_absolute() else root / value).resolve()
        source_files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "raw_sha256": file_sha256(path),
            }
        )
    artifacts = []
    for path in sorted(item for item in bundle_root.rglob("*") if item.is_file()):
        relative = path.relative_to(bundle_root).as_posix()
        if relative == "source_binding_manifest.v0.json":
            continue
        schema_version: str | None = None
        if path.suffix.lower() == ".json":
            try:
                mapping = json.loads(path.read_text(encoding="utf-8"))
                candidate = mapping.get("schema_version") if isinstance(mapping, dict) else None
                schema_version = candidate if isinstance(candidate, str) else None
            except (OSError, UnicodeError, json.JSONDecodeError):
                schema_version = None
        artifacts.append(
            {
                "path": relative,
                "raw_sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
                "schema_version": schema_version,
            }
        )
    return {
        "schema_version": R2_MANIFEST_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "input_sha256": input_sha256,
        "canonicalization_contract": canonicalization_contract(),
        "validation_mode": "no_cst_isolated_geometry_kernel",
        "status": "pass",
        "source_files": sorted(source_files, key=lambda item: item["path"]),
        "compile_records": [
            {
                "instance_id": record.instance_id,
                "compile_id": record.compile_id,
                "content_sha256": record.content_sha256,
                "schema_version": COMPILE_RECORD_SCHEMA_VERSION,
                "status": record.status,
                "region_count": len(record.region_geometries),
                "patch_count": record.patch_count,
                "live_cst_status": record.live_cst_status,
                "physical_acceptance_status": record.physical_acceptance_status,
            }
            for record in records
        ],
        "artifacts": artifacts,
        "checks": [
            "one_compiler_entry_for_both_instances",
            "semantic_and_representation_dependency_independence",
            "one_region_geometry_per_semantic_region",
            "one_owner_per_patch",
            "source_segment_parameter_partitions_complete_without_overlap",
            "shared_landmarks_resolved",
            "deterministic_region_patch_order_and_orientation",
            "required_continuity_passed_and_g1_g2_diagnostics_recorded",
            "profile_simple_nonnegative_and_axis_closable",
            "step_exported_and_brep_valid",
            "accepted_baseline_comparison_passed",
            "stage_c_source_native_provenance_preserved",
            "live_cst_not_run",
        ],
        "exclusions": [
            "family_induction",
            "observation_contract",
            "rf_metric_contract",
            "live_cst_execution",
            "rf_physical_acceptance",
            "optimization_search",
        ],
    }


__all__ = [
    "R2Bundle",
    "R2_BUNDLE_PREFIX",
    "R2_BUNDLE_SCHEMA_VERSION",
    "R2_MANIFEST_SCHEMA_VERSION",
    "write_r2_bundle",
]
