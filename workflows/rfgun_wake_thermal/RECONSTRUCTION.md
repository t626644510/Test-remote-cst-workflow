# Measured wake and missing-tail reconstruction

Migration authorized 2026-10-03 from the later validated analysis in thread
`01a0b3a2-4e8b-7831-b479-a63a988c36ed`. There is no runtime dependency on that
thread, its checkout or local skill paths.

Provenance (SHA-256 of the user-owned source scripts):

- `analysis_sigma50/analyze_four.py`: `9d12ad73bae2d50f9c6c672fc2ea9138d28dd9d9c0e922c9b8f20e38f7b5fe4a`.
  Observed-start free-phase variable projection, analytic Jacobian, measured
  trapezoidal CZT and missing-tail integral.
- `QuickCal_sigma70_20260925/quickcal.py`: `dcb8b84c64d28a903a8078e5c5df9ee6b670e7e5b58d4e757a6d733fca66471f`.
  Matrix-pencil frequency/decay seeding with multiple ranks.
- The associated `validated_z.py` and `full_peak_quantify.py` motivated local
  window confidence and boundary-tail contamination checks. Their manually
  selected frequencies/windows and old bunch lengths are not transferred.

## Numerical contract

`Z = Fourier(full measured wake) + Fourier(fitted tail from L to infinity)`.
Input distances are metres, wakes V/pC (axial) or V/pC/m (transverse), output
ohm or ohm/m. Gaussian deconvolution uses configured sigma and beta=1.
Longitudinal uses -FT and transverse +i FT. Trapezoidal CZT retains every
measured sample on uniform grids; arbitrary frequency grids use direct
quadrature. The fit's DC nuisance term is never extended to infinity.

Pencil ranks 24/32/48 and starts 1/3 m replace the previous random-Q starts.
The fit eliminates signed sine/cosine amplitudes analytically. Frequency and
decay are common to all four transverse components. Coefficients are anchored
at the observed interval rather than extrapolated backwards to zero. Thermal
physics, source offsets, mesh, geometry and solver settings are unchanged.
`seeds` and `q_bounds` remain loadable for old configurations but no longer
control this reconstruction; use `pencil_ranks` and `decay_bounds_per_m`.

Each fit has an independent prefix fit for held-out prediction; prefix seeds
do not see withheld data. Default error and peak-spread tolerance is 10%.
Peak windows cover the full configured band and include this record's poles
and tapered-spectrum peaks. Tapering only discovers windows, never changes
the reported spectrum. All fits, including unusable tails, remain in evidence.
Bound-controlled contributions above 5% of a window peak invalidate that
window. Unstable fits cannot establish a below-threshold result.

Two distinct outcomes are recorded: a precise scalar usable by a GP, and a
reliable threshold decision. Six quality-passing, locally uncontaminated fits
can consistently establish exceedance even if their peak magnitudes vary by
more than 10%. The latter rejects a design but supplies no regression value.
Wholly unresolved windows are not treated as zero or below threshold.

Baseline admission checks a complete four-template pipeline. An impedance
scalar or a validated exceedance is sufficient for each wake decision, and
both thermal powers must be valid. This permits partial-observation search
from a clearly rejected baseline without manufacturing its impedance values.
Final feasibility still requires both complete, stable impedance scalars.

## Recovery and monitoring

Completed axis evidence is reused; the original solve and failure records,
raw curves and previous fit reports are retained. Code/config fingerprint
migration is explicit and audited while owned processes are inactive. It does
not reset the 96-hour budget or silently replay a solve. The repair watchdog
ends when its diagnosed stage succeeds; normal downstream stages do not
consume the two-hour repair allowance, but do consume the overall budget.

Half-hour monitoring keeps a persistent issue key and consecutive count.
At the second consecutive confirmed occurrence with no intervening user
action, inspect and fix autonomously. Before a runtime change, safely finish
or stop only verified owned processes, snapshot state/evidence, test the fix,
record contract migration and resume without replaying completed solves.
Physical ambiguity is not permission to weaken thresholds, fabricate results,
increase budget, extend the wake or connect to another workstation.
