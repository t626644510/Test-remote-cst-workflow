# RF-CEM Literature Review GUI

This branch contains a no-CST review loop for the literature semantics pilot.
It combines the TESLA comparison paper, the SLS-2 paper, human review state,
and a generated SLS-2 geometry hypothesis in one local browser application.

## Run

From the repository root, using the project virtual environment:

```powershell
$env:PYTHONPATH = (Join-Path (Resolve-Path '.') 'src')
& .venv\Scripts\python.exe -m rf_cem.literature_semantics review-gui `
  --bundle-root analysis_outputs\rf_cem_literature_pilot_20260710 `
  --manifest corpus_manifest.json `
  --paper-id sls2 `
  --session-root analysis_outputs\rf_cem_literature_pilot_20260710\review_sessions\sls2_gui
```

The command prints a tokenized `http://127.0.0.1:<port>/` URL. Open that URL,
not the saved HTML through `file://`; the page and API intentionally require
the same loopback origin.

## Review layers

1. **Evidence** shows text evidence, image evidence, and embedded paper pages.
2. **Semantic candidates** shows classification, the six semantic sections,
   and draft-prior patches. Structured manual additions start as `pending`.
3. **Geometry projection** shows the generated model and the nested Helper2
   Geometry, Features, and UDSG views.

Every reviewable item uses the literature vocabulary:

- `pending`
- `accepted`
- `accepted_as_soft_only`
- `rejected`
- `needs_more_evidence`

Per-item and global review notes accept Chinese text. Reviews are overlays;
the source semantic JSON, paper summaries, PDFs, and draft prior are never
edited in place.

## SLS-2 candidate 1

The pinned paper approximation uses dimensions in millimetres:

| Parameter | Value | Meaning |
| --- | ---: | --- |
| `L` | 680.0 | total axial length |
| `l` | 188.671 | straight beam-pipe length on each side |
| `r` | 50.0 | beam-pipe radius |
| `R` | 249.901 | equator radius for published cavity 1 |
| `a` | 125.232 | equator-side ellipse axial semi-axis |
| `b` | 70.2322 | equator-side ellipse radial semi-axis |

The symmetric profile uses four sampled quarter ellipses. With
`h = L/2 - l`, the reconstructed lower ellipse semi-axes are `h - a` and
`R - r - b`. That reconstruction is an explicit geometry hypothesis. The
paper defines the symmetric parameterization and reports the candidate values,
but does not directly provide a repository-ready STEP construction.

CadQuery 2.5.2 generates the solid without a seed STEP or CST. The sampled
ellipse points are passed to `Workplane.splineApprox` with maximum degree 5;
the STEP curves are approximations, not exact conic entities. The generator
checks parameter guards, a non-empty mesh, BRep validity, and expected `L`/`R`
bounding extents.

## Parameter iteration

The Geometry view exposes `L/l/r/R/a/b` fields in millimetres. Submitting a
valid tuple generates a new content-addressed STEP and overlays:

- `baseline`: the paper candidate;
- `previous`: the last generated candidate;
- `current`: the new human-edited candidate.

An edited tuple is marked `human_preview_edit`, has no paper `source_refs`,
and keeps the published tuple separately under `paper_baseline`. Its lineage
binds the immediate parent hashes. Approval of one tuple does not silently
approve a later edited tuple.

Semantic OK/reject/add actions request a refreshed preview, but v1 does not
invent a numeric geometry change from free-form semantics. Change the six
explicit parameters when a semantic decision should alter the shape.

## Session artifacts

The ignored session directory contains:

- `review_session.v1.json`: atomically replaced current review state;
- `review_events.jsonl`: append-only review events;
- `rf_cem_literature_review_gui.html`: self-contained UI served by the local
  process;
- `review_launch.json`: current loopback URL and process metadata;
- `geometry_previews/<content-hash>/cavity.step`;
- content-bound generation reports, whole-model meshes, and Helper2 face
  meshes.

Do not commit these runtime artifacts. The repository `.gitignore` already
excludes `analysis_outputs/`.

Windows PowerShell 5.1 treats JSON keys case-insensitively and therefore
cannot `ConvertFrom-Json` an object containing both the paper symbols `L` and
`l`. Use the GUI or Python's standard `json` module to inspect parameter-tuple
artifacts; the JSON itself is valid and preserves the paper's notation.

## Safety and limits

- The service binds only `127.0.0.1`, uses a random token, validates Host and
  Origin, emits no CORS permission, limits request size, and applies optimistic
  session revisions.
- Live CST, CST recovery, production-prior merge, and campaign mutation are
  not exposed by this GUI.
- A valid STEP/BRep and a visually plausible profile do **not** reproduce the
  paper's resonant frequency, shunt impedance, field ratio, HOM behavior, or
  any other RF result.
- Helper2 feature and UDSG mappings remain `requires_review`; its 500 MHz
  normal-conducting profile is a heuristic classifier, not paper evidence.
- The current v1 server keeps the active preview in the browser and writes
  content-addressed generation reports. Review decisions persist across
  reloads; the most recent unsaved parameter draft does not.

## Validation boundary

Use no-CST tests for this feature. A representative command is:

```powershell
& .venv\Scripts\python.exe -m pytest -q `
  tests\test_rf_cem_literature_geometry_candidate.py `
  tests\test_rf_cem_literature_interactive_reviewer.py `
  tests\test_rf_cem_literature_review_server.py `
  tests\test_rf_cem_literature_review_bundle.py `
  tests\test_rf_cem_literature_review_app.py
```

Live-CST validation is intentionally out of scope for this application.
