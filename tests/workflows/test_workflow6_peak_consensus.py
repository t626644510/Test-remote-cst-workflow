"""Reconstructed-peak search migration, whole-band uncertainty and recovery."""
from dataclasses import replace
import copy
import numpy as np
import pytest
from workflows.rfgun_wake_thermal.config import Config,Paths,NAMES
from workflows.rfgun_wake_thermal.peak_consensus import summarize
from workflows.rfgun_wake_thermal.screening import search_metrics,ranking_metrics,screening_admission,stage_below
from workflows.rfgun_wake_thermal.search import Controller

pytestmark=pytest.mark.no_cst

@pytest.fixture
def cfg(tmp_path):
    c=Config(Paths({k:str(tmp_path/(k+'.cst')) for k in ('axis','x','y','thermal')},str(tmp_path/'d'),str(tmp_path/'e')))
    return replace(c,search=replace(c.search,observation_mode='reconstructed_peak_screening',gp_min_samples=2))

def detail(cfg,values=(1000,1010,990,1005,995,1000),bad=None,valid=None):
    fits=[dict(start_m=1 if i<3 else 3,rank=(24,32,48)[i%3],valid=(valid or [True]*6)[i],error=.01,holdout_error=.02,peak=v) for i,v in enumerate(values)]
    return dict(status='uncertain',value=None,reasons=[],diagnostics=dict(fits=fits,windows=[dict(band_hz=list(cfg.physics.band_hz),peaks=list(values),boundary_tail_peaks=bad or [0]*6,direct_peak=100,spread=.99)],direct_peak=100))

def candidate(cfg,d):
    return dict(id='p',parameters={n:sum(cfg.bounds[n])/2 for n in NAMES},metrics={'power5':200,'power6':210},details={'longitudinal':d,'thermal':{'status':'valid'}},complete=True,failed=False,stages={})

def test_direct_ft_not_training_or_gate(cfg):
    d=summarize(detail(cfg,values=(3000,3010,2990,3000,3010,2990)),cfg.physics,cfg.reconstruction,'longitudinal')
    c=candidate(cfg,d);s=dict(candidates=[c],rng=None)
    assert search_metrics(cfg,c)['longitudinal']==3000
    assert Controller(cfg,s).training_rows('longitudinal')[0][1]==3000
    assert not stage_below(cfg,c,'longitudinal')
    assert ranking_metrics(cfg,c)['longitudinal']>3000


def test_boundary_outlier_only_locally_removed_with_consensus(cfg):
    d=detail(cfg,values=(1000,1010,1e12,1005,995,1e11),bad=[0,0,1e12,0,0,1e11])
    r=summarize(d,cfg.physics,cfg.reconstruction,'longitudinal')
    u=r['diagnostics']['reconstructed_peak'];w=r['diagnostics']['local_consensus_windows'][0]
    assert r['status']=='valid' and 990<u['estimate']<1020
    assert set(w['excluded_fit_indices'])=={2,5}
    assert len(w['all_fit_peaks'])==6


def test_unresolved_window_not_dropped_from_global_or_feasibility(cfg):
    d=detail(cfg);lo,hi=cfg.physics.band_hz;mid=(lo+hi)/2
    d['diagnostics']['windows'][0]['band_hz']=[lo,mid]
    d['diagnostics']['windows'].append(dict(band_hz=[mid,hi],peaks=[4000,8000,40000,5000,9000,50000],boundary_tail_peaks=[0]*6,direct_peak=100))
    r=summarize(d,cfg.physics,cfg.reconstruction,'longitudinal');u=r['diagnostics']['reconstructed_peak']
    assert r['status']=='uncertain' and r['value'] is None
    assert u['estimate']>8000 and u['unresolved_windows']==[[mid,hi]]
    assert not stage_below(cfg,candidate(cfg,r),'longitudinal')


def test_no_finite_window_means_no_gp_value(cfg):
    d=detail(cfg);d['diagnostics']['windows'][0]['peaks']=[]
    r=summarize(d,cfg.physics,cfg.reconstruction,'longitudinal')
    assert 'longitudinal' not in search_metrics(cfg,candidate(cfg,r))


def test_incomplete_band_never_trains_or_passes(cfg):
    d=detail(cfg);d['diagnostics']['windows'][0]['band_hz'][1]-=1e8
    r=summarize(d,cfg.physics,cfg.reconstruction,'longitudinal')
    assert r['status']=='uncertain' and 'longitudinal' not in search_metrics(cfg,candidate(cfg,r))


def test_insufficient_support_kept_as_uncertain_estimate(cfg):
    d=detail(cfg,bad=[1000,1000,1000,0,0,0])
    r=summarize(d,cfg.physics,cfg.reconstruction,'longitudinal');u=r['diagnostics']['reconstructed_peak']
    assert u['unbounded'] and u['upper'] is None and u['relative_uncertainty']>=1
    assert search_metrics(cfg,candidate(cfg,r))['longitudinal']>0
    assert not stage_below(cfg,candidate(cfg,r),'longitudinal')


def test_threshold_straddle_never_formal_pass(cfg):
    r=summarize(detail(cfg,values=(1990,2010,1995,2005,1999,2001)),cfg.physics,cfg.reconstruction,'longitudinal')
    assert r['value'] is None and r['status']=='uncertain'


def test_direct_exceedance_remains_contradictory_evidence(cfg):
    d=detail(cfg);d['diagnostics']['windows'][0]['direct_peak']=2500
    r=summarize(d,cfg.physics,cfg.reconstruction,'longitudinal')
    assert r['status']=='uncertain' and r['diagnostics']['decision']=='exceeds'
    assert search_metrics(cfg,candidate(cfg,r))['longitudinal']==1000


def test_upper_endpoint_unresolved(cfg):
    d=detail(cfg);a={}
    for i in range(6):
        a[f'fit_{i}_frequency_hz']=np.linspace(*cfg.physics.band_hz,10)
        a[f'fit_{i}_impedance']=np.linspace(500,1000,10)[:,None].astype(complex)
    d['diagnostics']['base_resolution_hz']=1e8
    r=summarize(d,cfg.physics,cfg.reconstruction,'longitudinal',a)
    assert r['diagnostics']['reconstructed_peak']['band_edge_unresolved']
    assert r['value'] is None


def test_gp_noise_and_historical_native_replacement(cfg):
    r=summarize(detail(cfg,bad=[1000,1000,1000,0,0,0]),cfg.physics,cfg.reconstruction,'longitudinal')
    c=candidate(cfg,r);h=copy.deepcopy(c);h.update(source_kind='common_band_history',evidence_verified=True,band_hz=list(cfg.physics.band_hz),wake_length_m=35)
    s=dict(candidates=[c],historical_observations=[h],rng=None)
    rows=Controller(cfg,s).training_rows('longitudinal')
    assert len(rows)==1 and rows[0][3] is False and rows[0][2]>=1


def test_old_direct_only_history_is_not_imported_in_new_mode(cfg):
    c=candidate(cfg,detail(cfg));c.update(source_kind='common_band_history',evidence_verified=True,band_hz=list(cfg.physics.band_hz),wake_length_m=35,metrics={'longitudinal':42})
    assert Controller(cfg,dict(candidates=[],historical_observations=[c],rng=None)).training_rows('longitudinal')==[]


def test_radius_does_not_shrink_for_overlapping_uncertainty(cfg):
    state=dict(candidates=[],rng=None,radius=.25,improving=0,not_improving=0);ctrl=Controller(cfg,state)
    old={'longitudinal':1000,'transverse':100000};new={'longitudinal':1200,'transverse':110000}
    u={k:dict(lower=v*.5,upper=v*1.5,unbounded=False) for k,v in old.items()}
    for _ in range(7):ctrl.update_radius(old,new,u,u)
    assert state['radius']==.25 and state['not_improving']==0
    narrow={k:dict(lower=v*.99,upper=v*1.01,unbounded=False) for k,v in new.items()}
    old_u={k:dict(lower=v*.99,upper=v*1.01,unbounded=False) for k,v in old.items()}
    for _ in range(6):ctrl.update_radius(old,new,old_u,narrow)
    assert state['radius']<.25


def test_screening_admission_not_formal_feasibility(cfg):
    r=summarize(detail(cfg,bad=[1000]*6),cfg.physics,cfg.reconstruction,'longitudinal');c=candidate(cfg,r)
    c['details']['transverse']=copy.deepcopy(r)
    a=screening_admission(c,cfg)
    assert a['ready'] and not a['qualified_feasibility']


def test_reconstructed_observation_persistence_and_db_idempotence(cfg):
    from workflows.rfgun_wake_thermal.storage import Store
    c=candidate(cfg,summarize(detail(cfg),cfg.physics,cfg.reconstruction,'longitudinal'));c['screening_metrics']=search_metrics(cfg,c)
    st=Store(cfg,'reconstructed');st.state['candidates']=[c];st.save();st.mirror();st.mirror()
    rows=st.db.get_all_records();assert len(rows)==1 and rows[0]['source']=='wf6.reconstructed_screening'
    assert st.checkpoint.rng_state['observation_mode']=='reconstructed_peak_screening'
    assert st.checkpoint.rng_state['search_observations'][0][1]['longitudinal']==1000
    st.close()


def test_stage_gates_use_reconstruction_and_exploration_remains_possible(cfg):
    from workflows.rfgun_wake_thermal.campaign import Campaign
    d=summarize(detail(cfg,values=(3000,3010,2990,3000,3010,2990)),cfg.physics,cfg.reconstruction,'longitudinal')
    c=candidate(cfg,d);campaign=object.__new__(Campaign);campaign.config=cfg
    assert not campaign.gated(c,'axis') and campaign.gated(c,'x')
    d=summarize(detail(cfg),cfg.physics,cfg.reconstruction,'longitudinal');c['details']['longitudinal']=d
    assert not campaign.gated(c,'x')
    assert campaign.gated(c,'thermal')  # missing transverse cannot pass
    assert cfg.search.exploration_fraction==.2


def test_transverse_oblique_peak_consensus(cfg):
    d=detail(cfg,values=(200000,201000,199000,200500,199500,200000));a={}
    # Both diagonal entries are small enough individually; a 45-degree response
    # exceeds the 150 kohm/m target, so no diagonal-only feasibility is allowed.
    for i in range(6):
        a[f'fit_{i}_frequency_hz']=np.linspace(*cfg.physics.band_hz,10)
        a[f'fit_{i}_impedance']=np.tile(np.array([1e5,1e5,1e5,1e5],complex),(10,1))
    r=summarize(d,cfg.physics,cfg.reconstruction,'transverse',a)
    assert r['diagnostics']['reconstructed_peak']['estimate']==200000
    assert r['diagnostics']['decision']=='exceeds'


def test_observed_uncertainty_is_not_collapsed_in_cost_score(cfg):
    c=Controller(cfg,dict(candidates=[],rng=None));x=np.zeros((1,12))
    low=c.score(x,1,{'longitudinal':3000,'transverse':200000})
    high=c.score(x,1,{'longitudinal':3000,'transverse':200000},{'longitudinal':{'relative_uncertainty':1},'transverse':{'relative_uncertainty':1}})
    assert high[0]>low[0]
