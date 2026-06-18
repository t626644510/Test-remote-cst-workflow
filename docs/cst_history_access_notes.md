# CST History Access Notes

This note records the documented local CST APIs relevant to CST history access
and the extractor v0 design decision.  It intentionally avoids undocumented CST
object names or methods.

## Confirmed APIs From Local CST Documentation

- `_docs/Python/source/cst.interface.html`, `cst.interface.DesignEnvironment`:
  the Python interface can start or connect to a DesignEnvironment.  Documented
  project operations include `DesignEnvironment.new()`,
  `DesignEnvironment.connect(...)`, `DesignEnvironment.connect_to_any()`,
  `DesignEnvironment.connect_to_any_or_new()`, and
  `DesignEnvironment.open_project(path)`.
- `_docs/Python/source/cst.interface.html`, `cst.interface.Project`:
  a live CST project exposes `Project.open(path)`,
  `Project.connect(cst_file)`, `Project.connect_or_open(cst_file)`,
  `Project.filename()`, `Project.folder()`, `Project.save(...)`,
  `Project.close()`, `Project.model3d`, and `Project.modeler`.
- `_docs/Python/source/cst.interface.html`, `cst.interface.Model3D`:
  documented modeler APIs include `Model3D.add_to_history(header, vba_code)`,
  `Model3D.full_history_rebuild()`, `Model3D.get_active_solver_name()`,
  `Model3D.get_solver_run_info()`, `Model3D.get_tree_items()`,
  `Model3D.run_solver()`, and `Model3D.start_solver()`.
- `_docs/PythonTutorial/3d_simulation_structure_modeling.html`,
  "Shape Modeling", "Setting the Units", and "Creating a new Material":
  the tutorial demonstrates constructing VBA snippets and adding them to the
  History List with `prj.model3d.add_to_history("step name", vba_code)`.
  It shows examples for `With Units`, `With Brick`, and `With Material`.
- `_docs/PythonTutorial/3d_simulation_simulation_setup.html`,
  "Creating Discrete Ports" and "Solver Setup":
  the tutorial shows `With DiscretePort` commands and a solver setup snippet
  using `Solver.FrequencyRange ...` and `ChangeSolverType "HF Time Domain"`,
  then adds those snippets to the History List with `add_to_history`.
- `_docs/Python/source/cst.results.html`, `cst.results.ProjectFile`:
  the results module can open a CST file for result access and expose result
  tree APIs such as `ProjectFile.get_3d()`, `ProjectFile.get_schematic()`,
  `ResultModule.get_tree_items(...)`, and result item readers.  This is result
  access, not a documented History List body reader.

## Observed Direct Project File Path

For unpacked CST projects, this repository has observed a history file at:

```text
<project folder>/Model/3D/ModelHistory.json
```

For example, a project at `path\to\project.cst` may have an unpacked side folder:

```text
path\to\project\Model\3D\ModelHistory.json
```

The observed JSON shape is:

```json
{
  "general": {
    "version": "2026.0",
    "date": "2025-08-29",
    "acis": "35.0.0",
    "buildnumber": "20250829",
    "project_type": "MWS",
    "length": "mm",
    "frequency": {
      "unit": "MHz",
      "minimum": "498.80000000000001",
      "maximum": "500.80000000000001",
      "minimum_expr": "499.8-1",
      "maximum_expr": "499.8+1"
    },
    "time": "ns"
  },
  "history": [
    {
      "caption": "define units",
      "version": "2026.0|35.0.0|20250829",
      "hidden": false,
      "type": "vba",
      "code": [
        "With Units ",
        "     .SetUnit \"Length\", \"mm\"",
        "End With"
      ]
    }
  ]
}
```

This file directly provides the ordered history caption and VBA code body that
the extractor needs.  It is an observed CST project file format rather than a
documented CST Python API, so extraction reports mark it as direct
`ModelHistory.json` evidence.

## What Is Not Confirmed

- The local docs do not expose a documented Python method that returns existing
  History List item names, categories, ordered macro bodies, or full history
  block contents from an arbitrary `.cst` file.
- `Model3D.get_tree_items()` is documented as returning a flat list of tree
  paths.  The docs do not state that these paths include History List macro
  bodies.
- `cst.results.ProjectFile` can inspect result trees and result data.  The docs
  do not present it as a project settings or history extraction API.

## v0 Access Decision

The preferred `.cst` path is direct `ModelHistory.json` extraction:

```powershell
.venv\Scripts\python.exe -m cst_history_extractor --cst-file path\to\project.cst --output-dir runs\project_extract
```

When `Model/3D/ModelHistory.json` is already unpacked, the extractor reads it
without opening CST.  If the file is not found and `--cst-library-path` is
provided, the extractor opens the `.cst` file via documented CST Python APIs to
trigger unpacking, then checks for `ModelHistory.json` again.

Exported history/macro text remains supported:

```powershell
.venv\Scripts\python.exe -m cst_history_extractor --history-macro examples/example_history.bas --output-dir runs/baseline_extract
```

If neither direct `ModelHistory.json` nor exported macro text is available, the
extractor records the source and emits an explicit limitation explaining that
history bodies were not recoverable through documented local APIs.

## Classification Boundary

The extractor classifies macro text by conservative evidence such as CST object
names and method names.  It does not execute macros, validate solver settings,
or infer hidden CST defaults.  Unknown commands remain in
`unknown_or_unclassified_commands.json` for manual review.
