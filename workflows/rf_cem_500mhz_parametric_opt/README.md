# RF-CEM 500 MHz Parametric Optimization

This workflow explores `free_equator_smooth` RF vacuum geometries by writing
optimizer values into an expert-prior override, regenerating STEP, and preparing
the existing CSTTranslator payload. It does not use CST `StoreParameter` as the
geometry source of truth.

## Default Preset

`config.yaml` defaults to `parameter_preset: exploratory_12d`:

- Equator crown radius, midpoint z, left/right shoulder z, left/right shoulder r.
- Left/right nose internal NURBS r/z offsets.
- Left/right large blend arc radius offsets.

The frequency target is `500 MHz` with an initial acceptance window of
`490-510 MHz`. The objective direction is high `R/Q`, high
`R = (R/Q) * Q`, and `Q >= 30000` as a soft floor.

## No-CST Smoke

From a prepared checkout:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m workflows.rf_cem_500mhz_parametric_opt.runner `
  --output-dir runs\rf_cem_500mhz_parametric_opt_12d_no_cst_smoke
```

If `runs\parametric_geometry_500mhz\metadata\parametric_geometry.v0.json` is
missing, the runner first regenerates that baseline package from
`Appendix\500MHz_baseline`. Therefore the workstation must contain the
`Appendix\500MHz_baseline` input directory before running the scan.

Expected outputs:

- `parameter_table.json`: 12D parameter names, bounds, feature refs, segment refs.
- `scan_report.json`: baseline plus six exploratory candidates.
- `candidates\candidate_###\geometry\generated_vacuum.step`
- `candidates\candidate_###\metadata\parametric_geometry.v0.json`
- `candidates\candidate_###\translator\cst_payload.json`

No-CST records may show `POSTPROCESS_TEMPLATE_MISSING` or `SOLVER_NOT_RUN`;
that is not a geometry failure. Live-CST scans must use the verified
Tetrahedral eigenmode path and `.rpp/.r0d` result-template registration.

## Live-CST Campaign

`rf_cem.live_500mhz_postprocessing_diagnostic` evaluates one candidate and then
exits. Use the campaign runner for repeated live-CST evaluations:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m workflows.rf_cem_500mhz_parametric_opt.live_campaign `
  --mode quick-live `
  --output-dir runs\rf_cem_500mhz_live_campaign_004 `
  --template-project-dir "D:\ModelData\bare" `
  --library-path "D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries" `
  --start-at-index 4 `
  --max-evals 4
```

This evaluates `candidate_004` onward from the configured quick scan. Each
candidate is generated into the campaign output directory and saved with a
matching CST project name, avoiding package/project numbering mismatches.

Outputs:

- `live_records.jsonl`: one line per live-CST evaluation.
- `live_summary.json`: best frequency fit, best R/Q, and best shunt impedance.
- `candidates\candidate_###\live_postprocessing\live_postprocessing_diagnostic_report.json`
- `cst_projects\candidate_###_postprocess_solver.cst`

To optimize around `candidate_004` as the local seed:

```powershell
.\.venv\Scripts\python.exe -m workflows.rf_cem_500mhz_parametric_opt.live_campaign `
  --mode sao `
  --output-dir runs\rf_cem_500mhz_sao_seed004 `
  --template-project-dir "D:\ModelData\bare" `
  --library-path "D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries" `
  --seed-candidate-index 4 `
  --local-bounds-scale 0.35 `
  --n-initial 6 `
  --n-iterations 4 `
  --max-evals 10
```

`--seed-candidate-index 4` loads the configured quick-scan vector for
`candidate_004` and uses it as the SAO warm start. `--local-bounds-scale 0.35`
shrinks each parameter bound around that seed, so generated campaign candidates
are perturbations of candidate_004 rather than unrelated points across the full
12D space. Use `1.0` for the full original bounds.

The campaign runner intentionally does not pass `--evaluate-templates` by
default because the verified result tree readback is sufficient, while explicit
template evaluation may produce the non-blocking CST `HEX mesh is invalid`
message.
