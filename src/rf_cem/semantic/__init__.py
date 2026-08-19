"""Representation-independent RF boundary semantic layer.

R0B freezes this dependency boundary only.  Versioned family grammars,
instance boundary graphs, motifs, landmarks, and interfaces belong to R1.
This package must remain independent of geometry kernels, CST, and concrete
boundary-representation implementations.
"""

ARCHITECTURE_LAYER = "semantic"

__all__ = ["ARCHITECTURE_LAYER"]
