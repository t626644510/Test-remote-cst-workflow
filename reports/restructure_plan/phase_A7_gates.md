# Phase A7 -- Gate utilities

## Summary

Added `workflows/rfgun_sao/gates.py` with three pure Python gate
classes: `FrequencyGate`, `S11DepthGate`, and `MultiDipDetector`.
These are utility classes for later two-pass integration.  No runtime
behaviour is changed (all gates default to disabled).

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_sao/gates.py` | Created (3 gate classes) | New |
| `tests/workflows/test_rfgun_sao_imports.py` | Added 9 gate tests | Modified |
| `workflows/rfgun_sao/README.md` | Added gates.py to structure | Modified |
| `reports/restructure_plan/phase_A7_gates.md` | Created | New |

## Gate behaviour

| Gate | Enabled | Accepts | Rejects |
|---|---|---|---|
| `FrequencyGate` | `{enabled: true, target_ghz: 11.424, max_abs_offset_mhz: 20}` | `f0=11.424`, `f0=11.434` | `f0=11.5`, `f0=11.3` |
| `S11DepthGate` | `{enabled: true, threshold_db: -1.0}` | `|S11|=-10 dB`, `|S11|=-1 dB` | `|S11|=0 dB` |
| `MultiDipDetector` | `{enabled: true, mode_spacing_ghz: 0.04}` | Two dips within 0.04 GHz | Single dip |

All gates default to `enabled: false` (no effect on current behaviour).

## Behaviour impact

**None.**  Gates are not integrated into the evaluator or builder yet.
They are pure utility classes with no CST dependency.

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
**sao:** 33/33 passed (9 new gate tests).
**--help:** exit 0.

## Next recommended phase

**A8:** Integrate gates into the two-pass calibration flow (when
`evaluation.mode: two_pass`).
