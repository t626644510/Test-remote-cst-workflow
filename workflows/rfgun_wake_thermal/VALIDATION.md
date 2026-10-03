# WF6 validation — 2026-10-03

Branch `workflow/6-rfgun-wake-thermal`, created from main
`dedc5fcabfa1bde0be49726d14488baea6f7cea0`. Shared core was not modified.

## Offline validation

- Full branch suite: `python -m pytest -m 'not cst_required' -q`:
  **609 passed, 1 skipped** (4 warnings), 3.84 seconds.
- Includes **29 WF6 tests**: signed antenna mapping and negative heights;
  projection boundaries; explicit config types; complex full transverse matrix
  and diagonal false-pass regression; signed common-axis subtraction; WF2
  resonator/Fourier normalization; six-fit shared-pole synthetic reconstruction;
  missing/invalid data uncertainty; dynamic component loss sums and voltage
  scaling; narrow port repair and caps; partial GP observations and failure
  isolation; RNG resume; zero feasible domain; shared DB idempotence;
  runtime/exploration budget; retention ownership; completed-worker recovery;
  extraction-only retry; solver-start-without-success protection; Windows venv
  launcher/child-process watchdog regression.
- `compileall` completed for the entry point and workflow package.
- Actual four-template configuration validated without CST: physical baseline
  agreement, geometry, source/witness offsets, sigma, beta, wake length and
  effective frequency range. Baseline projections: P1=12.1416280697 mm and
  P2=16.6201391009 mm. Both are mapped to radius magnitude 25 mm before solving.

Validation used the specified repository `.venv\Scripts\python.exe`.
The skipped test belongs to the shared baseline. No mocked test is treated as
evidence that the live CST interface or physical baseline has passed.

## Live acceptance

A separate **baseline-only** process was launched on 2026-10-03 at 20:05 local
time using the ignored local configuration. It owns four independent stages,
with a shared cumulative 96-hour budget. The baseline must return reliable
longitudinal, transverse and both antenna power metrics before search is allowed.

The first axis attempt reproduced the anticipated mesh failure, with the exact
CST 2026 message: "Waveguide for port number 3 is too short. The waveguide must
be homogeneous for at least three equidistant mesh planes along propagation
direction." No time-domain integration was performed. All owned processes
exited and were verified absent before the diagnostic matcher was updated.
The Windows venv launcher/tree watchdog was also corrected and regression-tested.

Only the known failing port changed: Port2=20 mm, Port3=22 mm. Baseline-only
continuation began at 20:13 local time. The original failure and 235.515 seconds
remain charged; a local contract migration audit records the code change and
preserved budget. No previous successful numerical result was reused.

Live acceptance remains **pending**, and optimization has not started.
Machine-specific launch audits, state, raw data, logs and final reports remain
in the configured local directories, not Git. A half-hour heartbeat checks
progress. Search may start only after the full live baseline acceptance passes.

## Saved-result correction, 2026-10-03

- Complete branch no-CST suite: **621 passed, 1 skipped, 4 warnings** using the
  prescribed `.venv`. Includes fixed-tail success, stale/aborted/incomplete/zero
  steps, typed errors, secondary-only false success, and recovery identity tests.
- The Port2=20/Port3=22 axial solve finished all **132966/132966** time steps.
  The old completion phrase matcher rejected CST's normal fixed-tail stop.
- The explicit recovery entry exported the saved XYZ wake and complex impedance
  curves without opening CST or performing another solve. Saved charge RMS was
  **0.050000 m** and the tail reached **35.000110 m**. Native hashes remained
  unchanged; warnings and original failed worker output were preserved.
- This establishes saved axial extraction, not yet four-template live acceptance
  or reliable reconstructed HOM values. Six-fit reconstruction is checked
  separately and cannot be replaced by successful extraction.
- Untapered initial peak detection counted 227 peaks, including the strong
  working-mode truncation sidelobes, and exhausted the 24-pole capacity. A
  Blackman-Harris spectrum now seeds frequencies only (14 live seeds). Direct
  spectra and time-domain fit data remain untapered; quality limits are unchanged.
  A regression verifies retention of a 100x weaker HOM next to a strong working
  mode without counting its rectangular-tail sidelobes as independent modes.
- Live six-fit reanalysis took 78.95 seconds. Native direct HOM-band maximum was
  1167.97 ohm; independent finite-tail spectrum maximum was 1176.35 ohm. All six
  fits were rejected: errors 1.056--3.108 percent and correlations above 0.9995
  do not compensate for boundary-controlled, unstable resonator peaks. The lower
  band edge also requires review. These large fitted peaks are not accepted
  physical impedance measurements. No reliable longitudinal GP value is stored.
- Baseline remains paused for reconstruction review, before X/Y/thermal solves.
  Completed raw data, all six fits, prior failures and elapsed costs are retained.
