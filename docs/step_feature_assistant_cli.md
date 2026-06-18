# STEP Feature Assistant CLI

## Recommended Extraction

Use CadQuery for geometry intended for human review:

```powershell
.venv\Scripts\python.exe -m step_feature_assistant `
  --step-file StepData\bare_cavity_500mhz.stp `
  --output-dir runs\bare_cavity_500mhz `
  --axis z `
  --model-type bare_cavity_500mhz `
  --backend cadquery `
  --preview html
```

Review priority:

1. `preview/model_review.html`
2. `review_report.md`
3. `face_inventory.csv`
4. `feature_graph_draft.json`
5. `geometry_manifest.json` and `adjacency_graph.json` for machine auditing
6. `resolved_feature_graph.json` is the CSTTranslator input

## Main Options

- `--step-file`: required STEP/STP input.
- `--output-dir`: required project output directory. Prefer one stable directory
  per project instead of `_cad` or `_auto` suffixes.
- `--axis x|y|z`: beam axis; default `z`.
- `--model-type`: semantic rule profile:
  - `bare_cavity_500mhz`
  - `xband_2.3cell_gun`
  - `normal_conducting_500mhz`
- `--backend fallback|cadquery|auto`:
  - `cadquery`: production geometry review path.
  - `auto`: CadQuery first, fallback if unavailable.
  - `fallback`: portable STEP text diagnostics.
- `--preview html|none`: generate the offline reviewer; default `html`.
- `--open-reviewer`: open the generated HTML after extraction.
- `--hints`: optional expected features and known face/location hints.
- `--reviewed-labels`: validated human labels used to create the resolved graph.
- `--rules`: reviewed YAML override for model-profile thresholds.
- `--classifier-model`: experimental classifier used only for suggestions.

`--model-type` changes semantic candidates and thresholds.  It does not change
the CadQuery geometry manifest or face inventory.

## Human Review

Each run creates `reviewed_feature_labels.template.yaml`.  The interactive
reviewer can also download a populated `reviewed_feature_labels.yaml`.

```powershell
.venv\Scripts\python.exe -m step_feature_assistant `
  --step-file StepData\bare_cavity_500mhz.stp `
  --output-dir runs\bare_cavity_500mhz `
  --axis z `
  --model-type bare_cavity_500mhz `
  --backend cadquery `
  --preview html `
  --reviewed-labels runs\bare_cavity_500mhz\reviewed_feature_labels.yaml
```

Unknown face, group, solid, or rejected-candidate references fail with a clear
validation error.

## Rule Calibration

```powershell
.venv\Scripts\python.exe -m step_feature_assistant.calibration_cli `
  --review-roots runs\reviewed_projects `
  --output-dir runs\calibration
```

Outputs:

- `calibration_report.md`
- `calibration_proposal.yaml`

The proposal never changes production rules automatically.  Approved
thresholds must be placed under a model profile and passed with `--rules`.

## Experimental Classifier

Export reviewed data:

```powershell
.venv\Scripts\python.exe -m step_feature_assistant.classifier_cli export `
  --review-roots runs\reviewed_projects `
  --output-dir runs\training_dataset
```

Train the baseline:

```powershell
.venv\Scripts\python.exe -m step_feature_assistant.classifier_cli train `
  --dataset-dir runs\training_dataset `
  --output-dir runs\classifier_baseline
```

Display suggestions:

```powershell
.venv\Scripts\python.exe -m step_feature_assistant `
  --step-file StepData\bare_cavity_500mhz.stp `
  --output-dir runs\bare_cavity_500mhz `
  --axis z `
  --model-type bare_cavity_500mhz `
  --backend cadquery `
  --classifier-model runs\classifier_baseline\classifier.joblib
```

Classifier suggestions are written to `classifier_suggestions.json` and shown
in the reviewer.  They cannot alter the rule-based draft or resolved graph.
