import importlib.util
import json

import pytest

from step_feature_assistant.layer_builders import (
    build_feature_candidates,
    build_geometry_graph,
    build_udsg_geometry_layer,
)
from step_feature_assistant.reviewer import write_interactive_reviewer
from step_feature_assistant.topology_analyzer import build_adjacency_graph


pytestmark = pytest.mark.no_cst


def test_reviewer_generates_from_legacy_inputs(tmp_path):
    if importlib.util.find_spec("plotly") is None:
        pytest.skip("Plotly is not installed")
    manifest = _manifest()
    draft = _draft()
    mesh_path = _write_mesh(tmp_path)
    html_path = tmp_path / "model_review.html"

    write_interactive_reviewer(html_path, mesh_path, manifest, draft)

    html = html_path.read_text(encoding="utf-8")
    assert "Geometry" in html
    assert "Features" in html
    assert "UDSG" in html
    assert "Review" in html
    assert "Download reviewed labels YAML" in html
    assert "Download review_session.json" in html
    assert "Geometry Audit" in html
    assert "Surface Classification" in html
    assert "Binding Review Guide" in html
    assert "Fast drag" in html
    assert "Accept binding" in html
    assert "Apply binding edit" in html
    assert "Delete binding" in html
    assert "feature candidate -> geometry node -> evidence" in html
    assert "candidateRefs" in html
    assert "confirmed_features:" in html
    assert "rejected_candidates:" in html
    assert "manual_groups:" in html


def test_reviewer_embeds_three_layer_payload(tmp_path):
    if importlib.util.find_spec("plotly") is None:
        pytest.skip("Plotly is not installed")
    manifest = _manifest()
    draft = _draft()
    adjacency = build_adjacency_graph(manifest)
    geometry_graph = build_geometry_graph(manifest, adjacency)
    feature_candidates = build_feature_candidates(draft)
    udsg_layer = build_udsg_geometry_layer(geometry_graph, feature_candidates, draft["face_groups"])
    mesh_path = _write_mesh(tmp_path)
    html_path = tmp_path / "model_review.html"

    write_interactive_reviewer(
        html_path,
        mesh_path,
        manifest,
        draft,
        geometry_graph=geometry_graph,
        feature_candidates=feature_candidates,
        udsg_geometry_layer=udsg_layer,
    )

    html = html_path.read_text(encoding="utf-8")
    assert "geometry_graph.v0" in html
    assert "feature_candidates.v0" in html
    assert "udsg_geometry_layer.v0" in html
    assert "review_issues.v0" in html
    assert "bind_" in html
    assert "requires_review" in html
    assert "geometry_checks" in html
    assert "bindings" in html
    assert "recolorFaces" in html
    assert "bindingEdits" in html
    assert "original_geometry_node_id" in html


def _manifest():
    return {
        "schema_version": "0.1",
        "source_step": "fake.step",
        "reader": {"backend": "test", "units": "mm"},
        "model_summary": {
            "solid_count": 1,
            "shell_count": 1,
            "face_count": 2,
            "edge_count": 1,
            "bbox": {"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1, "zmin": 0, "zmax": 1},
            "detected_axis": "z",
        },
        "faces": [
            _face("F0001", "plane", [0.25, 0.25, 0.0], ["F0002"]),
            _face("F0002", "cylinder", [0.75, 0.75, 0.5], ["F0001"]),
        ],
    }


def _face(face_id, surface_type, centroid, adjacent):
    return {
        "face_id": face_id,
        "surface_type": surface_type,
        "area": 1.0,
        "centroid": centroid,
        "normal_estimate": [0.0, 0.0, 1.0],
        "bbox": {"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1, "zmin": 0, "zmax": 1},
        "axis_relation": {"is_axisymmetric": surface_type == "cylinder", "r_range": [0.0, 1.0], "z_range": [0, 1]},
        "edge_count": 1,
        "adjacent_faces": adjacent,
        "fingerprint": f"hash-{face_id}",
    }


def _draft():
    return {
        "schema_version": "0.1",
        "source_geometry_manifest": "geometry_manifest.json",
        "model_type": "bare_cavity_500mhz",
        "axis": "z",
        "features": [
            {
                "id": "wall_candidate_01",
                "type": "ConductingWall",
                "geometry_refs": ["face:F0002"],
                "confidence": 0.7,
                "evidence": ["test wall"],
                "status": "candidate",
                "requires_human_review": True,
            },
            {
                "id": "aperture_candidate_01",
                "type": "BeamAperture",
                "geometry_refs": ["face:F0001"],
                "confidence": 0.5,
                "evidence": ["test aperture"],
                "status": "candidate",
                "requires_human_review": True,
            },
        ],
        "face_groups": [{"group_id": "G0001", "member_faces": ["F0001"], "group_type_candidate": "plane_adjacent_faces"}],
        "unassigned_faces": [],
    }


def _write_mesh(tmp_path):
    mesh_path = tmp_path / "face_meshes.json"
    payload = {
        "faces": [
            {
                "face_id": "F0001",
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "triangles": [[0, 1, 2]],
            },
            {
                "face_id": "F0002",
                "vertices": [[0, 0, 1], [1, 0, 1], [0, 1, 1]],
                "triangles": [[0, 1, 2]],
            },
        ]
    }
    mesh_path.write_text(json.dumps(payload), encoding="utf-8")
    return mesh_path
