"""No-CST regression for portable exports, terminal bounds and surface accounting."""
from pathlib import Path
import json
import sys
import subprocess
import numpy as np
import pytest
from workflows.trk_multipacting.trk_model import population
from workflows.trk_multipacting.trk_late import event_windows
from workflows.trk_multipacting.endpoints import terminal_collision_bounds
from workflows.trk_multipacting.surfaces import reduce_surfaces
from workflows.trk_multipacting.analysis import analyze
from workflows.trk_multipacting.report import report
from workflows.trk_multipacting.io import write_json, fingerprint

pytestmark=pytest.mark.no_cst


def bounded_fixture(missing=1):
    a=np.array([[0,10,0,0,4,1,1,2],[1,11,1,4,6,2,2,2],
                [2,12,1,4,6,4,4,2],[3,13,1,4,6,8,8,2]],float)
    g=np.array([[0,0],[1,1],[2,1],[3,1]],float)
    st=dict(initial=1,secondary=3,ionization=0,final=3-missing,final_time_ns=6,
            into_solid=0,collided=1+missing,passed=0,blocked=0,dying=0)
    c={}
    for title,x,y,number in [('Collision',[0,1],[1,3*missing],1+missing),('Emission',[1],[14],3)]:
        c[f'1D Results\\Total {title} Information\\Current\\copper']=dict(y=[sum(y)],xlabel='',ylabel='Current / A')
        c[f'1D Results\\SEE {title} Information\\Current\\copper']=dict(x=x,y=y,xlabel='SEE Generation',ylabel='Current / A')
        c[f'1D Results\\Total {title} Information\\Particles\\copper']=dict(y=[number])
    return a,g,st,c


@pytest.mark.parametrize('missing',[1,2])
def test_terminal_count_is_inferred_not_hardcoded(missing):
    a,g,st,c=bounded_fixture(missing)
    bounds=terminal_collision_bounds(a,st)
    assert bounds['ambiguous_terminal_collisions']==missing
    result,meta=population(a,st)
    assert result[-1,1]==st['final']
    assert meta['terminal_charge_lower_C']<=meta['terminal_charge_upper_C']
    windows=event_windows(a,g,st,c,1000,strict_currents=False)
    final=windows['final_window']
    assert final['sey_lower']<=final['sey']<=final['sey_upper']
    assert final['incident_events']==st['collided']
    assert final['N_end']==st['final']
    if missing==1:
        assert final['sey_lower']==pytest.approx(14/9)
        assert final['sey_upper']==pytest.approx(14/3)


def test_terminal_mismatch_requires_native_count_evidence():
    a,g,st,c=bounded_fixture()
    st['collided']+=1
    with pytest.raises(ValueError,match='classification'):
        population(a,st)


def test_bound_surfaces_require_native_counts_and_charge_conservation(tmp_path):
    a,g,st,c=bounded_fixture()
    events=dict(track_index=np.arange(4),kind=np.array([0,1,1,1]),time_ns=np.array([4,4,4,4]),
                weight_C=np.array([1,2,4,8]),generation=np.array([0,1,1,1]),solid_index=np.zeros(4,int))
    windows=event_windows(a,g,st,c,1000,strict_currents=False)
    audit=reduce_surfaces(events,[dict(name='copper')],a,g,st,c,windows,tmp_path)
    assert audit['validated']
    assert audit['final'][0]['sey_lower']==windows['final_window']['sey_lower']
    events['solid_index'][0]=-1
    audit=reduce_surfaces(events,[dict(name='copper')],a,g,st,c,windows,tmp_path)
    assert not audit['validated'] and audit['final'][0]['sey'] is None


def write_export(path: Path):
    path.mkdir()
    a,g,st,c=bounded_fixture()
    st.update(steps=100,mesh_cells=123)
    labels={'initial':'Initial particle number','secondary':'Secondary particles created','final':'Final particle number',
            'collided':'Particles collided','passed':'Particles passed away','blocked':'Particles blocked in emission',
            'into_solid':'Particles emitted into solid','dying':'Particles dying in emission model',
            'ionization':'Ionization particles created','steps':'Total number of timesteps','mesh_cells':'Number of tetrahedrons'}
    text='Statistics for particle source particle7:\n'+'\n'.join(f'{label}: {st[key]}' for key,label in labels.items())
    text+='\nFinal simulation time 6 ns\nParticle Tracking Solver successful.\nParticle Tracking Solver has been aborted.\n'
    (path/'Model.log').write_text(text)
    write_json(path/'raw_curves.json',c)
    np.savetxt(path/'trajectory_lifetimes.txt',a,header='lifetimes',comments='')
    np.savetxt(path/'trajectory_extra.txt',g,header='index generation',comments='')
    return path


def test_legacy_export_report_is_portable_and_preserves_inputs(tmp_path):
    source=write_export(tmp_path/'legacy')
    before=fingerprint(source.iterdir())
    out=tmp_path/'analysis'
    result=analyze(source,out,label='custom-model',frequency_mhz=1000)
    assert result['source_name']=='particle7' and result['status']=='aborted_saved'
    assert result['last_3RF']['sey_lower']<result['last_3RF']['sey_upper']
    html=report([out],tmp_path/'report').read_text(encoding='utf8')
    assert 'custom-model' in html and 'MP5' not in html and 'MP6-3' not in html
    assert before==fingerprint(source.iterdir())
    assert (tmp_path/'report/comparison.svg').exists()


def test_analysis_rejects_inplace_and_missing_frequency(tmp_path):
    source=write_export(tmp_path/'legacy')
    with pytest.raises(ValueError,match='differ'):
        analyze(source,source)
    with pytest.raises(ValueError,match='frequency'):
        analyze(source,tmp_path/'out')


def test_cli_help_imports_without_cst():
    from workflows.trk_multipacting.cli import parser
    args=parser().parse_args(['report','--input','a','b','--output','c'])
    assert len(args.input)==2
    assert 'cst.interface' not in sys.modules


def test_export_refuses_pic_before_connecting(tmp_path):
    from workflows.trk_multipacting.export import export_saved
    project=tmp_path/'PIC.cst';project.write_text('input')
    raw=tmp_path/'PIC/Result';raw.mkdir(parents=True)
    (raw/'Model.log').write_text('PIC solver finished')
    with pytest.raises(ValueError,match='TRK'):
        export_saved(project,tmp_path/'out','not-installed')


def test_surface_mapping_rejects_distant_and_ambiguous_geometry(tmp_path):
    vtk=pytest.importorskip('vtk')
    from workflows.trk_multipacting.surfaces import map_events
    a,g,st,c=bounded_fixture()
    source=tmp_path/'source';geom=source/'surface_time';geom.mkdir(parents=True)
    output=tmp_path/'output';output.mkdir()
    (source/'model.gex').write_text('<root><Shape name="component:copper" material="Copper"/></root>')
    (geom/'solids.txt').write_text('0|component:copper|True\n')
    cube=vtk.vtkCubeSource();cube.Update()
    triangles=vtk.vtkTriangleFilter();triangles.SetInputData(cube.GetOutput());triangles.Update()
    writer=vtk.vtkSTLWriter();writer.SetFileName(str(geom/'solid_0.stl'));writer.SetInputData(triangles.GetOutput());writer.Write()
    p=np.c_[np.arange(4),np.full((4,6),100.)]
    np.savetxt(geom/'endpoint_positions.txt',p,header='positions',comments='')
    events,solids=map_events(source,output,a,g,st)
    assert np.all(events['solid_index']==-1)
    assert len(solids)==1
    p[:,1:]=0.5
    np.savetxt(geom/'endpoint_positions.txt',p,header='positions',comments='')
    events,_=map_events(source,output,a,g,st)
    assert np.all(events['solid_index']==0)
    (source/'model.gex').write_text('<root><Shape name="component:copper" material="Copper"/><Shape name="component:duplicate" material="Copper"/></root>')
    (geom/'solids.txt').write_text('0|component:copper|True\n1|component:duplicate|True\n')
    (geom/'solid_1.stl').write_bytes((geom/'solid_0.stl').read_bytes())
    events,_=map_events(source,output,a,g,st)
    assert np.all(events['solid_index']==-1)


def test_generation_total_discrepancy_is_advisory():
    from workflows.trk_multipacting.trk_model import combined_sey
    a,g,st,c=bounded_fixture()
    c['1D Results\\SEE Collision Information\\Current\\copper']['y'][0] *= 2
    result=combined_sey(c, strict_currents=False)
    assert result['statistical_warnings'] and not result['by_generation']
    assert result['combined_sey'] is not None
    with pytest.raises(ValueError,match='disagrees'):
        combined_sey(c)


def test_saved_source_name_is_read_from_log(tmp_path):
    source=write_export(tmp_path/'legacy')
    log=source/'Model.log'
    log.write_text(log.read_text().replace('particle7','Cathode source'))
    assert analyze(source,tmp_path/'analysis',frequency_mhz=1000)['source_name']=='Cathode source'
    with pytest.raises(ValueError,match='differ'):
        analyze(source,source/'surface_time',frequency_mhz=1000)


@pytest.mark.parametrize('action',['export','scan'])
def test_initialization_failure_closes_only_captured_session(tmp_path,monkeypatch,action):
    import os
    import cst_optimization.core as core
    import cst_optimization.core.connection as connections
    import cst_optimization.core.results as results
    import cst_optimization.core.session_cleanup as cleanup
    from workflows.trk_multipacting.export import export_saved
    from workflows.trk_multipacting import trk_run
    from workflows.trk_multipacting.model import Task
    calls=[]
    class Connection:
        pid=os.getpid()
        def __init__(self,*args,**kwargs):pass
        def connect(self):pass
        def set_quiet_mode(self,value):raise RuntimeError('quiet setup failed')
    class Reader:
        def __init__(self,*args,**kwargs):pass
        def list_tree_items(self):return []
        def invalidate_cache(self):pass
    def close(connection,pid,created):
        calls.append((pid,created));return {'closed':True}
    monkeypatch.setattr(core,'init_cst_path',lambda _:None)
    monkeypatch.setattr(connections,'CSTConnection',Connection)
    monkeypatch.setattr(results,'ResultReader',Reader)
    monkeypatch.setattr(cleanup,'close_owned_session',close)
    monkeypatch.setattr(trk_run,'close_owned_session',close)
    project=tmp_path/'saved.cst';project.write_text('saved')
    raw=tmp_path/'saved/Result';raw.mkdir(parents=True)
    (raw/'Model.log').write_text('Particle Tracking Solver successful.')
    (raw/'trajectories.bix').write_bytes(b'trajectories')
    monkeypatch.setattr(trk_run,'prepare',lambda *args:{'project':str(project)})
    monkeypatch.setattr(trk_run,'tasks',lambda:[Task('particle1',0,0)])
    with pytest.raises(RuntimeError,match='quiet setup failed'):
        if action=='export':export_saved(project,tmp_path/'export','mock')
        else:trk_run.run(tmp_path/'scan',project,cst_library='mock')
    assert len(calls)==1 and calls[0][0]==os.getpid()
