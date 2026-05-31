# Phase 02 -- Workflow 1 Scaffold

## Summary

Created the directory skeleton for the extracted Workflow 1 package and
fixed encoding garbled characters in the Phase 1 inventory report.  No
runtime behaviour was changed.

## Files changed

| File | Action | Status |
|---|---|---|
| `workflows/rfgun_single_pass/__init__.py` | Created | New |
| `workflows/rfgun_single_pass/README.md` | Created | New |
| `workflows/rfgun_single_pass/BRANCH_CONTEXT.md` | Created | New |
| `reports/workflow1_split/phase_02_scaffold.md` | Created | New |
| `reports/workflow1_split/phase_01_inventory.md` | Fixed | Encoding fix |

### Encoding fixes in phase_01_inventory.md

The Phase 01 report contained visible encoding artifacts from Unicode
characters that re-encoded as garbled text during a UTF-8 to GBK
round-trip:

- Garbled em dash (displayed as two garbled CJK characters) replaced
  with ASCII ` - `
- Garbled multiplication sign (displayed as CJK character) replaced
  with ASCII `x`

These are cosmetic only.  All technical conclusions are unchanged.

## Behaviour changes

**None.**  The `workflows/rfgun_single_pass/` package is an empty
skeleton with no imported modules and no runtime side effects.
`run_workflow_1.py` still runs from the project root using the shared
`cst_optimization` package.

## Backward compatibility

- `run_workflow_1.py` -- identical behaviour.
- `run_workflow_2.py` / `run_workflow_3.py` -- untouched.
- `src/cst_optimization/` -- untouched.
- `config/default.yaml` -- untouched.

## Tests run

```powershell
python -m compileall src workflows run_workflow_1.py
```

### Real terminal output

```
Listing 'C:\Users\...\src'...
Listing 'C:\Users\...\src\cst_optimization'...
Listing 'C:\Users\...\src\cst_optimization\core'...
Listing 'C:\Users\...\src\cst_optimization\objectives'...
Listing 'C:\Users\...\src\cst_optimization\optimization'...
Listing 'C:\Users\...\src\cst_optimization\parameters'...
Listing 'C:\Users\...\src\cst_optimization\physics'...
Listing 'C:\Users\...\src\cst_optimization\sensitivity'...
Listing 'C:\Users\...\src\cst_optimization\utils'...
Listing 'C:\Users\...\src\cst_optimization\workflows'...
Listing 'C:\Users\...\workflows'...
Listing 'C:\Users\...\workflows\rfgun_single_pass'...
```

Exit code: **0** (all files compile clean; the new `__init__.py` at
`workflows/rfgun_single_pass/` compiled without errors).

## Remaining non-ASCII characters in phase_01_inventory.md

Only U+2192 (rightwards arrow) remains in the config-key table where it
is used intentionally as a visual separator (e.g. `key -> description`).
This character is standard UTF-8 and renders correctly in all modern
editors.

## Risks

None at this phase -- the skeleton is entirely inert.  The encoding
fixes to Phase 1 report are cosmetic and do not alter the technical
content of the dependency inventory.

## Next recommended phase

**Phase 3: Runner migration.**  Create an entry point inside
`workflows/rfgun_single_pass/` (e.g. `run.py`) that delegates to the
same `build_workflow_1()` and `opt.optimize()` path currently in
`run_workflow_1.py`.  The root `run_workflow_1.py` can then become a
thin wrapper that imports from the new package.
