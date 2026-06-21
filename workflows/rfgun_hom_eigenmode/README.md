# Workflow 4 — HOM Eigenmode

Workflow 4 batches CST eigenmode solves around measured suspicious-HOM
frequencies and performs all transverse coupling calculations offline.

```powershell
.\.venv\Scripts\python.exe run_workflow_4.py --plan-only
.\.venv\Scripts\python.exe run_workflow_4.py --audit-results
.\.venv\Scripts\python.exe run_workflow_4.py --window-id WIN_0001
.\.venv\Scripts\python.exe run_workflow_4.py --resume
.\.venv\Scripts\python.exe run_workflow_4.py --offline-only D:\Results\workflow4\hom_campaign_...
```

The input CSV and source CST template are read-only.  Every live run uses a
campaign-owned template copy.  Exact result-tree paths and field-export
filenames are configured in `config.yaml`; audit them after every material
template change.
