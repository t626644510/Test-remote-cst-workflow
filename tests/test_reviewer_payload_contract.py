"""Embedded and standalone reviewers share semantic payloads."""
from step_feature_assistant.reviewer import build_reviewer_payload

def test_embedded_payload_keeps_semantics_without_mesh_traces():
    mesh={"faces":[{"face_id":"F1","vertices":[[0,0,0],[1,0,0],[0,1,0]],"triangles":[[0,1,2]]}]}
    manifest={"faces":[{"face_id":"F1","surface_type":"plane"}]}
    args=(mesh,manifest,{"unassigned_faces":["F1"]},{},{},{},{},{"issues":[]},{"reviewed":True})
    full=build_reviewer_payload(*args)
    embedded=build_reviewer_payload(*args,include_traces=False)
    for key in ("faceIds","faces","draft","layers","review","palette"):
        assert embedded[key] == full[key]
    assert full["faceTraceCount"] == 1 and len(full["traces"]) == 3
    assert embedded["traces"] == [] and embedded["faceTraceCount"] == 0
    assert embedded["adjacencyTraceIndex"] is None and embedded["labelsTraceIndex"] is None
