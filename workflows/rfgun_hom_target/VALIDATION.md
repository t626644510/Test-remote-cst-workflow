# WF5 validation record

Date: 2026-09-28. Shared-core baseline: `dedc5fc` (`main`).

## No-CST validation

Using the repository `.venv\Scripts\python.exe`:

```text
python -m pytest -m "not cst_required" -q
756 passed, 1 skipped
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

The corrected live baseline is running. CST reports a saved-template warning
that port 1 omits at least one propagating mode. Its settings are retained as
requested; this warning must accompany any numerical target result.
No extra convergence or confirmation solve is part of this workflow. The final
live outcome will be appended after the campaign stops.
