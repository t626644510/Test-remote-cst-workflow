# Phase 08.5 -- n_initial config key fix

## Summary

Fixed a config-key mismatch in ``workflow.py::_build_sao()`` where the
local builder read ``opt_cfg.get("n_initial", 20)`` instead of
``opt_cfg.get("n_initial_samples", ...)``.  The config YAML and CLI
``--n-initial`` override both use ``n_initial_samples``, so the CLI
override was never propagated to the SAO constructor.

## Bug fixed

**Symptom (Phase 8.4 log):**
```
CLI: --n-initial 1
SAO log: Pre-loaded 3 prior evaluations; LHS set to 17 (base=20 - prior=3 + extra=0)
```

The SAO constructor received ``n_initial=20`` (fallback) instead of
``n_initial=1`` (CLI override).  The ``--n-initial`` flag wrote to
``cfg["optimization"]["n_initial_samples"]``, but ``_build_sao()``
read ``cfg["optimization"]["n_initial"]``.

**Fix:** Changed ``_build_sao()`` to check ``n_initial_samples`` first
with fallback to the old ``n_initial`` key:

```python
# Before:
n_initial = opt_cfg.get("n_initial", 20)

# After:
n_initial = opt_cfg.get("n_initial_samples", opt_cfg.get("n_initial", 20))
```

This ensures compatibility with:
- ``config.yaml`` (uses ``n_initial_samples``)
- CLI ``--n-initial`` (writes ``n_initial_samples``)
- Any existing configs using the old ``n_initial`` key (fallback)

The ``n_iterations`` key was already consistent (both CLI and config
use ``n_iterations``) and was not changed.

## Files changed

| File | Action | Status |
|---|---|---|
| ``workflows/rfgun_single_pass/workflow.py`` | ``_build_sao()`` reads ``n_initial_samples`` first | Modified |
| ``tests/workflows/test_rfgun_single_pass_imports.py`` | Added regression test | Modified |
| ``reports/workflow1_split/phase_08_5_n_initial_key_fix.md`` | Created | New |

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
pytest tests/workflows/test_rfgun_single_pass_imports.py -v --tb=short
Select-String -Path workflows/rfgun_single_pass/workflow.py -Pattern "n_initial_samples"
```

### Real terminal output

**Test 1 -- compileall (exit 0):**
```
Compiling 'workflows\\rfgun_single_pass\\workflow.py'...
```

**Test 2 -- --help (exit 0):** CLI unchanged.

**Test 3 -- pytest (11/11 passed):**
```
test_workflow_build_sao_reads_n_initial_samples_key PASSED  [ 90%]  ← NEW
```

**Test 4 -- Select-String confirms n_initial_samples in _build_sao:**
```
workflow.py:314: n_initial = opt_cfg.get("n_initial_samples", opt_cfg.get("n_initial", 20))
```

## Live CST re-run instruction

After this fix, ``--n-initial`` will correctly propagate to the SAO
constructor:

```powershell
# With explicit override:
python run_workflow_1.py --n-initial 1 --n-iter 0

# With local config:
python run_workflow_1.py --config workflows/rfgun_single_pass/config.local.yaml --n-initial 1 --n-iter 0
```

Expected log: ``LHS set to 1 (base=1 - prior=0 + extra=0)`` (with no
prior checkpoint), or ``(base=1 - prior=N + extra=0)`` (with prior
data).

## Risks

None.  The fix adds a fallback chain: try ``n_initial_samples`` first
(config/CLI standard), fall back to ``n_initial`` (old configs), fall
back to 20 (original default).  This is strictly more compatible.

## Next recommended phase

**Phase 8.6:** Re-run live CST validation with the fixed key to confirm
the SAO budget is correctly controlled by CLI ``--n-initial``.
