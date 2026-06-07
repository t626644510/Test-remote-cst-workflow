"""Workflow 2 — HOM antenna multi-project optimisation (RF gun).

This package is the future home of the legacy Workflow 2 runtime.
The root entry point ``run_workflow_2.py`` has been repointed to
import ``build_workflow_2`` from this package (W2-4A seam).

Current legacy entry point::

    python run_workflow_2.py

Migration plan (see ``reports/restructure_plan/workflow2_current_context.md``):
    W2-0  — context document                                          ✅ done
    W2-1  — no-CST characterization tests                            ✅ done
    W2-2  — package skeleton (this file)                             ✅ done
    W2-3  — workflow2 config isolation                               ✅ done
    W2-4A — builder ownership seam                                   ✅ done
    W2-4B — builder implementation migration                         ✅ done
    W2-5  — orchestrator ownership assessment                        ✅ done
    W2-6  — semantic risk cleanup plan                               ✅ done
    W2-6A — root docstring fix (R1)                                  ✅ done
    W2-6D — scheduler/root shim compatibility                        ✅ done
    W2-6B — solver timeout decision (R2)                             ✅ done
    W2-6C — checkpoint callback decision (R4)                        ✅ done
    W2-6E — evaluator-only callback ownership (R4 fixed)             ✅ done
    W2-6F — solver timeout runtime fix (R2 fixed)                    ✅ done
"""

__version__ = "0.1.0"
__legacy_entry__ = "run_workflow_2.py"
