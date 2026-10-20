# WF8 PIC multipacting screen

Local scan of 21 named primary sources, field scale 0:0.2:1 and
phase 0:45:315 degrees. Zero field is evaluated once per source:
861 actual runs, 1008 logical points. The original primary emission face
groups and material laws are unchanged. factor1=1 is labelled 500 kV using
the user's calibration; the imported eigenfield multiplier is 0.618*factor1.

Use the repository `.venv` Python with `run_workflow_8.py --config <local.json>`.
Install the workflow's optional affinity/sampling dependency with `pip install -e ".[wf8]"`.
`--dry-run` prints the grid without CST, `--cases <keys...>` selects smoke cases,
`--limit N` bounds a batch, `--resume` continues, and `--analyze-only` recomputes
SEY from exported data without CST. Existing case result records, including
failed cases, are not retried automatically. A `STOP` file in the output
directory stops dispatch after the current case. A `RUNNING.json` refuses
duplicate dispatch; do not remove it while its dispatcher is alive.

Required local configuration (do not commit): `template`, `field_project`,
`output`, `cst_library`, `receivers` (CST tree path suffixes such as
`component5\\solid1`); optional `timeout_s` defaults to 7200.
Optional `cpu_affinity` is a list of Windows logical processor indexes;
`sample_hardware: true` records owned CST process CPU-seconds, RSS and affinity
every three seconds in `hardware.jsonl`. Pinning applies only to the dispatcher
and its newly created CST session; user sessions and system services are untouched.
For production set `sample_hardware: false`: affinity enforcement continues,
but per-process telemetry is not accumulated for the entire scan.

For concurrent local CST sessions set `cpu_groups`, for example
`[[0,1,2,3,4,5,6,7],[8,9,10,11,12,13,14,15]]`. These indexes are machine-specific:
on the verified i9-13900K they are two disjoint groups of four P cores including
their SMT siblings. Confirm topology before using on another machine.
Each worker owns its template, scratch directory, state and results under
`workers/workerN`. An idle worker receives the next pending case; faster cores
therefore process more cases. Completed/failed keys are deduplicated across all
workers on resume. Each case starts a fresh private CST session and reuses the
prepared template; no persistent IPC server or recovery tree is needed.
Keep CPU groups unchanged when resuming an existing output directory.
Parent `STOP` propagates to workers, allowing active solves to finish.
Remove the parent and worker STOP files explicitly only when resuming is intended.
Independent sessions require enough CST licenses and memory; benchmark identical
cases serially and concurrently before choosing a production worker count.

Each run exports unmodified MP 1D arrays in `raw_1d.npz`, with CST paths and
axis labels in `curves.json`. `sey.json` uses emitted/incident charge on the
same receiving surface, excluding primary emission. Current is A, time ns
is converted to seconds before integration. The verified CST convention
is incident positive and secondary negative. The main window is 5–20 ns;
5–10, 10–15, 15–20 and 0–20 ns are also reported. Endpoints use actual
samples without extrapolation. Zero collisions mean undefined SEY, not zero.
Missing currents are not invented except an omitted zero secondary current
supported by a zero secondary-emission histogram. Combined SEY covers only
successfully paired receiving surfaces, and lists exclusions.

The seed template is retained once per worker, each successful raw export is checked
by rereading, and then only the closed scan-owned `working` directory is
removed. Unknown/export/connection/timeout errors stop and preserve working
data. Ordinary solver failures are recorded without automatic retries.
Small solver text logs are retained for timing and failure diagnosis.
No global process sweep, lock deletion, remote recovery, or GP is used.

`summary.csv` contains per-case parameters, status, timings and primary SEY
metrics. `grid.json` explicitly records zero-field aliases. `state.json`
shows the current task/stage; its timestamp is a stage transition, not a
solver heartbeat. Solver progress remains in `working/case/Result/Model.log`.
The only 3D suppression is removal of PIC position monitors from the private
copy. No production template, external field project, or material is changed.

A 20 ns result is an initial screen, not proof of absence of sustained MP at
other amplitudes/phases or with a complete elastic/rediffused emission model.

API evidence: CST 2026 installed VBA documentation for `PICSolver`
(`DefineActiveParticleSourcesAndInterfaces`, `SimulationTime`),
`PredefinedField.SetExternalField`, `PICPositionMonitor.Delete`,
`Solver.MaximumNumberOfThreads` and application `DeleteResults`.
Python interaction uses the shared `CSTConnection`, `CSTProject`,
`SolverRunner` and `ResultReader` wrappers. Once projects are closed, verify the
private session's PID, creation time and parent-child birth ordering, then use
shared `close_targeted`. This avoids the observed GUI exit Crash Report and
never falls back to a machine-wide sweep. Cleanup failure stops new dispatch.
