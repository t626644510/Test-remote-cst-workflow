"""No-CST checks for fixed-mesh TRK scan and generation-weighted SEE analysis."""
from pathlib import Path
import json
import numpy as np
import pytest
from workflows.trk_multipacting.trk_model import tasks, logical_grid, combined_sey, population
from workflows.trk_multipacting.trk_run import configure_macro, completed, digest
from workflows.trk_multipacting.model import Task

pytestmark = pytest.mark.no_cst


def pair(inc, out):
    d={}
    for kind,bins in [('Collision',inc),('Emission',out)]:
        d[f'1D Results\\SEE {kind} Information\\Current\\copper'] = dict(x=list(bins),y=list(bins.values()),xlabel='SEE Generation',ylabel='Current / A')
        d[f'1D Results\\Total {kind} Information\\Current\\copper'] = dict(x=[],y=[sum(bins.values())],xlabel='',ylabel='Current / A')
    return d


def test_grid_and_aliases():
    assert len(tasks()) == len({t.key for t in tasks()}) == 484
    assert len(logical_grid()) == 528
    assert {r['actual_key'] for r in logical_grid()} == {t.key for t in tasks()}
    assert sum(t.factor1 == 0 for t in tasks()) == 4


def test_generation_alignment_and_weighting():
    r=combined_sey(pair({0:10,1:2,2:1},{1:2,2:1}))
    assert [v['sey'] for v in r['by_generation']] == [.2,.5,0]
    assert r['combined_sey'] == pytest.approx(3/13)


def test_missing_nonzero_curve_is_not_zero():
    d=pair({0:2},{1:1});del d['1D Results\\SEE Emission Information\\Current\\copper']
    result=combined_sey(d)
    assert result['combined_sey']==.5
    assert result['unresolved_generation_curves']
    assert not result['by_generation']


def test_no_incident_has_no_sey():
    assert combined_sey(pair({},{}))['combined_sey'] is None


@pytest.mark.parametrize('final,end,expected',[ (0,2.2,0), (1,2,1)])
def test_population_terminal_convention(final,end,expected):
    a=np.array([[0,1,0,0,1,1,1,2],[1,2,0,0,2,1,1,2]],float)
    data,r=population(a,dict(initial=2,secondary=0,ionization=0,final=final,final_time_ns=end))
    assert r['final_alive']==expected
    assert data[0,1]==2


def test_population_bad_terminal_count():
    a=np.array([[0,1,0,0,1,1,1,2],[1,2,0,0,2,1,1,2]],float)
    with pytest.raises(ValueError,match='survivor'):
        population(a,dict(initial=2,secondary=0,ionization=0,final=2,final_time_ns=2))


def test_runtime_settings_avoid_geometry_parameters():
    s=dict(field_macro='With PredefinedField\n.UseLocalCopyOnly "False"\n.SetExternalField "True", "field.cst", "0.618*factor1", "phase", "0", "True"\nEnd With',tracking_macro='With TrackingSolver\n.Reset\n.AddTrackingSource "Particle", "particle1"\nEnd With')
    m=configure_macro(s,Task('particle4',.5,30))
    assert '"0.309", "30"' in m and '"particle4"' in m
    assert 'StoreParameter' not in m and 'Rebuild' not in m and 'Mesh.' not in m


def test_resume_only_accepts_durable_results(tmp_path):
    p=tmp_path/'cases'/'s01_f010_p000';p.mkdir(parents=True)
    (p/'task.json').write_text('{}')
    assert not completed(tmp_path)
    (p/'result.json').write_text(json.dumps({'status':'completed'}))
    assert len(completed(tmp_path))==1


def test_mesh_digest_on_supported_python(tmp_path):
    p=tmp_path/'mesh';p.write_bytes(b'abc')
    assert digest(p)=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
