"""Deterministic, content-addressed proof bundles for R1 semantic contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from .adapters import RF500_INSTANCE_ID, SLS2_INSTANCE_ID, R1Contracts
from .contracts import (
    SemanticContractError,
    canonical_json_bytes,
    canonical_sha256,
    canonicalization_contract,
)


VALIDATION_SCHEMA_VERSION = "semantic_validation.v0"
SOURCE_MANIFEST_SCHEMA_VERSION = "semantic_source_binding_manifest.v0"
BUNDLE_PREFIX = "r1_semantic_core"


@dataclass(frozen=True)
class R1Bundle:
    """Location and deterministic identity of one written R1 proof bundle."""

    path: Path
    bundle_id: str
    content_sha256: str
    manifest: Mapping[str, Any]


def write_r1_bundle(contracts: R1Contracts, output_root: Path) -> R1Bundle:
    """Write a new immutable R1 bundle and refuse any existing target."""

    grammar_mapping = contracts.grammar.to_mapping()
    graph_mappings = {
        graph.instance_id: graph.to_mapping() for graph in contracts.graphs
    }
    diff_mapping = contracts.graph_diff.to_mapping()
    validation_mapping = _validation_mapping(contracts)
    object_mappings: dict[str, Mapping[str, Any]] = {
        "family_grammar.v0.json": grammar_mapping,
        (
            f"instances/{SLS2_INSTANCE_ID}.instance_boundary_graph.v0.json"
        ): graph_mappings[SLS2_INSTANCE_ID],
        (
            f"instances/{RF500_INSTANCE_ID}.instance_boundary_graph.v0.json"
        ): graph_mappings[RF500_INSTANCE_ID],
        "instance_graph_diff.v0.json": diff_mapping,
        "semantic_validation.v0.json": validation_mapping,
    }
    artifact_records = tuple(
        _artifact_record(relative_path, mapping)
        for relative_path, mapping in sorted(object_mappings.items())
    )
    content_preimage = {
        "contract": "r1_semantic_proof_bundle.v0",
        "canonicalization_contract": canonicalization_contract(),
        "source_bindings": [
            item.to_mapping() for item in contracts.source_bindings
        ],
        "artifacts": list(artifact_records),
    }
    content_sha256 = canonical_sha256(content_preimage)
    bundle_id = f"{BUNDLE_PREFIX}.{content_sha256[:16]}"
    manifest: dict[str, Any] = {
        "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "content_sha256": content_sha256,
        "canonicalization_contract": canonicalization_contract(),
        "validation_mode": "no_cst_source_audit",
        "source_bindings": [
            item.to_mapping() for item in contracts.source_bindings
        ],
        "artifacts": list(artifact_records),
        "exclusions": [
            "geometry_compilation",
            "common_geometry_parameter_vector",
            "live_cst_execution",
            "rf_physical_acceptance",
        ],
    }
    object_mappings["source_binding_manifest.v0.json"] = manifest

    root = output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / bundle_id
    if target.exists():
        raise FileExistsError(f"R1 proof bundle already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle_id}.tmp-", dir=root))
    try:
        for relative_path, mapping in sorted(object_mappings.items()):
            destination = temporary / Path(relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(_json_file_bytes(mapping))
        if target.exists():
            raise FileExistsError(f"R1 proof bundle already exists: {target}")
        os.replace(temporary, target)
    except BaseException:
        if temporary.exists() and temporary.parent == root:
            shutil.rmtree(temporary)
        raise
    return R1Bundle(
        path=target,
        bundle_id=bundle_id,
        content_sha256=content_sha256,
        manifest=manifest,
    )


def _validation_mapping(contracts: R1Contracts) -> dict[str, Any]:
    graphs = contracts.graphs_by_id
    sls2 = graphs[SLS2_INSTANCE_ID]
    rf500 = graphs[RF500_INSTANCE_ID]
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "status": "pass",
        "validation_mode": "no_cst_source_audit",
        "grammar_id": contracts.grammar.grammar_id,
        "grammar_sha256": canonical_sha256(contracts.grammar.to_mapping()),
        "instance_graphs": [
            {
                "instance_id": graph.instance_id,
                "graph_id": graph.graph_id,
                "graph_sha256": canonical_sha256(graph.to_mapping()),
                "region_count": len(graph.regions),
                "nose_presence": graph.nose_presence,
                "reviewed_region_count": sum(
                    1 for region in graph.regions if region.review.is_terminal
                ),
            }
            for graph in contracts.graphs
        ],
        "graph_diff_sha256": canonical_sha256(
            contracts.graph_diff.to_mapping()
        ),
        "checks": [
            "family_grammar_accepts_sls2",
            "family_grammar_accepts_rf500",
            "sls2_nose_absent_reviewed_topology",
            "rf500_paired_nose_present_and_evidence_bound",
            "all_regions_have_stable_id_evidence_and_terminal_review",
            "interfaces_and_landmarks_form_one_oriented_linear_boundary",
            "graph_diff_is_semantic_topology_not_missing_parameters",
            "common_geometry_parameter_vector_not_introduced",
        ],
        "assertions": {
            "sls2_region_count": len(sls2.regions),
            "sls2_nose_region_count": sum(
                region.region_type == "NoseRegion" for region in sls2.regions
            ),
            "rf500_region_count": len(rf500.regions),
            "rf500_nose_region_count": sum(
                region.region_type == "NoseRegion" for region in rf500.regions
            ),
            "common_region_count": len(contracts.graph_diff.common_regions),
            "right_only_region_count": len(
                contracts.graph_diff.right_only_regions
            ),
            "adjacency_change_count": len(
                contracts.graph_diff.adjacency_changes
            ),
            "parameter_comparison": contracts.graph_diff.parameter_comparison,
        },
        "exclusions": [
            "family_induction",
            "geometry_compilation",
            "live_cst_execution",
            "rf_physical_acceptance",
        ],
    }


def _artifact_record(
    relative_path: str, mapping: Mapping[str, Any]
) -> dict[str, str]:
    data = _json_file_bytes(mapping)
    schema_version = mapping.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        raise SemanticContractError(
            f"semantic artifact {relative_path} lacks schema_version"
        )
    return {
        "relative_path": relative_path,
        "schema_version": schema_version,
        "raw_sha256": hashlib.sha256(data).hexdigest(),
        "canonical_payload_sha256": canonical_sha256(mapping),
    }


def _json_file_bytes(mapping: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(mapping) + b"\n"
