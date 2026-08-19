"""Versioned representation-independent RF boundary semantic ontologies."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


REGION_ONTOLOGY_VERSION = "semantic_region_ontology.v0"
LANDMARK_ONTOLOGY_VERSION = "semantic_landmark_ontology.v0"

BEAM_PIPE_REGION = "BeamPipeRegion"
IRIS_REGION = "IrisRegion"
GAP_SHAPING_REGION = "GapShapingRegion"
NOSE_REGION = "NoseRegion"
OUTER_WALL_REGION = "OuterWallRegion"
EQUATOR_REGION = "EquatorRegion"

AXIAL_APERTURE_LANDMARK = "AxialApertureLandmark"
REGION_JUNCTION_LANDMARK = "RegionJunctionLandmark"
SYMMETRY_LANDMARK = "SymmetryLandmark"


_REGION_TERMS: tuple[dict[str, Any], ...] = (
    {
        "term_id": BEAM_PIPE_REGION,
        "parent_term_id": None,
        "label": "Beam pipe",
        "definition": "RF-vacuum boundary region extending along a beam-pipe section.",
    },
    {
        "term_id": IRIS_REGION,
        "parent_term_id": GAP_SHAPING_REGION,
        "label": "Iris",
        "definition": "Local aperture/throat region controlling the transition from beam pipe into the cell.",
    },
    {
        "term_id": GAP_SHAPING_REGION,
        "parent_term_id": OUTER_WALL_REGION,
        "label": "Gap shaping",
        "definition": "Cell-wall region shaping the accelerating gap between iris and outer wall.",
    },
    {
        "term_id": NOSE_REGION,
        "parent_term_id": GAP_SHAPING_REGION,
        "label": "Nose",
        "definition": "Optional protruding gap-shaping region with distinct semantic identity.",
    },
    {
        "term_id": OUTER_WALL_REGION,
        "parent_term_id": None,
        "label": "Outer wall",
        "definition": "Cell-wall region between gap shaping and the equator region.",
    },
    {
        "term_id": EQUATOR_REGION,
        "parent_term_id": OUTER_WALL_REGION,
        "label": "Equator",
        "definition": "Maximum-radius central cell-wall region around the mirror plane.",
    },
)

_LANDMARK_TERMS: tuple[dict[str, Any], ...] = (
    {
        "term_id": AXIAL_APERTURE_LANDMARK,
        "label": "Axial aperture",
        "definition": "Oriented endpoint of the represented RF-vacuum wall profile.",
        "incident_region_cardinality": [1],
    },
    {
        "term_id": REGION_JUNCTION_LANDMARK,
        "label": "Region junction",
        "definition": "Shared topological landmark joining two consecutive semantic regions.",
        "incident_region_cardinality": [2],
    },
    {
        "term_id": SYMMETRY_LANDMARK,
        "label": "Symmetry landmark",
        "definition": "Mirror-plane landmark bound to the central equator region.",
        "incident_region_cardinality": [1],
    },
)


def region_ontology_mapping() -> dict[str, Any]:
    """Return a defensive mapping for the semantic-region ontology v0."""

    return {
        "schema_version": REGION_ONTOLOGY_VERSION,
        "terms": deepcopy(list(_REGION_TERMS)),
    }


def landmark_ontology_mapping() -> dict[str, Any]:
    """Return a defensive mapping for the semantic-landmark ontology v0."""

    return {
        "schema_version": LANDMARK_ONTOLOGY_VERSION,
        "terms": deepcopy(list(_LANDMARK_TERMS)),
    }


def region_type_ids() -> frozenset[str]:
    """Return all region term identifiers defined by ontology v0."""

    return frozenset(str(term["term_id"]) for term in _REGION_TERMS)


def landmark_type_ids() -> frozenset[str]:
    """Return all landmark term identifiers defined by ontology v0."""

    return frozenset(str(term["term_id"]) for term in _LANDMARK_TERMS)


__all__ = [
    "AXIAL_APERTURE_LANDMARK",
    "BEAM_PIPE_REGION",
    "EQUATOR_REGION",
    "GAP_SHAPING_REGION",
    "IRIS_REGION",
    "LANDMARK_ONTOLOGY_VERSION",
    "NOSE_REGION",
    "OUTER_WALL_REGION",
    "REGION_JUNCTION_LANDMARK",
    "REGION_ONTOLOGY_VERSION",
    "SYMMETRY_LANDMARK",
    "landmark_ontology_mapping",
    "landmark_type_ids",
    "region_ontology_mapping",
    "region_type_ids",
]
