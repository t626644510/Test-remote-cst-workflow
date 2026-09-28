# WF5 validation record

Date: 2026-09-28. Shared-core baseline: `dedc5fc` (`main`).

## No-CST validation

Using the repository `.venv\Scripts\python.exe`:

```text
python -m pytest -m "not cst_required" -q
790 passed, 1 skipped
```

This includes the complete 581-test shared-core baseline and WF5 configuration,
geometry, physics, search, storage and mocked runtime checks. The optional
installed-CST test is skipped; it is not counted as live interface validation.

Checks include exact swept-tube projection versus dense surface sampling;
dimensionless objective and normalized GP inputs; phase/amplitude invariance;
mode reordering and ambiguous signature assignments; missing/overlapping modes;
immediate target stopping; solver-budget reservations before launch; fresh-copy
retry limits; interrupted saved-result recovery; archive tamper refusal; and
source project/lock preservation. CLI help and local configuration validation
also passed. `git diff --check` passed.
Final additions cover exact-PID orphan-session recovery, cleanup after close
exceptions, UUID-linked cleanup evidence, and diagnostic CSV/Markdown tables.

## Saved real-field regression (no new CST solve)

The prior HOM audit's Mode 1 and Mode 3 field archives were processed read-only.
All 13 checked source-file hashes were unchanged. Strongest real-direction
impedances exactly equal the archived skill result (absolute difference zero):

| Mode | Strongest-direction impedance / kΩ/m | Gradient disagreement | Half-density integration difference |
|---|---:|---:|---:|
| 1 | 325.17605261742113 | 0.0012714835 | 0.0000059628061 |
| 3 | 567.7382805611593 | 0.0007256831 | 0.000011913755 |

The archived audit omitted another in-window mode's field evidence. Whole-window
offline replay correctly marks that old bundle incomplete; the two individual
regressions do not certify the new template or full-window optimization target.

## Live-CST validation

The user-requested independent-copy baseline is being validated separately.
Template: `Overhaul_Enew2.cst`; original mesh/material/port settings are inherited.

An initial interface-validation solve was stopped through the documented
`DesignEnvironment.connect(recorded_pid)` / `get_open_project(owned_path)` /
`Model3D.abort_solver()` calls after identifying an upper-frequency coverage
configuration issue. Only the owned project was addressed. That launched solve
counts against the total 40 budget; the corrected campaign has 39 remaining.

The official General (Lossy) documentation limits returned eigenfrequencies to
the global frequency maximum. The implementation therefore separates the
1070 MHz default solver maximum from the 1060 MHz acceptance maximum. This is
covered by regression tests; no JDM-only full-window switch is used. A sentinel
mode above 1060 MHz and a contiguous ascending table establish coverage.

The corrected baseline completed on implementation commit `9708630` at 11:32
local time. Six requested modes did not establish coverage, so the workflow
requested twelve on a fresh copy. CST returned seven modes, including sentinels
at 1065.227827 and 1066.074762 MHz. Both solves reported success; frequency/Q
reading and all five in-window complex-field/energy extractions completed.
The final recovery/report additions were validated without another CST solve.
Offline replay of the complete new field bundle produced exactly the same
JSON-normalized result as live postprocessing and did not import `cst`.

The startup stage stopped with `baseline_failed` / `quality_failed`; parameter
search did not start. A Q=1.736269 mode fails the configured isolated-mode
applicability guard. Its broad linewidth also triggers the overlap guard for
the other modes. The following values are diagnostics from the specified
single-mode formula, **not accepted full-window impedances or a target pass**:

| Mode | Frequency / MHz | Total-Q | Diagnostic strongest-direction Z / kΩ/m |
|---|---:|---:|---:|
| 1 | 1036.994819 | 1397.598775 | 338.825830 |
| 2 | 1043.459145 | 4131.481116 | 3.921932 |
| 3 | 1048.493076 | 398.863353 | 54.088894 |
| 4 | 1055.277150 | 1175.977884 | 490.499058 |
| 5 | 1057.545131 | 1.736269 | withheld: low Q |

All field extraction checks passed their numerical tolerances: largest gradient
disagreement 1.86556%; largest half-density integration difference 0.00166056%.
The low-Q mode's R/Q is 0.00008019723 Ω/m, but small coupling alone is not used
to bypass the applicability guard. Resolving that mode's treatment requires a
physical interpretation/acceptance policy; no guard was weakened automatically.

The total launched solve count is **3 / 40**: one initial aborted solve plus
two corrected-baseline solves. No optimization candidates or extra mesh
confirmation solves were run. Source manifest verification is unchanged.
CST warned that port 1 omits at least one propagating mode and that fewer modes
exist in the search area than requested; original port settings were retained.
Owned cleanup records report success; an independent exact-PID query confirmed
all five recorded corrected-campaign sessions were absent after completion.
Saved projects, raw fields, native tables,
diagnostic mode reports and resumable state remain in local output directories.
Changing executable code still invalidates automatic cache reuse; this live
campaign retains its original code identity rather than rewriting provenance.
