from pathlib import Path
import importlib.util

import pytest

import json
import re

from step_feature_assistant.cadquery_reader import read_cadquery_geometry_manifest
from step_feature_assistant.feature_candidate_generator import generate_feature_graph_draft
from step_feature_assistant.reviewer import write_interactive_reviewer


pytestmark = pytest.mark.no_cst


def test_cadquery_reader_builds_kernel_manifest_for_bare_cavity(tmp_path):
    if importlib.util.find_spec("cadquery") is None:
        pytest.skip("CadQuery is not installed")
    step_file = Path("StepData/bare_cavity_500mhz.stp")
    if not step_file.exists():
        pytest.skip("StepData fixture is not available")

    mesh_path = tmp_path / "face_meshes.json"
    manifest = read_cadquery_geometry_manifest(step_file, "z", mesh_path)

    assert manifest["reader"]["backend"] == "cadquery_ocp"
    assert manifest["reader"]["measurement_quality"] == "cad_kernel"
    assert manifest["model_summary"]["face_count"] == 26
    assert manifest["model_summary"]["edge_count"] == 64
    assert manifest["model_summary"]["bbox"]["zmax"] > manifest["model_summary"]["bbox"]["zmin"]

    first_face = manifest["faces"][0]
    assert first_face["measurement_quality"] == "cad_kernel"
    assert first_face["area"] > 0
    assert first_face["area_method"] == "cadquery_ocp_area"
    assert first_face["edge_count"] > 0
    assert first_face["adjacent_faces"]
    assert first_face["solid_refs"]
    assert first_face["shell_refs"]
    mesh = json.loads(mesh_path.read_text(encoding="utf-8"))
    assert len(mesh["faces"]) == 26

    draft = generate_feature_graph_draft(manifest, "bare_cavity_500mhz", "z")
    html_path = tmp_path / "model_review.html"
    write_interactive_reviewer(html_path, mesh_path, manifest, draft)
    html = html_path.read_text(encoding="utf-8")
    assert "Download reviewed labels YAML" in html
    assert "Download review_session.json" in html
    assert "Geometry" in html
    assert "Features" in html
    assert "UDSG" in html
    assert "Review" in html
    assert "Add selected faces" in html
    assert "data-remove-ref" in html
    assert "candidateRefs" in html
    assert "Plotly.restyle(plot,{color:" not in html
    assert re.search(r'"name":"F0017".*?"color":"#d64045"', html, re.DOTALL)
    assert re.search(r'"name":"F0021".*?"color":"#d64045"', html, re.DOTALL)
