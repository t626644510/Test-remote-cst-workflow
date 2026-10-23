"""Verified same-physics historical GP transfer without relabelling observations."""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
import time,json
from .config import Config,load_config
from .geometry import Geometry
from .io import read_json,atomic_json,digest,validate_manifest
from .observations import Observation
from .search import Sample

def compatibility(config: Config) -> dict:
    """SI excitation/RF definitions and fixed mm geometry must be identical.

    Search bounds and weights may change. Other template/fixed-geometry rounds
    cannot enter this transfer, even if their parameter names happen to match.
    """
    r=config.runtime
    return dict(physics=asdict(config.physics),reconstruction=asdict(config.reconstruction),
        fixed_parameters=config.fixed_parameters,port_outer_policy=config.port_outer_policy,
        port_wall_mm=config.port_wall_mm,fixed_port_outer_mm=config.fixed_port_outer_mm,
        template_sha256=digest(config.paths.template),backend=dict(precision=r.precision,
        copper_terms=r.copper_terms,port_layer_m=r.port_layer_m,upstream_revision=r.upstream_revision))

def validate_seed(record: dict,baseline: dict,config: Config) -> None:
    """Only explicit recorded parameter edits to a verified old candidate are allowed."""
    path=Path(record['parent_state'])
    if digest(path)!=record['parent_state_sha256']:raise ValueError('Seed parent changed')
    old=next(c for c in read_json(path)['candidates'] if c['id']==record['candidate_id'])
    expected=dict(old['parameters']);expected.update(record['changes'])
    if expected!=baseline or Geometry(config).violations(baseline):raise ValueError('Seed edits do not match new geometry')

def build_bundle(parent: Path,config: Config) -> dict:
    """Import immutable analyzed stages at their original coordinates, per metric."""
    old=load_config(parent/'config.snapshot.json');provenance=read_json(parent/'provenance.json')
    if (json.dumps(compatibility(old),sort_keys=True)!=json.dumps(compatibility(config),sort_keys=True)
            or provenance['template_sha256']!=digest(config.paths.template)):
        raise ValueError('Historical physics, fixed geometry or source template differs')
    state=read_json(parent/'state.json');merged={};evidence=[]
    from .quality_revision import load_revision,revised_observations
    revision=load_revision(state)
    for item in state.get('results',[]):
        path=Path(item['result_path'])
        if digest(path)!=item['result_sha256']:raise ValueError('Changed registered history result')
        result=read_json(path);candidate=state['candidates'][result['candidate_index']]
        if result['parameters']!=candidate['parameters']:raise ValueError('History parameter mismatch')
        directory=Path(result['field_directory'])
        if digest(directory/'wake.npz')!=result['raw_sha256']:raise ValueError('Historical numerical wake changed')
        matches=[]
        for m in directory.glob('analysis_*/manifest.json'):
            analyzed=read_json(m.parent/'result.json')
            if all(analyzed.get(k)==result.get(k) for k in ('stage','parameters','observations','raw_sha256')):
                validate_manifest(m.parent,read_json(m));matches.append(str(m))
        if not matches:raise ValueError('Verified historical analysis missing')
        effective=revised_observations(item,result,revision)
        merged.setdefault(candidate['id'],{}).update(effective)
        record=dict(result=str(path),sha256=item['result_sha256'],analyses=matches)
        if item['key'] in revision:record['observation_revision']=revision[item['key']]
        evidence.append(record)
    rows=[]
    for c in state['candidates']:
        if not c['observations']:continue
        if merged.get(c['id'])!=c['observations']:raise ValueError('State/immutable observations disagree')
        if Geometry(config).training_violations(c['parameters']):raise ValueError('History outside original physical domain')
        for value in c['observations'].values():Observation(**value)
        rows.append(dict(id=c['id'],parameters=c['parameters'],observations=c['observations']))
    return dict(version=1,compatibility=compatibility(config),parent=str(parent),
        parent_state_sha256=digest(parent/'state.json'),candidates=rows,evidence=evidence,
        semantics='historical training only; original coordinates; no native quota, feasibility, trust or budget credit')

def load_samples(record: dict | None,config: Config) -> list[Sample]:
    """Require the frozen training bundle on every proposal; current data win per metric."""
    if not record:return []
    if digest(record['path'])!=record['sha256']:raise ValueError('History bundle changed')
    bundle=read_json(record['path'])
    if bundle['compatibility']!=compatibility(config):
        # JSON converts immutable tuples to lists; compare canonical JSON.
        import json
        if json.dumps(bundle['compatibility'],sort_keys=True)!=json.dumps(compatibility(config),sort_keys=True):
            raise ValueError('History bundle no longer compatible')
    return [Sample(c['parameters'],{k:Observation(**v) for k,v in c['observations'].items()},historical=True)
            for c in bundle['candidates']]

def create_cooling_revision(config_path: Path,parent: Path,seed_id: str='candidate_0038') -> dict:
    """Prepare STOP-marked narrowed search, carrying the same 48 h clock once."""
    from .campaign import Campaign
    from .revision import verify_parent
    from .state import WriterLock
    with WriterLock(parent/'coordinator.lock'):
        state=verify_parent(parent);old_hash=digest(parent/'state.json')
        config=load_config(config_path)
        if Path(config.paths.output_dir).resolve()==parent.resolve():raise ValueError('Distinct revision root required')
        bundle=build_bundle(parent,config)
        seed=next(c for c in state['candidates'] if c['id']==seed_id)
        baseline=dict(seed['parameters']);baseline['DownHeight']=max(160.,config.bounds['DownHeight'][0])
        record=dict(parent_state=str(parent/'state.json'),parent_state_sha256=old_hash,candidate_id=seed_id,
                    changes={'DownHeight':baseline['DownHeight']})
        campaign=Campaign(config_path)
        if campaign.store.cap!=state['cap_seconds']:raise ValueError('Round cap changed')
        campaign.initialize(baseline,reviewed_seed=record)
        path=campaign.root/'history_bundle.json';atomic_json(path,bundle)
        data=campaign.store.data
        data.update(active_seconds=state['active_seconds'],search_active_offset=state['active_seconds'],
                    exploration_seconds=0.,radius=config.search.radius,status='paused',
                    history_bundle=dict(path=str(path),sha256=digest(path)),search_seed=baseline)
        audit=dict(at=time.time(),parent=str(parent),parent_state_sha256=old_hash,
                   carried_active_seconds=state['active_seconds'],cap_seconds=state['cap_seconds'],
                   remaining_hours=(state['cap_seconds']-state['active_seconds'])/3600,
                   seed=record,historical_coordinates=len(bundle['candidates']),native_imports=0)
        data['budget_origin']=audit
        (campaign.root/'STOP').write_text('Prepared cooling revision. Await explicit user start.\n',encoding='utf-8')
        campaign.store.save();campaign.report();atomic_json(campaign.root/'cooling_revision.json',audit)
        if digest(parent/'state.json')!=old_hash:raise ValueError('Parent changed during revision')
        return audit
