"""Read-only observation layer for compiled RF boundary geometry.

R0B establishes the dependency boundary.  Representation-independent shape
observations, descriptors, and engineering constraints are R4 deliverables;
this layer must not generate or mutate geometry.
"""

ARCHITECTURE_LAYER = "observation"

__all__ = ["ARCHITECTURE_LAYER"]
