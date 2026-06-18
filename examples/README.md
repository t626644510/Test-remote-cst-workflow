# CST History Extractor Examples

`example_history.bas` is a small review fixture that resembles exported CST
history macro content.  It is designed to exercise the parser and classifier;
it is not a certified CST macro for production execution.

Run the extractor from the repository root:

```powershell
.venv\Scripts\python.exe -m cst_history_extractor --history-macro examples/example_history.bas --output-dir runs/baseline_extract
```

Direct `.cst` extraction is also supported when CST has unpacked the project
side folder containing `Model\3D\ModelHistory.json`:

```powershell
.venv\Scripts\python.exe -m cst_history_extractor --cst-file path\to\project.cst --output-dir runs\project_extract
```

Expected output groups:

```text
runs/baseline_extract/
  raw_history/
    history_raw.txt
    history_items.json
    cst_probe.json
    history_source_metadata.json
  analysis/
    command_inventory.json
    cst_recipe_manifest.json
    geometry_history_summary.json
    unknown_or_unclassified_commands.json
  reports/
    history_analysis_report.md
```

`expected_outputs/` contains representative outputs for this fixture.

## STEP Feature Assistant Example

`step_feature_assistant` reads STEP B-Rep topology and produces geometry review
artifacts for drafting a FeatureGraph:

```powershell
.venv\Scripts\python.exe -m step_feature_assistant --step-file StepData\bare_cavity_500mhz.stp --output-dir runs\bare_cavity_features --axis z --model-type bare_cavity_500mhz
```

Optional hints can be supplied with:

```powershell
.venv\Scripts\python.exe -m step_feature_assistant --step-file StepData\xband_2.3cell_gun.stp --output-dir runs\xband_features --axis z --model-type xband_2.3cell_gun --hints examples\user_hints.example.yaml
```

The v2 CadQuery/OCP backend provides CAD-kernel measurements when the optional
CAD dependency is installed:

```powershell
.venv\Scripts\python.exe -m pip install "cadquery==2.5.2"
.venv\Scripts\python.exe -m pip install "plotly==5.24.1"
.venv\Scripts\python.exe -m step_feature_assistant --step-file StepData\bare_cavity_500mhz.stp --output-dir runs\bare_cavity_500mhz --axis z --model-type bare_cavity_500mhz --backend cadquery --preview html
```

Use `--backend auto` to try CadQuery first and fall back to the STEP text parser
with the failure recorded in `geometry_manifest.json`.

Expected output groups:

```text
runs/bare_cavity_features/
  geometry_manifest.json
  face_inventory.csv
  face_inventory.json
  adjacency_graph.json
  feature_graph_draft.json
  review_report.md
  preview/
    face_coloring_legend.json
```

After manual review, use `examples/reviewed_feature_labels.example.yaml` as the
template for generating `resolved_feature_graph.json`.

Current runs also generate a project-specific
`reviewed_feature_labels.template.yaml`; prefer that file because it contains
the actual candidate and face ids for the current STEP import.  Complete CLI
usage is documented in `docs/step_feature_assistant_cli.md`.
