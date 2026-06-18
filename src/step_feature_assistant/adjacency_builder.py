"""Build face adjacency graphs from shared STEP edge references."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Sequence, Set


def build_face_adjacency(face_edges: Mapping[str, Sequence[str]]) -> Dict[str, List[str]]:
    """Return face adjacency based on shared edge ids."""
    edge_to_faces: dict[str, set[str]] = defaultdict(set)
    for face_id, edge_ids in face_edges.items():
        for edge_id in edge_ids:
            edge_to_faces[str(edge_id)].add(face_id)

    adjacency: dict[str, set[str]] = {face_id: set() for face_id in face_edges}
    for faces in edge_to_faces.values():
        if len(faces) < 2:
            continue
        for face in faces:
            adjacency.setdefault(face, set()).update(other for other in faces if other != face)

    return {face_id: sorted(neighbors) for face_id, neighbors in sorted(adjacency.items())}


def connected_components(seed_faces: Iterable[str], adjacency: Mapping[str, Sequence[str]]) -> List[List[str]]:
    """Return connected components constrained to ``seed_faces``."""
    remaining: Set[str] = set(seed_faces)
    components: List[List[str]] = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        component = {start}
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, []):
                if neighbor not in remaining:
                    continue
                remaining.remove(neighbor)
                component.add(neighbor)
                stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda values: (len(values), values[0]), reverse=True)
