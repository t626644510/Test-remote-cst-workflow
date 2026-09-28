# WF5 asynchronous distinct-candidate execution

The coordinator chooses different geometries for machine-local workers and
merges their completed observations into one GP. A worker runs the existing
`CSTEvaluator`, `CSTConnection`, `CSTProject`, `SolverRunner` and `ResultReader`.
No new CST API calls or alternate impedance formula are introduced.

## Configuration and launch

Use `run_workflow_5_async.py`. Each node has its own ordinary WF5 YAML, with
identical numerical/search settings and different `paths` entries. Keep node
configs and cluster JSON outside Git. A portable cluster JSON example is:

```json
{
  "nodes": [
    {
      "name": "local",
      "root": "D:/simulation/run/local_worker",
      "config": "D:/simulation/run/config.local.yaml",
      "python": "C:/simulation/.venv/Scripts/python.exe",
      "repository": "C:/simulation/repository"
    },
    {
      "name": "remote",
      "root": "D:/simulation/worker",
      "config": "D:/simulation/config.local.yaml",
      "python": "D:/simulation/.venv/Scripts/python.exe",
      "repository": "D:/simulation/repository",
      "ssh_config": "C:/simulation/worker.ssh.conf",
      "ssh_host": "configured-worker-alias"
    }
  ]
}
```

On each workstation, launch a persistent worker in the logged-in Windows
desktop session. An interactive scheduled task can keep it independent of SSH.
One worker owns a local lock and evaluates one candidate at a time:

```powershell
python run_workflow_5_async.py worker --config CONFIG --root WORKER_ROOT
```

Import a stopped serial campaign into a fresh coordinator output directory:

```powershell
python run_workflow_5_async.py coordinator --config CONFIG --cluster CLUSTER --import-serial OLD_ROOT --original-identity ORIGINAL_CONTRACT_JSON --prior-solves N --import-only
python run_workflow_5_async.py coordinator --config CONFIG --cluster CLUSTER --resume
```

`ORIGINAL_CONTRACT_JSON` contains the exact original configuration, template
manifest and code digests whose combined fingerprint matches the serial journal.
Import refuses active CST sessions, changed scientific settings, missing raw
fields, or unreproducible valid scores. The global budget must equal the old
campaign limit plus `N` earlier solves; the imported consumed count is increased
by the same `N`, so remaining capacity cannot be reset. Existing projects and
records remain in the frozen source campaign. This is an explicit schema
migration, not a generic fingerprint override.

## Protocol and stopping

- Workers use local disks, not an SMB-hosted project or shared SQLite file.
- Template contents, all workflow/shared source bytes, numerical library
  versions and CST Python SDK source must match. Paths are excluded from the
  cross-machine scientific identity; coordinator endpoint mapping is frozen.
- Coordinator state, database and checkpoints have a single writer. Worker
  inbox tasks, requests and grants are immutable, idempotent JSON messages.
- Every call to the existing evaluator's `reserve` callback creates a fresh
  request. The coordinator atomically persists both the increment and reply
  before sending permission. A lost reply is replayed without incrementing.
  An uncertain start is charged conservatively and never silently refunded.
- Geometry/save failures before `reserve` consume no CST solver call. Coverage
  searches or transient retries request another slot and cannot exceed the cap.
- In-flight geometries participate in deduplication but never GP fitting. The
  existing normalized GP/EI planner is reused, preferring points at least 0.05
  normalized Euclidean distance from an in-flight point when feasible.
- Results are accepted as they arrive. Beam fields, stored energy and sampling
  settings are replayed centrally. Cross-CPU rounding tolerance is 1e-8 relative,
  far below the scientific extraction tolerances; accepted objectives use the
  central replay. No low-Q/linewidth guard is reintroduced under `largest_two`.
- A valid threshold pass immediately stops new dispatch/grants. Already
  permitted work drains (at most one other candidate with two workers). Unknown
  disconnected work remains in flight instead of being duplicated.
- Raw proof bundles return first. Native 3D results stay on their source node.
  At campaign completion, a remote best native project is archived, checked and
  downloaded to `best_native/`; the best record then points to that local copy.

## Pause, recovery and inspection

Create a `PAUSE` file in the coordinator output directory to stop new dispatch
and drain current work. Worker `STOP` files request exit after the current task.
Neither operation kills arbitrary CST processes. To resume a paused run, remove
only these workflow-owned request files, restart stopped workers, and use the
coordinator's `--resume` command. A crashed coordinator can resume while workers
continue; journaled grants, task IDs, RNG state and observations are retained.

`inspect --root WORKER_ROOT` returns a compact worker heartbeat, active phases,
CST log tails, pending permit requests and outcomes without importing CST.
The live coordinator `state.json` exposes both nodes, their jobs and contact
state. An unreachable node does not automatically imply a failed simulation.

On missing-field postprocessing failure, the worker enters `needs_attention`.
Stop that worker with its owned `STOP` file and verify it exits, then run:

```powershell
python run_workflow_5_async.py recover-postprocess --root WORKER_ROOT --task-id TASK_ID
```

This command requires the worker lock, verified inactive sessions and a valid
saved solve. It archives the failed outcome and requeues only postprocessing;
restart the worker and resume the coordinator if it stopped. The existing
evaluator consumes no new solve for this recovery. Other cleanup/ownership
failures require diagnosis and are never automatically retried.

## Validation

No-CST tests cover distinct jobs, pending-point exclusion, global 40-call budget,
lost grant replies, disconnect persistence, immutable messages, successful-point
early stop, wrong contracts, path traversal, raw field replay and tampering.
Run the entire branch-local suite with the repository `.venv` Python. Live CST
validation is separate and uses a new candidate on each workstation, never a
duplicate baseline or additional mesh refinement solve.
