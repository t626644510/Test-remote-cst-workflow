# CST History Analysis Report: example_history

## Source

- Source: `examples\example_history.bas`
- Parsed history items: 12

## Command Inventory Summary

- boundary: 1
- geometry: 2
- material: 1
- mesh: 1
- monitors: 1
- ports: 1
- project: 2
- results: 2
- solver: 1

## Recognized Command Types

- boundary/global_boundary: 1
- geometry/import: 1
- geometry/primitive_creation: 1
- material/material_definition: 1
- mesh/global_mesh: 1
- monitors/e_field_monitor: 1
- ports/waveguide_port: 1
- project/parameters: 1
- project/units: 1
- results/export_3d: 1
- results/result_template: 1
- solver/eigenmode_solver: 1

## Key Recipe Findings

- Solver type: `eigenmode`
- Solver confidence: `0.95`
- Ports: 1
- Global mesh present: True
- Global boundary present: True
- Monitors: 1
- Result exports/postprocessing: 2

## Geometry History Summary

- Geometry command count: 2
- Imported geometry: ['baseline_cavity.step']
- Final components (best effort): ['vacuum']
- Final solids (best effort): ['rf_vacuum']

## Unknown Or Unclassified Commands

- None.

## Review Guidance

- Treat this report as a recipe-extraction aid, not as a CST macro validator.
- Review `source_history_indices` in JSON outputs before promoting settings into CSTTranslator.
- Unknown commands are preserved for manual inspection instead of being dropped.
