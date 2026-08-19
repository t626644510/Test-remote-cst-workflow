"""Family-agnostic mathematical boundary-representation layer.

R0B establishes the package boundary without prematurely standardising the
legacy RF500 and SLS-2 curve payloads.  The versioned representation protocol
and concrete core types are an R2 deliverable.  This package must not depend
on concrete cavity families, semantic-region classes, or CST.
"""

ARCHITECTURE_LAYER = "representation"

__all__ = ["ARCHITECTURE_LAYER"]
