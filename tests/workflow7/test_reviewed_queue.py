"""A user-requested finite batch must stop both dispatch and speculative GP work."""
from types import SimpleNamespace
from pathlib import Path
import pytest
from workflows.rfgun_wakis.campaign import Campaign
from workflows.rfgun_wakis.pipeline import PreparationPipeline
from workflows.rfgun_wakis.io import atomic_json

def fake_candidate(status):
    return dict(id='candidate_0001',status=status,forced_transverse=False)

def test_queued_dispatch_and_no_automatic_proposal():
    c=object.__new__(Campaign)
    c.store=SimpleNamespace(data=dict(dispatch_mode='queued_only',candidates=[fake_candidate('axis_pending')]))
    assert c.next_job()['stage']=='axis'
    c.store.data['candidates'][0]['status']='x_pending'
    assert c.next_job()['stage']=='x'
    c.store.data['candidates'][0]['status']='completed'
    assert c.next_job() is None
    with pytest.raises(RuntimeError,match='forbids'):c.propose_candidate()

def test_normal_dispatch_keeps_gp():
    c=object.__new__(Campaign);c.store=SimpleNamespace(data=dict(candidates=[]))
    def propose():
        c.store.data['candidates'].append(fake_candidate('axis_pending'));return 0
    c.propose_candidate=propose
    assert c.next_job()['candidate_index']==0

def test_queue_prefetch_never_proposes_extra_geometry(tmp_path,monkeypatch):
    from workflows.rfgun_wakis.cst_prepare import ProcessIdentity
    monkeypatch.setattr(ProcessIdentity,'alive',lambda self:True)
    request=tmp_path/'solve.json';atomic_json(request.with_suffix('.owner.json'),{'processes':[dict(pid=123,parent=1,created=1.,command=['python'])]})
    atomic_json(tmp_path/'status.json',dict(phase='wake',step=1,total=10))
    data=dict(dispatch_mode='queued_only',status='running',active_seconds=0.,
              candidates=[fake_candidate('axis_pending')],prefetch=None,
              pending=dict(candidate_index=0,phase='axis_solve_00',field_directory=str(tmp_path),phase_requests={'axis_solve_00':str(request)}))
    c=SimpleNamespace(store=SimpleNamespace(data=data,cap=100),root=tmp_path,
                      config=SimpleNamespace(runtime=SimpleNamespace(prefetch=True)))
    # No RAM/proposer/supervisor attributes: the empty queue must return first.
    PreparationPipeline(c).maybe_start()
    assert data['prefetch'] is None


@pytest.mark.parametrize('axis_only',[False,True])
def test_axis_only_replay_does_not_admit_forced_x(tmp_path,axis_only):
    from workflows.rfgun_wakis.config import Config,Paths
    from workflows.rfgun_wakis.observations import Observation
    c=object.__new__(Campaign)
    candidate=dict(id='candidate_0000',parameters={},observations={'longitudinal':Observation(1000,.02,980,1020,True).as_dict()},
                   axis_directory=str(tmp_path),forced_transverse=True,status='axis_pending')
    if axis_only:candidate['requested_stages']=['axis']
    c.config=Config(Paths(*['dummy']*6));c.report=lambda:None
    c.store=SimpleNamespace(data=dict(candidates=[candidate],results=[],radius=.25),save=lambda:None)
    c.apply_results();c.apply_results()
    assert candidate['status']==('axis_only' if axis_only else 'x_pending')
    assert 'transverse_x' not in candidate['observations']

def test_final_prefetch_failure_drains_without_begin_none(tmp_path):
    from workflows.rfgun_wakis.state import RoundStore
    c=object.__new__(Campaign);c.root=tmp_path;c.config=SimpleNamespace(validate=lambda live:None,compact_retention=False)
    c.store=RoundStore(tmp_path/'state.json','test');c.store.data.update(dispatch_mode='queued_only',candidates=[fake_candidate('axis_pending')])
    class Pipeline:
        job={'candidate_index':0}
        def wait(self):
            c.store.data['candidates'][0]['status']='failed';self.job=None
    c.pipeline=Pipeline();c.tick=lambda:None;c.check_provenance=lambda:None;c.apply_results=lambda:None;c.report=lambda:None
    c.run()
    assert c.store.data['status']=='paused' and c.store.data['pending'] is None
    assert (tmp_path/'STOP').exists()
