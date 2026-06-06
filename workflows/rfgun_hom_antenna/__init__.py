"""Workflow 2 — HOM antenna multi-project optimisation (RF gun).

This package is the future home of the legacy Workflow 2 runtime.
It is currently a **skeleton** — no runtime has been migrated.

Current legacy entry point (not yet repointed)::

    python run_workflow_2.py

Migration plan (see ``reports/restructure_plan/workflow2_current_context.md``):
    W2-0  — context document                                          ✅ done
    W2-1  — no-CST characterization tests                            ✅ done
    W2-2  — package skeleton (this file)                             ✅ done
    W2-3  — workflow2 config isolation                               ⬅️ current
    W2-4  — builder ownership migration
    W2-5  — orchestrator ownership assessment
    W2-6  — fix documented semantic risks
    W2-7  — core candidate evaluation
    W2-8  — minimal live CST validation
"""

__version__ = "0.1.0"
__legacy_entry__ = "run_workflow_2.py"
