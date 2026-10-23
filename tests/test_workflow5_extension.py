"""No-CST additional-budget import, replay and failure isolation."""
from dataclasses import replace
import json
import pytest

from test_workflow5_seeding import archive
from workflows.rfgun_hom_target.extension import import_completed
from workflows.rfgun_hom_target.postprocess import analyze_bundle
from workflows.rfgun_hom_target.storage import CampaignStore, atomic_json, fingerprint, project_manifest
from workflows.rfgun_hom_target.search import Campaign
from workflows.rfgun_hom_target.runtime import read_baseline

pytestmark = pytest.mark.no_cst


@pytest.fixture
def completed(archive):
    config, root, template, bundle = archive
    previous = config.as_dict()
    identity = dict(settings={k:v for k,v in previous.items() if k!='paths'}, template=project_manifest(template))
    state = json.loads((root/'state.json').read_text())
    processed = analyze_bundle(bundle, mode_policy='largest_two')
    state['records'][0].update(status='valid', modes=processed.to_dict(), worst=processed.worst_impedance_ohm_per_m)
    state.update(status='budget_exhausted', contract=fingerprint(identity), jobs={})
    atomic_json(root/'config.resolved.json', previous)
    atomic_json(root/'execution_identity.json', identity)
    atomic_json(root/'state.json', state)
    return replace(config, search=replace(config.search,max_solves=15,coverage_points=10,candidate_pool=16)), root, template


def test_extension_replays_and_limits_additional_calls_to_15(completed):
    config, root, template = completed
    before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
    store = CampaignStore(config.paths.output_dir, 'new', 15)
    try:
        import_completed(config,store,template,root)
        assert store.state['solve_count']==0 and len(store.state['records'])==1
        assert store.state['records'][0]['history_import']
        assert store.state['extension_provenance']['previous_solves']==1
        # Keep imported synthetic point above threshold so the test exercises
        # the extension's hard budget instead of the standard early-stop path.
        store.state['records'][0].update(worst=1e9,objective=10.)
        calls=[]
        def evaluate(parameters, attempt, reserve):
            reserve(str(attempt)); calls.append(parameters)
            return dict(status='valid',worst=2e9)
        report=Campaign(config,store,evaluate).run(read_baseline(template,config))
        assert report['status']=='budget_exhausted' and len(calls)==15
        assert report['solve_count']==15 and len(store.state['reservations'])==15
        assert all(p.read_bytes()==data for p,data in before.items())
    finally:
        store.close()


@pytest.mark.parametrize('mutation',['template','solver','sampling','mapping','active','inflight','identity','field'])
def test_extension_refuses_incompatible_or_corrupt_history(completed, mutation):
    config,root,template=completed
    if mutation=='template': template.write_bytes(b'changed')
    if mutation=='solver': config=replace(config,solver=replace(config.solver,mode_count=5))
    if mutation=='sampling': config=replace(config,physics=replace(config.physics,z_samples=103))
    if mutation=='mapping': config=replace(config,parameters=(replace(config.parameters[0],cst_name='other'),*config.parameters[1:]))
    if mutation in {'active','inflight','identity'}:
        state=json.loads((root/'state.json').read_text())
        if mutation=='active': state['status']='running'
        if mutation=='inflight': state['jobs']={'job':{'state':'running'}}
        if mutation=='identity': state['contract']='changed'
        atomic_json(root/'state.json',state)
    if mutation=='field':
        field=next(root.rglob('energy.csv')); field.write_text('U_J,Q_wall_postprocess\n0,1000\n')
    store=CampaignStore(config.paths.output_dir,'new',15)
    try:
        with pytest.raises(ValueError): import_completed(config,store,template,root)
        assert not store.state['records'] and store.state['solve_count']==0
    finally:
        store.close()
