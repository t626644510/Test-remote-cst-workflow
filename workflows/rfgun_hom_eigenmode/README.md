# Workflow 4 — HOM Eigenmode

Workflow 4 batches CST eigenmode solves around measured suspicious-HOM
frequencies and performs all transverse coupling calculations offline.

```powershell
.\.venv\Scripts\python.exe run_workflow_4.py --plan-only
.\.venv\Scripts\python.exe run_workflow_4.py --audit-results
.\.venv\Scripts\python.exe run_workflow_4.py --window-id WIN_0001
.\.venv\Scripts\python.exe run_workflow_4.py --resume-preview
.\.venv\Scripts\python.exe run_workflow_4.py --resume
.\.venv\Scripts\python.exe run_workflow_4.py --resume --window-id WIN_0004 --force-retry
.\.venv\Scripts\python.exe run_workflow_4.py --template-migration-preview
.\.venv\Scripts\python.exe run_workflow_4.py --adopt-template-revision --template-change-note "disable adaptive meshing"
.\.venv\Scripts\python.exe run_workflow_4.py --offline-only D:\Results\workflow4\hom_campaign_...
```

The input CSV and source CST template are read-only.  Every live run uses a
campaign-owned template copy.  Exact result-tree paths and field-export
filenames are configured in `config.yaml`; audit them after every material
template change.

Each solver attempt owns an independent CST project copied from the immutable
template.  Fast pre-mesh failures may use four clean attempts; once a mesh or
mode table exists, a window is limited to two long attempts across resumes.
Warnings about unconsidered propagating port modes are recorded as
`boundary_sensitive` but do not automatically invalidate derived quantities.
The flag is sticky across duplicate modes from overlapping windows. Missing
propagating channels can under-estimate leakage and over-estimate Q; reflected
power can also shift frequency, field shape, and polarization, so the bias is
not guaranteed to be one-directional. In the audited template, port 1 warned
from the lowest band and ports 4/5/6 from about 1.5 GHz. In particular,
2.7--3.0 GHz loaded/external/radiated Q values remain diagnostic rather than
final impedance evidence.

Changing the template is never accepted by ordinary `--resume`. Use the
read-only migration preview first, then explicitly adopt the new revision.
Successful old-template windows remain traceable and long-related failed
windows receive fresh retry budgets; purely fast-failed windows remain
avoided. Every new attempt and result row records its template revision/hash.

Workflow 4 owns dedicated `mode="new"` CST processes. After explicitly saving
and closing a project, it terminates only the recorded process tree and
verifies that PID exited. It never uses a machine-wide CST process sweep. A
failed PID verification stops the campaign as `cleanup_incomplete`.

Migration-preview ETA values deliberately retain the old frequency-band
estimator and are conservative after solver/mesh changes. Recalibrate runtime
after one low-frequency and one high-frequency live smoke window.
