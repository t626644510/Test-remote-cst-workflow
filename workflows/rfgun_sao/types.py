"""Re-exports of canonical evaluation types from shared core.

These were previously duplicated here to avoid a dependency on the
legacy workflow module.  Phase 1 consolidates them — the single
source of truth is now ``cst_optimization.workflows.recovery``.
"""

from cst_optimization.workflows.recovery import EvaluationResult  # noqa: F401
from cst_optimization.workflows.recovery import EvaluationStatus  # noqa: F401
