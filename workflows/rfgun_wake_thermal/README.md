# WF6 — staged wake impedance and antenna metal losses

Canonical branch: `workflow/6-rfgun-wake-thermal`, based on main
`dedc5fcabfa1bde0be49726d14488baea6f7cea0`. The shared core is unchanged.
No runtime dependency on WF2, WF5, another worktree or a user skill installation.

## Invocation

Copy `config.example.yaml` to the git-ignored `config.local.yaml` and supply all
four complete CST projects (container plus same-name companion directory).
Supply `cst_library_path` or `CST_PYTHON_LIB`. Use the repository's `.venv`
Python, with this worktree as the working directory:

```powershell
$wf6Python = 'C:\Users\lau\cst_ver3\.venv\Scripts\python.exe'
& $wf6Python run_workflow_6.py --config workflows/rfgun_wake_thermal/config.local.yaml validate
& $wf6Python run_workflow_6.py --config workflows/rfgun_wake_thermal/config.local.yaml baseline
# Explicit continuation of an existing campaign, preserving its accumulated budget:
& $wf6Python run_workflow_6.py --config workflows/rfgun_wake_thermal/config.local.yaml resume
# Continue a baseline while retaining its stop-after-baseline boundary:
& $wf6Python run_workflow_6.py --config workflows/rfgun_wake_thermal/config.local.yaml resume --baseline-only
```

`optimize` starts a new campaign, first running its complete baseline. Search
is enabled after all four templates pass pipeline admission: each impedance
needs a reliable scalar or a validated exceedance decision, and both thermal
powers must be reliable. An exceedance without a stable scalar is never a GP
observation or a feasible design. Fully unresolved wakes block admission. `baseline` stops
after the four-template baseline. `stage --stage axis|x|y|thermal` diagnoses one
stage in a new directory. `resume` never ignores an occupied worker/CST PID.
`offline --candidate candidate_0000 --destination <new-directory>` reconstructs
retained numerical evidence; it neither imports CST nor changes campaign state.
Creating `STOP` in the metadata directory pauses after the current action.
Remove that file before explicitly resuming. No remote execution is supported.

## Scientific contract

The physical coordinates are twelve values, in degrees and mm. Each antenna
has selfangle, UpperHeight, DownHeight, Lin, projection and fork length. The
projection is the double-bend displacement `P=2R(1-cos(theta))`, bounded
5.43–19.57 mm, with fixed radius magnitude 25 mm. Antenna 1 stores negative
radius and angle; `Lin1` maps to CST `Lin`. Negative DownHeight is supported:
`abs(DownHeight) <= UpperHeight - 0.01` and `Lin - DownHeight >= 0.01`.
The baseline is collapsed from the templates and rebuilt at the fixed radius.

Axis/X/Y wakes must cover the same full 550–2047.8288539789505 MHz band,
with Gaussian sigma=50 mm, beta=1 and the fixed 35 m wake. Both offset beams
are +2 mm; both integration witnesses remain on the global beam axis.
Signed axis subtraction gives the full transverse matrix in V/pC/m. No
diagonal-only approximation or missing-result zero is used.

For complex `Z`, the worst real-direction transverse response is
`sqrt(lambda_max(Re(Z.conj().T @ Z)))` in ohm/m. Longitudinal magnitude is in
ohm. Default limits are 2000 ohm and 150000 ohm/m. This transverse definition
is distinct from WF5's individual eigenmode dissipative-polarization metric.

Reconstruction now preserves the full measured wake and adds only its missing
infinite tail, following the later validated reference analysis. Three pencil
ranks and two starting positions produce six joint free-phase fits. Independent
prefix fits predict the withheld tail. Defaults: 10% residual/holdout error,
0.95 correlation, 10% local peak spread. Bound-controlled tail contributions
and unresolved peak windows are retained explicitly, never filled with zero.
Longitudinal fits include the working mode; transverse fits share poles across
all four signed components. Full complex native spectra verify units and phase.
See [RECONSTRUCTION.md](RECONSTRUCTION.md) for provenance and limitations.

The thermal stage identifies exactly one returned working mode in 498–502 MHz.
QFactor exports all solids and component5/6 are summed dynamically. The same
mode's complex axial voltage integral normalizes the losses to peak 500 kV,
CW, beta=1: `P_i=sum(P_solid)*abs(500000/Vacc)**2`. Power units are W. No
temperature, port output power or beam-driven HOM heat is included. The
default 150 W per antenna is a soft aspiration; search continues after it is
met. Eigenmode accuracy 1e-6 and external-Q accuracy 1e-4 are separate values.
The template's mesh strategy is preserved; no extra mesh convergence solves.

## Partial evaluations, numerical faults and search

Each stage uses an independent owned copy. Parameters are rebuilt, saved
without old results and reopened before solver settings are applied and
checked. Solver success requires fresh explicit log/message evidence and
complete newly read results. A solved task with failed extraction is retained;
explicit resume retries only extraction. An interrupted solve without success
evidence is recorded as interrupted, never silently rerun.

Only explicit port 2/3 nonuniform/inhomogeneous mesh diagnostics activate
repair. Defaults: 20,22,18,24,16,26,14,28,12,30,10 mm; only diagnosed ports
change. There are at most ten repair retries and two cumulative repair hours
per candidate. Changing the combination invalidates all active wake stages;
new axis/X/Y results must use the same combination. Old evidence stays in the
journal and is not used as mixed-geometry observations. Other failures do not
become artificial impedance penalties or shrink the trust region.

Four independent Matérn GPs use only each metric's reliable observations,
with normalized coordinates and `log1p(metric/threshold)` outputs. Fewer than
six observations, or GP failure, falls back to feasible coverage. The initial
baseline plus twelve valid longitudinal coordinates use maximin coverage;
partial-stage promotions are interleaved. Four transverse and two thermal
observations are bootstrap priorities subject to actual time availability.
Later pools are half global, half local; valuable transverse partial points
remain eligible centers even when their longitudinal gate fails.

The controller compares partially evaluated and new points using predicted
remaining cost. Before impedance feasibility it rewards lower worst normalized
violation and uncertainty. Afterwards it uses Monte Carlo expected worst-antenna
power improvement multiplied by impedance feasibility probability and divided
by remaining cost. Radius starts at 0.25, expands after three comparable valid
improvements, and contracts after six comparable valid non-improvements down
to 0.05. Failed or missing observations do not affect these counters.

About 20% of measured runtime is reserved for gate-crossing exploration,
balanced between near/uncertain and broadly distributed candidates. A full
baseline can initially exceed that fraction; subsequent dispatches repay that
exploration debt. Gates remain mandatory for final accepted designs.

## Runtime, recovery and data ownership

Default budget is 48 hours of active coordinator/worker/reconstruction time per round.
Paused downtime is excluded. The budget is a dispatch deadline: once reached, no
new stage starts. The current solve and postprocessing finish normally; actual
overrun is charged to the finishing round and never deducted from the next 48 hours.
Independent fault/repair watchdogs still apply. At closure STOP is written and
resuming that closed round is refused; subsequent rounds require user audit and
explicit manual authorization. There is no automatic round loop or round-count cap. Count forecasts are
reported only after all four baseline stage costs have been measured.

The parent supervises an independent Python worker. Session UUID, PID and
Windows process creation time protect targeted cleanup from PID reuse. Only
owned processes are stopped; no global CST cleanup or project lock deletion.
Recovery refuses occupied or unverifiable worker/session identities. Immutable
template, parameter, port, solver, configuration and code fingerprints prevent
cache reuse across different contracts. Editing code during a campaign is
unsupported; use a separate, reviewed campaign contract for a changed workflow.

Put `output_dir` on the metadata drive (D in the local configuration), and
`artifact_dir` on the large-data drive (E locally). The former contains state,
the shared evaluation SQLite database, checkpoint, heartbeat, campaign log,
`report.json` and `candidates.csv`. The latter contains immutable templates,
candidate projects, raw numerical bundles, per-fit spectra and loss tables.

Native project retention keeps the baseline, best feasible result, up to five
Pareto alternatives and two recent completed candidates. Reserved tasks and
failed-extraction projects are protected. Other completed stage project copies
can be removed only after their permanent numerical evidence manifest verifies.
The cleanup checks resolved ownership and never traverses into source templates
or another campaign. Disk reserve exhaustion pauses with an explicit error.

## Provenance and verification

- WF2 `pso_wake_fit.py`, branch commit `6a6c99d`: damped wake basis, Gaussian
  bunch factor, amplitude-to-R/Q normalization and resonator impedance formula.
  The joint shared-pole fit and ensemble uncertainty checks are WF6 additions.
  The legacy missing-result zero and fallback-success paths were not migrated.
- WF5: owned CST lifecycle, exact-PID recovery gate, verified copying and
  VectorPlot3D extraction macro. These reuse shared connection/project/solver
  classes; no shared module has been copied into this workflow.
- User-validated `loss_field_probe_20260923`: QFactor per-solid ASCII loss export
  and peak-voltage scaling. Solid names are discovered from each new export.

Run the complete branch-local suite with:

```powershell
& $wf6Python -m pytest -m 'not cst_required' -q
```

No-CST tests do not establish live API acceptance. The separate baseline must
demonstrate actual result paths, units, mesh-error classification, full-band
curves and component-loss normalization before optimization is enabled.

### Saved wake recovery

CST 2026 normally ends a fixed-length wake with `Maximum number of pulse widths
simulated, solver stopped.` This is accepted only with wrapper success, a fresh
WakefieldSolver completion log, matching positive simulated/planned time-step
counts, no error/abort, and complete saved curves. Secondary-quantity success
alone is insufficient. Charge extraction uses `Charge distribution (distance)`
and validates its distance unit and measured RMS bunch length.

For an already finished wake rejected by an older completion matcher, use
`--config <config> recover-saved --task <attempt/task.json>`. This command never
opens a CST session or launches a solve. It verifies inactive owned processes,
task/parameter/port/settings identity, native log agreement, full-tail evidence,
and unchanged native hashes. It writes numerical bundles and a separate recovery
receipt; original failure records are retained. It does not silently migrate
campaign fingerprints or restart optimization. Integrate the recovered stage
through an audited compatibility migration, retaining prior runtime charges,
then perform offline reconstruction before continuing the baseline.

Pole initialization uses a Blackman-Harris tapered spectrum to reduce finite-tail
sidelobes around the working mode. Only frequency seeds use this taper: reported
direct spectra, signed fit data, residual checks, and acceptance thresholds are
unchanged. The saved reconstruction bundle includes both spectra and all six
fits. A low wake residual alone does not validate boundary-controlled or unstable
resonator impedances.

### Longer-tail comparison and preliminary screening

An explicitly authorized one-off comparison can run outside the campaign clock:
`--config <config> verify-tail --length-m 50 --output <separate-state> --artifacts <separate-bulk>`.
It copies the original immutable snapshots and baseline coordinates/port pair,
runs axis/X/Y once each, verifies the effective tail setting, and reconstructs
the complete matrix. It never solves thermal, repairs ports, retries a failed
solve, alters meshes, changes the original state, or starts search. `--resume`
only recovers already dispatched work; a failed solve is not replayed. The
comparison records its own elapsed time, source-state hash, and three-start cap.

After reviewing the comparison, an audited config migration can enable
`search.observation_mode: finite_tail_screening`. This explicitly uses the
fixed-length measured Fourier peaks for both impedance GP observations and
stage priorities. It consistently uses those proxies even for candidates with
reliable reconstructions; thermal observations remain validated metal power.
All six reconstructed fits and qualified metrics remain separate and unchanged.
Screening admission does not set qualified baseline acceptance or physical
feasibility. Reports distinguish `screening_best` from a qualified best design,
and retention protects the top proxy-ranked native projects. Narrow resonances
can be underestimated; these rankings select directions for later validation.
Do not mix 35 m and 50 m proxies in one campaign or silently change observation
mode, code fingerprint, or the existing runtime budget.

`recover-thermal --task <saved-task>` accepts fresh structured eigenmode success
messages together with the native result table. It verifies saved identity and
settings, extracts QFactor losses/voltage on an isolated native copy, and checks
that the original result hashes are unchanged. It performs no eigenmode solve;
the original failure remains available for an audited state migration.

Validation on 2026-10-04: full branch-local no-CST suite, 635 passed, 1 skipped
(4 existing NumPy integration deprecation warnings). Separately, live saved
thermal recovery succeeded without solving: mode 499.659176738 MHz; at 500 kV
peak CW, component5 388.457 W and component6 519.070 W. The longer-tail run is
a separate live validation; unit tests do not establish its completion.


### Common-band historical observations (2026-10-04)

Audited `state.historical_observations` may supply GP-only finite-tail proxies from another bunch length after raw curves are recomputed on the current full band using their own Gaussian sigma. The wake length and physical coordinates must agree; full transverse matrices must be formed within a consistent source trio. These records do not count as new stage completions, initial-coverage quota, budget, incumbent feasibility, or trust-radius comparisons. A current observation supersedes a historical observation at the same coordinates separately for each metric.

`search.history_relative_noise` defaults to 0.20 for historical impedance; `native_relative_noise` defaults to 0.02. These are search-model uncertainty assumptions, not proven numerical error bars. CW working-mode metal powers with verified identical geometry and thermal settings use native noise. Noise is converted to log1p output units and divided by the actual output normalization before becoming the GP diagonal variance. Raw histories, common-band fits and provenance remain available; the state, checkpoint and evaluation database preserve their GP-only identity. Formal acceptance still requires current campaign evidence.


### Reconstructed-peak screening (current WF6 contract)

Use `search.observation_mode: reconstructed_peak_screening`. The 2000 ohm and
150000 ohm/m gates refer to **reconstructed** impedances. Direct measured FT
spectra remain evidence and contradiction checks only. They are not GP targets,
stage gate values, sorting values, or trust-radius observations in this mode.

`peak_consensus.py` assesses a partition of the entire configured band. Local
peak agreement requires at least four of six quality-passing fits, covering both
start positions and at least two pencil ranks. Boundary-tail contamination is
assessed locally; rejected fit values remain in evidence. Unsupported windows
remain in the global peak estimate and mark it unresolved. A missing finite
window or missing band coverage excludes the scalar from the GP. Rising upper
band endpoints prevent qualified acceptance.

Search uses the maximum of local reconstructed median estimates; its relative
uncertainty includes fit/holdout error and ensemble spread (minimum 25% for an
unresolved local peak, at least 100% when no bounded envelope is supported).
These are sensitivity/model assumptions, not calibrated confidence limits.
Formal `metrics`/`feasible` require every window to qualify, no unresolved band
edge, and no threshold-straddling envelope. `screening_metrics` and
`screening_best.estimated_metrics` are expressly preliminary and include the
full uncertainty record. A supported finite upper envelope controls ordinary
stage promotion; unresolved/unbounded points can still use the unchanged 20%
actual-time cross-gate exploration allocation. Sorting uses the upper estimate
or an uncertainty penalty for unbounded windows, without treating that penalty
as a physical upper bound.

The GP targets reconstructed estimates, with ensemble uncertainty combined
conservatively with the native/history noise floor before the existing log1p
normalization. Historical common-band records require reconstructed evidence;
legacy direct-FT history is excluded until reprocessed. Current sigma70 values
replace same-coordinate sigma50 observations metric by metric. Observed partial
results keep their uncertainty in cost-aware acquisition. Trust-radius streaks
change only for non-overlapping, comparable reconstructed envelopes; uncertain
comparisons and numerical failures cannot shrink the radius.

Migration retains original raw curves, old fit evidence, all stage identities,
CST start counts, and budget history. Offline reanalysis creates a new evidence
revision, checkpoint and database observations record the new definition, and
an explicit config/code/template fingerprint migration is required before resume.
No CST replay is needed for this change. The sigma70 band and 35 m tail remain
unchanged; uncovered high frequencies cannot be declared suppressed.


## Transverse coverage policy and manual rounds

`search.policy: transverse_coverage` requires `reconstructed_peak_screening`.
The normal X/Y admission line is a finite, full-band, noncontradictory longitudinal
upper envelope at or below `search.transverse_admission_ohm: 3000` ohm. Final
targets remain 2000 ohm longitudinal and 150000 ohm/m transverse. Above-gate or
unbounded cases retain 20% actual-time X/Y exploration, split by charged time
between GP merit and coverage distance from transverse-observed points. Thermal
time is excluded from this exploration ledger. Completion of Y has a small tie
preference; remaining wake cost excludes previously completed stages and heat.

Four GP models and their observation-quality/noise rules remain unchanged. Before
both impedance screening envelopes pass their targets, acquisition uses saturated
log-normalized constraint violations with longitudinal/transverse weights 2:1.
Below-target longitudinal improvements supply no further reward. After both
screening envelopes pass, acquisition uses heat improvement times joint impedance
feasibility probability; the 150 W per-antenna soft target also saturates. Thermal
evaluation is offered to the best five known wake combinations (configured by
`retain_pareto`), independently of X/Y exploration. These are search heuristics;
they do not establish formal physical feasibility or calibrated confidence bounds.

For a reviewed transition, create a local config with separate new output/artifact
directories, identical physics/templates/reconstruction, and `search.hours: 48`.
Run `run_workflow_6.py --config <new.local.yaml> prepare-round --source <previous-output>`.
This is offline preparation only: it verifies inherited raw/analysis manifests,
clones observations and the applied stage journal, copies current analysis caches,
creates a fresh zero clock and a cumulative ancestry ledger, and leaves STOP set.
Old failures stay failed and inherited native results are excluded from retention.
Changed physics, unresolved journals, reused storage, or altered templates are
rejected. After the user authorizes starting, remove only the new round's STOP and
use `resume` with that config. Never use `optimize` to erase/restart inherited state.

Previously charged costs outside the source state may be carried once with
`prepare-round --prior-external-seconds <audited-seconds>`; subsequent rounds
inherit that separate ledger automatically and reject charging it again.
