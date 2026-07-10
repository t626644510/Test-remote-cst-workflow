"""Phase 2 HOM Antenna Optimisation — entry point (compatibility shim).

This file is a **compatibility shim**.  The actual runner logic lives in
``workflows/rfgun_hom_antenna/run.py``.

Usage::

    python run_workflow_2.py
    python run_workflow_2.py --auto-resume
    python run_workflow_2.py --auto-resume --recovery-only
    python run_workflow_2.py --auto-resume --heartbeat
    python run_workflow_2.py --warmup-from-db D:/Results/wf2_warmup_total/index.total.jsonl
    python run_workflow_2.py --config D:/smoke/config.yaml --smoke-only

Reads ``workflows/rfgun_hom_antenna/config.yaml`` through the package runner,
opens a single CST DesignEnvironment connection with sequential
frequency-domain and wakefield solver execution (inter-pass reset may recreate
the DE between phases), builds the orchestrator + optimiser, and runs the full
Bayesian optimisation loop.

See ``workflows/rfgun_hom_antenna/run.py`` for the full implementation.
"""

from workflows.rfgun_hom_antenna.run import main

if __name__ == "__main__":
    main()
