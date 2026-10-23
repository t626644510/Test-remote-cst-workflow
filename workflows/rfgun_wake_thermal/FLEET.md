# WF6 two-station execution

Use `run_workflow_6_fleet.py`. The existing serial CLI remains available for
serial rounds; never run both coordinators against one journal. The same OS
coordinator lock enforces this. Each station has one persistent worker and its
own local projects. Only the developer station writes campaign state/SQLite or
fits GPs. Scientific reconstruction, acceptance thresholds, and GP noise rules
are unchanged.

## Failure and identity rules

- Each parameter / port / stage combination may be attempted once per station.
  Remote definitive failure queues a local attempt before ordinary local work.
  Local definitive failure likewise queues the remote station. Each attempt has
  a separate job ID, original errors, elapsed seconds and retained artifacts.
- Candidate failure and bounded port repair are considered only after both
  stations failed that combination. Only the existing explicit port-mesh error
  enables repair; changed ports invalidate the complete wake trio as before.
- Disconnect, stale heartbeat, live/unknown prior session, cleanup/ownership
  failure, and digest mismatch are diagnostic states, not transferable failures.
  Preserve pending ownership. Never dispatch a duplicate because SSH timed out.
- A worker durably claims a task before execution. Restart with saved completion
  permits extraction only; restart without saved completion preserves an
  interrupted failure and never silently repeats the same solve. One automatic
  extraction-only retry is allowed for a saved, fingerprinted completion.
- The cross-station execution hash covers all WF6/shared-core Python sources,
  both entry points, all scientific/search settings, all four complete template
  manifests, CST Python SDK and numpy/scipy/scikit-learn versions. Paths differ;
  numerical identities must match. Central replay checks task, raw manifest and
  saved-solve identities. Remote native project references include host names.

## Budget and operation

The round is 48 hours of active elapsed time, not 48 hours per station. Parallel
station effort is a separate `node_seconds` ledger. Cross-gate exploration keeps
its existing wall-time definition; concurrent gated jobs share that interval.
At the cap or STOP, admit no new stages and drain both stations, including result
transfer and reconstruction. An unknown remote task remains pending until its
state is established. No next round starts automatically. Paused idle is not
charged. After coordinator downtime, an unresolved reservation conservatively
keeps its elapsed interval charged; a paused empty campaign does not.

Tasks expire for *admission* after at most 90 seconds or at the round deadline.
Expiry before start is not a solver failure and may be requeued. Already claimed
stages finish under the existing non-budget safety watchdog. The repair clock
remains candidate-wide, including station attempts.

`migrate --config CONFIG --nodes NODES` requires a quiescent paused serial journal
and saves the old state, database, checkpoint, owner/config and source snapshot.
Existing stage evidence and round budget remain. Incomplete historical failures
are preserved and queued for a fresh remote/local cycle; saved-postprocessing
failures remain held for extraction review. Migration maintenance is charged once.
The legacy scientific contract remains, with an additional recursive fleet
execution contract; serial resume must not bypass the fleet gate.

`worker --config CONFIG --root ROOT --node NAME` runs inside the logged-in Windows
interactive session (use a dedicated WF6 scheduled task, never WF5's registration).
`coordinator --config CONFIG --nodes NODES` runs on the developer station only.
`inspect --root ROOT` is read-only and does not connect to CST. SSH/SFTP must use
pinned keys. Root paths and Python/config/repository paths are in an ignored local
nodes JSON, never in committed source. Worker STOP is sticky; explicitly clear
it only for an authorized verified resume. Keep the code immutable while running.

## Hourly monitoring and diagnostics

Read the handoff's current paths, fleet state/report/heartbeat, `pending_nodes`,
`fleet_retry`, node seconds, and both station status/heartbeat files. Remote
inspection uses the configured SSH alias and `inspect`; actual owned process
checks use PID + creation time + command line + parent edge (child born later).
Check current task, solve_started, worker result, Model.log/MCalc.log and CPU
increments on each host. A static port table by itself is not a hang. Verify
parameter/port identity, raw/analysis manifests, duplicate reservations, stage
age/watchdogs and local/remote disk space. Below 20 GiB, station admission stops.
Native projects remain on their station; this initial fleet implementation never
automatically deletes them. Any authorized later retention must preserve best,
permanent numerical evidence, backups and previous rounds and verify ownership
and the permanent raw manifest before deleting only that job's native project.

Report the first clear new fault. Repeated unchanged faults permit the previously
authorized safe diagnosis/fix/validation; never treat a network loss or scientific
uncertainty as permission to repeat a solve. Both stations must be quiescent before
code/config migration. At closure report screening estimates separately from
formal feasibility, missing/uncertain evidence, elapsed and machine hours, then
pause the monitor pending user audit. Stay quiet otherwise.
