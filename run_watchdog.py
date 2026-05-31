"""External watchdog launcher — monitors a workflow and restarts on crash.

Usage::

    python run_watchdog.py -- run_workflow_2.py
    python run_watchdog.py --max-restarts 5 --cooldown 30 -- run_workflow_3.py
"""

import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_project_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from cst_optimization.watchdog import _main

if __name__ == "__main__":
    _main()
