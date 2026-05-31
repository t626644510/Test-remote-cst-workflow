"""Mock verification of two-level conditional trigger chain for Workflow 2."""
import sys
sys.path.insert(0, 'src')

import yaml
import numpy as np
from unittest.mock import MagicMock, patch

with open('config/default.yaml') as fh:
    cfg = yaml.safe_load(fh)

with patch('cst_optimization.factory.CSTConnection') as MockConn:
    MockConn.return_value = MagicMock(pid=12345)

    from cst_optimization.factory import build_workflow_2
    from cst_optimization.core.solver import SolverResult

    orch, opt, evaluator = build_workflow_2(cfg['workflow_2'])

    # Setup mock CST project
    mock_proj = MagicMock()
    mock_proj.filename = 'D:/workflow2/test.cst'

    for spec in orch._specs:
        spec.connection.open_project.return_value = mock_proj

    # Mock solver always succeeds
    orch._solver = MagicMock()
    orch._solver.run.return_value = SolverResult(
        success=True, elapsed_s=10.0, mesh_cells=1000,
    )

    # Mock message logger
    orch._msg = MagicMock()
    orch._msg.capture.return_value = ''
    orch._msg.has_history_failure.return_value = False

    obj_names = [obj.name for obj in orch._objectives]
    zl = obj_names.index('z_longitudinal')
    zt = obj_names.index('z_transverse')

    # ================================================================
    # Case C: Pre-filter REJECT (antenna_absorption > -24 dB)
    # ================================================================
    def _eval_c(obj, rf):
        if obj.name in ('antenna_absorption', 'antenna_absorption_db'):
            return -20.0  # > -24 dB => REJECT
        return 0.0

    with patch.object(orch, '_evaluate_objective', side_effect=_eval_c):
        p = orch.execute(np.full(14, 150.0), iteration=99)
        ok = np.allclose(p, 1.0)
        print(f"Case C (pre-filter reject): {'PASSED' if ok else 'FAILED'}")

    # ================================================================
    # Case D: wakefield triggers, wakefield_offset SKIPPED
    # ================================================================
    _seq_d = []

    def _eval_d(obj, rf):
        _seq_d.append(obj.name)
        if obj.name == 'antenna_absorption':
            return -35.0  # good, penalty ~0
        if obj.name == 'antenna_absorption_db':
            return -32.0
        if obj.name == 'z_longitudinal':
            return 500.0  # high -> penalty >> 0.2 -> skip wakefield_offset
        return 0.0

    with patch.object(orch, '_evaluate_objective', side_effect=_eval_d):
        p = orch.execute(np.full(14, 150.0), iteration=99)
        ok1 = p[zt] == 0.0  # skipped -> neutral
        ok2 = p[zl] > 0.0  # computed via mode (penalty > 0 for bad impedance)
        print(
            f"Case D (z_long bad -> skip wf_offset): "
            f"zt_skip={ok1} zl_penalty={p[zl]:.3f} "
            f"{'PASSED' if ok1 and ok2 else 'FAILED'}"
        )
        print(f"  eval_sequence: {_seq_d}")

    # ================================================================
    # Case A: Both wakefield AND wakefield_offset trigger
    # ================================================================
    _seq_a = []

    def _eval_a(obj, rf):
        _seq_a.append(obj.name)
        if obj.name == 'antenna_absorption':
            return -40.0
        if obj.name == 'antenna_absorption_db':
            return -38.0
        if obj.name == 'z_longitudinal':
            return 0.0  # perfect -> penalty=0 < 0.2
        if obj.name == 'z_transverse':
            return 10000.0
        return 0.0

    with patch.object(orch, '_evaluate_objective', side_effect=_eval_a):
        p = orch.execute(np.full(14, 150.0), iteration=99)
        ok1 = p[zt] != 0.0  # computed (not skipped)
        ok2 = p[zl] == 0.0  # perfect z_long
        print(
            f"Case A (all good -> both trigger): "
            f"zt_computed={ok1}({p[zt]:.3f}) zl_perfect={ok2} "
            f"{'PASSED' if ok1 and ok2 else 'FAILED'}"
        )
        print(f"  eval_sequence: {_seq_a}")

    print()
    print("All mock trigger-chain verifications complete.")
