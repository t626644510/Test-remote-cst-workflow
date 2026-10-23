# WF5 validation record

Date: 2026-09-28. Shared-core baseline: `dedc5fc` (`main`).

## No-CST validation

Using the repository `.venv\Scripts\python.exe`:

```text
python -m pytest -m "not cst_required" -q
819 passed, 1 skipped
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

## User-approved fixed-window campaign

The user subsequently requested 6 modes over 1030–1060 MHz. The new explicit
`fixed_window` policy accepts that configured search extent without an upper
sentinel and without automatic mode-count expansion. It still rejects empty,
discontinuous, unordered and out-of-range result tables, missing fields and
failed physical-quality checks. Coverage is recorded as a user acceptance,
not an automatically verified spectral-completeness claim.

Thirteen added no-CST cases validate this configuration and single-solve
behavior, including retaining the low-Q guard. A new local campaign uses
37 remaining solves, preserving the original aggregate budget of 40 including
the 3 already launched. The earlier campaign's data are retained independently.

## User-approved two-largest single-mode policy

The fixed-window baseline completed one solve and full field extraction, then
stopped under the original strict Q/linewidth guards. The user subsequently
requested removing the low-Q check and considering only the two largest
single-mode impedances. Explicit `physics.mode_policy: largest_two` disables
both isolated-mode applicability guards, retains all numerical extraction
checks, and ranks current in-window Q*(R/Q) scores rather than fixed mode IDs.

The previous six-mode field bundle was imported into a new campaign using
`--seed-campaign`, with no new CST solve. Template/native result evidence,
configuration compatibility, previous-score reproducibility, and remaining
budget were checked. The old archive stayed unchanged. All six modes pass
the remaining numerical checks; the two selected scores are 372030.861707 and
476001.270510 ohm/m (current IDs 1 and 4). These are the agreed single-mode
optimization scores; no overlapping broadband spectrum was reconstructed.

The imported baseline is valid under the new policy but above target. There
are 36 further solves available, preserving 40 total including 4 already used.
Sixteen new no-CST tests cover policy selection/ranking, retained numerical
checks, report selection, offline seed import, source locking, incompatible
settings, tampered/missing evidence and budget reset refusal.

## JSON persistence recovery (2026-09-28)

A live candidate completed CST solving and field extraction, then the campaign
journal rejected a NumPy boolean in supplemental mode-assignment evidence.
Mode matching now returns native Python booleans for both tie and ambiguity
comparisons. Numerical scores, matching decisions and solver settings are unchanged.
Four regression cases persist unique, rotated, unmatched and no-baseline
assignments through strict JSON and the campaign store. Full branch-local
no-CST validation: **823 passed, 1 skipped**.

The completed native result was fingerprint-verified and recovered without
reserving another solve. The local recovery audit preserves the old state and
full contract components, verifies that only the two boolean conversions changed
executable code, and records the old/new contracts before continuing. No general
fingerprint bypass was added. The recovered candidate's largest selected score
is 474016.830765 ohm/m; it is valid under the requested policy but above target.
Live continuation committed that result and proceeded to the next candidate.

## Two-workstation asynchronous launch (2026-09-28)

Full branch-local no-CST validation after adding the asynchronous workflow:
**848 passed, 1 skipped**. Twenty-five new tests cover different candidates,
in-flight deduplication without GP contamination, an aggregate 40-call budget,
lost permit replies, disconnected workers, immutable messages, result identity,
artifact traversal/corruption, central raw-field replay and changed conventions,
saved postprocessing recovery, active-worker exclusion and serial migration.

The serial controller was stopped only after its owned CST sessions had exited;
its immutable source state remains available. Thirteen records were imported
and valid field bundles replayed. Eight total historical solves were preserved,
leaving 32 of the original 40 for both nodes combined. No baseline was rerun.

Both Windows workers report the same complete execution fingerprint, including
workflow/shared code, template, CST Python SDK source and numerical versions.
The remote process runs in the logged-in desktop via a workflow-owned scheduled
task, independently of SSH lifetime. The local worker and coordinator likewise
run independently of the read-only terminal monitor. SFTP and SSH use a pinned
host key and a dedicated login key.

Live launch: different candidates `async_0001` (remote) and `async_0002` (local)
entered CST solving. The first local candidate `async_0000` returned a native
mesh failure through the worker/relay/journal path; its solve was charged and
its failed observation excluded from the GP. At this launch check the global
reservation count was 11/40, including both in-flight tasks. The first remote
candidate's complete field extraction and central numerical replay had not yet
finished; this launch evidence does not claim completed remote numerical validation.

## Live relay completion and heartbeat repair (2026-09-28)

The first remote result completed field extraction, evidence transfer and central
numerical replay: `async_0001` was valid with worst selected impedance
474911.119435 ohm/m. Local `async_0003` also passed at 481192.806264 ohm/m.
Total evaluation times were approximately 19.7 and 16.7 minutes respectively.
Two local mesh failures were charged normally and excluded from GP training.

A Windows reader briefly prevented replacing `heartbeat.json`. The unhandled
PermissionError terminated the local heartbeat thread; both workers' stale
heartbeats then prevented further dispatch after their results were collected.
Atomic JSON publication now retries PermissionError for at most one second,
preserving the previous complete document. Periodic heartbeat publication also
survives I/O failures and logs failure/recovery. Persistent failure still leaves
the heartbeat stale and blocks dispatch; it never starts another CST solve.
Three regression tests cover transient sharing violations, bounded permanent
failure and recovery to the current ready state. Full no-CST suite:
**851 passed, 1 skipped**.

Both workers and the coordinator exited normally at a completed-job boundary.
The local audit backed up all state, verified inactive owned CST sessions, and
verified that only the two I/O/liveness source files changed. Template, numerical
configuration, SDK and numerical-library fingerprints remained identical.
All 17 records, the RNG state and 12 consumed solves were preserved; completed
task contracts remain historical evidence. No general fingerprint bypass was
introduced. After deploying identical code to both machines, live continuation
dispatched distinct `async_0004` and `async_0005`; both entered CST solving with
fresh heartbeats and a combined reservation count of 14/40. Their final numerical
results were still pending at this verification point.

## Strongest-two quality selection (2026-09-29)

Under the user-selected `largest_two` policy, finite transverse impedances in
ohm/m are ranked before quality acceptance. Gradient and sampling cross-check
failures on weaker modes remain recorded but no longer reject the candidate.
Either selected mode failing those checks still rejects it; missing or nonfinite
mode data cannot be classified as weak. `strict_all` is unchanged.

Eleven regression cases cover weak-mode failures, invalid selected modes,
unrankable data, and a previously weak mode becoming the strongest. Full
branch-local no-CST suite: **862 passed, 1 skipped**.

Offline replay of 29 locally available campaign field bundles preserved all
25 previously valid worst impedances exactly. Four candidates previously rejected
only for a weak-mode gradient check now pass extraction quality, with worst
impedances 476816.236282, 470875.471942, 488703.097522 and 468777.784738 ohm/m.
None meets the 100000 ohm/m target or improves the existing campaign best.
Replay did not import CST or alter historical campaign state. No new live-CST
validation, remote deployment, search change or failure-isolation change was made.

## Model topology floors (2026-09-29)

Following the user's CST modeling diagnosis, configurable floors were added for
DownHeight2 (2 mm), UpperHeight2 (5 mm), and the single-bend centerline displacement
`r * (1 - cos(angle_deg * pi / 180))` (5.43 mm). The existing positive clearance
is added to each floor. Default height search bounds are now 2.01 and 5.01 mm.
The full swept-conductor envelope still enforces the 25 mm flange limit; a
centerline lower limit is not a replacement for that surface upper limit.
The 1-cos convention was verified against the WF2 and WF3 configurations and
the shared constraint implementation. Their old 2.75/9.785 mm limits were not copied.

Boundary, configuration, small-bend regression and existing dense-surface tests
passed. Full branch-local no-CST suite: **877 passed, 1 skipped**.
Offline prescreen of 101 historical records rejects 50 of 64 save failures,
including all five supplied modeling-debug examples. Fourteen save failures still
pass the prescreen, so these constraints do not establish a complete failure cure.
Fourteen of the 25 previously valid points also fail the new floors; historical
simulation evidence is preserved rather than relabeled or deleted. The old best
violates the DownHeight2 floor. The best previously valid point passing the new
rules is async_0081, with worst transverse impedance 457537.511662 ohm/m.
No CST solve, remote deployment, historical config/state rewrite, search algorithm
change or failure-isolation change was performed.

## Confirmed 90-degree model limit (2026-09-29)

The user confirmed that this model cannot rebuild bends above 90 degrees.
The default inner_angle3 search upper bound and configurable
`maximum_bend_angle_deg` preflight limit are now both 90 degrees, inclusive.
Mathematical swept-envelope tests above 90 degrees remain independent of this
model-specific limit. Tests cover the exact boundary, observed returning bends,
configurability and invalid settings. Full no-CST suite: **888 passed, 1 skipped**.
With the previously added floors, offline screening now rejects all 64 historical
save-failed points, including the remaining 14. This does not constitute a live
rebuild or proof that all possible modeling failures have been eliminated.

Search behavior was inspected, documented and left unchanged: preflight rejects
do not reach `observe`; completed failed evaluations do count as non-improvements,
so they can halve the shared six-dimensional local radius every four observations.
They remain excluded from GP fitting. Global bounds and exploration remain intact.
No CST process was started and historical campaign state was not modified.

## Additional coverage budget and valid-only adaptation (2026-09-29)

Completed failures now preserve the local radius and valid-result improvement
counters. Optional maximin coverage selects feasible global candidates farthest
from previous feasible attempts in normalized six-dimensional coordinates;
historical imports and failed evaluations do not count toward the valid-new-point
quota. After that quota, the existing GP/EI controller resumes.

A separate extension can replay completed distributed campaign evidence after
checking its execution identity, immutable template, parameter mapping, solver
settings and field contract. Admissible fields are copied and recomputed; excluded
coordinates remain only for deduplication. Prior solver consumption is recorded
separately and the additional hard budget starts at zero. Historical state is not
rewritten. Changed templates, numerical settings, active campaigns and corrupted
field evidence are rejected. Tests include 15-call budget exhaustion and preserved
historical files, failure counters, maximin selection and deterministic recovery.
Full no-CST suite: **905 passed, 1 skipped**.

## Signed dual-antenna and fork coordinates (2026-09-29)

Added a configurable fourteen-coordinate model while preserving the six-coordinate
default. Antenna 1 keeps negative bend angle and radius in CST and uses their
reflected positive physical dimensions for the same preflight geometry. The
canonical Lin1 coordinate can map to the template's Lin parameter without a
runtime model-name constant. Each fork has an inclusive configurable 5.43 mm
floor; the example 30 mm upper bound is a search choice only.

Tests cover both signs, angle/radius and topology limits, independent antenna
validation, fork boundaries, missing parameters, wrong configuration types,
normalization and fourteen-dimensional coverage search, empty feasible regions,
and signed writes through the existing wrapper with length-unit conversion.
Full branch-local no-CST suite: **926 passed, 1 skipped**. No live CST validation
or new campaign was started. Saved template metadata passed an offline baseline
geometry/bounds check; this does not certify rebuild or solve success.

2026-10-01 composite pilot: full no-live-CST branch suite via .venv Python and pytest -m 'not cst_required': 936 passed, 1 skipped. Historical 23 raw-field bundles replayed and imported with zero new solves; 8 feasible references and 15 outside-domain training observations. Live two-node validation is recorded in the local campaign launch audit, separately from these tests.
