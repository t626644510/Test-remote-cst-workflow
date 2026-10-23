"""No-CST tests of weighted late windows, censoring and finite subset completion."""
from pathlib import Path
import json
import numpy as np
import pytest
from workflows.trk_multipacting.trk_late import event_windows
from workflows.trk_multipacting import trk_supervise as s
from workflows.trk_multipacting.trk_run import generation_lifetime_macro
pytestmark=pytest.mark.no_cst

def fixture(end=4,final=1):
    a=np.array([[0,10,0,0,1,1,1,2],[1,11,1,1,2,2,2,2],[2,12,1,2,end,3,3,2]],float)
    stats=dict(initial=1,secondary=2,ionization=0,final=final,final_time_ns=end if final else end+5,
               into_solid=0,collided=2 if final else 3,passed=0,blocked=0,dying=0)
    curves={}
    for kind,x,y in [('Collision',[0,1] if final else [0,1,2],[1,2] if final else [1,2,3]),('Emission',[1,2],[2,3])]:
        curves[f'1D Results\\Total {kind} Information\\Current\\copper']=dict(y=[sum(y)])
        curves[f'1D Results\\SEE {kind} Information\\Current\\copper']=dict(x=x,y=y)
    return a,np.array([[0,0],[1,1],[2,2]]),stats,curves

def test_late_window_weighted_not_count_ratio():
    r=event_windows(*fixture(),1000,3)
    assert r['final_window']['sey']==pytest.approx(1.5)
    assert r['final_window']['secondary_events']==r['final_window']['incident_events']==1
    assert r['final_window']['start_ns']==1 and r['final_window']['end_ns']==4
    assert r['final_window']['N_end']==1

def test_no_collision_keeps_undefined_even_with_alive_particles():
    r=event_windows(*fixture(end=10),1000,3)
    assert r['final_window']['sey'] is None and r['final_window']['N_end']==1

def test_all_dead_retains_end_and_undefined_empty_window():
    r=event_windows(*fixture(end=5,final=0),1000,3)
    assert r['final_window']['end_ns']==10 and r['final_window']['N_end']==0
    assert r['final_window']['sey'] is None

def test_short_run_is_not_a_three_rf_window():
    r=event_windows(*fixture(),500,3)
    assert not r['window_complete'] and r['final_window'] is None

def test_current_mismatch_rejected():
    a,g,st,c=fixture();c['1D Results\\Total Collision Information\\Current\\copper']['y']=[100]
    with pytest.raises(ValueError,match='currents'):event_windows(a,g,st,c,1000)

def test_macro_exports_generation_once_per_trajectory():
    m=generation_lifetime_macro(Path('life.txt'),Path('gen.txt'))
    assert 'Dim gs As Variant' in m and 'SEEGeneration' in m
    assert 'For Output As #2' in m and 'Close #2' in m
    assert m.count('LoadTrajectoryData')==1

def test_finite_selected_subset_does_not_launch_other_keys(tmp_path,monkeypatch):
    key=s.tasks()[0].key;template=tmp_path/'MP5.cst'
    plan=dict(keys=[key],cases=[],report_dir=str(tmp_path/'report'),template=str(template),solve_limit_seconds=600)
    selection=tmp_path/'input.json';s.write_json(selection,plan)
    monkeypatch.setattr(s,'selected_report',lambda _:None)
    monkeypatch.setattr(s,'completed',lambda _: {key:{}})
    def forbidden(*a,**k):raise AssertionError('Must not launch unselected cases')
    monkeypatch.setattr(s.subprocess,'Popen',forbidden)
    s.Supervisor(tmp_path,template,'unused',selection=selection).run()
    assert s.read_json(tmp_path/'guard_state.json')['status']=='complete'
    assert s.read_json(tmp_path/'selection.json')==plan

def test_selection_change_rejected_on_resume(tmp_path,monkeypatch):
    template=tmp_path/'MP5.cst';keys=[s.tasks()[0].key]
    old=dict(keys=keys,template=str(template),solve_limit_seconds=600)
    s.write_json(tmp_path/'selection.json',old)
    other=dict(old,keys=[s.tasks()[1].key]);s.write_json(tmp_path/'changed.json',other)
    with pytest.raises(ValueError,match='Frozen selection changed'):
        s.Supervisor(tmp_path,template,'unused',selection=tmp_path/'changed.json').run()


def test_advisory_currents_preserve_sey_and_record_difference():
    a,g,st,c=fixture()
    c['1D Results\\Total Collision Information\\Current\\copper']['y']=[100]
    c['1D Results\\SEE Collision Information\\Current\\copper']['y']=[1,2.01]
    r=event_windows(a,g,st,c,1000,strict_currents=False)
    assert r['final_window']['sey']==pytest.approx(1.5)
    assert len(r['statistical_warnings'])==2
    assert r['current_check_policy']=='advisory'
