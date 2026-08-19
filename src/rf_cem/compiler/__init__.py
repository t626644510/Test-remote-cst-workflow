"""RF boundary compiler layer joining semantic and representation contracts.

The generic ``Compile(T, {Ri(theta_i)})`` implementation is deliberately
deferred to R2.  R0B reserves this as the only core layer allowed to combine
semantic topology with boundary representations.
"""

ARCHITECTURE_LAYER = "compiler"

__all__ = ["ARCHITECTURE_LAYER"]
