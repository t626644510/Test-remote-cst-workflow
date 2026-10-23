"""Explicit compact-evidence retention; never claim retired raw traces are replayable."""
from __future__ import annotations
from pathlib import Path
import time
from .config import Config
from .io import read_json,atomic_json,digest,validate_manifest
from .observations import Observation,feasibility

RAW_NAMES={'Ez_lines.h5','thermal_traces.h5','port_traces.h5'}
PREPARED_NAMES={'effective_metrics.npz','copper_surface.vtp','thermal_surface.npz'}
MATRIX_SUFFIXES={'.mat','.m2h','.fmp','.fmm','.sic','.slm'}

def safe_file(base: Path,relative: str) -> Path:
    """Resolve each deletion target under its explicit root, rejecting junction escape."""
    rel=Path(relative);p=base/rel
    if rel.is_absolute() or '..' in rel.parts or not p.resolve().is_relative_to(base.resolve()):
        raise ValueError('Unsafe retention target')
    return p

def validate_retained_manifest(directory: Path,entries: dict,manifest_name: str='raw_manifest.json') -> list[str]:
    """Validate survivors and a manifest-bound intentional-retirement certificate.

    This is for audits only. Strict solver/recovery validation is unchanged.
    A retired file cannot be silently substituted or recreated with other bytes.
    """
    path=directory/'retention.json';retired={}
    if path.exists():
        record=read_json(path)
        if record['manifest_sha256']!=digest(directory/manifest_name):raise ValueError('Retirement manifest changed')
        retired=record['files']
        allowed=RAW_NAMES if manifest_name=='raw_manifest.json' else PREPARED_NAMES
        if not set(retired)<=allowed or any(entries.get(n)!=v for n,v in retired.items()):
            raise ValueError('Invalid retirement certificate')
    validate_manifest(directory,{n:v for n,v in entries.items() if n not in retired or safe_file(directory,n).exists()})
    return sorted(n for n in retired if not safe_file(directory,n).exists())

def retire_manifest_files(directory: Path,manifest_name: str,names: set[str],*,execute: bool) -> dict:
    """Hash before unlink; persist intent first for interruption-safe replay."""
    allowed={'raw_manifest.json':RAW_NAMES,'manifest.json':PREPARED_NAMES}.get(manifest_name)
    if allowed is None or not names<=allowed:raise ValueError('Non-disposable files cannot be retired')
    manifest_path=directory/manifest_name;entries=read_json(manifest_path)
    validate_retained_manifest(directory,entries,manifest_name)
    selected={n:v for n,v in entries.items() if n in names}
    targets=[safe_file(directory,n) for n in selected]
    remaining=sum(p.stat().st_size for p in targets if p.is_file())
    if execute and selected:
        atomic_json(directory/'retention.json',dict(at=time.time(),manifest_sha256=digest(manifest_path),
            files=selected,policy='compact-v1',state='intent',raw_reanalysis_available=False))
        for p in targets:
            if p.exists():p.unlink()
        record=read_json(directory/'retention.json');record['state']='completed';atomic_json(directory/'retention.json',record)
    return dict(directory=str(directory),files=list(selected),bytes=remaining)

def retained_candidates(config: Config,state: dict) -> set[str]:
    """Keep pinned geometry and best L/port2/port3 envelope scores, plus pending lanes.

    Ranking is for storage only: ohm/1800 and W/75 dimensionless envelopes;
    unknown/unqualified values cannot become a formal optimum by this ranking.
    """
    keep=set(config.retained_candidate_ids)
    limits=dict(longitudinal=config.physics.longitudinal_limit,leak_2=config.physics.leakage_limit_w,leak_3=config.physics.leakage_limit_w)
    def score(c):
        values=[c['observations'].get(k,{}) for k in limits]
        ratios=[v.get('upper')/limit if v.get('upper') is not None else float('inf') for v,limit in zip(values,limits.values())]
        passes=feasibility({k:Observation(**v) for k,v in c['observations'].items()},config)['passes']
        return (sum(not passes[k] for k in limits),sum(max(0,r-1) for r in ratios),max(ratios))
    eligible=[c for c in state['candidates'] if c.get('axis_directory')]
    keep.update(c['id'] for c in sorted(eligible,key=score)[:config.retained_best_count])
    keep.update(c['id'] for c in state['candidates'] if c['status'] not in ('completed','axis_only'))
    for job in (state.get('pending'),state.get('prefetch')):
        if job:keep.add(state['candidates'][job['candidate_index']]['id'])
    return keep

def compact_campaign(config: Config,state: dict,*,execute: bool=True) -> dict:
    """Called only by the coordinator/locked maintenance; preserve all GP and wake data.

    Non-final candidates and both active lanes are protected. Remove only named
    raw HDF5, prepared numerical tensors and disposable CST matrix extensions.
    CST geometry archives/Model data, logs, results, fits and signed wakes stay.
    Full per-stage analysis and registered result identity are checked first.
    """
    bulk=Path(config.paths.artifact_dir).resolve();keep=retained_candidates(config,state);actions=[]
    registered={}
    for item in state.get('results',[]):
        p=Path(item['result_path'])
        if digest(p)!=item['result_sha256']:raise ValueError('Registered result changed before retention')
        result=read_json(p);registered.setdefault(result['candidate_index'],[]).append(result)
    for index,c in enumerate(state['candidates']):
        if c['id'] in keep:continue
        directory=safe_file(bulk,c['id'])
        done=directory/'compact_complete.json'
        if done.exists():continue
        for result in registered.get(index,[]):
            field=Path(result['field_directory'])
            if not field.resolve().is_relative_to(directory.resolve()) or result['parameters']!=c['parameters']:
                raise ValueError('Retirement candidate/stage ownership mismatch')
            if digest(field/'wake.npz')!=result['raw_sha256']:raise ValueError('Numerical wake changed')
            matches=[]
            for m in field.glob('analysis_*/manifest.json'):
                a=read_json(m.parent/'result.json')
                if all(a.get(k)==result.get(k) for k in ('stage','parameters','observations','raw_sha256')):
                    validate_manifest(m.parent,read_json(m));matches.append(m)
            if not matches:raise ValueError('Cannot retire without complete postprocessing')
            actions.append(retire_manifest_files(field,'raw_manifest.json',RAW_NAMES,execute=execute))
        if not registered.get(index):continue
        prepared=Path(c['prepared'])
        if not prepared.resolve().is_relative_to(directory.resolve()):raise ValueError('Prepared ownership mismatch')
        actions.append(retire_manifest_files(prepared,'manifest.json',PREPARED_NAMES,execute=execute))
        # Keep the editable .cst and Model sidecar; only disposable matrix bytes.
        project=Path(c['cst']['project'])
        results=project.with_suffix('')/'Result'
        if not results.resolve().is_relative_to(directory.resolve()):raise ValueError('CST result ownership mismatch')
        audit=prepared.parent/'cst_matrix_retention.json'
        if results.is_dir():
            files={}
            if audit.exists():
                old=read_json(audit)
                if old['root']!=str(results):raise ValueError('Matrix retirement root changed')
                files=old['files']
            else:
                for p in results.rglob('*'):
                    if p.is_file() and p.suffix.lower() in MATRIX_SUFFIXES:
                        safe_file(results,str(p.relative_to(results)))
                        files[str(p.relative_to(results))]=dict(bytes=p.stat().st_size,sha256=digest(p))
            size=0
            for n,v in files.items():
                p=safe_file(results,n)
                if p.suffix.lower() not in MATRIX_SUFFIXES:raise ValueError('Forbidden matrix retirement suffix')
                if p.exists():
                    if p.stat().st_size!=v['bytes'] or digest(p)!=v['sha256']:raise ValueError('Matrix changed before deletion')
                    size+=v['bytes']
            if execute:
                atomic_json(audit,dict(root=str(results),files=files,state='intent',at=time.time()))
                for n in files:
                    p=safe_file(results,n)
                    if p.exists():p.unlink()
                record=read_json(audit);record['state']='completed';atomic_json(audit,record)
            actions.append(dict(directory=str(results),files=len(files),bytes=size))
        if execute:atomic_json(done,dict(at=time.time(),policy='compact-v1',raw_reanalysis_available=False))
    record=dict(at=time.time(),execute=execute,kept_candidates=sorted(keep),actions=actions,
                reclaimed_bytes=sum(a['bytes'] for a in actions))
    if execute:atomic_json(Path(config.paths.output_dir)/'retention_latest.json',record)
    return record
