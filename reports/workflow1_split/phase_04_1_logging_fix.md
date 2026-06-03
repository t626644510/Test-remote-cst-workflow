# Phase 04.1 -- Logging fix: config path log after logging setup

## Summary

Fixed a bug where the log message for the selected config path was
emitted **before** ``_setup_logging()`` was called, causing it to be
sent to the root logger rather than the file handler.  Also removed
two unused imports left over from the original runner.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_single_pass/run.py` | Fixed logging order + removed unused imports | Modified |
| `reports/workflow1_split/phase_04_1_logging_fix.md` | Created | New |

## Exact bug fixed

**Before (lines 111-115):**
```python
    config_path = Path(args.config).expanduser().resolve()
    _logger.info("Workflow 1 starting  config=%s", config_path)  # BUG: fires BEFORE file handler
    cfg = yaml.safe_load(open(config_path, "r", encoding="utf-8"))
    log_dir = _setup_logging(cfg.get("logging", {}))             # file handler attached HERE
    _logger.info("Python: %s", sys.executable)
```

**After:**
```python
    config_path = Path(args.config).expanduser().resolve()
    cfg = yaml.safe_load(open(config_path, "r", encoding="utf-8"))
    log_dir = _setup_logging(cfg.get("logging", {}))             # file handler attached FIRST
    _logger.info("Workflow 1 starting")
    _logger.info("Config: %s", config_path)                      # now goes to file
    _logger.info("Python: %s", sys.executable)
```

The config path message is now written to ``workflow_1_runtime.log``
as intended.

## Unused imports removed

- ``import time as _time`` -- was never referenced in the runner.
- ``from datetime import datetime`` -- was never referenced in the
  runner (``CheckpointManager`` handles timestamps internally).

## Behaviour impact

None at runtime.  The file-sink log output now includes the config
path line which was previously only visible on stderr.

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
python -c "from workflows.rfgun_single_pass.run import DEFAULT_CONFIG_PATH; print(DEFAULT_CONFIG_PATH)"
python -c "import ast; text = open('workflows/rfgun_single_pass/run.py', encoding='utf-8-sig').read(); ast.parse(text); print('AST OK')"
```

### Real terminal output

**Test 1 -- compileall (exit 0):**
```
Listing 'src'...
Listing 'src\cst_optimization'...
Listing 'src\cst_optimization\core'...
Listing 'src\cst_optimization\objectives'...
Listing 'src\cst_optimization\optimization'...
Listing 'src\cst_optimization\parameters'...
Listing 'src\cst_optimization\physics'...
Listing 'src\cst_optimization\sensitivity'...
Listing 'src\cst_optimization\utils'...
Listing 'src\cst_optimization\workflows'...
Listing 'workflows'...
Listing 'workflows\rfgun_single_pass'...
```

**Test 2 -- ``--help`` (exit 0):**
```
usage: run_workflow_1.py [-h] [--config CONFIG] [--seed SEED]
                         [--n-iter N_ITER] [--n-initial N_INITIAL]

Workflow 1 SAO optimisation

optional arguments:
  -h, --help            show this help message and exit
  --config CONFIG       Path to Workflow 1 YAML config (default: ...)
  --seed SEED           ...
```

**Test 3 -- DEFAULT_CONFIG_PATH (exit 0):**
```
C:\Users\lau\cst_ver3\workflows\rfgun_single_pass\config.yaml
```

**Test 4 -- AST parse (exit 0):**
```
AST OK
```

## Risks

None.  This is a purely internal logging reorder with no behavioural
change to the optimisation loop, CLI, or config loading.

## Next recommended phase

**Phase 5: Evaluator extraction.**  Extract the
``_evaluate_single_pass()`` closure from ``factory.py`` into a
standalone evaluator class inside ``workflows/rfgun_single_pass/``.
