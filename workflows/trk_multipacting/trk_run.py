"""Serial, fixed-mesh TRK source/field sweep using a private persistent CST session.

Numeric external-field setters intentionally avoid StoreParameter/history replay.
Applied factor and phase are recorded per case; the scratch project's parameter
table remains the original template table. No geometry rebuild or result deletion.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
import xml.etree.ElementTree as ET
from typing import Any

import numpy as np
import psutil
from .model import Task
from .trk_model import tasks, logical_grid, combined_sey, log_statistics, population
from cst_optimization.core.session_cleanup import close_owned_session


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(tmp, path)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def mesh_identity(project: Path) -> dict[str, str]:
    """Fingerprint full volume mesh plus imported RF field cache, not just counts."""
    base = project.with_suffix('')
    names = ['Result/3d.slim', 'Result/topot.tet', 'Result/moegeom.tet',
             'Result/Mesh_Output.QuasiModel.tet', 'Model/3D/extfield_0.c3c']
    return {name: digest(base/name) for name in names}


def configure_macro(snapshot: dict[str, Any], task: Task) -> str:
    """Use template RF normalization 0.618*factor1 and phase in degrees."""
    field = snapshot['field_macro'].replace('"0.618*factor1"', f'"{.618*task.factor1:.12g}"')
    field = field.replace('"phase"', f'"{task.phase}"')
    field = field.replace('.UseLocalCopyOnly "False"', '.UseLocalCopyOnly "True"')
    track = snapshot['tracking_macro']
    track = re.sub(r'\.AddTrackingSource "Particle", "particle\d+"',
                   f'.AddTrackingSource "Particle", "{task.source}"', track)
    return 'Sub Main\n'+field+'\n'+track+'\nEnd Sub'


def lifetime_macro(output: Path) -> str:
    """Official ParticleTrajectoryReader API, already verified against MP4."""
    return f'''Sub Main
Dim n As Long
Dim ts() As Single, qs() As Single
Dim ids() As Long, src() As Long
ParticleTrajectoryReader.Reset
ParticleTrajectoryReader.LoadTrajectoryData
Open "{output}" For Output As #1
Print #1, "trajectory_index particle_id emission_id birth_ns end_ns first_macrocharge_C last_macrocharge_C stored_points"
For n = 0 To ParticleTrajectoryReader.GetNTrajectories()-1
 ParticleTrajectoryReader.SelectTrajectory n
 ts = ParticleTrajectoryReader.GetQuantityValues("Time", "")
 qs = ParticleTrajectoryReader.GetMacroCharges()
 ids = ParticleTrajectoryReader.GetParticleIDs()
 src = ParticleTrajectoryReader.GetEmissionIDs()
 Print #1, n; " "; ids(LBound(ids)); " "; src(LBound(src)); " "; ts(LBound(ts)); " "; ts(UBound(ts)); " "; qs(LBound(qs)); " "; qs(UBound(qs)); " "; UBound(ts)-LBound(ts)+1
Next n
Close #1
ParticleTrajectoryReader.Reset
End Sub'''


def generation_lifetime_macro(output: Path, generations: Path) -> str:
    """One Model3D VBA pass for endpoint records plus SEE generation (LongArray)."""
    macro = lifetime_macro(output).replace('Dim n As Long', 'Dim n As Long\nDim gs As Variant')
    macro = macro.replace('For n = 0 To', f'Open "{generations}" For Output As #2\nPrint #2, "index generation"\nFor n = 0 To')
    return macro.replace('Next n', 'gs = ParticleTrajectoryReader.GetQuantityValues("SEEGeneration", "")\nPrint #2,n;" ";gs(LBound(gs))\nNext n').replace('Close #1', 'Close #1\nClose #2')


def export_curves(project: Path) -> dict[str, Any]:
    from cst_optimization.core.results import ResultReader
    r = ResultReader(str(project), allow_interactive=True)
    curves = {}
    for path in r.list_tree_items():
        if path.startswith('1D Results') and ('Information\\' in path or 'Particle Sources\\' in path):
            item = r.get_result_item(path)
            curves[path] = dict(x=np.atleast_1d(np.asarray(item.get_xdata(), float)).tolist(),
                               y=np.atleast_1d(np.asarray(item.get_ydata(), float)).tolist(),
                               xlabel=item.xlabel, ylabel=item.ylabel)
    r.invalidate_cache()
    return curves


def validate_source_currents(active: list[str], expected: str, text: str, requested_abort: bool) -> str:
    """Aborted CST runs omit the source iteration curve but retain source statistics.

    Only a recorded native abort with exactly the expected statistics source may
    use this fallback. Generation, total currents and seed/track counts are still
    independently checked by log_statistics, population and event_windows.
    """
    if active == [expected]:
        return 'source_current_curve'
    if (not active and requested_abort and 'Particle Tracking Solver has been aborted.' in text
            and re.findall(r'Statistics for particle source (particle\d+):',text)==[expected]):
        return 'native_abort_source_statistics'
    raise ValueError(f'Unexpected nonzero source currents: {active}')


def analyze_case(directory: Path, task: Task, timing: dict[str, float]) -> dict[str, Any]:
    curves = json.loads((directory/'raw_curves.json').read_text())
    text = (directory/'Model.log').read_text(errors='replace')
    stats = log_statistics(text, task.source)
    active = [p.rsplit('\\', 1)[1] for p, c in curves.items()
              if p.startswith('1D Results\\Particle Sources\\Current vs. Iteration\\')
              and np.any(np.asarray(c['y']) != 0)]
    source_validation=validate_source_currents(active,task.source,text,(directory/'abort_request.json').exists())
    try:
        sey = combined_sey(curves, strict_currents=False)
        a = np.loadtxt(directory/'trajectory_lifetimes.txt', skiprows=1)
        array, pop = population(a, stats)
        np.savetxt(directory/'particle_number_vs_time.csv', array, delimiter=',',
                   header='time_ns,recorded_alive_trajectories,sum_abs_stored_macrocharge_C', comments='')
        write_json(directory/'combined_sey.json', sey)
        record = dict(task.record(), status='completed', completed_utc=utc(), **timing,
                      combined_sey=sey['combined_sey'], statistical_warnings=sey['statistical_warnings'], source_validation=source_validation, **stats, **pop)
        if (directory/'trajectory_generations.txt').exists():
            from .trk_late import event_windows, save_windows
            frequency = float(ET.parse(directory/'field_import_0_0.rex').getroot().find('SimulationProperties').attrib['frequency'])
            late = event_windows(a, np.loadtxt(directory/'trajectory_generations.txt',skiprows=1),
                                 stats, curves, frequency, width_rf=3, strict_currents=False)
            save_windows(directory, late)
            record.update(late_3RF_sey=late['final_window']['sey'] if late['final_window'] else None,
                          late_3RF_sey_lower=late['final_window'].get('sey_lower') if late['final_window'] else None,
                          late_3RF_sey_upper=late['final_window'].get('sey_upper') if late['final_window'] else None,
                          late_window_rf=3, late_window_complete=late['window_complete'],
                          statistical_warnings=sey['statistical_warnings']+late['statistical_warnings'], current_check_policy='advisory')
    except (ValueError, ArithmeticError) as exc:
        # Raw files already saved; a scientific reduction issue must not stop scanning.
        # No synthetic SEY or population is inserted when the calculation is undefined.
        write_json(directory/'analysis_error.json',dict(error=repr(exc),utc=utc(),action='retain_raw_continue'))
        record=dict(task.record(),status='analysis_unavailable',completed_utc=utc(),
                    **timing,**stats,combined_sey=None,late_3RF_sey=None,
                    source_validation=source_validation,analysis_error=repr(exc))
    request_path=directory/'abort_request.json'
    if request_path.exists():
        request=json.loads(request_path.read_text())
        timer=json.loads((directory/'solve_timer.json').read_text())
        if request.get('key') != task.key or request.get('owner') != timer.get('owner'):
            raise ValueError('Abort request does not belong to this solve')
        aborted='Particle Tracking Solver has been aborted.' in text
        record.update(status=record['status'] if record['status']=='analysis_unavailable' else ('aborted_saved' if aborted else 'completed'),
                      native_aborted=aborted, abort_reason=request['reason'],
                      partial_record_warning='The particle data may be incomplete or inaccurate.' in text)
    write_json(directory/'result.json', record)
    return record


def completed(root: Path) -> dict[str, Any]:
    return {p.parent.name: json.loads(p.read_text()) for p in (root/'cases').glob('*/result.json')}


def timed_out(root: Path) -> set[str]:
    """Durable time-limit outcomes are not successful scientific observations."""
    return {p.parent.name for p in (root/'cases').glob('*/timeout.json')
            if json.loads(p.read_text()).get('status') == 'solve_time_limit'}


def summary(root: Path) -> None:
    rows = list(completed(root).values())
    if not rows:
        return
    keys = sorted(set().union(*(r.keys() for r in rows)))
    tmp = root/'summary.csv.tmp'
    with tmp.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader(); writer.writerows(rows)
    os.replace(tmp, root/'summary.csv')


def prepare(root: Path, template: Path) -> dict[str, Any]:
    """Freeze source/history and copy its existing mesh without changing the original."""
    snapshot_path = root/'snapshot.json'
    if snapshot_path.exists():
        return json.loads(snapshot_path.read_text())
    history = json.loads((template.with_suffix('')/'Model/3D/ModelHistory.json').read_text())['history']
    field = '\n'.join([b for b in history if b['caption']=='predefined external field settings'][-1]['code'])
    track = '\n'.join([b for b in history if b['caption']=='define tracking solver parameters'][-1]['code'])
    track = '\n'.join(l for l in track.splitlines() if not l.strip().startswith('Mesh.'))
    step_match = re.search(r'\.MaxTimeSteps "(\d+)"', track)
    if ('"0.618*factor1"' not in field or '"phase"' not in field or not step_match
            or int(step_match.group(1)) <= 0 or '.Method "Tetrahedral"' not in track):
        raise ValueError('Template lacks accepted RF expressions or positive TET tracking steps')
    sources = {f'particle{i}': [b for b in history if b['caption']==f'define particle source: particle{i}'][-1]
               for i in range(1,5)}
    original_hash = digest(template)
    identity = mesh_identity(template)
    project = root/'working'/template.name; project.parent.mkdir(parents=True, exist_ok=True)
    if project.exists() or project.with_suffix('').exists():
        raise RuntimeError('Incomplete preparation exists; preserve it for review')
    shutil.copy2(template, project)
    shutil.copytree(template.with_suffix(''), project.with_suffix(''), ignore=shutil.ignore_patterns('*.lok', '*.lock'))
    if digest(template) != original_hash or mesh_identity(template) != identity or mesh_identity(project) != identity:
        raise RuntimeError('Template changed during snapshot')
    snapshot = dict(template=str(template), template_sha256=original_hash, created_utc=utc(),
                    mesh=identity, field_macro=field, tracking_macro=track, sources=sources,
                    max_steps=int(step_match.group(1)),
                    project=str(project), actual_count=len(tasks()), logical_count=len(logical_grid()),
                    parameter_policy='Numerical field setters; template parameter table deliberately unchanged to preserve mesh',
                    code={p.name:digest(p) for p in [Path(__file__), Path(__file__).with_name('trk_model.py')]})
    write_json(root/'logical_grid.json', logical_grid())
    write_json(snapshot_path, snapshot)
    return snapshot


def run(root: Path, template: Path, selected: list[str] | None = None, limit: int | None = None,
        cst_library: str = '',
        solve_limit_s: float = 600, abort_grace_s: float = 180) -> None:
    """One private CST session; STOP is honored between complete cases."""
    if not np.isfinite(abort_grace_s) or abort_grace_s <= 0:
        raise ValueError('Abort grace must be finite and positive')
    if not np.isfinite(solve_limit_s) or solve_limit_s <= 0:
        raise ValueError('Solve limit must be finite and positive')
    root.mkdir(parents=True, exist_ok=True)
    lock = root/'RUNNING.json'
    owner = dict(pid=os.getpid(), created=psutil.Process().create_time(), utc=utc())
    with lock.open('x', encoding='utf-8') as f:
        json.dump(owner, f)
    connection = project = None
    session = None
    status = 'failed'
    try:
        selection = json.loads((root/'selection.json').read_text()) if (root/'selection.json').exists() else None
        if selection:
            if selected is not None and list(selected) != selection['keys']:
                raise ValueError('Selected keys differ from frozen selection')
            selected = selection['keys']
        snapshot = prepare(root, template)
        work = Path(snapshot['project'])
        done = completed(root)
        skipped = timed_out(root)
        queue = [t for t in tasks() if t.key not in done and t.key not in skipped and (selected is None or t.key in selected)]
        if selected and set(selected)-{t.key for t in tasks()}:
            raise ValueError('Unknown case key')
        if limit is not None:
            queue = queue[:limit]
        if queue and not (root/'STOP').exists():
            from cst_optimization.core.connection import CSTConnection
            connection = CSTConnection(cst_library, mode='new')
            connection.connect(); connection.set_quiet_mode(True)
            session = (connection.pid, psutil.Process(connection.pid).create_time())
            write_json(root/'owner.json', dict(owner, cst_pid=session[0], cst_created=session[1]))
            project = connection.open_project(str(work))
            for task in queue:
                if (root/'STOP').exists():
                    break
                directory = root/'cases'/task.key; directory.mkdir(parents=True, exist_ok=True)
                write_json(root/'state.json', dict(status='running', current=task.record(), completed=len(done),
                                                  total=len(tasks()), utc=utc(), owner=owner))
                if mesh_identity(work) != snapshot['mesh']:
                    raise RuntimeError('Mesh or imported field cache changed before dispatch')
                mesh_log = work.with_suffix('')/'Result/log.tet'
                mesh_stat = (mesh_log.stat().st_mtime_ns, digest(mesh_log)) if mesh_log.exists() else None
                macro = configure_macro(snapshot, task)
                (directory/'settings.bas').write_text(macro, encoding='utf-8')
                write_json(directory/'task.json', dict(task.record(), external_field_scale=.618*task.factor1,
                                                      external_phase_deg=task.phase, started_utc=utc()))
                started = time.perf_counter()
                project.project.schematic.execute_vba_code(macro, timeout=120)
                solve_started = time.time_ns()
                t = time.perf_counter()
                # Cross-process monotonic wall clock: solver launch through solver
                # post-processing, excluding geometry setup and our result export.
                timer = dict(key=task.key, owner=owner, started_monotonic=time.monotonic(),
                             limit_s=solve_limit_s, finished=False, utc=utc(),
                             stop_policy='native_abort_then_collect', abort_grace_s=abort_grace_s)
                write_json(directory/'solve_timer.json', timer)
                try:
                    project.model3d.run_solver(timeout=int(np.ceil(solve_limit_s+abort_grace_s))+30)
                except Exception as exc:
                    write_json(directory/'solver_call_error.json',dict(error=repr(exc),utc=utc()))
                    request_path=directory/'abort_request.json'
                    request=json.loads(request_path.read_text()) if request_path.exists() else {}
                    text=(work.with_suffix('')/'Result/Model.log').read_text(errors='replace')
                    if (request.get('owner')!=owner or request.get('key')!=task.key
                            or 'Particle Tracking Solver has been aborted.' not in text
                            or 'Particle Tracking Solver successful.' not in text
                            or project.model3d.is_solver_running(timeout=15)):
                        raise
                    # An expected native abort can raise while valid partial results exist.
                    # Full current, generation and endpoint validation still follows below.
                write_json(directory/'solve_timer.json', dict(timer, finished=True))
                solve_s = time.perf_counter()-t
                logfile = work.with_suffix('')/'Result/Model.log'
                if logfile.stat().st_mtime_ns < solve_started:
                    raise RuntimeError('No fresh solve log')
                shutil.copy2(logfile, directory/'Model.log')
                log_statistics(logfile.read_text(errors='replace'), task.source)
                after_mesh_log = (mesh_log.stat().st_mtime_ns, digest(mesh_log)) if mesh_log.exists() else None
                verification = dict(identity=mesh_identity(work), expected=snapshot['mesh'],
                                    mesh_log_unchanged=mesh_stat == after_mesh_log)
                write_json(directory/'mesh_verification.json', verification)
                if verification['identity'] != snapshot['mesh'] or not verification['mesh_log_unchanged']:
                    raise RuntimeError('Fixed mesh or mesh reuse verification failed')
                if not project.save(include_results=True):
                    raise RuntimeError('Could not save private project results')
                write_json(directory/'raw_curves.json', export_curves(work))
                shutil.copy2(work.with_suffix('')/'Result/field_import_0_0.rex', directory/'field_import_0_0.rex')
                macro = generation_lifetime_macro(directory/'trajectory_lifetimes.txt', directory/'trajectory_generations.txt')
                # Installed CST post_processing/s_parameters.py uses this executor;
                # matched endpoint+generation export validated on MP5/MP6 copies.
                project.project.model3d._execute_vba_code(macro)
                rec = analyze_case(directory, task, dict(solve_s=solve_s, case_s=time.perf_counter()-started))
                done[task.key] = rec
                summary(root)
                if selection:
                    from .trk_late import selected_report
                    selected_report(root)
                print(json.dumps({k:rec[k] for k in ['key','combined_sey','final','solve_s','case_s']}), flush=True)
                if (directory/'abort_request.json').exists():
                    break  # Close this saved session before dispatching another case.
        status = 'paused' if (root/'STOP').exists() else ('complete' if len(completed(root))==len(tasks()) else 'batch_complete')
    except Exception as exc:
        write_json(root/'failure.json', dict(error=repr(exc), utc=utc()))
        raise
    finally:
        try:
            if project is not None:
                project.project.close()
            if connection is not None and session is not None:
                write_json(root/'cleanup.json', close_owned_session(connection, *session))
        except Exception as exc:
            status='cleanup_failed'
            write_json(root/'cleanup_failed.json', dict(error=repr(exc), utc=utc()))
        write_json(root/'state.json', dict(status=status, completed=len(completed(root)), total=len(tasks()), utc=utc()))
        if lock.exists() and json.loads(lock.read_text()) == owner:
            lock.unlink()  # Only the lock created by this invocation; never remove stale owners.


def main() -> None:
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--solve-limit-seconds', type=float, default=600)
    parser.add_argument('--cst-library', required=True)
    parser.add_argument('--abort-grace-seconds', type=float, default=180)
    args=parser.parse_args()
    run(args.root, args.template, args.cases, args.limit, args.cst_library, args.solve_limit_seconds, args.abort_grace_seconds)


if __name__ == '__main__':
    main()
