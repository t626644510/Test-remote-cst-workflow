"""No-CST regression for the double-bend pilot and asynchronous phase barrier."""
from dataclasses import replace
from pathlib import Path
import math

import numpy as np
import pytest
import yaml

from workflows.rfgun_hom_target.config import load_config
from workflows.rfgun_hom_target.composite import CompositePlanner, collapse
from workflows.rfgun_hom_target.geometry import GeometryConstraints
from workflows.rfgun_hom_target.search import objective
from workflows.rfgun_hom_target.distributed.coordinator import issue_permit
from workflows.rfgun_hom_target.storage import CampaignStore

pytestmark = pytest.mark.no_cst


@pytest.fixture
def setup(tmp_path):
    doc = yaml.safe_load((Path(__file__).parents[1]/'workflows/rfgun_hom_target/config.dual.example.yaml').read_text(encoding='utf-8'))
    doc['workflow_5']['geometry']['bend_segments'] = 2
    doc['workflow_5']['physics']['z_range_mm'] = [-100.,100.]
    path = tmp_path/'cfg.yaml'
    path.write_text(yaml.safe_dump(doc), encoding='utf-8')
    cfg = load_config(path)
    cfg = replace(cfg, search=replace(cfg.search, max_solves=12, candidate_pool=16, candidate_draws=1024))
    p = dict(selfangle1=50., UpperHeight1=20., DownHeight1=8., Lin1=30., projection1=18., FolkHeight=15.,
             selfangle2=90., UpperHeight2=25., DownHeight2=10., Lin2=30., projection2=20., FolkHeight2=15.)
    plan = dict(bend_radii_mm=[25.,25.], adaptive_points=6,
                first_wave=[dict(id=f'C{i+1:02d}', parameters={**p,'selfangle1':float(i*10)}) for i in range(6)])
    state = dict(records=[], jobs={}, radius=None, improvements=0, no_improvement=0)
    return cfg, state, plan, p


@pytest.mark.parametrize('projection', [5.43, 8.155, 17., 25.])
def test_inverse_and_double_bend_inclusive_bounds(setup, projection):
    cfg,state,plan,p = setup
    planner = CompositePlanner(cfg,state,plan)
    p.update(projection1=projection, projection2=projection)
    full = planner.expand(p)
    assert full['inner_angle'] < 0 and full['inner_r'] == -25.
    assert full['inner_angle3'] > 0 and full['inner_r2'] == 25.
    assert collapse(full)['projection1'] == pytest.approx(projection, abs=1e-12)
    assert planner.geometry.feasible(full)
    if projection < 10.88:
        assert not GeometryConstraints(antenna_count=2).feasible(full)


@pytest.mark.parametrize('projection', [5.429,25.001,float('nan')])
def test_invalid_projection_rejected(setup, projection):
    cfg,state,plan,p = setup
    with pytest.raises(ValueError):
        CompositePlanner(cfg,state,plan).expand({**p,'projection1':projection})


def test_six_probes_wait_for_all_results_then_six_adaptive_slots(setup):
    cfg,state,plan,p = setup
    planner = CompositePlanner(cfg,state,plan)
    for i in range(6):
        assert planner.can_dispatch()
        full,source=planner.ask_async({},list(state['jobs'].values()))
        assert source == f'probe_C{i+1:02d}'
        state['jobs'][str(i)] = dict(parameters=full,state='dispatched')
    assert not planner.can_dispatch()
    for job in state['jobs'].values():
        job['state']='finished'
    assert planner.can_dispatch()
    for i in range(6,12):
        state['jobs'][str(i)] = dict(parameters=full,state='dispatched')
    assert planner.complete() and not planner.can_dispatch()


def test_outside_history_informs_gp_without_becoming_incumbent(setup, monkeypatch):
    cfg,state,plan,p=setup
    planner=CompositePlanner(cfg,state,plan)
    full=planner.expand(p)
    outside={**full,'inner_r2':25.,'inner_angle3':90.}
    state['records']=[dict(parameters=full,status='valid',objective=objective(430000,100000)),
        dict(parameters=outside,status='history_outside_domain',objective=objective(80000,100000))]
    x,y=planner.valid_training_data()
    assert len(x)==2 and x[1,10]>1
    for i in range(6):state['jobs'][str(i)]=dict(parameters=full,state='finished')
    candidate,source=planner.ask_async({},[])
    assert planner.geometry.feasible(candidate)
    assert source.startswith('adaptive_')
    # Failure cannot shrink or alter the valid-result streak.
    before=(state['radius'],state['no_improvement'])
    planner.observe(dict(status='geometry_failed'), math.inf)
    assert before==(state['radius'],state['no_improvement'])


def test_retry_and_failure_permits_share_twelve_hard_budget(tmp_path):
    store=CampaignStore(tmp_path/'campaign','contract',12)
    try:
        for i in range(14):
            request=dict(task_id='probe',request_id=f'r{i}',contract='contract',attempt=f'a{i}')
            reply=issue_permit(store,request,dict(id='probe',node='local'))
            assert ('number' in reply)==(i<12)
            assert issue_permit(store,request,dict(id='probe',node='local'))==reply
        assert store.state['solve_count']==12
    finally:store.close()
