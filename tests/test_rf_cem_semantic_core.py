"""No-CST contract and source-adapter tests for RF-CEM semantic core R1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping

import pytest

from rf_cem.family_profile import (
    FAMILY_ID,
    FAMILY_IDENTITY,
    canonical_sha256 as family_sha256,
    make_family_profile,
)
from rf_cem.family_profile.core import FamilyInstance
from rf_cem.semantic.adapters import (
    RF500_INSTANCE_ID,
    SLS2_INSTANCE_ID,
    R1SourceSet,
    build_r1_contracts,
)
from rf_cem.semantic.artifacts import write_r1_bundle
from rf_cem.semantic.cli import main as semantic_main
from rf_cem.semantic.contracts import (
    FamilyGrammar,
    InstanceBoundaryGraph,
    SemanticContractError,
    load_family_grammar,
    load_instance_boundary_graph,
    load_instance_graph_diff,
    validate_graph_against_grammar,
)
from rf_cem.semantic.ontology import NOSE_REGION
from rf_cem.semantic.schema import (
    load_family_grammar_schema,
    load_graph_diff_schema,
    load_instance_boundary_graph_schema,
)
from rf_cem.workbench import (
    RegistryReader,
    WorkbenchServer,
    WorkbenchSourceSet,
    rebuild_workbench,
)


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH_TOKEN = "semantic-w1-test-token-0123456789"


_SLS2_SEGMENTS = (
    ("seg_beam_pipe_left", ["feature.beam_pipe_left"]),
    (
        "seg_ellipse_left_lower",
        ["feature.beam_pipe_left", "feature.ellipse_wall_left"],
    ),
    (
        "seg_ellipse_left_upper",
        ["feature.ellipse_wall_left", "feature.equator"],
    ),
    (
        "seg_ellipse_right_upper",
        ["feature.equator", "feature.ellipse_wall_right"],
    ),
    (
        "seg_ellipse_right_lower",
        ["feature.ellipse_wall_right", "feature.beam_pipe_right"],
    ),
    ("seg_beam_pipe_right", ["feature.beam_pipe_right"]),
)
_CANDIDATES = {
    "beam_aperture_candidate_01": "BeamAperture",
    "beam_exit_candidate_01": "BeamExit",
    "beam_pipe_left_candidate_01": "BeamPipeLeft",
    "beam_pipe_right_candidate_01": "BeamPipeRight",
    "conducting_wall_candidate_01": "ConductingWall",
    "equator_region_candidate_01": "EquatorRegion",
    "iris_candidate_01": "Iris",
    "iris_candidate_02": "Iris",
    "rfvacuum_volume_candidate_01": "RFVacuumVolume",
}


def _write_json(path: Path, value: Mapping[str, Any]) -> str:
    data = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _evidence(raw_sha256: str = "a" * 64) -> dict[str, object]:
    return {
        "bundle_relative_path": "fixture/source.json",
        "locator": "#/fixture",
        "source_file_sha256": raw_sha256,
    }


def _family_instance(
    instance_id: str,
    native_payload: Mapping[str, Any],
    *,
    source_artifact_raw_sha256: str,
    artifacts: list[dict[str, object]],
) -> dict[str, object]:
    native_hash = family_sha256(native_payload)
    return {
        "schema_version": "family_instance.v0",
        "instance_id": instance_id,
        "family_id": FAMILY_ID,
        "source_binding": {
            "manifest_id": instance_id,
            "manifest_schema_version": "fixture_manifest.v0",
            "manifest_raw_sha256": "b" * 64,
            "artifacts": artifacts,
        },
        "native_schema": "fixture_native.v0",
        "native_model_type": "axisymmetric_fixture",
        "native_variant": "reviewed_fixture",
        "native_units": {"length": "mm"},
        "parameter_payload": {
            "adapter_id": "semantic_r1_fixture.v0",
            "native_schema_version": "fixture_native.v0",
            "native_payload": deepcopy(native_payload),
            "native_payload_locator": "fixture/source.json#/payload",
            "native_payload_canonical_sha256": native_hash,
            "source_payload_canonical_sha256": native_hash,
            "portable_projection_canonical_sha256": native_hash,
            "source_artifact_raw_sha256": source_artifact_raw_sha256,
            "parameter_groups": {
                "fixture_parameters": {
                    "values": {"fixture": 1.0},
                    "count": 1,
                    "scope": "fixture_only",
                }
            },
            "parameter_count": {"fixture_parameters": 1, "total": 1},
            "units": {"length": "mm"},
            "scope": "fixture_source_payload",
            "source_refs": [_evidence(source_artifact_raw_sha256)],
        },
        "geometry_artifacts": [
            {
                "role": "fixture_geometry",
                "bundle_relative_path": "fixture/geometry.step",
                "raw_sha256": "c" * 64,
            }
        ],
        "validation_layers": {
            "payload_schema_validation": {"status": "pass"},
            "parameter_validation": {"status": "pass"},
            "geometry_generation": {"status": "pass"},
            "geometry_validation": {"status": "pass"},
            "human_review": {"status": "pass"},
            "helper2_review": {"status": "partial"},
            "live_cst": {"status": "not_linked"},
            "physical_acceptance": {"status": "not_established"},
        },
        "family_assertion_evidence": {
            key: {
                "claim": claim,
                "status": "supported",
                "evidence": [_evidence(source_artifact_raw_sha256)],
            }
            for key, claim in FAMILY_IDENTITY.items()
        },
        "provenance": {"fixture": True, "no_cst": True},
        "live_cst": {"status": "not_linked"},
        "physical_acceptance": {"status": "not_established"},
    }


def _rf500_native_payload() -> dict[str, object]:
    segments = [
        ("seg_beam_pipe_left", ["BeamPipeLeft"]),
        ("seg_nose_left_smooth_nurbs", ["NoseCone", "TransitionBlend"]),
        ("seg_blend_left", ["TransitionBlend", "EquatorRegion"]),
        ("seg_equator_free_crown", ["EquatorRegion"]),
        ("seg_blend_right", ["TransitionBlend", "EquatorRegion"]),
        ("seg_nose_right_smooth_nurbs", ["TransitionBlend", "NoseCone"]),
        ("seg_beam_pipe_right", ["BeamPipeRight"]),
    ]
    bindings: list[dict[str, object]] = []
    definitions = (
        ("beam_aperture_candidate_01", "BeamAperture", ["seg_beam_pipe_left"]),
        ("beam_exit_candidate_01", "BeamExit", ["seg_beam_pipe_right"]),
        ("beam_pipe_left_candidate_01", "BeamPipeLeft", ["seg_beam_pipe_left"]),
        ("beam_pipe_right_candidate_01", "BeamPipeRight", ["seg_beam_pipe_right"]),
        ("conducting_wall_candidate_01", "ConductingWall", []),
        ("equator_region_candidate_01", "EquatorRegion", ["seg_equator_free_crown"]),
        (
            "iris_candidate_01",
            "NoseCone",
            [
                "seg_nose_left_inner_semicircle",
                "seg_nose_left_outer_quarter",
                "seg_nose_right_outer_quarter",
                "seg_nose_right_inner_semicircle",
            ],
        ),
        ("transition_blend_candidate_01", "TransitionBlend", ["seg_blend_left", "seg_blend_right"]),
    )
    for feature_id, feature_type, segment_ids in definitions:
        bindings.append(
            {
                "feature_id": feature_id,
                "feature_type": feature_type,
                "confidence": 0.9,
                "provenance": f"reviewed_feature_labels.yaml::feature.{feature_type.casefold()}",
                "segment_ids": segment_ids,
            }
        )
    return {
        "schema_version": "parametric_geometry.v0",
        "profile": {
            "segments": [
                {"id": segment_id, "feature_refs": feature_refs}
                for segment_id, feature_refs in segments
            ]
        },
        "feature_bindings": bindings,
    }


def _source_set(tmp_path: Path) -> R1SourceSet:
    generation: dict[str, object] = {
        "schema_version": "literature_geometry_generation.v0",
        "candidate_id": "sls2.cavity_1.paper_approximation",
        "profile": {
            "symmetry": {"left_right_mirrored": True, "plane": "z=0"},
            "segments": [
                {"id": segment_id, "feature_refs": feature_refs}
                for segment_id, feature_refs in _SLS2_SEGMENTS
            ],
        },
    }
    semantics: dict[str, object] = {
        "schema_version": "literature_semantics.v0",
        "request_context": {
            "geometry_scope": "axisymmetric_single_cell_rf_vacuum",
            "operating_regime": "normal_conducting",
        },
        "classification": {"cell_count": "single"},
        "evidence_sources": [{"id": "paper", "source_type": "paper"}],
    }
    candidates = {
        feature_id: {
            "type": feature_type,
            "status": "confirmed",
            "geometry_refs": [f"face:{index:04d}"],
        }
        for index, (feature_id, feature_type) in enumerate(_CANDIDATES.items(), 1)
    }
    bindings = {
        f"bind_{feature_id}": {
            "feature_id": feature_id,
            "geometry_node_id": candidate["geometry_refs"][0],
            "status": "accepted",
            "deleted": False,
        }
        for feature_id, candidate in candidates.items()
    }
    review: dict[str, object] = {
        "schema_version": "review_session.v1",
        "revision": 149,
        "helper2_reviews": {
            "sls2.cavity_1.paper_approximation": {
                "revision": 147,
                "review": {
                    "schema_version": "helper2_review_session.v1",
                    "candidates": candidates,
                    "bindings": bindings,
                    "geometry": {
                        f"F{index:04d}": {"status": "accepted"}
                        for index in range(1, 10)
                    },
                },
            }
        },
        "review_decisions": {
            "sls2::geometry::geometry_projection::sls2.cavity_1.paper_approximation": {
                "status": "accepted",
                "revision": 72,
            }
        },
    }
    generation_path = tmp_path / "sls2" / "generation.core.json"
    semantics_path = tmp_path / "sls2" / "literature_semantics.v0.json"
    review_path = tmp_path / "sls2" / "review_session.v1.json"
    generation_hash = _write_json(generation_path, generation)
    semantics_hash = _write_json(semantics_path, semantics)
    review_hash = _write_json(review_path, review)

    sls2_native = {"fixture": "sls2"}
    sls2_instance = _family_instance(
        SLS2_INSTANCE_ID,
        sls2_native,
        source_artifact_raw_sha256=generation_hash,
        artifacts=[
            {"bundle_relative_path": "generation.core.json", "raw_sha256": generation_hash},
            {"bundle_relative_path": "literature_semantics.v0.json", "raw_sha256": semantics_hash},
            {"bundle_relative_path": "review_session.v1.json", "raw_sha256": review_hash},
        ],
    )
    rf500_hash = "d" * 64
    rf500_instance = _family_instance(
        RF500_INSTANCE_ID,
        _rf500_native_payload(),
        source_artifact_raw_sha256=rf500_hash,
        artifacts=[
            {
                "bundle_relative_path": "source/parametric_geometry.v0.json",
                "raw_sha256": rf500_hash,
            }
        ],
    )
    profile = make_family_profile(
        [
            FamilyInstance.from_mapping(sls2_instance),
            FamilyInstance.from_mapping(rf500_instance),
        ]
    ).to_mapping()
    profile_path = tmp_path / "family" / "family_profile.v0.json"
    _write_json(profile_path, profile)
    return R1SourceSet(
        repo_root=tmp_path,
        family_profile=profile_path,
        sls2_generation=generation_path,
        sls2_semantics=semantics_path,
        sls2_review=review_path,
    )


def test_schema_contracts_are_versioned_and_representation_independent() -> None:
    grammar_schema = load_family_grammar_schema()
    graph_schema = load_instance_boundary_graph_schema()
    diff_schema = load_graph_diff_schema()
    assert grammar_schema["properties"]["schema_version"]["const"] == "family_grammar.v0"
    assert graph_schema["properties"]["schema_version"]["const"] == "instance_boundary_graph.v0"
    assert diff_schema["properties"]["schema_version"]["const"] == "instance_boundary_graph_diff.v0"
    schema_text = json.dumps(
        [grammar_schema, graph_schema, diff_schema], sort_keys=True
    )
    for forbidden in ("cadquery", "OCP", "cst.interface", "common_parameter_vector"):
        assert forbidden not in schema_text


def test_sources_build_both_topologies_and_strict_round_trips(tmp_path: Path) -> None:
    contracts = build_r1_contracts(_source_set(tmp_path))
    graphs = contracts.graphs_by_id
    sls2 = graphs[SLS2_INSTANCE_ID]
    rf500 = graphs[RF500_INSTANCE_ID]

    assert len(sls2.regions) == 9
    assert sls2.nose_presence == "absent_reviewed_topology"
    assert all(region.region_type != NOSE_REGION for region in sls2.regions)
    assert len(rf500.regions) == 11
    assert rf500.nose_presence == "present"
    assert sum(region.region_type == NOSE_REGION for region in rf500.regions) == 2
    assert all(
        region.region_id.startswith(f"{graph.instance_id}.region.")
        and region.evidence
        and region.review.is_terminal
        for graph in contracts.graphs
        for region in graph.regions
    )
    assert len(contracts.graph_diff.common_regions) == 9
    assert len(contracts.graph_diff.right_only_regions) == 2
    assert contracts.graph_diff.left_only_regions == ()
    assert contracts.graph_diff.adjacency_changes
    assert contracts.graph_diff.parameter_comparison.endswith(
        "no_common_geometry_parameter_vector"
    )

    grammar_round_trip = FamilyGrammar.from_mapping(contracts.grammar.to_mapping())
    assert grammar_round_trip == contracts.grammar
    for graph in contracts.graphs:
        assert InstanceBoundaryGraph.from_mapping(graph.to_mapping()) == graph
        validate_graph_against_grammar(grammar_round_trip, graph)

    forbidden_keys = {
        "named_parameters",
        "derived_parameters",
        "parameter_groups",
        "parameter_values",
    }
    assert not (forbidden_keys & _all_mapping_keys(contracts.grammar.to_mapping()))
    for graph in contracts.graphs:
        assert not (forbidden_keys & _all_mapping_keys(graph.to_mapping()))


def test_invalid_adjacency_cardinality_and_interface_fail_closed(
    tmp_path: Path,
) -> None:
    contracts = build_r1_contracts(_source_set(tmp_path))
    sls2, rf500 = contracts.graphs
    with pytest.raises(SemanticContractError, match="allowed_adjacencies"):
        replace(
            contracts.grammar,
            allowed_adjacencies=tuple(
                pair
                for pair in contracts.grammar.allowed_adjacencies
                if pair != ("BeamPipeRegion", "IrisRegion")
            ),
        )

    cardinalities = dict(contracts.grammar.type_cardinality)
    cardinalities[NOSE_REGION] = (0,)
    with pytest.raises(SemanticContractError, match="motif/cardinality"):
        replace(
            contracts.grammar,
            type_cardinality=tuple(sorted(cardinalities.items())),
        )

    broken_interface = replace(
        sls2.interfaces[0], right_region_id=sls2.regions[2].region_id
    )
    with pytest.raises(SemanticContractError, match="ordered adjacency"):
        replace(sls2, interfaces=(broken_interface, *sls2.interfaces[1:]))


def test_source_hash_and_review_topology_mismatches_fail_closed(
    tmp_path: Path,
) -> None:
    sources = _source_set(tmp_path)
    generation = json.loads(sources.sls2_generation.read_text(encoding="utf-8"))
    generation["tampered"] = True
    _write_json(sources.sls2_generation, generation)
    with pytest.raises(SemanticContractError, match="source hash mismatch"):
        build_r1_contracts(sources)

    second = _source_set(tmp_path / "second")
    review = json.loads(second.sls2_review.read_text(encoding="utf-8"))
    candidates = review["helper2_reviews"]["sls2.cavity_1.paper_approximation"]["review"]["candidates"]
    candidates["nose_candidate_01"] = {
        "type": "NoseCone",
        "status": "confirmed",
        "geometry_refs": ["face:F9999"],
    }
    new_review_hash = _write_json(second.sls2_review, review)
    profile = json.loads(second.family_profile.read_text(encoding="utf-8"))
    profile["instances"][0]["source_binding"]["artifacts"][2][
        "raw_sha256"
    ] = new_review_hash
    _write_json(second.family_profile, profile)
    with pytest.raises(SemanticContractError, match="candidate set|nose"):
        build_r1_contracts(second)


def test_bundle_is_deterministic_loadable_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    contracts = build_r1_contracts(_source_set(tmp_path / "sources"))
    first = write_r1_bundle(contracts, tmp_path / "one")
    second = write_r1_bundle(contracts, tmp_path / "two")
    assert first.bundle_id == second.bundle_id
    assert first.content_sha256 == second.content_sha256
    assert _tree_bytes(first.path) == _tree_bytes(second.path)
    with pytest.raises(FileExistsError):
        write_r1_bundle(contracts, tmp_path / "one")

    grammar = load_family_grammar(first.path / "family_grammar.v0.json")
    graphs = [
        load_instance_boundary_graph(path)
        for path in sorted((first.path / "instances").glob("*.json"))
    ]
    assert {graph.instance_id for graph in graphs} == {
        SLS2_INSTANCE_ID,
        RF500_INSTANCE_ID,
    }
    for graph in graphs:
        validate_graph_against_grammar(grammar, graph)
    diff = load_instance_graph_diff(first.path / "instance_graph_diff.v0.json")
    assert diff.right_only_regions


def test_cli_build_validate_and_diff(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sources = _source_set(tmp_path / "sources")
    output_root = tmp_path / "bundles"
    assert semantic_main(
        [
            "build",
            "--repo-root",
            str(sources.repo_root),
            "--family-profile",
            str(sources.family_profile),
            "--sls2-generation",
            str(sources.sls2_generation),
            "--sls2-semantics",
            str(sources.sls2_semantics),
            "--sls2-review",
            str(sources.sls2_review),
            "--output-root",
            str(output_root),
        ]
    ) == 0
    result = json.loads(capsys.readouterr().out)
    bundle = output_root / result["bundle_id"]
    graph_paths = sorted((bundle / "instances").glob("*.json"))
    assert semantic_main(
        [
            "validate",
            "--grammar",
            str(bundle / "family_grammar.v0.json"),
            "--graph",
            str(graph_paths[0]),
            "--graph",
            str(graph_paths[1]),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pass"
    assert semantic_main(
        ["diff", "--left", str(graph_paths[0]), "--right", str(graph_paths[1])]
    ) == 0
    assert json.loads(capsys.readouterr().out)["classification"] == (
        "semantic_topology_difference"
    )


def test_workbench_w1_indexes_and_renders_semantic_graphs() -> None:
    scratch = ROOT / ".codex_tmp"
    scratch.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="semantic-w1-", dir=scratch) as value:
            workdir = Path(value)
            semantic_sources = _source_set(workdir / "sources")
            contracts = build_r1_contracts(semantic_sources)
            bundle = write_r1_bundle(contracts, workdir / "proofs")
            graphs = tuple(sorted((bundle.path / "instances").glob("*.json")))
            database = workdir / "workbench.sqlite"
            source_set = WorkbenchSourceSet(
                repo_root=ROOT,
                family_profile=semantic_sources.family_profile,
                family_grammar=bundle.path / "family_grammar.v0.json",
                instance_boundary_graphs=graphs,
                instance_graph_diff=bundle.path / "instance_graph_diff.v0.json",
            )
            first = rebuild_workbench(database, source_set)
            first_snapshot = RegistryReader(database).snapshot()
            second = rebuild_workbench(database, source_set)
            assert first.input_set_sha256 == second.input_set_sha256
            assert first_snapshot == RegistryReader(database).snapshot()

            counts = RegistryReader(database).entity_counts()
            assert counts["family_grammar"] == 1
            assert counts["instance_graph"] == 2
            assert counts["semantic_motif"] == 1
            assert counts["semantic_region"] == 20
            assert counts["semantic_landmark"] == 24
            assert counts["boundary_interface"] == 18
            assert counts["graph_diff"] == 1
            entities = {
                (item["entity_kind"], item["entity_id"]): item
                for item in RegistryReader(database).snapshot()["entities"]
            }
            assert entities[("validation", "w1.semantic-hard-gate")]["status"] == "pass"
            assert entities[
                (
                    "instance_graph",
                    f"{SLS2_INSTANCE_ID}.boundary_graph.v0",
                )
            ]["payload"]["nose_presence"] == "absent_reviewed_topology"
            assert entities[
                (
                    "instance_graph",
                    f"{RF500_INSTANCE_ID}.boundary_graph.v0",
                )
            ]["payload"]["nose_presence"] == "present"

            with WorkbenchServer(
                database,
                source_root=ROOT,
                token=WORKBENCH_TOKEN,
            ) as server:
                connection = HTTPConnection(server.host, server.port, timeout=5)
                connection.request(
                    "GET", f"/semantic-graphs?token={WORKBENCH_TOKEN}"
                )
                response = connection.getresponse()
                body = response.read().decode("utf-8")
                connection.close()
            assert response.status == 200
            assert "Semantic Graphs / W1" in body
            assert "Nose: absent (reviewed topology)" in body
            assert "Nose: present (paired motif)" in body
            assert "Optional semantic motifs" in body
            assert "Semantic topology diff" in body
            assert "BeamPipeRegion" in body
            assert "NoseRegion" in body
    finally:
        try:
            scratch.rmdir()
        except OSError:
            pass


def _all_mapping_keys(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        result.update(str(key) for key in value)
        for item in value.values():
            result.update(_all_mapping_keys(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_all_mapping_keys(item))
    return result


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
