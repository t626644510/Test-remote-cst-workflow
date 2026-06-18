import json
from pathlib import Path

import pytest

from step_feature_assistant.calibration_cli import build_calibration
from step_feature_assistant.classifier import SklearnFeatureScorer
from step_feature_assistant.classifier_cli import (
    export_training_dataset,
    train_baseline_classifier,
)


pytestmark = pytest.mark.no_cst


def test_dataset_train_score_and_calibration_round_trip(tmp_path):
    project = tmp_path / "reviewed" / "project_a"
    project.mkdir(parents=True)
    manifest = _manifest()
    draft = {
        "features": [
            {"id": "wall_candidate", "type": "ConductingWall", "geometry_refs": ["F0001"], "status": "candidate"},
            {"id": "iris_candidate", "type": "Iris", "geometry_refs": ["F0002"], "status": "candidate"},
        ],
        "face_groups": [],
        "unassigned_faces": [],
        "missing_expected_features": [],
    }
    resolved = {
        "features": [
            {
                "id": "wall_candidate",
                "type": "ConductingWall",
                "geometry_refs": ["face:F0001"],
                "status": "confirmed",
            },
            {
                "id": "iris_candidate",
                "type": "Iris",
                "geometry_refs": ["face:F0002"],
                "status": "confirmed",
            },
        ]
    }
    _write(project / "geometry_manifest.json", manifest)
    _write(project / "feature_graph_draft.json", draft)
    _write(project / "resolved_feature_graph.json", resolved)

    dataset_dir = tmp_path / "dataset"
    metadata = export_training_dataset([project.parent], dataset_dir)
    assert metadata["face_row_count"] == 2

    model_dir = tmp_path / "model"
    model_metadata = train_baseline_classifier(dataset_dir, model_dir)
    assert model_metadata["experimental"] is True
    assert model_metadata["production_decision_authority"] is False

    suggestions = SklearnFeatureScorer(model_dir / "classifier.joblib", threshold=0.0).score_manifest(manifest)
    assert suggestions["changes_rule_based_graph"] is False
    assert len(suggestions["faces"]) == 2

    calibration = build_calibration([project.parent], tmp_path / "calibration")
    assert calibration["automatic_rule_changes"] is False
    assert set(calibration["feature_statistics"]) == {"ConductingWall", "Iris"}


def _manifest():
    return {
        "source_step": "project_a.step",
        "model_summary": {
            "detected_axis": "z",
            "bbox": {"xmin": -10, "xmax": 10, "ymin": -10, "ymax": 10, "zmin": 0, "zmax": 20},
        },
        "faces": [
            _face("F0001", "cylinder", 100.0, 8.0, [5.0, 8.0], True),
            _face("F0002", "torus", 20.0, 2.0, [9.0, 11.0], True),
        ],
    }


def _face(face_id, surface_type, area, radius, z_range, axisymmetric):
    return {
        "face_id": face_id,
        "surface_type": surface_type,
        "area": area,
        "radius": radius,
        "centroid": [radius, 0.0, sum(z_range) / 2],
        "normal_estimate": [1.0, 0.0, 0.0],
        "bbox": {"xmin": -radius, "xmax": radius, "ymin": -radius, "ymax": radius, "zmin": z_range[0], "zmax": z_range[1]},
        "axis_relation": {
            "radius_mean": radius,
            "r_range": [radius, radius],
            "z_range": z_range,
            "is_axisymmetric": axisymmetric,
        },
        "edge_count": 4,
        "adjacent_faces": [],
    }


def _write(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")
