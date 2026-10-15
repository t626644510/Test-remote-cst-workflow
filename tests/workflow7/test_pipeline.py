"""No-CST tests for two-lane ownership, stop boundaries and exact-once replay."""
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import time
import numpy as np
import pytest
from workflows.rfgun_wakis.campaign import Campaign
from workflows.rfgun_wakis.config import Config,Paths
from workflows.rfgun_wakis.cst_prepare import ProcessIdentity
from workflows.rfgun_wakis.geometry import Geometry
from workflows.rfgun_wakis.io import atomic_json,read_json,digest
from workflows.rfgun_wakis.processes import Supervisor,RunningPhase,OwnershipError
from workflows.rfgun_wakis.monitor import escalation
from workflows.rfgun_wakis.revision import create_revision

def make_campaign(tmp_path,monkeypatch):
    config=Config(Paths(*(str(tmp_path/n) for n in ('template.cst','light','bulk','python','wakis','cst'))))
    path=tmp_path/'config.json';atomic_json(path,config.as_dict());c=Campaign(path)
    points=Geometry(config).sample(np.random.default_rng(5),2)
    c.store.data['candidates']=[dict(id=f'candidate_{i:04}',parameters=p,observations={},status='axis_pending',
        forced_transverse=False,proposal={}) for i,p in enumerate(points)]
    c.store.activate();c.store.begin(dict(key='candidate_0000_axis',candidate_index=0,stage='axis',
        field_directory=str(c.bulk/'candidate_0000/axis_00'),phase='axis_solve_00',phase_requests={}))
    request=c.root/'jobs/candidate_0000_axis/axis_solve_00.json'
    c.store.data['pending']['phase_requests']['axis_solve_00']=str(request)
    atomic_json(request,dict(phase='solve',request_id='gpu',contract=config.digest()))
    atomic_json(request.with_suffix('.owner.json'),dict(processes=[asdict(ProcessIdentity.read(__import__('os').getpid()))]))
    atomic_json(Path(c.store.data['pending']['field_directory'])/'status.json',dict(phase='wake',step=256,total=4096))
    monkeypatch.setattr(c,'check_provenance',lambda:None)
    import psutil
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=40*2**30))
    starts=[];result={'value':None}
    monkeypatch.setattr(c.supervisor,'start',lambda request,timeout:starts.append(request) or SimpleNamespace(request=request))
    monkeypatch.setattr(c.supervisor,'poll',lambda handle:result['value'])
    return c,starts,result

def completion(c,index=1):
    prepared=c.bulk/f'candidate_{index:04}/prepared';atomic_json(prepared/'manifest.json',{})
    return dict(status='completed',result=dict(prepared=str(prepared),cst=dict(parameters=c.store.data['candidates'][index]['parameters'])))

def test_one_preparation_overlaps_live_gpu_and_is_reused_exactly_once(tmp_path,monkeypatch):
    c,starts,result=make_campaign(tmp_path,monkeypatch)
    before=c.store.data['pending']['key'];c.pipeline.service();c.pipeline.service()
    assert len(starts)==1 and c.pipeline.job['candidate_index']==1
    assert c.store.data['pending']['key']==before
    result['value']=completion(c);c.pipeline.service();c.pipeline.service()
    assert c.pipeline.job is None and len(starts)==1
    assert c.store.data['candidates'][1]['prepared']
    assert len(c.store.data['preparations'])==1 and not c.store.data.get('results')

@pytest.mark.parametrize('mode',['no_wake','completed','budget','stop','low_ram','dead_worker'])
def test_no_prefetch_outside_admission_boundary(tmp_path,monkeypatch,mode):
    c,starts,_=make_campaign(tmp_path,monkeypatch);field=Path(c.store.data['pending']['field_directory'])
    if mode=='no_wake':atomic_json(field/'status.json',dict(phase='GPU_initialization'))
    if mode=='completed':atomic_json(field/'field_complete.json',{})
    if mode=='budget':c.store.data['active_seconds']=c.store.cap
    if mode=='stop':(c.root/'STOP').write_text('pause')
    if mode=='low_ram':
        import psutil
        monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=23*2**30))
    if mode=='dead_worker':monkeypatch.setattr(ProcessIdentity,'alive',lambda self:False)
    c.pipeline.service();assert not starts and c.pipeline.job is None

def test_stop_drains_preparation_without_launching_its_gpu(tmp_path,monkeypatch):
    c,starts,_=make_campaign(tmp_path,monkeypatch);c.pipeline.service()
    # The foreground stage finished, leaving a still-running CPU preparation.
    c.store.data['pending']=None;c.store.data['candidates'][0]['status']='axis_only'
    c.store._last=None  # Simulate coordinator recovery with no clock active yet.
    c.store.data['status']='paused';c.store.save()
    calls=[]
    def poll(handle):
        calls.append('poll')
        if len(calls)<2:return None
        (c.root/'STOP').write_text('user pause during prefetched preparation')
        return completion(c)
    monkeypatch.setattr(c.supervisor,'poll',poll)
    monkeypatch.setattr(c.supervisor,'run',lambda *args:pytest.fail('STOP must not admit prefetched GPU'))
    monkeypatch.setattr(Config,'validate',lambda self,**kw:None)
    c.run()
    assert c.store.data['status']=='paused' and c.store.data['pending'] is None
    assert c.store.data['candidates'][1]['prepared'] and len(starts)==1

def test_prefetch_owner_fault_requests_drain_and_does_not_discard_foreground(tmp_path,monkeypatch):
    c,_,_=make_campaign(tmp_path,monkeypatch)
    monkeypatch.setattr(c.supervisor,'start',lambda *args:(_ for _ in ()).throw(OwnershipError('foreign tree')))
    c.pipeline.service()
    assert c.store.data['status']=='draining' and c.store.data['pending']['key']=='candidate_0000_axis'
    assert c.store.data['pipeline_error']['error']=="OwnershipError('foreign tree')"
    with pytest.raises(OwnershipError):c.pipeline.wait()

def test_single_prefetch_failure_is_preserved_and_skipped_after_bounded_retries(tmp_path,monkeypatch):
    c,starts,result=make_campaign(tmp_path,monkeypatch);c.pipeline.service()
    result['value']=dict(status='failed',traceback='RuntimeError: temporary initialization failure')
    for _ in range(4):c.pipeline.service()
    assert len(starts)==3 and c.store.data['status']=='running'
    assert c.store.data['candidates'][1]['status']=='failed'
    assert len(c.store.data['failures'])==1 and c.pipeline.job is None

def test_terminal_replay_does_not_launch_and_checks_live_owner(tmp_path,monkeypatch):
    c,_,_=make_campaign(tmp_path,monkeypatch)
    s=Supervisor(c.config,lambda:None);request=c.root/'request.json'
    spec=dict(request_id='abc',contract=c.config.digest());atomic_json(request,spec)
    atomic_json(request.with_suffix('.reply.json'),dict(spec,status='completed',result={}))
    handle=s.start(request,1);assert handle.proc is None and s.poll(handle)['status']=='completed'
    atomic_json(request.with_suffix('.owner.json'),dict(processes=[asdict(ProcessIdentity.read(__import__('os').getpid()))]))
    with pytest.raises(OwnershipError):s.start(request,1)

def test_supervisor_timeout_only_cleans_its_tracked_tree(tmp_path,monkeypatch):
    from workflows.rfgun_wakis import processes
    c,_,_=make_campaign(tmp_path,monkeypatch);s=Supervisor(c.config,lambda:None)
    root=ProcessIdentity(123,1,100,('owned',));request=c.root/'request.json'
    handle=RunningPhase(request,1,dict(request_id='q',contract='c'),SimpleNamespace(poll=lambda:None),root,
                        {(123,100):root},started=time.monotonic()-10)
    cleaned=[];monkeypatch.setattr(s,'_record_owner',lambda h:None)
    monkeypatch.setattr(processes,'cleanup',lambda identities,path:cleaned.extend(identities))
    assert s.poll(handle)['error']=='Phase timeout' and cleaned==[root]
    assert s.poll(handle)['error']=='Phase timeout' and cleaned==[root]

def test_auxiliary_memory_guard_releases_cpu_tree_before_gpu_threshold(tmp_path,monkeypatch):
    import psutil
    from workflows.rfgun_wakis import processes
    c,_,_=make_campaign(tmp_path,monkeypatch);s=Supervisor(c.config,lambda:None)
    cpu=ProcessIdentity(123,1,100,('cpu',));gpu=ProcessIdentity(456,1,101,('gpu',))
    cpu_handle=RunningPhase(c.root/'cpu.json',100,dict(request_id='cpu',contract='c'),
        SimpleNamespace(poll=lambda:None),cpu,{(123,100):cpu},memory_floor_gib=12.,memory_grace_s=0.)
    gpu_handle=RunningPhase(c.root/'gpu.json',100,dict(request_id='gpu',contract='c'),
        SimpleNamespace(poll=lambda:None),gpu,{(456,101):gpu})
    cleaned=[];monkeypatch.setattr(s,'_record_owner',lambda h:None)
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=11*2**30))
    monkeypatch.setattr(processes,'cleanup',lambda identities,path:cleaned.extend(identities))
    assert s.poll(cpu_handle)['error']=='Host memory protection'
    assert s.poll(gpu_handle) is None and cleaned==[cpu]

def test_monitor_requires_two_distinct_rounds_without_progress():
    progress={'step':100};first=escalation({},'fault',progress,1000)
    assert first['consecutive_count']==1 and not first['handoff_required']
    prev=dict(first,issue_key='fault',progress=progress)
    assert escalation(prev,'fault',progress,1001)['consecutive_count']==1
    assert escalation(prev,'fault',progress,2800)['handoff_required']
    assert not escalation(prev,'fault',{'step':200},2800)['handoff_required']
    assert not escalation(prev,None,progress,2800)['handoff_required']

def test_revision_preserves_budget_parent_and_excludes_old_observations(tmp_path,monkeypatch):
    c,_,_=make_campaign(tmp_path,monkeypatch)
    parent=tmp_path/'parent';atomic_json(parent/'state.json',dict(status='paused',pending=None,active_seconds=32029.5,
        cap_seconds=172800,candidates=[{'observations':{'longitudinal':123}}]))
    (parent/'STOP').write_text('paused');old=digest(parent/'state.json')
    source=Path(c.config.paths.template);source.write_bytes(b'fake CST archive for no-CST persistence test')
    point=c.store.data['candidates'][0]['parameters'];expanded=Geometry(c.config).expand(point)
    atomic_json(source.with_suffix('')/'Model/Parameters.json',dict(parameters=[dict(name=k,value=v) for k,v in expanded.items()]))
    # A distinct destination and empty state are required by migration.
    config=c.config.as_dict();config['paths']['output_dir']=str(tmp_path/'new_light');config['paths']['artifact_dir']=str(tmp_path/'new_bulk')
    config_path=tmp_path/'new_config.json';atomic_json(config_path,config)
    monkeypatch.setattr(Config,'validate',lambda self,**kw:None)
    record=create_revision(config_path,parent);state=read_json(tmp_path/'new_light/state.json')
    assert record['remaining_seconds']==140770.5 and state['active_seconds']==32029.5
    assert state['search_active_offset']==32029.5 and state['exploration_seconds']==0
    assert state['candidates'][0]['observations']=={} and state['status']=='paused'
    assert digest(parent/'state.json')==old and (tmp_path/'new_light/STOP').exists()
    with pytest.raises(RuntimeError):create_revision(config_path,parent)
