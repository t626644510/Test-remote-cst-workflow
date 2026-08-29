"""Representation-independent RF boundary semantic layer."""

from .adapters import (
    RF500_INSTANCE_ID,
    R1_GRAMMAR_ID,
    SLS2_INSTANCE_ID,
    R1Contracts,
    R1SourceSet,
    build_r1_contracts,
)
from .artifacts import R1Bundle, write_r1_bundle
from .contracts import (
    BoundaryInterface,
    EvidenceRef,
    FamilyGrammar,
    GrammarSlot,
    InstanceBoundaryGraph,
    InstanceGraphDiff,
    MotifInsertionRule,
    ReviewBinding,
    SemanticContractError,
    SemanticLandmark,
    SemanticMotif,
    SemanticRegion,
    diff_instance_graphs,
    load_family_grammar,
    load_instance_boundary_graph,
    load_instance_graph_diff,
    validate_reviewed_graph_intrinsic,
    validate_graph_against_grammar,
)

ARCHITECTURE_LAYER = "semantic"

__all__ = [
    "ARCHITECTURE_LAYER",
    "BoundaryInterface",
    "EvidenceRef",
    "FamilyGrammar",
    "GrammarSlot",
    "InstanceBoundaryGraph",
    "InstanceGraphDiff",
    "MotifInsertionRule",
    "RF500_INSTANCE_ID",
    "R1Bundle",
    "R1Contracts",
    "R1SourceSet",
    "R1_GRAMMAR_ID",
    "ReviewBinding",
    "SLS2_INSTANCE_ID",
    "SemanticContractError",
    "SemanticLandmark",
    "SemanticMotif",
    "SemanticRegion",
    "build_r1_contracts",
    "diff_instance_graphs",
    "load_family_grammar",
    "load_instance_boundary_graph",
    "load_instance_graph_diff",
    "validate_reviewed_graph_intrinsic",
    "validate_graph_against_grammar",
    "write_r1_bundle",
]
