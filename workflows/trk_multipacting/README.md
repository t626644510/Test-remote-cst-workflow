# WF8.1 — TRK multipacting

Canonical branch: `workflow/8.1-trk-multipacting`. WF8 retains the PIC solver.
This branch contains no PIC workflow dependency. Run from this checkout with
the project's `.venv` Python. Install `.[dev]`; add `.[trk-surfaces]` for optional
offline CAD attribution (VTK). Offline analysis never imports CST interfaces.

## Commands

```
python run_workflow_8_1.py scan --root RUN --template INITIALIZED.cst --cst-library CST_LIB
python run_workflow_8_1.py resume --root RUN --cst-library CST_LIB
python run_workflow_8_1.py export --project SAVED.cst --output NEW_EXPORT --cst-library CST_LIB --surfaces
python run_workflow_8_1.py analyze --input NEW_EXPORT --output NEW_ANALYSIS --surfaces
python run_workflow_8_1.py report --input NEW_ANALYSIS OTHER_ANALYSIS --output REPORT
```

`CST_PYTHON_LIB` can supply the library path. All machine paths are explicit
arguments/environment values. `scan` starts a new run; `resume` requires an
existing snapshot, preserves its frozen selection and honors STOP/owner locks.
`export` opens only a copied, saved project and never starts a solver. It uses
the existing verified ParticleTrajectoryReader, Solid/STL and ResultReader APIs.
It requires disk capacity for a private copy including saved trajectories.
`analyze` writes separately from source exports; `report` reads analysis outputs.

## Preserved scan contract

The validated scan uses particle1–particle4 independently, factor1=0:0.1:1,
phase=0:30:330 degrees. Zero-field phase aliases preserve 484 actual/528 logical
cases and the existing case keys. The accepted template expressions remain
0.618*factor1 and phase, with initialized tetrahedral tracking and imported field
cache. The voltage label assumes factor1=1 corresponds to 500 kV; this is the
existing template calibration, not a newly measured accelerating voltage.
`--selection` retains the legacy frozen selected-case format. Source/material
settings and maximum pushes remain those of the saved template.

Default solver wall deadline is 600 s, then native abort with up to 180 s to
flush; both are configurable. A frozen legacy selection retains its own deadline
unless explicitly overridden consistently. Full mesh/cache identity is checked.
Only the owned private worker/session can be stopped; unrelated projects remain
outside the cleanup contract. No history rebuild/remesh in the scan loop.

Completed, aborted_saved, timeout and analysis_unavailable remain distinct.
An advisory current/generation discrepancy does not stop the scan. Invalid
source, changed mesh, uncertain process ownership or failed cleanup still does.
Saved result.json observations are reused; timeout records are not successes.

## Scientific outputs and limitations

Time ns; RF frequency MHz; geometry mm; macrocharge C; voltage labels kV.
Combined SEY sums secondary-emission currents / incident currents. Generation
g impacts correspond to emission g+1; generation is never treated as time.
Time windows are (t-window,t], default 3 RF periods, and use absolute macrocharge.
Initial seeds and terminal survivors are excluded from secondary/collision events.
No collision denominator means undefined, never zero. N(t) is a reconstruction
of recorded finite TRK trajectories, not self-consistent PIC particle density.

Rounded terminal times can hide collisions among survivors. Native counts must
support this classification; actual eligible macrocharges bound the missing
charge without assigning unknown track IDs. SEY intervals are saved explicitly;
the legacy scalar is their midpoint for plotting. Other unresolved classes fail
analysis rather than fabricate a yield. Truncation is not an MP/no-MP verdict.

Per-solid time attribution is geometric reconstruction from saved birth/end
positions and active non-vacuum CAD surfaces. Matching distance/separation,
native per-solid counts, generation currents and global charge conservation are
recorded. Failed attribution keeps evidence but emits no certified per-solid SEY.
STL export uses 0.001 mm surface tolerance; matching defaults to a 2 mm search
limit and 0.0001 mm minimum distance margin. Unexplained events remain unresolved.

Legacy exports with trajectory_extra.txt or trajectory_generations.txt, raw_curves,
Model.log and field_import_0_0.rex are read directly. Frequency can instead be
supplied as --frequency-mhz. Optional legacy surface_time exports are supported.
Original data and private projects are never committed to Git. Reports contain
HTML, CSV and PNG/SVG plots, with actual labels, source names, solid lists, statuses,
statistics and uncertainty; no MP4/MP5/MP6-specific statements are embedded.

## Provenance and validation

Migrated from the preserved WF8 TRK implementation and MP5/MP6 saved-result scripts,
including normal-abort supervision, late-3RF processing and endpoint/CAD mapping.
One-off deployment, repair and remote-takeover scripts remain local archives.
Official CST 2026 help: PredefinedField, TrackingSolver and ParticleTrajectoryReader
objects; Python Project.connect/abort_solver and existing verified repository
wrappers. No unverified CST API has been introduced.

Run `python -m pytest -q -m "not cst_required"`. No-CST tests do not validate a new
live solver/export run. This migration does not authorize or perform live solves.
