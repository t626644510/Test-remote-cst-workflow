# Phase A9 -- Two-pass config helpers

## Summary

Added two-pass evaluation config defaults to `config.yaml` and
four pure Python helper functions to `workflow.py` for parsing
the evaluation config into gate objects.  No runtime behaviour
change: gates default to disabled, `two_pass` still fail-fast.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/config.yaml` | Added two-pass/gate config defaults | Modified |
| `workflows/rfgun_sao/workflow.py` | Added gates import + 4 helpers | Modified |
| `tests/workflows/test_rfgun_sao_imports.py` | Added 6 config/gate resolution tests | Modified |
| `workflows/rfgun_sao/README.md` | Updated test count | Modified |
| `reports/restructure_plan/phase_A9_two_pass_config_helpers.md` | Created | New |

## New helpers

| Function | Returns | Purpose |
|---|---|---|
| `_build_frequency_gate(eval_cfg)` | `FrequencyGate` | Parse frequency_gate config section |
| `_build_s11_depth_gate(eval_cfg)` | `S11DepthGate` | Parse s11_depth_gate config section |
| `_build_multi_dip_detector(eval_cfg)` | `MultiDipDetector` | Parse multi_dip_detection config section |
| `_resolve_two_pass_settings(config)` | `dict` | Aggregated mode + gate objects |

## Behaviour impact

**None.**  All gates default to `enabled: false`.  `two_pass` mode
still raises `NotImplementedError` before CST connection.

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
**sao:** 45/45 passed (6 new config/helper tests).
**--help:** exit 0.

## Next recommended phase

**A10:** Integrate gates and calibration into `evaluation.mode: two_pass`
path in `build_workflow_1()`.
