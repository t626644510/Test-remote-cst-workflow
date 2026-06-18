import pytest

from step_feature_assistant.review_merger import (
    build_review_template,
    merge_reviewed_labels,
)


pytestmark = pytest.mark.no_cst


def test_review_merge_normalizes_refs_and_validates_faces():
    manifest = {
        "model_summary": {"solid_count": 1},
        "faces": [{"face_id": "F0001"}, {"face_id": "F0002"}],
    }
    draft = {
        "features": [
            {
                "id": "wall_candidate_01",
                "type": "ConductingWall",
                "geometry_refs": ["F0001"],
                "status": "candidate",
            }
        ],
        "face_groups": [{"group_id": "G0001"}],
        "unassigned_faces": ["F0002"],
    }
    review = {
        "confirmed_features": {
            "wall_candidate_01": {
                "type": "ConductingWall",
                "geometry_refs": ["F0001"],
            }
        },
        "manual_groups": {
            "internal_plane": {
                "type": "InternalIrisPlane",
                "geometry_refs": ["F0002"],
            }
        },
        "rejected_candidates": [],
    }

    resolved = merge_reviewed_labels(draft, review, manifest)

    by_id = {feature["id"]: feature for feature in resolved["features"]}
    assert by_id["wall_candidate_01"]["geometry_refs"] == ["face:F0001"]
    assert by_id["internal_plane"]["geometry_refs"] == ["face:F0002"]
    assert by_id["internal_plane"]["status"] == "modified"


def test_review_merge_rejects_unknown_face_and_candidate():
    manifest = {"model_summary": {"solid_count": 1}, "faces": [{"face_id": "F0001"}]}
    draft = {"features": [], "face_groups": [], "unassigned_faces": ["F0001"]}

    with pytest.raises(ValueError, match="Unknown rejected candidate"):
        merge_reviewed_labels(draft, {"rejected_candidates": ["missing"]}, manifest)

    with pytest.raises(ValueError, match="Unknown face reference"):
        merge_reviewed_labels(
            draft,
            {
                "manual_groups": {
                    "manual": {"type": "Wall", "geometry_refs": ["F9999"]}
                }
            },
            manifest,
        )


def test_review_template_contains_current_candidate_reference():
    draft = {
        "features": [
            {
                "id": "iris_candidate_01",
                "type": "Iris",
                "geometry_refs": ["F0003"],
                "confidence": 0.62,
            }
        ],
        "unassigned_faces": ["F0017"],
    }

    template = build_review_template(draft)

    assert template["confirmed_features"] == {}
    assert template["candidate_reference"]["iris_candidate_01"]["geometry_refs"] == ["face:F0003"]
    assert template["unassigned_faces"] == ["face:F0017"]
