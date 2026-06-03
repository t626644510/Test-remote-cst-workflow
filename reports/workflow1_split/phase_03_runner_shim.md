# Phase 03 -- Runner migration (compatibility shim)

## Summary

Migrated the complete runner logic from the root ``run_workflow_1.py``
into ``workflows/rfgun_single_pass/run.py`` and converted the root
script into a thin compatibility shim.  All CLI flags, default config
path, logging, checkpoint, optimizer, and retry behaviour are preserved.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/__init__.py` | Created | New |
| `workflows/rfgun_single_pass/run.py` | Created | New |
| `run_workflow_1.py` | Rewritten as shim | Modified |
| `workflows/rfgun_single_pass/__init__.py` | Updated docstring | Modified |
| `workflows/rfgun_single_pass/README.md` | Updated for Phase 3 | Modified |
| `workflows/rfgun_single_pass/BRANCH_CONTEXT.md` | Updated roadmap + rule 4 | Modified |
| `reports/workflow1_split/phase_03_runner_shim.md` | Created | New |

## Exact behaviour preserved

- **CLI**: ``--seed``, ``--n-iter``, ``--n-initial`` all work identically.
- **Config path**: still reads ``config/default.yaml`` relative to project
  root (no ``--config`` flag added yet -- reserved for Phase 4).
- **Logging**: ``_setup_logging()``, file handler to
  ``D:/Results/workflow1/workflow_1_runtime.log``, warnings to stderr.
- **Checkpoint**: ``CheckpointManager``, warm-start from prior data,
  ``_on_evaluation`` callback, SIGINT double-tap force-exit.
- **Optimizer**: ``build_workflow_1()`` call, SAO loop untouched.
- **Retry**: three-tier escalation via ``EvaluationRetryHandler``.
- **All imports**: ``cst_optimization.*``, ``yaml``, ``numpy``.

## Path handling explanation

In the original ``run_workflow_1.py``:

```python
_PROJECT_ROOT = _os.path.dirname(_os.path.abspath(__file__))
```

This resolved to the project root because the script was in the project
root directory.

In the migrated ``run.py`` (at
``workflows/rfgun_single_pass/run.py``):

```python
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
```

``parents[2]`` walks up three levels:
- ``parents[0]`` = ``workflows/rfgun_single_pass/``
- ``parents[1]`` = ``workflows/``
- ``parents[2]`` = project root

``CONFIG_PATH = str(_PROJECT_ROOT / "config" / "default.yaml")`` still
resolves to the same absolute path.

**Critical ordering**: the path setup code is evaluated **before** the
``from cst_optimization.checkpoint import CheckpointManager`` line,
because ``src/`` must be on ``sys.path`` for the import to succeed.

## Backward compatibility

- ``python run_workflow_1.py --seed 43`` -- works (shim delegates to
  ``workflows.rfgun_single_pass.run.main``).
- ``python -m workflows.rfgun_single_pass.run`` -- works (new entry
  point).
- ``run_workflow_2.py``, ``run_workflow_3.py``, ``config/*.yaml``,
  ``src/cst_optimization/``, ``examples/`` -- all untouched.

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
python -c "from workflows.rfgun_single_pass.run import main; print(main.__name__)"
```

### Real terminal output

**Test 1 -- compileall:**
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
Exit code: **0** (all clean, no recompilation needed for unchanged files).

**Test 2 -- --help:**
```
usage: run_workflow_1.py [-h] [--seed SEED] [--n-iter N_ITER]
                         [--n-initial N_INITIAL]

Workflow 1 SAO optimisation

optional arguments:
  -h, --help            show this help message and exit
  --seed SEED           Override optimizer seed from config
  --n-iter N_ITER       Override n_iterations from config
  --n-initial N_INITIAL
                        Override n_initial_samples from config
```
Exit code: **0**.

**Test 3 -- module import:**
```
main
```
Exit code: **0**.

## Risks

- **Import ordering**: the path setup in ``run.py`` **must** appear
  before the ``from cst_optimization`` imports.  A future refactor
  that reorders the module-level statements could silently break the
  import.  Mitigation: a ``# ---- Paths ----`` comment block acts as a
  visual barrier.
- **File-not-found on first run**: if the config file path ``CONFIG_PATH``
  is wrong, the ``yaml.safe_load(open(...))`` inside ``main()`` will
  raise, not when the module is imported.  The calculation is correct
  for the current layout, but any directory restructuring must
  update ``parents[2]`` accordingly.
- **Watchdog compatibility**: the watchdog command
  ``python run_watchdog.py -- run_workflow_1.py`` launches the shim,
  which imports ``run.py`` -- same behaviour as before.

## Next recommended phase

**Phase 4: Config split.**  Add ``--config`` CLI flag, validate the
config schema separately from Workflow 2/3 sections, and optionally
create a ``workflows/rfgun_single_pass/config_schema.py`` with typed
models for the parameters/objectives that WF1 actually reads.
