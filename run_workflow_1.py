"""Workflow 1 -- single-project single-pass frequency-domain SAO optimisation.

This file is a **compatibility shim**.  The actual runner logic lives in
``workflows/rfgun_sao/run.py`` (consolidated SAO workflow).

Usage::

    .venv\\Scripts\\python run_workflow_1.py
    .venv\\Scripts\\python run_workflow_1.py --seed 43

Watchdog::

    .venv\\Scripts\\python run_watchdog.py -- run_workflow_1.py
"""

from workflows.rfgun_sao.run import main

if __name__ == "__main__":
    main()
