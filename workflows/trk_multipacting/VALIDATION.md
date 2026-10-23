# WF8.1 validation — 2026-10-24

All validation used the project `.venv/Scripts/python.exe` (Python 3.9).
No CST solver or saved-project export session was started. Live export/run
behavior is based on the preserved, verified implementations and requires a
separate authorized live check; no-CST results do not claim live validation.

## Automated checks

`python -m pytest -q -m "not cst_required" --tb=short`:
**684 passed, 1 skipped**, 14 upstream matplotlib/pyparsing deprecation warnings.
The skipped test is inherited from the shared baseline; VTK tests ran with 9.6.2.
`git diff --check` and standalone `run_workflow_8_1.py --help` passed.

Tests cover complete/aborted-saved outcomes, native abort ownership, timeout,
resumption and STOP, mesh/cache invariants, source validation, advisory current
and generation differences, no collisions, shorter-than-three-period records,
variable terminal ambiguity, legacy input protection, dynamic source/report
labels, missing dependencies, and distant/coincident ambiguous CAD surfaces.

## Existing-data regression

Time is ns, frequency MHz, charge C. SEY below is charge-weighted over the last
three RF periods. N is the native-checked reconstruction of recorded trajectories.

| Export | Final N | Late SEY lower | Late SEY upper |
|---|---:|---:|---:|
| MP5 | 285563 | 1.8603905711641726 | 1.8603905711641726 |
| MP5-5 | 193909 | 1.8367828516961757 | 1.8367828516961757 |
| MP6-3 | 520911 | 1.9883462940522345 | 1.988375509368598 |

These match legacy machine-readable results (rtol 1e-8, atol 1e-10); native
per-solid event counts, generation currents and charge conservation all pass.
Every source fingerprint remained unchanged. MP6-3 retains an interval: no
terminal collision identities were invented. Reports were regenerated from the
actual data as HTML, CSV, PNG and SVG; the comparison PNG was visually checked.

The new VTK endpoint/CAD mapper was also run directly on MP5-5 saved STL surfaces:
688349 events, 0 unresolved; all native validation checks passed. Other two
per-solid regressions used their saved geometric mappings with the new reducer.

## Source and evidence

Original TRK modules/tests and artifacts scripts are preserved in the local
Git-reorganization backup, alongside the pre-change bundle, patches and ZIP hash
inventory. Deployment/takeover/patch scripts remain archived, not runtime inputs.
Source paths, complete local pytest logs, input fingerprints, comparison reports
and verification JSON are under the workstation's ignored
`.codex_tmp/git_reorg_20261024/` directory. Simulation exports are deliberately
outside Git. Canonical workflow and archive locations are listed in
`docs/WORKFLOW_BRANCHES.md` on the shared baseline.
