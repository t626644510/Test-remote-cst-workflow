"""One explicitly requested longer-tail comparison, outside the search budget.

Exactly one axis/X/Y triple, no optimization, thermal solve, mesh refinement or
automatic repair/retry. Uses shared stage workers and the same physical point.
Length is metres; impedance units and conventions remain those of the campaign.
"""
from __future__ import annotations
from dataclasses import replace
import json,logging,shutil,time
from pathlib import Path
import numpy as np
import yaml
from .config import Config
from .io import atomic_json,digest,fingerprint,project_manifest
from .storage import Store,campaign_lock,verify_evidence
from .supervision import launch_worker,check_recovery
from .campaign import offline_candidate

LOG=logging.getLogger(__name__)


def validation_config(base:Config,output:Path,artifacts:Path,length_m:float)->Config:
    """Separate state/bulk roots and target tail; preserve geometry, mesh and band."""
    if not np.isfinite(length_m) or length_m<=base.physics.wake_length_m:
        raise ValueError('Validation tail must exceed the original tail')
    roots=[Path(base.paths.output_dir).resolve(),Path(base.paths.artifact_dir).resolve()]
    for target in (output.resolve(),artifacts.resolve()):
        if any(target==old or target.is_relative_to(old) or old.is_relative_to(target) for old in roots):
            raise ValueError('Validation roots must be separate from campaign roots')
    sources={s:str(Path(base.paths.artifact_dir)/'templates'/s/Path(p).name) for s,p in base.paths.templates.items()}
    cfg=replace(base,paths=replace(base.paths,templates=sources,output_dir=str(output.resolve()),artifact_dir=str(artifacts.resolve())),
                physics=replace(base.physics,wake_length_m=length_m))
    cfg.validate();return cfg


def run_validation(base:Config,output:Path,artifacts:Path,length_m:float,resume:bool=False,backend=launch_worker)->dict:
    """Run at most three distinct solves; completed-stage recovery never re-solves.

    The original state is read-only. The worker applies Solver.WakeLength after
    rebuild, then verifies effective settings. Original immutable templates may
    retain their original length, and are never opened for editing.
    """
    source_state=Path(base.paths.output_dir)/'state.json'
    original=json.loads(source_state.read_text());point=original['candidates'][0]
    if original['pending'] is not None or original['status']=='running':
        raise ValueError('Original campaign must be inactive before tail validation')
    for job in original['jobs']:check_recovery(Path(job['directory']))
    cfg=validation_config(base,output,artifacts,length_m);cfg.validate(live=True)
    manifests={s:project_manifest(Path(p)) for s,p in cfg.paths.templates.items()}
    code={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}
    contract=fingerprint(dict(config=cfg.as_dict(),parameters=point['parameters'],ports=point['ports'],templates=manifests,code=code))
    root=Path(cfg.paths.output_dir);bulk=Path(cfg.paths.artifact_dir)
    with campaign_lock(root):
        if (root/'state.json').exists() and not resume:raise ValueError('Existing validation requires explicit --resume')
        if resume and not (root/'state.json').exists():raise ValueError('No validation to resume')
        marker=bulk/'owner.json'
        if marker.exists():
            if json.loads(marker.read_text())['contract']!=contract:raise ValueError('Validation fingerprint changed')
        elif bulk.exists() and any(bulk.iterdir()):raise ValueError('Validation bulk root not empty')
        bulk.mkdir(parents=True,exist_ok=True)
        atomic_json(marker,dict(contract=contract,scope='one_axis_x_y_tail_validation',excluded_from_campaign_budget=True))
        config_path=root/'effective_config.yaml'
        config_path.write_text(yaml.safe_dump({'workflow_6':cfg.as_dict()},sort_keys=False),encoding='utf-8')
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
            handlers=[logging.FileHandler(root/'validation.log',encoding='utf-8'),logging.StreamHandler()])
        store=Store(cfg,contract);s=store.state
        if not s['candidates']:
            s['candidates'].append(dict(id='validation_0000',parameters=point['parameters'],ports=point['ports'],stages={},metrics={},details={},complete=False,failed=False,source='tail_validation'))
            atomic_json(root/'provenance.json',dict(source_state=str(source_state),source_state_sha256=digest(source_state),
                original_active_seconds=original['active_seconds'],original_contract=original['contract'],
                excluded_from_campaign_budget=True,max_solver_starts=3,wake_lengths_m=[base.physics.wake_length_m,length_m],
                parameters=point['parameters'],ports=point['ports'],code=code,templates=manifests,
                source_analysis=str(Path(base.paths.artifact_dir)/'evidence'/point['id']/f"revision_{point['revision']:03d}/analysis.json")))
        c=s['candidates'][0];store.start_clock();s['status']='validation_running';store.save()
        try:
            for stage in ('axis','x','y'):
                if stage in c['stages']:continue
                if (root/'STOP').exists():
                    s['status']='validation_paused';break
                for drive in (root,bulk):
                    if shutil.disk_usage(drive).free<cfg.runtime.minimum_free_gib*2**30:
                        raise RuntimeError('Disk free space below configured reserve')
                jobs=[j for j in s['jobs'] if j['stage']==stage]
                if jobs:
                    j=jobs[0];check_recovery(Path(j['directory']))
                    result_path=Path(j['directory'])/'worker_result.json'
                    if result_path.exists():result=json.loads(result_path.read_text())
                    elif (Path(j['directory'])/'solved.json').exists():
                        result=backend(config_path,j,store,cfg.runtime.postprocess_timeout_s+300)
                    else:raise ValueError('Interrupted validation solve: no implicit retry')
                else:
                    if len(s['jobs'])>=3:raise ValueError('Validation three-solve cap reached')
                    identity=fingerprint(dict(contract=contract,stage=stage))
                    task=dict(identity=identity,directory=str(bulk/'candidates'/c['id']/f"attempt_{len(s['jobs']):05d}"),
                        stage=stage,template=cfg.paths.templates[stage],parameters=c['parameters'],ports=c['ports'])
                    j=store.reserve(c,stage,task,None);start=time.monotonic()
                    LOG.info('Validation dispatch %s length=%s m ports=%s',stage,length_m,c['ports'])
                    result=backend(config_path,j,store,cfg.runtime.stage_timeout_s+cfg.runtime.postprocess_timeout_s+600)
                    j['elapsed_s']=time.monotonic()-start
                store.complete_job(j,result)
                if result['status']!='complete':
                    c.update(failed=True,failure=result);s['status']='validation_failed';break
                if not verify_evidence(Path(result['raw'])):raise ValueError('Validation result manifest failed')
                c['stages'][stage]=result;j['applied']=True;store.save()
            if len(c['stages'])==3:
                c.update(offline_candidate(cfg,c,bulk/'evidence'/c['id']))
                c['complete']=True;s['status']='validation_complete'
        except BaseException as exc:
            s['status']='validation_needs_attention';s['error']=f'{type(exc).__name__}: {exc}';raise
        finally:
            store.tick();store.save()
            source_unchanged=digest(source_state)==json.loads((root/'provenance.json').read_text())['source_state_sha256']
            report=dict(status=s['status'],source_campaign_state_unchanged=source_unchanged,
                excluded_from_campaign_budget=True,validation_seconds=s['active_seconds'],solver_starts=len(s['jobs']),
                stages=list(c['stages']),metrics=c['metrics'],details=c['details'],
                original_metrics=point['metrics'],original_details=point['details'],
                wake_lengths_m=[base.physics.wake_length_m,length_m],
                next_action='Review 35/50 m reconstruction and resume original campaign as preliminary screening; no automatic additional validation solves.')
            atomic_json(root/'comparison.json',report);store.close()
        return report
