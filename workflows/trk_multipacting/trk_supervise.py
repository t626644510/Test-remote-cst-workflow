"""Process-isolated TRK initialization watchdog and bounded session recycling.

The scientific worker is unchanged: preserve mesh, RF field, SEY model and template
step limit. CST sessions are recycled after a configurable batch (default 32 cases). Only an idle,
unchanged *pre-tracking* initialization may be interrupted; long tracking and
post-processing are not classified as initialization stalls. A separate hard
wall-clock solve limit requests native abort; 180 s additional grace permits
result flushing. Only an unresponsive session is force-stopped after that grace. Timed-out points are retained as incomplete, not classified as MP.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import psutil

from .trk_run import completed, timed_out, digest, mesh_identity, utc, write_json
from .trk_model import tasks
from .trk_late import selected_report


def read_json(path: Path) -> dict[str, Any]:
    """Read atomic worker records, tolerating only an absent record."""
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def initialization_stalled(text: str, log_age: float, elapsed: float,
                           cpu_span: float, cpu_delta: float, idle_s: float) -> bool:
    """Seconds and cumulative solver CPU seconds; never infer a tracking timeout."""
    return (elapsed >= idle_s and log_age >= idle_s and cpu_span >= 60
            and 0 <= cpu_delta < 1.0 and ('Pure tracking mode' in text
                or ('Initializing' in text and 'Using TET mesh' in text))
            and not any(x in text for x in ('Running field solver', 'Running time loop',
                                           'Tracking solver finished', 'Solver successful')))


def native_initialization_failure(text: str) -> bool:
    """An explicit native failure before tracking; not an analysis/SEY rejection."""
    return ('Initializing' in text and 'Terminated abnormally' in text
            and not any(x in text for x in ('Running field solver','Running time loop',
                                           'Tracking solver finished')))


def recoverable_native_failure(text: str, error: str) -> bool:
    """Retry an unfinished native solve, never a completed solve or analysis failure.

    A CST run_solver connection loss can precede the log's Initializing marker.
    The caller still requires a fresh log, one unfinished case and verified cleanup.
    """
    if any(marker in text.lower() for marker in
           ('tracking solver finished', 'solver successful')):
        return False
    return native_initialization_failure(text) or (
        'run_solver' in error and 'Connection has been closed' in error)


def solve_deadline_reached(timer: dict[str, Any], owner: dict[str, Any],
                           key: str | None, now: float) -> bool:
    """Monotonic seconds; ignore stale workers, finished solves and invalid clocks."""
    started, limit = timer.get('started_monotonic'), timer.get('limit_s')
    return bool(key and timer.get('key') == key and timer.get('owner') == owner
                and timer.get('finished') is False
                and isinstance(started, (int, float)) and math.isfinite(started)
                and isinstance(limit, (int, float)) and math.isfinite(limit) and limit > 0
                and now >= started and now-started >= limit)


def identity(process: psutil.Process) -> dict[str, Any]:
    """Capture PID, birth time, edge and command before any termination."""
    return dict(pid=process.pid, created=process.create_time(), parent=process.ppid(),
                name=process.name(), command=process.cmdline(),
                cpu_s=sum(process.cpu_times()[:2]))


def matches(record: dict[str, Any]) -> bool:
    try:
        return psutil.Process(record['pid']).create_time() == record['created']
    except psutil.NoSuchProcess:
        return False


def owned_tree(anchor: dict[str, Any]) -> list[dict[str, Any]]:
    """Discover descendants only through valid, birth-ordered current edges."""
    if not matches(anchor):
        return []
    try:
        root = psutil.Process(anchor['pid'])
        rows = [identity(root)]
    except psutil.NoSuchProcess:
        return []
    pending = [root]
    while pending:
        parent = pending.pop(0)
        try:
            children = parent.children()
        except psutil.NoSuchProcess:
            continue
        for child in children:
            try:
                row = identity(child)
                if row['parent'] != parent.pid or row['created'] < parent.create_time():
                    raise RuntimeError('Invalid process ancestry; cleanup refused')
                rows.append(row); pending.append(child)
            except psutil.NoSuchProcess:
                pass
    return rows


def terminate_verified(rows: list[dict[str, Any]]) -> None:
    """Terminate only the captured worker tree, children first; fail closed on reuse."""
    for row in reversed(rows):
        try:
            p = psutil.Process(row['pid'])
            if p.create_time() != row['created'] or p.ppid() != row['parent']:
                raise RuntimeError('Process identity changed; cleanup refused')
            p.kill(); p.wait(timeout=15)
        except psutil.NoSuchProcess:
            pass
    if any(matches(row) for row in rows):
        raise RuntimeError('Owned process remains; refusing restart')


def preserve_lock(root: Path, audit: Path, rows: list[dict[str, Any]]) -> None:
    """Archive an exited worker's exact lock; never remove an unrelated lock."""
    lock = root/'RUNNING.json'
    if not lock.exists():
        return
    record = read_json(lock)
    if not any(record['pid'] == r['pid'] and record['created'] == r['created'] for r in rows):
        raise RuntimeError('Lock is not owned by this worker')
    if matches(record):
        raise RuntimeError('Lock owner still running')
    lock.replace(audit/'RUNNING_preserved.json')


def fresh_project(root: Path, audit: Path) -> None:
    """Restore only a scratch copy from unchanged initialized input, retaining old copy."""
    snap = read_json(root/'snapshot.json'); source = Path(snap['template'])
    if digest(source) != snap['template_sha256'] or mesh_identity(source) != snap['mesh']:
        raise RuntimeError('Initialized input changed; refusing recovery')
    work = audit/'fresh_working'/source.name
    work.parent.mkdir()
    shutil.copy2(source, work)
    shutil.copytree(source.with_suffix(''), work.with_suffix(''),
                    ignore=shutil.ignore_patterns('*.lok', '*.lock'))
    if mesh_identity(work) != snap['mesh']:
        raise RuntimeError('Recovery mesh mismatch')
    write_json(audit/'snapshot_before.json', snap)
    snap['project'] = str(work)
    write_json(root/'snapshot.json', snap)


class Supervisor:
    """Keep blocking CST calls in a separate worker process with one bounded retry."""

    def __init__(self, root: Path, template: Path, library: str,
                 batch_size: int = 32, initial_idle_s: float = 300, solve_limit_s: float = 600, selection: Path | None = None, abort_grace_s: float = 180):
        self.root, self.template, self.library = root, template, library
        if not math.isfinite(solve_limit_s) or solve_limit_s <= 0:
            raise ValueError('Solve limit must be finite and positive')
        self.batch_size, self.idle_s = batch_size, initial_idle_s
        self.solve_limit_s = solve_limit_s
        self.selection = selection
        if not math.isfinite(abort_grace_s) or abort_grace_s <= 0:
            raise ValueError("Abort grace must be finite and positive")
        self.abort_grace_s = abort_grace_s

    def enforce_solve_limit(self, child: subprocess.Popen, anchor: dict[str, Any],
                            audit: Path, state: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
        """Hard deadline independent of a blocked CST call; preserve and skip once.

        Full unflushed trajectories are not guaranteed after a forced stop. The
        working project is retained in the snapshot audit, never reused as success.
        """
        key = state.get('current', {}).get('key')
        if not key:
            return False
        case = self.root/'cases'/key
        timer = read_json(case/'solve_timer.json'); owner = state.get('owner', {})
        if not solve_deadline_reached(timer, owner, key, time.monotonic()):
            return False
        if timer.get('stop_policy') == 'native_abort_then_collect':
            request_path = case/'abort_request.json'
            request = read_json(request_path)
            if not request:
                if (case/'result.json').exists():
                    return False
                session_owner = read_json(self.root/'owner.json')
                request = dict(key=key, owner=owner, session_owner=session_owner,
                               project=read_json(self.root/'snapshot.json')['project'],
                               requested_monotonic=time.monotonic(), utc=utc(),
                               reason='solve_wall_limit', limit_s=timer['limit_s'])
                write_json(request_path, request)
                cmd = [sys.executable,'-u','-m','workflows.trk_multipacting.trk_abort',
                       '--root',str(self.root),'--request',str(request_path),
                       '--cst-library',self.library]
                with (case/'abort_stdout.log').open('wb') as out, (case/'abort_stderr.log').open('wb') as err:
                    helper = subprocess.Popen(cmd,stdout=out,stderr=err,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    write_json(case/'abort_helper.json',identity(psutil.Process(helper.pid)))
                return False
            if request.get('key') != key or request.get('owner') != owner:
                raise RuntimeError('Stale abort request; refusing cleanup')
            if time.monotonic()-request['requested_monotonic'] < timer.get('abort_grace_s', self.abort_grace_s):
                return False  # Keep worker alive to flush, validate and export partial data.
        worker = psutil.Process(owner['pid'])
        if worker.create_time() != owner['created']:
            raise RuntimeError('Worker identity changed; timeout cleanup refused')
        worker.suspend()  # Freeze dispatch before checking for a completion race.
        latest = read_json(self.root/'state.json')
        if (latest.get('current', {}).get('key') != key or latest.get('owner') != owner
                or read_json(case/'solve_timer.json') != timer or (case/'result.json').exists()):
            worker.resume()
            return False
        incident = audit/'solve_time_limit'; incident.mkdir()
        elapsed = time.monotonic()-timer['started_monotonic']
        evidence = dict(status='solve_time_limit', key=key, limit_s=timer['limit_s'],
                        elapsed_s=elapsed, utc=utc(), state=state, processes=rows,
                        abort_request=read_json(case/'abort_request.json'),
                        abort_response=read_json(case/'abort_response.json'),
                        scientific_classification='incomplete; not an MP verdict')
        write_json(incident/'evidence.json', evidence)
        shutil.copytree(case, incident/'case_before_stop')
        snap = read_json(self.root/'snapshot.json')
        log = Path(snap['project']).with_suffix('')/'Result/Model.log'
        if log.exists(): shutil.copy2(log, incident/'Model.log')
        terminate_verified(owned_tree(anchor))
        child.wait(timeout=15)
        preserve_lock(self.root, incident, rows)
        write_json(incident/'cleanup.json', dict(all_owned_exited=True))
        write_json(case/'timeout.json', evidence)
        write_json(self.root/'state.json', dict(status='solve_time_limit', current=state['current'],
                   completed=len(completed(self.root)), timed_out=len(timed_out(self.root)), utc=utc()))
        fresh_project(self.root, incident)
        selected_report(self.root)
        return True

    def monitor(self, child: subprocess.Popen, anchor: dict[str, Any], audit: Path) -> bool:
        """Return True for a preserved, cleaned init retry or terminal solve timeout."""
        samples: deque = deque()
        last_key = None
        while child.poll() is None:
            state = read_json(self.root/'state.json')
            rows = owned_tree(anchor)
            owner = state.get('owner', {})
            valid = any(r['pid'] == owner.get('pid') and r['created'] == owner.get('created') for r in rows)
            key = state.get('current', {}).get('key') if valid and state.get('status') == 'running' else None
            if key and self.enforce_solve_limit(child, anchor, audit, state, rows):
                return True
            if key != last_key:
                samples.clear(); last_key = key
            solvers = [r for r in rows if r['name'].lower() == 'solver_trk_amd64.exe']
            now = time.time()
            if key and len(solvers) == 1:
                solver = solvers[0]
                if samples and samples[-1][2:] != (solver['pid'], solver['created']):
                    samples.clear()
                samples.append((now, solver['cpu_s'], solver['pid'], solver['created']))
                while len(samples) > 1 and now - samples[1][0] >= 60:
                    samples.popleft()
                snap = read_json(self.root/'snapshot.json')
                log = Path(snap['project']).with_suffix('')/'Result/Model.log'
                started = datetime.fromisoformat(state['utc']).timestamp()
                if log.exists() and log.stat().st_mtime >= started:
                    log_stamp = (log.stat().st_mtime_ns, log.stat().st_size)
                    text = log.read_text(errors='replace')
                    span, delta = now-samples[0][0], solver['cpu_s']-samples[0][1]
                    if initialization_stalled(text, now-log.stat().st_mtime, now-started,
                                              span, delta, self.idle_s):
                        incident = audit/'initial_stall'; incident.mkdir()
                        write_json(incident/'evidence.json', dict(utc=utc(),state=state,processes=rows,
                                   cpu_span_s=span,cpu_delta_s=delta,log_age_s=now-log.stat().st_mtime))
                        shutil.copy2(log, incident/'Model.log')
                        shutil.copytree(self.root/'cases'/key, incident/'case_before_retry')
                        # Freeze dispatch before cleanup, independently of blocked CST API.
                        p = psutil.Process(owner['pid'])
                        if p.create_time() != owner['created']:
                            raise RuntimeError('Worker identity changed')
                        p.suspend()
                        latest = read_json(self.root/'state.json')
                        if (latest.get('current', {}).get('key') != key
                                or (log.stat().st_mtime_ns, log.stat().st_size) != log_stamp
                                or (self.root/'cases'/key/'result.json').exists()):
                            p.resume()
                            samples.clear()
                            continue
                        terminate_verified(owned_tree(anchor))
                        child.wait(timeout=15)
                        preserve_lock(self.root, incident, rows)
                        write_json(incident/'cleanup.json', dict(all_owned_exited=True))
                        retry_path = self.root/'guard_retries.json'; retries = read_json(retry_path)
                        retries[key] = retries.get(key, 0)+1; write_json(retry_path, retries)
                        if retries[key] > 1:
                            write_json(self.root/'state.json',dict(status='initialization_retry_exhausted',current=state['current'],completed=len(completed(self.root)),utc=utc()))
                            raise RuntimeError(f'Initialization stalled again: {key}; evidence retained')
                        fresh_project(self.root, incident)
                        return True
            write_json(self.root/'guard_state.json',dict(status='watching',utc=utc(),worker=anchor,
                       current=key,completed=len(completed(self.root)),batch_size=self.batch_size,
                       initialization_idle_seconds=self.idle_s,solve_limit_seconds=self.solve_limit_s,
                       timed_out=len(timed_out(self.root))))
            time.sleep(1)
        return False

    def recover_native_initialization(self, audit: Path, anchor: dict[str, Any]) -> bool:
        """Retry one unfinished native crash only after confirmed owned cleanup."""
        snap = read_json(self.root/'snapshot.json')
        log = Path(snap['project']).with_suffix('')/'Result/Model.log'
        if not log.exists() or log.stat().st_mtime < anchor['created']:
            return False
        if not recoverable_native_failure(log.read_text(errors='replace'),
                                          read_json(self.root/'failure.json').get('error', '')):
            return False
        cleanup = read_json(self.root/'cleanup.json'); owner = read_json(self.root/'owner.json')
        if (not cleanup.get('success') or (self.root/'RUNNING.json').exists()
                or matches(dict(pid=owner['pid'],created=owner['created']))
                or matches(dict(pid=owner['cst_pid'],created=owner['cst_created']))):
            raise RuntimeError('Native failure cleanup not confirmed')
        candidates = [p for p in (self.root/'cases').glob('*/task.json')
                      if p.stat().st_mtime >= anchor['created'] and not (p.parent/'result.json').exists()]
        if len(candidates) != 1:
            raise RuntimeError('Ambiguous failed case; refusing automatic retry')
        case = candidates[0].parent; key = case.name
        incident = audit/'native_initialization_failure'; incident.mkdir()
        shutil.copytree(case,incident/'case_before_retry'); shutil.copy2(log,incident/'Model.log')
        for name in ('failure.json','cleanup.json','owner.json','state.json'):
            shutil.copy2(self.root/name,incident/name)
        retries=read_json(self.root/'guard_retries.json'); retries[key]=retries.get(key,0)+1
        write_json(self.root/'guard_retries.json',retries)
        if retries[key] > 1:
            raise RuntimeError(f'Native solve failed again: {key}; evidence retained')
        fresh_project(self.root,incident)
        return True

    def run(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target_keys = {t.key for t in tasks()}
        frozen = self.root/'selection.json'
        if self.selection:
            plan = read_json(self.selection)
            keys = plan.get('keys', [])
            if not keys or len(keys) != len(set(keys)) or not set(keys) <= target_keys:
                raise ValueError('Invalid/duplicate selected scan keys')
            if Path(plan['template']).resolve() != self.template.resolve():
                raise ValueError('Selection template mismatch')
            if plan['solve_limit_seconds'] != self.solve_limit_s:
                raise ValueError('Selection time limit mismatch')
            if frozen.exists() and read_json(frozen) != plan:
                raise ValueError('Frozen selection changed; use a new run root')
            if not frozen.exists(): write_json(frozen, plan)
        if frozen.exists():
            plan = read_json(frozen); keys = plan.get('keys', [])
            if not keys or len(keys) != len(set(keys)) or not set(keys) <= target_keys:
                raise ValueError('Invalid frozen scan keys')
            if Path(plan['template']).resolve() != self.template.resolve() or plan['solve_limit_seconds'] != self.solve_limit_s:
                raise ValueError('Frozen selection configuration mismatch')
            target_keys = set(keys)
        selected_report(self.root)
        lock = self.root/'GUARD.json'; owner = identity(psutil.Process())
        with lock.open('x', encoding='utf-8') as f:
            json.dump(owner, f)
        status = 'failed'
        try:
            if (self.root/'RUNNING.json').exists():
                raise RuntimeError('Existing worker lock; refusing duplicate launch')
            while not (self.root/'STOP').exists():
                if target_keys <= (set(completed(self.root)) | timed_out(self.root)):
                    status = 'complete_with_timeouts' if timed_out(self.root) else 'complete'; break
                audit = self.root/'guard_runs'/datetime.now().strftime('%Y%m%dT%H%M%S%f')
                audit.mkdir(parents=True)
                cmd = [sys.executable,'-u','-m','workflows.trk_multipacting.trk_run',
                       '--root',str(self.root),'--template',str(self.template),
                       '--cst-library',self.library,'--limit',str(self.batch_size),
                       '--solve-limit-seconds',str(self.solve_limit_s),'--abort-grace-seconds',str(self.abort_grace_s)]
                env = dict(os.environ, PYTHONUTF8='0', PYTHONIOENCODING='utf-8')
                repository = Path(__file__).resolve().parents[2]
                env['PYTHONPATH'] = os.pathsep.join([str(repository/'src'), str(repository), env.get('PYTHONPATH', '')])
                with (audit/'stdout.log').open('wb') as out, (audit/'stderr.log').open('wb') as err:
                    child = subprocess.Popen(cmd, stdout=out, stderr=err, env=env,
                                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    anchor = identity(psutil.Process(child.pid)); write_json(audit/'launch.json',anchor)
                    recovered = self.monitor(child, anchor, audit)
                for helper_path in self.root.glob('cases/*/abort_helper.json'):
                    helper = read_json(helper_path)
                    if matches(helper):
                        p = psutil.Process(helper['pid'])
                        if p.ppid()!=os.getpid():
                            raise RuntimeError('Abort helper ownership changed')
                        try:p.wait(timeout=5)
                        except psutil.TimeoutExpired:terminate_verified(owned_tree(helper))
                if recovered:
                    continue
                state = read_json(self.root/'state.json'); cleanup = read_json(self.root/'cleanup.json')
                if child.returncode != 0 or state.get('status') not in ('batch_complete','complete','paused'):
                    if state.get('status') == 'failed' and self.recover_native_initialization(audit, anchor):
                        continue
                    raise RuntimeError(f'Worker failed: {state}; inspect {audit}')
                if not cleanup.get('success') or (self.root/'RUNNING.json').exists():
                    raise RuntimeError('Cleanup unconfirmed; refusing next session')
            else:
                status = 'paused'
        except Exception as exc:
            write_json(self.root/'guard_failure.json',dict(utc=utc(),error=repr(exc)))
            raise
        finally:
            selected_report(self.root)
            write_json(self.root/'guard_state.json',dict(status=status,utc=utc(),completed=len(completed(self.root)),
                       timed_out=len(timed_out(self.root)),solve_limit_seconds=self.solve_limit_s))
            if read_json(lock) == owner:
                lock.unlink()  # Only the supervisor's own lock, never a worker's lock.


def main() -> None:
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--template',type=Path,required=True)
    p.add_argument('--cst-library',required=True)
    p.add_argument('--batch-size',type=int,default=32)
    p.add_argument('--initial-idle-seconds',type=float,default=300)
    p.add_argument('--solve-limit-seconds',type=float,default=600)
    p.add_argument('--selection',type=Path)
    p.add_argument('--abort-grace-seconds',type=float,default=180)
    a=p.parse_args()
    if a.batch_size<1 or a.initial_idle_seconds<120:
        p.error('Require positive batch size and at least 120 seconds initial idle threshold')
    Supervisor(a.root,a.template,a.cst_library,a.batch_size,a.initial_idle_seconds,a.solve_limit_seconds,a.selection,a.abort_grace_seconds).run()


if __name__=='__main__':
    main()
