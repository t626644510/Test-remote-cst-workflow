# Phase 04 -- Config split

## Summary

Created a Workflow-1-specific ``config.yaml`` inside the
``workflows/rfgun_single_pass/`` package, extracted from the shared
``config/default.yaml``.  Added a ``--config`` CLI flag to the runner
and changed the default config path from the shared config to the
WF1-specific one.

The shared ``config/default.yaml`` is **not deleted** -- it continues
to serve Workflow 2, Workflow 3, and legacy entry points.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_single_pass/config.yaml` | Created | New |
| `workflows/rfgun_single_pass/run.py` | Added ``--config`` + ``DEFAULT_CONFIG_PATH`` | Modified |
| `workflows/rfgun_single_pass/README.md` | Updated for Phase 4 | Modified |
| `workflows/rfgun_single_pass/BRANCH_CONTEXT.md` | Added ``config.yaml`` to allowed modifications | Modified |
| `reports/workflow1_split/phase_04_config_split.md` | Created | New |

## Config sections copied

Only the 8 sections that Workflow 1 actually reads (from Phase 1
inventory):

| Section | Top-level keys kept | Notes |
|---|---|---|
| ``cst`` | ``library_path``, ``connect_mode`` | ``result_cache`` excluded (not read by WF1) |
| ``solver`` | ``stagnation_timeout_s``, ``settle_s`` | |
| ``logging`` | ``output_dir`` | ``enabled``, ``auto_flush_interval`` excluded |
| ``project`` | ``cst_path`` | |
| ``evaluation`` | ``post_eval_recovery`` | |
| ``optimization`` | ``algorithm``, ``n_initial_samples``, ``n_iterations``, ``acquisition_function``, ``acquisition_xi``, ``acquisition_kappa``, ``seed``, ``retry.*`` | |
| ``parameters`` | 13 geometry parameter entries | Only WF1 optimisation params, not tolerance params |
| ``objectives`` | 7 objective entries | resonant_freq, coupling_beta, peak_e_field, q0, max_modified_poynting, field_flatness, pulsed_heating |

## Config sections excluded

The following sections from ``config/default.yaml`` were deliberately
omitted because they belong to Workflow 2 or Workflow 3:

- ``workflow_2:`` (entire block -- HOM antenna wakefield workflow)
- ``tolerance:`` (entire block -- tolerance / robustness analysis)
- ``cst.result_cache`` (not read by WF1 code path)
- ``logging.enabled``, ``logging.auto_flush_interval`` (not used by WF1)

## Default config path before / after

| Phase | Default config path |
|---|---|
| Phase 1-3 | ``<project>/config/default.yaml`` |
| Phase 4 | ``<project>/workflows/rfgun_single_pass/config.yaml`` |

The ``--config`` flag allows overriding:

```powershell
python run_workflow_1.py --config path/to/custom.yaml
```

## Backward compatibility

- ``python run_workflow_1.py`` -- now reads the WF1-specific config
  instead of the shared default.  The same key structure means the
  behaviour is identical.
- ``python run_workflow_1.py --config config/default.yaml`` -- reads the
  old shared config (explicit override).
- ``run_workflow_2.py``, ``run_workflow_3.py`` -- unchanged; they still
  read ``config/default.yaml`` and ``config/workflow_3.yaml``.
- ``src/cst_optimization/`` -- untouched.
- ``config/default.yaml`` -- untouched, still present on disk.

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py run_workflow_2.py run_workflow_3.py
python run_workflow_1.py --help
python run_workflow_1.py --config workflows/rfgun_single_pass/config.yaml --help
python -c "import yaml; from pathlib import Path; p=Path('workflows/rfgun_single_pass/config.yaml'); cfg=yaml.safe_load(open(p, encoding='utf-8')); print(sorted(cfg.keys()))"
python -c "from workflows.rfgun_single_pass.run import DEFAULT_CONFIG_PATH; print(DEFAULT_CONFIG_PATH)"
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
  --config CONFIG       Path to Workflow 1 YAML config (default: C:\Users\lau\
                        cst_ver3\workflows\rfgun_single_pass\config.yaml)
  --seed SEED           Override optimizer seed from config
  --n-iter N_ITER       Override n_iterations from config
  --n-initial N_INITIAL
                        Override n_initial_samples from config
```

**Test 3 -- ``--config`` explicit override (exit 0):**
Same output as Test 2 (confirming the override path is accepted).

**Test 4 -- config key validation (exit 0):**
```
['cst', 'evaluation', 'logging', 'objectives', 'optimization',
 'parameters', 'project', 'solver']
```

**Test 5 -- ``DEFAULT_CONFIG_PATH`` import (exit 0):**
```
C:\Users\lau\cst_ver3\workflows\rfgun_single_pass\config.yaml
```

## Risks

- **Stale shared config**: if ``config/default.yaml`` changes the
  structure of the WF1 sections (e.g. a new key is added to
  ``optimization``), the WF1-specific ``config.yaml`` must be manually
  synchronised.  No automated sync mechanism exists yet.
- **Missed key**: if a key that WF1 actually reads was accidentally
  excluded from the extracted config, the ``yaml.safe_load`` will still
  succeed but ``cfg.get("key")`` will return ``None``, relying on the
  fallback default in the evaluator code.  The Phase 1 inventory
  cross-checked the keys; the 8 sections above match what the code
  reads.
- **Absolute paths in config**: the ``config.yaml`` contains absolute
  paths (``D:/CST2026/...``, ``F:/workflow_elgun/...``,
  ``D:/Results``) inherited from the original.  These are
  machine-specific and would need templating for portability.

## Next recommended phase

**Phase 5: Evaluator extraction.**  Extract the
``_evaluate_single_pass()`` closure and physics computation from
``factory.py::build_workflow_1()`` into a standalone evaluator class
inside ``workflows/rfgun_single_pass/``.  This would make the CST
evaluation logic independently testable and break the dependency on
the God-object factory.
