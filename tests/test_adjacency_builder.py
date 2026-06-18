import pytest

from step_feature_assistant.adjacency_builder import build_face_adjacency, connected_components


pytestmark = pytest.mark.no_cst


def test_build_face_adjacency_from_shared_edges():
    adjacency = build_face_adjacency(
        {
            "F0001": ["E1", "E2"],
            "F0002": ["E2", "E3"],
            "F0003": ["E4"],
        }
    )

    assert adjacency == {
        "F0001": ["F0002"],
        "F0002": ["F0001"],
        "F0003": [],
    }


def test_connected_components_are_constrained_to_seed_faces():
    adjacency = {
        "F0001": ["F0002"],
        "F0002": ["F0001", "F0003"],
        "F0003": ["F0002"],
        "F0004": [],
    }

    components = connected_components(["F0001", "F0002", "F0004"], adjacency)

    assert components == [["F0001", "F0002"], ["F0004"]]
