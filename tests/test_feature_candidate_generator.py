import pytest

from step_feature_assistant.feature_candidate_generator import generate_feature_graph_draft


pytestmark = pytest.mark.no_cst


def test_feature_candidate_generator_finds_core_candidates():
    manifest = {
        "schema_version": "0.1",
        "source_step": "fake.step",
        "model_summary": {
            "solid_count": 1,
            "shell_count": 1,
            "face_count": 6,
            "edge_count": 8,
            "bbox": {"xmin": -60, "xmax": 60, "ymin": -60, "ymax": 60, "zmin": 0, "zmax": 100},
            "detected_axis": "z",
        },
        "faces": [
            _face("F0001", "cylinder", 5, 5, [0, 10], True, ["F0002"]),
            _face("F0002", "cylinder", 5, 5, [10, 20], True, ["F0001"]),
            _face("F0003", "cylinder", 50, 50, [40, 60], True, []),
            _face("F0004", "plane", 20, 20, [0, 0], False, []),
            _face("F0005", "plane", 20, 20, [100, 100], False, []),
            _face("F0006", "plane", 60, 60, [45, 55], False, []),
        ],
    }
    manifest["faces"][5]["normal_estimate"] = [1.0, 0.0, 0.0]

    draft = generate_feature_graph_draft(manifest, "bare_cavity_500mhz", "z")
    feature_types = {feature["type"] for feature in draft["features"]}

    assert "RFVacuumVolume" in feature_types
    assert "BeamPipeLeft" in feature_types
    assert "ConductingWall" in feature_types
    assert "BeamAperture" in feature_types
    assert "BeamExit" in feature_types
    assert "UnknownSidePort" in feature_types


def test_xband_z_min_plane_becomes_cathode_candidate():
    manifest = {
        "schema_version": "0.1",
        "source_step": "fake.step",
        "model_summary": {
            "solid_count": 1,
            "shell_count": 1,
            "face_count": 1,
            "edge_count": 4,
            "bbox": {"xmin": -10, "xmax": 10, "ymin": -10, "ymax": 10, "zmin": -5, "zmax": 50},
            "detected_axis": "z",
        },
        "faces": [_face("F0001", "plane", 8, 8, [-5, -5], False, [])],
    }

    draft = generate_feature_graph_draft(manifest, "xband_2.3cell_gun", "z")

    assert any(feature["type"] == "CathodeSurface" for feature in draft["features"])


def test_model_profile_changes_semantics_not_geometry_input():
    manifest = {
        "schema_version": "0.1",
        "source_step": "fake.step",
        "model_summary": {
            "solid_count": 1,
            "shell_count": 1,
            "face_count": 1,
            "edge_count": 4,
            "bbox": {"xmin": -10, "xmax": 10, "ymin": -10, "ymax": 10, "zmin": 0, "zmax": 20},
            "detected_axis": "z",
        },
        "faces": [_face("F0001", "plane", 5, 5, [0, 0], False, [])],
    }

    bare = generate_feature_graph_draft(manifest, "bare_cavity_500mhz", "z")
    xband = generate_feature_graph_draft(manifest, "xband_2.3cell_gun", "z")

    assert any(feature["type"] == "BeamAperture" for feature in bare["features"])
    assert any(feature["type"] == "CathodeSurface" for feature in xband["features"])
    assert manifest["model_summary"]["face_count"] == 1


def _face(face_id, surface_type, rmin, rmax, z_range, axisymmetric, adjacent):
    return {
        "face_id": face_id,
        "surface_type": surface_type,
        "centroid": [rmax, 0.0, sum(z_range) / 2.0],
        "normal_estimate": [0.0, 0.0, 1.0],
        "axis_relation": {
            "is_axisymmetric": axisymmetric,
            "radius_mean": (rmin + rmax) / 2.0,
            "r_range": [rmin, rmax],
            "z_range": z_range,
        },
        "adjacent_faces": adjacent,
        "edge_count": 4,
    }
