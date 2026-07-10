"""Workflow 2 — HOM antenna multi-project optimisation (RF gun).

This package is the Workflow2 runner/config/builder home (W2-7, W2-8).
The root entry point ``run_workflow_2.py`` is a compatibility shim (W2-7) that
delegates to ``workflows/rfgun_hom_antenna/run.py``, which imports
``build_workflow_2`` from this package's ``workflow.py`` (W2-4B).

Current legacy entry point::

    python run_workflow_2.py

Migration status:
    Workflow2 migration is complete on ``main``.  The compact repository
    summary is ``reports/project_context_capsule.md``; detailed phase evidence
    is retained in git history and milestone tags.
"""

__version__ = "0.1.0"
__legacy_entry__ = "run_workflow_2.py"
