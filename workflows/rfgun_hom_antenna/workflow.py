"""Workflow 2 — builder ownership seam.

W2-4A state: **thin delegation wrapper only**.

This module provides the workflow2-local ``build_workflow_2`` entry point.
In this phase (W2-4A) the function is a pure delegation wrapper: it accepts
the same arguments and returns the same four-value tuple as the legacy
builder, but the implementation still lives in the shared factory module.

Status
------
- No builder implementation has been copied or migrated yet.
- The actual implementation remains at
  ``src/cst_optimization.factory.build_workflow_2``.
- Once W2-4A is accepted, W2-4B will migrate the real implementation into
  this module.
- The four-value return contract (``orchestrator, optimizer, evaluator,
  retry_handler``) is preserved.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

# Delegate to the legacy shared factory.
from cst_optimization.factory import build_workflow_2 as _legacy_build


def build_workflow_2(
    config: dict[str, Any],
    checkpoint_callback: Callable[[np.ndarray, np.ndarray, np.ndarray, bool, str], None]
    | None = None,
):
    """Build the Phase-2 multi-project orchestrator and optimiser from config.

    W2-4A: thin delegation wrapper over ``cst_optimization.factory.build_workflow_2``.

    Parameters
    ----------
    config : dict
        The ``workflow_2`` section of ``default.yaml`` (or merged equivalent).
    checkpoint_callback : callable or None
        Optional callback invoked after each evaluation with
        ``(params, raw_values, penalties, solver_ok, error)``.

    Returns
    -------
    orchestrator : DualProjectOrchestrator
    optimizer : BaseOptimizer
    evaluator : callable
    retry_handler : EvaluationRetryHandler or None
    """
    return _legacy_build(config, checkpoint_callback=checkpoint_callback)
