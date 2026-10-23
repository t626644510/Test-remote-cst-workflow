"""Watchdog safety/decision tests: no CST launch, no real process termination."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from workflows.trk_multipacting import trk_supervise as s
pytestmark=pytest.mark.no_cst

@pytest.mark.parametrize('suffix',['Running field solver','Running time loop...', 'Tracking solver finished','Solver successful'])
def test_tracking_is_not_initialization_stall(suffix):
 assert not s.initialization_stalled('Pure tracking mode\n'+suffix,999,999,60,0,300)

def test_idle_initialization_requires_all_signals():
 assert s.initialization_stalled('Pure tracking mode',301,310,60,.2,300)
 for values in [(299,310,60,0),(301,299,60,0),(301,310,59,0),(301,310,60,2)]:
  assert not s.initialization_stalled('Pure tracking mode',*values,300)
 assert not s.initialization_stalled('Initializing',999,999,60,0,300)

class FakeProcess:
 def __init__(self,pid,born,parent=0):self.pid=pid;self.born=born;self.parent_id=parent;self.killed=False
 def create_time(self):return self.born
 def ppid(self):return self.parent_id
 def name(self):return 'mock'
 def cmdline(self):return ['mock']
 def cpu_times(self):return (0,0)
 def children(self):return []
 def kill(self):self.killed=True
 def wait(self,timeout):pass

def test_reused_pid_never_killed(monkeypatch):
 p=FakeProcess(2,20,1);monkeypatch.setattr(s.psutil,'Process',lambda _:p)
 with pytest.raises(RuntimeError,match='identity'):
  s.terminate_verified([dict(pid=2,created=10,parent=1)])
 assert not p.killed

def test_invalid_birth_edge_refused(monkeypatch):
 parent=FakeProcess(1,20);child=FakeProcess(2,10,1);parent.children=lambda:[child]
 monkeypatch.setattr(s.psutil,'Process',lambda _:parent)
 with pytest.raises(RuntimeError,match='ancestry'):s.owned_tree(dict(pid=1,created=20))
 assert not child.killed

def test_archive_only_exact_dead_worker_lock(tmp_path,monkeypatch):
 a=tmp_path/'audit';a.mkdir();p=tmp_path/'RUNNING.json';o=dict(pid=1,created=2,parent=0)
 p.write_text(json.dumps(o));monkeypatch.setattr(s,'matches',lambda _:True)
 with pytest.raises(RuntimeError,match='still running'):s.preserve_lock(tmp_path,a,[o])
 assert p.exists()
 monkeypatch.setattr(s,'matches',lambda _:False)
 with pytest.raises(RuntimeError,match='not owned'):s.preserve_lock(tmp_path,a,[dict(pid=2,created=2)])
 assert p.exists()
 s.preserve_lock(tmp_path,a,[o]);assert not p.exists() and (a/'RUNNING_preserved.json').exists()

def test_fresh_project_refuses_changed_input(tmp_path,monkeypatch):
 source=tmp_path/'input.cst';source.write_text('changed');a=tmp_path/'audit';a.mkdir()
 (tmp_path/'snapshot.json').write_text(json.dumps(dict(template=str(source),template_sha256='old',mesh={})))
 with pytest.raises(RuntimeError,match='input changed'):s.fresh_project(tmp_path,a)
 assert not (a/'fresh_working').exists()

def test_fresh_project_preserves_old_mesh_and_snapshot(tmp_path):
 source=tmp_path/'input.cst';source.write_bytes(b'cst')
 for name in ['Result/3d.slim','Result/topot.tet','Result/moegeom.tet','Result/Mesh_Output.QuasiModel.tet','Model/3D/extfield_0.c3c']:
  p=source.with_suffix('')/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode())
 (source.with_suffix('')/'old.lok').write_text('lock')
 old=dict(template=str(source),template_sha256=s.digest(source),mesh=s.mesh_identity(source),project='previous')
 s.write_json(tmp_path/'snapshot.json',old);a=tmp_path/'audit';a.mkdir();s.fresh_project(tmp_path,a)
 new=s.read_json(tmp_path/'snapshot.json');assert new['mesh']==old['mesh']
 assert s.mesh_identity(Path(new['project']))==old['mesh']
 assert s.read_json(a/'snapshot_before.json')==old
 assert (source.with_suffix('')/'old.lok').exists()
 assert not (Path(new['project']).with_suffix('')/'old.lok').exists()

def test_duplicate_guard_does_not_remove_existing_lock(tmp_path):
 lock=tmp_path/'GUARD.json';lock.write_text('{"existing":true}')
 with pytest.raises(FileExistsError):s.Supervisor(tmp_path,Path('unused'),'unused').run()
 assert lock.read_text()=='{"existing":true}'

def test_stop_prevents_any_launch(tmp_path,monkeypatch):
 (tmp_path/'STOP').write_text('User pause')
 def forbidden(*a,**k):raise AssertionError('Must not launch')
 monkeypatch.setattr(s.subprocess,'Popen',forbidden)
 s.Supervisor(tmp_path,Path('unused'),'unused').run()
 assert s.read_json(tmp_path/'guard_state.json')['status']=='paused'
 assert not (tmp_path/'GUARD.json').exists()

def test_monitor_preserves_then_retries_once_and_stops_on_repeat(tmp_path,monkeypatch):
 import os
 root=tmp_path;work=root/'working/a.cst';log=work.with_suffix('')/'Result/Model.log';log.parent.mkdir(parents=True)
 log.write_text('Pure tracking mode');os.utime(log,(100,100))
 key='s02_f040_p240';case=root/'cases'/key;case.mkdir(parents=True);(case/'task.json').write_text('{}')
 owner=dict(pid=100,created=10)
 s.write_json(root/'state.json',dict(status='running',current=dict(key=key),owner=owner,utc='1970-01-01T00:00:00+00:00'))
 s.write_json(root/'snapshot.json',dict(project=str(work)))
 proc=FakeProcess(100,10);proc.suspend=lambda:None;proc.resume=lambda:None
 monkeypatch.setattr(s.psutil,'Process',lambda _:proc)
 rows=[dict(pid=100,created=10,name='python.exe'),dict(pid=101,created=11,name='Solver_TRK_AMD64.exe',cpu_s=0)]
 monkeypatch.setattr(s,'owned_tree',lambda _:rows)
 calls=[];child=SimpleNamespace(returncode=None)
 child.poll=lambda:child.returncode
 child.wait=lambda timeout:child.returncode
 def terminate(r):calls.append('kill');child.returncode=1
 monkeypatch.setattr(s,'terminate_verified',terminate)
 monkeypatch.setattr(s,'preserve_lock',lambda *a:calls.append('archive_lock'))
 monkeypatch.setattr(s,'fresh_project',lambda *a:calls.append('fresh_project'))
 ticks=iter(range(400,10000,5));monkeypatch.setattr(s.time,'time',lambda:next(ticks));monkeypatch.setattr(s.time,'sleep',lambda _:None)
 supervisor=s.Supervisor(root,Path('unused'),'unused')
 a=root/'audit1';a.mkdir()
 assert supervisor.monitor(child,owner,a)
 assert calls==['kill','archive_lock','fresh_project']
 assert s.read_json(root/'guard_retries.json')[key]==1
 assert (a/'initial_stall/Model.log').exists() and (a/'initial_stall/case_before_retry/task.json').exists()
 child.returncode=None;a=root/'audit2';a.mkdir()
 with pytest.raises(RuntimeError,match='stalled again'):supervisor.monitor(child,owner,a)
 assert s.read_json(root/'state.json')['status']=='initialization_retry_exhausted'
 assert calls==['kill','archive_lock','fresh_project','kill','archive_lock']

def test_early_tet_initialization_idle_is_also_guarded():
 assert s.initialization_stalled('Initializing\nUsing TET mesh',301,310,60,0,300)
 assert not s.initialization_stalled('Initializing\nUsing TET mesh',301,310,60,20,300)

@pytest.mark.parametrize('text,expected',[
 ('Initializing\nTerminated abnormally',True),
 ('Initializing\nRunning field solver\nTerminated abnormally',False),
 ('Initializing\nRunning time loop\nTerminated abnormally',False),
 ('Initializing\nTracking solver finished\nTerminated abnormally',False),
 ('Initializing',False),('Failed to calculate SEY',False)])
def test_native_failure_stage_gate(text,expected):
 assert s.native_initialization_failure(text)==expected

def test_descendant_exit_during_enumeration_is_normal(monkeypatch):
 parent=FakeProcess(1,10);child=FakeProcess(2,20,1);parent.children=lambda:[child]
 def gone():raise s.psutil.NoSuchProcess(2)
 child.children=gone
 monkeypatch.setattr(s.psutil,'Process',lambda _:parent)
 rows=s.owned_tree(dict(pid=1,created=10))
 assert [r['pid'] for r in rows]==[1,2]

def test_root_exit_between_identity_reads_is_normal(monkeypatch):
 p=FakeProcess(1,10);calls=[]
 def factory(pid):
  calls.append(pid)
  if len(calls)>1:raise s.psutil.NoSuchProcess(pid)
  return p
 monkeypatch.setattr(s.psutil,'Process',factory)
 assert s.owned_tree(dict(pid=1,created=10))==[]


@pytest.mark.parametrize('text,error,expected',[
 ('Particle Tracking Solver run', 'run_solver: Connection has been closed!', True),
 ('Initializing\nRunning time loop', 'run_solver: Connection has been closed!', True),
 ('Tracking solver finished', 'run_solver: Connection has been closed!', False),
 ('Particle Tracking Solver successful.', 'run_solver: Connection has been closed!', False),
 ('Initializing\nTerminated abnormally', '', True),
 ('Initializing', 'SEY analysis failed', False),
 ('Initializing', 'mesh hash mismatch', False),
 ('Initializing', 'export: Connection has been closed!', False),
])
def test_native_connection_loss_is_bounded_to_unfinished_solver(text,error,expected):
 assert s.recoverable_native_failure(text,error)==expected


def native_fixture(root):
 work=root/'working/a.cst';log=work.with_suffix('')/'Result/Model.log'
 log.parent.mkdir(parents=True);log.write_text('Particle Tracking Solver run')
 s.write_json(root/'snapshot.json',dict(project=str(work)))
 case=root/'cases/s01_f030_p120';case.mkdir(parents=True)
 s.write_json(case/'task.json',dict(key=case.name))
 s.write_json(root/'failure.json',dict(error='run_solver: Connection has been closed!'))
 s.write_json(root/'cleanup.json',dict(success=True))
 s.write_json(root/'owner.json',dict(pid=1,created=1,cst_pid=2,cst_created=2))
 s.write_json(root/'state.json',dict(status='failed'))
 return log,case


def test_closed_connection_recovery_preserves_case_and_retries_once(tmp_path,monkeypatch):
 log,case=native_fixture(tmp_path)
 monkeypatch.setattr(s,'matches',lambda _:False)
 calls=[];monkeypatch.setattr(s,'fresh_project',lambda *a:calls.append('fresh'))
 supervisor=s.Supervisor(tmp_path,Path('unused'),'unused')
 for n in (1,2):
  audit=tmp_path/str(n);audit.mkdir()
  if n==1:assert supervisor.recover_native_initialization(audit,dict(created=0))
  else:
   with pytest.raises(RuntimeError,match='failed again'):
    supervisor.recover_native_initialization(audit,dict(created=0))
  assert (audit/'native_initialization_failure/case_before_retry/task.json').exists()
 assert calls==['fresh']
 assert s.read_json(tmp_path/'guard_retries.json')[case.name]==2


@pytest.mark.parametrize('gate',['live_owner','lock','cleanup_failed','completed','stale_log'])
def test_native_recovery_requires_cleanup_and_unfinished_fresh_case(tmp_path,monkeypatch,gate):
 log,case=native_fixture(tmp_path)
 monkeypatch.setattr(s,'matches',lambda _:gate=='live_owner')
 def forbidden(*args):raise AssertionError('Must not copy/restart')
 monkeypatch.setattr(s,'fresh_project',forbidden)
 if gate=='lock':(tmp_path/'RUNNING.json').write_text('{}')
 if gate=='cleanup_failed':s.write_json(tmp_path/'cleanup.json',dict(success=False))
 if gate=='completed':s.write_json(case/'result.json',dict(ok=True))
 audit=tmp_path/'audit';audit.mkdir()
 supervisor=s.Supervisor(tmp_path,Path('unused'),'unused')
 if gate=='stale_log':assert not supervisor.recover_native_initialization(audit,dict(created=log.stat().st_mtime+1))
 else:
  with pytest.raises(RuntimeError):supervisor.recover_native_initialization(audit,dict(created=0))
 assert not (tmp_path/'guard_retries.json').exists()
