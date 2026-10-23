"""Offline, versioned observation reassessment without solving or replacing evidence.

Original stage results, fits, signed wakes and parent campaigns stay immutable.
Only a paused, locked campaign may adopt an explicitly prepared revision. No
clock is activated: units and physical contracts remain those of the source.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from .config import Config, load_config
from .io import atomic_json, digest, read_json, validate_manifest
from .observations import Observation, from_reconstruction, feasibility
from .peak_consensus import VERSION, summarize
from .state import WriterLock

POLICIES=('local-reconstructed-quality-v2',VERSION)


def load_revision(state: dict) -> dict:
    """Verify the committed revision index before replaying any old result."""
    record=state.get('observation_revision')
    if not record:return {}
    if digest(record['path'])!=record['sha256']:raise ValueError('Observation revision changed')
    revision=read_json(record['path'])
    if revision['policy'] not in POLICIES or revision['contract']!=state['contract']:
        raise ValueError('Observation revision contract differs')
    if not set(revision['stages'])<=set(state['completed_stage_keys']):
        raise ValueError('Observation revision contains foreign stages')
    return revision['stages']


def revised_observations(item: dict, result: dict, revision: dict) -> dict:
    """Apply verified RF/power assessments; raw results and field values stay exact."""
    entry=revision.get(item['key'])
    if entry is None:return copy.deepcopy(result['observations'])
    if (entry['source_result_path']!=item['result_path'] or entry['source_result_sha256']!=item['result_sha256']
            or entry['parameters']!=result['parameters'] or entry['raw_sha256']!=result['raw_sha256']):
        raise ValueError('Reassessment source identity differs')
    if digest(entry['summary_path'])!=entry['summary_sha256']:raise ValueError('Reassessment summary changed')
    summary=read_json(entry['summary_path'])
    if summary['diagnostics']['reconstructed_peak']['method'] not in POLICIES:raise ValueError('Wrong reassessment policy')
    obs=from_reconstruction(summary)
    metric='longitudinal' if result['stage']=='axis' else 'transverse_x'
    if metric!=entry['metric']:raise ValueError('Reassessment metric differs')
    output=copy.deepcopy(result['observations'])
    if obs is None:output.pop(metric,None)
    else:output[metric]=obs.as_dict()
    if 'power_observations' in entry:
        if (result['stage']!='axis' or digest(entry['source_power_path'])!=entry['source_power_sha256']):
            raise ValueError('Reassessment power source changed')
        if not set(entry['power_observations'])<=set(('heat_1','heat_2','leak_2','leak_3')):
            raise ValueError('Foreign reassessment power metric')
        for name in ('heat_1','heat_2','leak_2','leak_3'):output.pop(name,None)
        output.update({k:Observation(**v).as_dict() for k,v in entry['power_observations'].items()})
    return output


def assert_paused(root: Path, state: dict) -> None:
    """Require STOP, drained lanes and a dead recorded coordinator; never kill it."""
    if state['status']!='paused' or state.get('pending') or state.get('prefetch') or not (root/'STOP').exists():
        raise RuntimeError('Reassessment adoption requires a fully paused STOP campaign')
    if (root/'owner.json').exists():
        from .cst_prepare import ProcessIdentity
        owner=read_json(root/'owner.json')
        if ProcessIdentity(**dict(owner,command=tuple(owner['command']))).alive():
            raise RuntimeError('Recorded coordinator still alive')


def reassess_result(config: Config, path: Path, expected_sha: str, output: Path,
                    analyses: list[str] | None = None) -> dict:
    """Reassess saved fits with their original spectra; no field reconstruction.

    Loading reconstruction.npz only rechecks the existing band-edge evidence
    against the new contributor union. No raw HDF5 or electromagnetic run needed.
    """
    if digest(path)!=expected_sha:raise ValueError('Registered source result changed')
    result=read_json(path);field=Path(result['field_directory'])
    if digest(field/'wake.npz')!=result['raw_sha256']:raise ValueError('Saved signed wake changed')
    matches=[]
    for m in ([Path(p) for p in analyses] if analyses is not None else sorted(field.glob('analysis_*/manifest.json'))):
        original=read_json(m.parent/'result.json')
        if all(original.get(k)==result.get(k) for k in ('stage','parameters','observations','raw_sha256')):
            validate_manifest(m.parent,read_json(m));matches.append(m)
    if not matches:raise ValueError('No verified matching reconstruction evidence')
    source=matches[-1].parent
    metric='longitudinal' if result['stage']=='axis' else 'transverse_x'
    limit=config.physics.longitudinal_limit if metric=='longitudinal' else config.physics.transverse_limit
    with np.load(source/'reconstruction.npz',allow_pickle=False) as arrays:
        summary=summarize(read_json(source/'reconstruction.json'),config.physics,config.reconstruction,
                          metric,arrays=arrays,threshold=limit)
    atomic_json(output,summary)
    entry=dict(source_result_path=str(path),source_result_sha256=expected_sha,
                source_analysis_manifest=str(matches[-1]),source_analysis_manifest_sha256=digest(matches[-1]),
                source_reconstruction_sha256=digest(source/'reconstruction.json'),
                raw_sha256=result['raw_sha256'],parameters=result['parameters'],metric=metric,
                summary_path=str(output),summary_sha256=digest(output))
    power=source/'power_analysis.json'
    if result['stage']=='axis':
        from .postprocess import power_observations
        if not power.exists() and any(k in result['observations'] for k in ('heat_1','heat_2','leak_2','leak_3')):
            raise ValueError('Saved power evidence missing')
        if power.exists():
            entry.update(source_power_path=str(power),source_power_sha256=digest(power),
                         power_observations={k:v.as_dict() for k,v in power_observations(read_json(power),config).items()})
    return entry


def prepare(config_path: Path, destination: Path) -> Path:
    """Create an immutable dry-run revision and revised history in a NEW directory."""
    config=load_config(config_path);root=Path(config.paths.output_dir)
    state=read_json(root/'state.json');assert_paused(root,state)
    load_revision(state)  # A new immutable revision may supersede a verified one.
    previous=read_json(state['observation_revision']['path']) if state.get('observation_revision') else {}
    if destination.exists():raise FileExistsError('Use a fresh revision directory')
    destination.mkdir(parents=True)
    before=destination/'before';before.mkdir()
    for name in ('state.json','provenance.json','report.json','candidates.csv','owner.json','heartbeat.json',
                 'monitor_state.json','monitor_handoff.json','config.snapshot.json','STOP'):
        if (root/name).exists():(before/name).write_bytes((root/name).read_bytes())
    original_state_sha=digest(root/'state.json')
    revision=dict(policy=VERSION,contract=config.digest(),prepared_at=time.time(),
                  state_before_sha256=original_state_sha,provenance_before_sha256=digest(root/'provenance.json'),
                  stages={},history_stages=[],history_before=state.get('history_bundle'),
                  previous_revision=state.get('observation_revision'))
    revised=copy.deepcopy(state)
    for item in state.get('results',[]):
        key=item['key']
        if key in revision['stages']:raise ValueError('Duplicate registered stage')
        path=Path(item['result_path']);result=read_json(path)
        candidate=revised['candidates'][result['candidate_index']]
        if result['parameters']!=candidate['parameters']:raise ValueError('Source candidate identity differs')
        entry=reassess_result(config,path,item['result_sha256'],destination/'native'/key/'reconstruction.json')
        revision['stages'][key]=entry
        effective=revised_observations(item,result,revision['stages'])
        for name in result['observations']:
            if name not in effective:candidate['observations'].pop(name,None)
        candidate['observations'].update(effective)
    historical=state.get('history_bundle')
    if historical:
        if digest(historical['path'])!=historical['sha256']:raise ValueError('History bundle changed')
        bundle=read_json(historical['path']);new_bundle=copy.deepcopy(bundle);matched=set()
        old_history={e['source_result_path']:e for e in previous.get('history_stages',[])}
        for index,evidence in enumerate(bundle['evidence']):
            result=read_json(evidence['result'])
            metric='longitudinal' if result['stage']=='axis' else 'transverse_x'
            old_entry=old_history.get(evidence['result'],evidence.get('observation_revision'))
            item=dict(key='history',result_path=evidence['result'],result_sha256=evidence['sha256'])
            old_effective=revised_observations(item,result,{'history':old_entry} if old_entry else {})
            targets=[i for i,c in enumerate(bundle['candidates']) if c['parameters']==result['parameters']
                     and metric in c['observations'] and c['observations'][metric]==old_effective.get(metric)]
            if not targets:continue
            entry=reassess_result(config,Path(evidence['result']),evidence['sha256'],
                                  destination/'history'/str(index)/'reconstruction.json',evidence['analyses'])
            revision['history_stages'].append(entry)
            effective=revised_observations(item,result,{'history':entry})
            new_bundle['evidence'][index]['observation_revision']=entry
            for i in targets:
                actual=new_bundle['candidates'][i]['observations']
                if any(actual.get(k)!=v for k,v in old_effective.items()):
                    raise ValueError('Historical observation differs from saved assessment')
                for name in old_effective:actual.pop(name,None)
                actual.update(effective)
                matched.add((i,metric))
        expected={(i,k) for i,c in enumerate(bundle['candidates']) for k in ('longitudinal','transverse_x') if k in c['observations']}
        if matched!=expected:raise ValueError('Historical RF observation missing verified fit evidence')
        new_bundle['quality_revision']=dict(policy=VERSION,source=historical)
        hp=destination/'history_bundle.json';atomic_json(hp,new_bundle)
        revised['history_bundle']=dict(path=str(hp),sha256=digest(hp))
        revision['history_after']=revised['history_bundle']
    for c in revised['candidates']:
        c['feasibility']=feasibility({k:Observation(**v) for k,v in c['observations'].items()},config)
    index=destination/'index.json';atomic_json(index,revision)
    revised['observation_revision']=dict(path=str(index),sha256=digest(index))
    atomic_json(destination/'state.preview.json',revised)
    if digest(root/'state.json')!=original_state_sha:raise RuntimeError('Campaign changed during preparation')
    return index


def adopt(config_path: Path, index: Path) -> dict:
    """Commit reviewed saved-fit reassessment under the campaign writer lock.

    Old result registrations stay byte-identical. Interrupted commits fail
    provenance checks; retry can finish the same revision without double work.
    """
    from .campaign import Campaign, code_manifest
    config=load_config(config_path);root=Path(config.paths.output_dir)
    with WriterLock(root/'coordinator.lock'):
        current=read_json(root/'state.json');assert_paused(root,current)
        revision=read_json(index);preview=read_json(index.parent/'state.preview.json')
        if revision['contract']!=config.digest():raise ValueError('Revision/config mismatch')
        record=dict(path=str(index),sha256=digest(index))
        retry=current.get('observation_revision')==record
        if not retry and digest(root/'state.json')!=revision['state_before_sha256']:
            raise ValueError('State changed since reassessment preparation')
        if preview.get('observation_revision')!=record:raise ValueError('Preview revision index differs')
        before=read_json(index.parent/'before/state.json')
        invariant=('contract','status','active_seconds','cap_seconds','exploration_seconds','pending','prefetch',
                   'results','completed_stage_keys','failures','radius','trust','preparations','budget_origin')
        for name in invariant:
            if preview.get(name)!=before.get(name) or current.get(name)!=before.get(name):
                raise ValueError('Non-observation campaign state changed: '+name)
        for a,b in zip(preview['candidates'],before['candidates']):
            if {k:v for k,v in a.items() if k not in ('observations','feasibility')}!={k:v for k,v in b.items() if k not in ('observations','feasibility')}:
                raise ValueError('Candidate geometry/scheduling changed')
        if len(preview['candidates'])!=len(before['candidates']):raise ValueError('Candidate count changed')
        stages=load_revision(preview)
        for item in preview['results']:
            if digest(item['result_path'])!=item['result_sha256']:raise ValueError('Original result changed')
            result=read_json(item['result_path']);effective=revised_observations(item,result,stages)
            actual=preview['candidates'][result['candidate_index']]['observations']
            if any(actual.get(k)!=v for k,v in effective.items()):raise ValueError('Preview observation differs')
        hp=preview.get('history_bundle')
        if hp!=revision.get('history_after',revision.get('history_before')):raise ValueError('Preview history identity differs')
        if hp and digest(hp['path'])!=hp['sha256']:raise ValueError('Revised history changed')
        for entry in list(stages.values())+revision['history_stages']:
            if digest(entry['source_result_path'])!=entry['source_result_sha256']:
                raise ValueError('Revision original result changed')
            if digest(entry['source_analysis_manifest'])!=entry['source_analysis_manifest_sha256']:
                raise ValueError('Revision original analysis manifest changed')
            if digest(entry['summary_path'])!=entry['summary_sha256']:raise ValueError('Revised summary changed')
        provenance=read_json(root/'provenance.json')
        if provenance['config_digest']!=config.digest() or digest(config.paths.template)!=provenance['template_sha256']:
            raise ValueError('Template or physics/config changed')
        if not retry and digest(root/'provenance.json')!=revision['provenance_before_sha256']:
            raise ValueError('Provenance changed since preparation')
        atomic_json(root/'state.json',preview)
        provenance.update(code=code_manifest(),observation_revision=record,history_bundle=hp)
        atomic_json(root/'provenance.json',provenance)
        campaign=Campaign(config_path);campaign.check_provenance();campaign.apply_results()
        final=campaign.store.data
        for name in invariant:
            if final.get(name)!=before.get(name):raise RuntimeError('Unexpected replay state change: '+name)
        assert_paused(root,final)
        receipt=dict(policy=VERSION,state_before_sha256=revision['state_before_sha256'],
                     state_after_sha256=digest(root/'state.json'),revision=record,
                     stages=len(stages),history_stages=len(revision['history_stages']),
                     active_seconds=final['active_seconds'],cap_seconds=final['cap_seconds'],
                     paused=True,no_solver_started=True,adopted_at=time.time())
        atomic_json(index.parent/'adoption.json',receipt)
        return receipt


def main() -> None:
    """Explicit offline prepare/adopt commands; this entry point never resumes."""
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',type=Path);group.add_argument('--adopt',type=Path)
    args=parser.parse_args()
    if args.prepare:print(prepare(args.config,args.prepare))
    else:print(json.dumps(adopt(args.config,args.adopt),indent=2))


if __name__=='__main__':main()
