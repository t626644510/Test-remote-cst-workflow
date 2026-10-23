"""Two-antenna sign conventions, fork geometry and fourteen-dimensional search."""
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from workflows.rfgun_hom_target.config import load_config, ConfigurationError
from workflows.rfgun_hom_target.geometry import GeometryConstraints
from workflows.rfgun_hom_target.search import CandidatePlanner
from workflows.rfgun_hom_target import runtime as rt

pytestmark = pytest.mark.no_cst


@pytest.fixture
def dual(tmp_path):
    doc = yaml.safe_load((Path(__file__).parents[1] / 'workflows/rfgun_hom_target/config.dual.example.yaml').read_text())
    doc['workflow_5']['physics']['z_range_mm'] = [-100,100]
    doc['workflow_5']['search']['candidate_pool'] = 16
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(doc))
    return load_config(path), path, doc


@pytest.fixture
def point():
    return dict(selfangle2=45.,UpperHeight2=26.,DownHeight2=4.,Lin2=12.,inner_angle3=71.,inner_r2=12.,
                selfangle1=90.,UpperHeight1=26.,DownHeight1=15.,Lin1=27.,inner_angle=-60.,inner_r=-12.,
                FolkHeight=5.43,FolkHeight2=10.)


def test_dual_example_mapping_and_independent_normalization(dual, point):
    cfg,_,_=dual
    assert len(cfg.parameters)==14 and cfg.geometry.antenna_count==2
    assert next(p for p in cfg.parameters if p.name=='Lin1').cst_name=='Lin'
    planner=CandidatePlanner(cfg,dict(records=[],radius=None))
    x=np.array([point[n] for n in planner.space.names])
    np.testing.assert_allclose(planner.space.denormalize(planner.space.normalize(x)),x)
    assert planner.geometry.feasible(point)


@pytest.mark.parametrize('changes', [dict(inner_angle=60.),dict(inner_r=12.),dict(inner_angle=-90.01),
    dict(inner_r=-5.43),dict(inner_angle=-5.),dict(UpperHeight1=5.),dict(DownHeight1=2.),
    dict(Lin1=15.),dict(FolkHeight=5.4299),dict(FolkHeight2=5.4299)])
def test_dual_rejects_either_antenna_or_fork_violation(point, changes):
    point.update(changes)
    assert not GeometryConstraints(antenna_count=2).feasible(point)


def test_mirrored_antenna_has_same_physical_feasibility(point):
    geometry=GeometryConstraints(antenna_count=2)
    for angle in (15.,45.,60.,90.,110.):
        for radius in (5.44,6.,12.,25.):
            left={**point,'inner_angle':-angle,'inner_r':-radius}
            right={**point,'inner_angle3':angle,'inner_r2':radius}
            assert geometry.feasible(left)==geometry.feasible(right)
    assert geometry.feasible({**point,'inner_angle':-90.,'FolkHeight2':5.43})


def test_dual_requires_all_coordinates_even_if_all_new_fields_missing(point):
    for name in ('selfangle1','UpperHeight1','DownHeight1','Lin1','inner_angle','inner_r','FolkHeight','FolkHeight2'):
        point.pop(name)
    assert not GeometryConstraints(antenna_count=2).feasible(point)
    assert GeometryConstraints().feasible(point)


@pytest.mark.parametrize('mutation',['missing','positive_angle','positive_radius','count','fractional_count','fork_floor'])
def test_dual_configuration_fails_closed(dual, mutation):
    _,path,doc=dual
    root=doc['workflow_5']
    if mutation=='missing':root['parameters'].pop()
    if mutation in ('positive_angle','positive_radius'):
        name='inner_angle' if mutation=='positive_angle' else 'inner_r'
        next(p for p in root['parameters'] if p['name']==name)['upper']=1
    if mutation=='count':root['geometry']['antenna_count']=3
    if mutation=='fractional_count':root['geometry']['antenna_count']=2.0
    if mutation=='fork_floor':root['geometry']['minimum_fork_length_mm']=0
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ConfigurationError):load_config(path)


def test_both_signed_parameters_reach_existing_cst_wrapper_without_flipping(dual,point,tmp_path,monkeypatch):
    cfg,_,_=dual
    evaluator=object.__new__(rt.CSTEvaluator)
    evaluator.config=cfg;evaluator.template=tmp_path/'source.cst';evaluator.info={'length_unit':'cm'}
    path=tmp_path/'candidate.cst';written={}
    monkeypatch.setattr(rt,'copy_verified_project',lambda *a:(path,{}))
    monkeypatch.setattr(rt,'metadata',lambda p:dict(length_unit='cm',parameters=written))
    def update(mapping,**kwargs):
        assert kwargs=={'use_full_rebuild':True};written.update(mapping);return True
    @contextmanager
    def project(*args):yield SimpleNamespace(update_parameters=update,save=lambda **k:True)
    monkeypatch.setattr(evaluator,'_project',project)
    assert evaluator._prepare(point,tmp_path)==path
    assert 'Lin1' not in written and written['Lin']==2.7
    assert written['inner_angle']==-60. and written['inner_r']==-1.2
    assert written['inner_angle3']==71. and written['inner_r2']==1.2
    assert written['FolkHeight']==pytest.approx(.543)
    assert rt.read_baseline(path,cfg)==pytest.approx(point)


def test_fourteen_dimensional_search_and_zero_feasible_region(dual,point):
    cfg,_,_=dual
    state=dict(records=[dict(parameters=point,status='valid',objective=1.)],radius=None)
    planner=CandidatePlanner(cfg,state)
    candidate,source=planner.ask(point)
    assert len(candidate)==14 and source=='coverage_maximin'
    assert planner.geometry.feasible(candidate) and candidate['inner_r']<0 and candidate['inner_angle']<0
    assert planner.valid_training_data()[0].shape==(1,14)
    impossible=replace(cfg,parameters=tuple(replace(p,lower=1.,upper=2.) if p.name=='FolkHeight' else p for p in cfg.parameters),
                       search=replace(cfg.search,candidate_draws=1000))
    with pytest.raises(ValueError,match='No unseen feasible'):
        CandidatePlanner(impossible,dict(records=[],radius=None)).ask(point)
