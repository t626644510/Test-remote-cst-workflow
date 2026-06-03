# Phase A10 -- Two-pass orchestration skeleton

## Summary

Added `workflows/rfgun_sao/two_pass.py` with pure Python
`TwoPassDecision` dataclass and `evaluate_two_pass_decision()`
function that combines calibration, frequency gate, S11 depth gate,
and multi-dip diagnostics into a single decision.  No runtime
behaviour change (not integrated into workflow builder yet).

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/two_pass.py` | Created (TwoPassDecision, evaluate_two_pass_decision) | New |
| `tests/workflows/test_rfgun_sao_imports.py` | Added 6 two_pass tests | Modified |
| `workflows/rfgun_sao/README.md` | Updated status and test count | Modified |
| `reports/restructure_plan/phase_A10_two_pass_skeleton.md` | Created | New |

## Decision behavior

| Scenario | `accepted` | `reason` |
|---|---|---|
| Successful calibration, all gates disabled | `True` | `accepted` |
| Failed calibration | `False` | `calibration_failed` |
| Frequency gate rejects | `False` | `frequency_gate_reject` |
| S11 depth gate rejects | `False` | `s11_depth_gate_reject` |
| Multi-dip detected | `True` | `accepted` (diagnostic only) |

## Behaviour impact

**None.**  `two_pass.py` is not integrated into the workflow builder.
`evaluation.mode=two_pass` still raises `NotImplementedError`.

## Tests run

`powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
pytest tests/workflows/test_rfgun_single_pass_imports.py -q
pytest tests/workflows/test_rfgun_sao_imports.py -q
python -m workflows.rfgun_sao.run --help
`

### Real terminal output

**compileall:** exit 0.
**single_pass:** 12/12 passed.
**sao:** 51/51 passed (6 new two_pass tests).
**--help:** exit 0.

## Next recommended phase

**A11:** Integrate `two_pass.py` decision logic into
`build_workflow_1()` when `evaluation.mode: two_pass`.
