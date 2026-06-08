"""Workflow 3 builder — single-project recovery optimisation.

The canonical ``build_workflow_3`` lives in ``cst_optimization.factory``.
This module re-exports it for the WF3 package.

When WF3-specific builder logic grows, it can be extracted from factory.py
into this module (the pattern used by WF1 and WF2).
"""

from cst_optimization.factory import build_workflow_3  # noqa: F401
