# CST Recipe Manifest Design v0.1

`cst_recipe_manifest.json` is an intermediate review artifact for future
`CSTTranslator` work.  It is not a final CST script and it is not treated as a
complete reconstruction of a project.

## Goals

- Preserve reliable CST setup evidence from exported history/macro text.
- Keep raw history references through `source_history_indices`.
- Attach confidence to extracted settings so uncertain values are reviewable.
- Leave unknown or unreliable fields as `null`, `"unknown"`, or empty lists.
- Provide a stable bridge toward `FeatureGraph + SimulationRecipe + MeshRecipe
  + PostProcessRecipe`.

## Top-Level Shape

```json
{
  "schema_version": "0.1",
  "project_id": "example_history",
  "source": "examples/example_history.bas",
  "project": {
    "units": {},
    "background": null,
    "parameters": {}
  },
  "materials": [],
  "geometry_summary": {},
  "boundaries": {
    "global": null,
    "symmetry": [],
    "local": []
  },
  "ports": [],
  "mesh": {
    "global": null,
    "local_refinements": []
  },
  "solver": {
    "type": "unknown",
    "settings": {},
    "confidence": 0.0,
    "source_history_indices": []
  },
  "monitors": [],
  "postprocessing": [],
  "result_exports": []
}
```

## Confidence Policy

- `0.9` and above: direct CST object or method evidence, for example
  `With Units`, `With Material`, `With DiscretePort`, `EigenmodeSolver`.
- `0.8` to `0.89`: strong keyword evidence but possibly context-dependent,
  for example mesh refinement or result metric keywords.
- Below `0.8`: weak or derived evidence.  v0 generally avoids using weak
  evidence for manifest fields.
- Missing or unsupported data is represented as `null`, `"unknown"`, or an
  empty list rather than invented values.

## Mapping To Future Semantic Recipes

- `geometry_summary.imported_files`, `components`, and `solids` can seed
  `FeatureGraph` geometry references.  v0 does not create final feature IDs
  or infer face selectors.
- `solver`, `boundaries`, and `ports` seed `SimulationRecipe`.
- `mesh` seeds `MeshRecipe`.
- `monitors`, `postprocessing`, and `result_exports` seed
  `PostProcessRecipe`.
- `materials` can support both `FeatureGraph` material semantics and
  `SimulationRecipe` assignment policies, but v0 keeps definitions and
  assignments close to their source history commands.

## Review Rules Before Promotion To CSTTranslator

- Confirm every CST command family against official CST documentation or an
  already verified repository wrapper.
- Keep source history indices in translator design notes so a reviewer can
  trace the setting back to the baseline project.
- Do not promote geometry construction details until there is a stable
  cross-project need.  Use geometry summaries first.
- Treat CST defaults as unknown unless the baseline history or official docs
  explicitly state them.
