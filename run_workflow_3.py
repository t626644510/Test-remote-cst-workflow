"""Workflow 3 — single-project recovery optimisation.

This file is a **compatibility shim**.  The actual runner logic lives in
``workflows/rfgun_recovery/run.py``.

Usage::

    .venv\\Scripts\\python run_workflow_3.py
    .venv\\Scripts\\python run_workflow_3.py --resume-from D:/Results/workflow3/stage_2
"""

from workflows.rfgun_recovery.run import main

if __name__ == "__main__":
    main()
