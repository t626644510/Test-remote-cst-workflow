"""Durable stage journal, shared evaluation database, runtime budget and retention."""
from __future__ import annotations
from contextlib import contextmanager
import json, os, shutil, time
from pathlib import Path
from .config import Config, NAMES
from .io import atomic_json, fingerprint, digest


class Store:
    """JSON write-ahead state is mirrored idempotently to the shared database."""
    def __init__(self,config: Config,contract: str):
        from cst_optimization.evaluation.evaluation_database_storage import SQLiteEvaluationDatabase, EvaluationDatabaseConfig
        from cst_optimization.checkpoint import CheckpointManager
        self.config=config; self.root=Path(config.paths.output_dir);self.root.mkdir(parents=True,exist_ok=True)
        self.file=self.root/'state.json'
        self.state=json.loads(self.file.read_text()) if self.file.exists() else dict(
            contract=contract,status='created',active_seconds=0.,exploration_seconds={'near':0.,'global':0.},
            candidates=[],jobs=[],pending=None,rng=None,radius=config.search.radius,improving=0,not_improving=0,accepted=False)
        if self.state['contract']!=contract:raise ValueError('Campaign fingerprint changed; use a new output directory')
        self.db=SQLiteEvaluationDatabase(EvaluationDatabaseConfig(enabled=True,path=str(self.root/'evaluations.sqlite')))
        self.db.open();self.db.set_run_id(contract)
        self.checkpoint=CheckpointManager(str(self.root/'search'))
        self.last_tick=None;self.exploration=None
        self.save();self.mirror()

    def save(self):
        from cst_optimization.checkpoint import EvalRecord
        atomic_json(self.file,self.state)
        self.checkpoint.rng_state={'random':self.state['rng'],'budget':self.state['active_seconds'],
            'observations':[(c['id'],c.get('metrics',{})) for c in self.state['candidates']],
            'historical_observations':[(c['id'],c.get('metrics',{}),c.get('evidence_manifest_sha256')) for c in self.state.get('historical_observations',[])]}
        self.checkpoint.records=[EvalRecord(x=[c['parameters'][n] for n in NAMES],status='completed' if c.get('complete') else 'pending',
            phases_done=list(c['stages']),raw_values=c.get('metrics',{})) for c in self.state['candidates']]
        self.checkpoint.save()

    def mirror(self):
        from cst_optimization.evaluation.evaluation_database_schema import EvaluationDatabaseRecord,ParameterIdentity,RawEvaluationPayload
        seen={r['provenance'].get('job') for r in self.db.get_all_records() if r.get('provenance')}
        for c in self.state.get('historical_observations',[]):
            key='history:'+c['id']+':'+fingerprint(c)
            if key in seen:continue
            self.db.insert_final_record(EvaluationDatabaseRecord(
                parameter_identity=ParameterIdentity(list(NAMES),[c['parameters'][n] for n in NAMES]),
                status='success',source='wf6.historical_screening_only',
                raw_payload=RawEvaluationPayload(raw_metrics=c['metrics'],diagnostics=c,artifact_refs={'evidence':c.get('evidence','')}),
                provenance={'job':key,'contract':self.state['contract'],'source_contract':c.get('source_contract'),
                            'qualification':'GP-only; not current stage completion or feasibility'}))
        for j in self.state['jobs']:
            if j['status']=='reserved' or j['id'] in seen:continue
            c=next(c for c in self.state['candidates'] if c['id']==j['candidate'])
            record=EvaluationDatabaseRecord(parameter_identity=ParameterIdentity(list(NAMES),[c['parameters'][n] for n in NAMES]),
                status='success' if j['status']=='complete' else 'solver_failed',source='wf6.stage',
                raw_payload=RawEvaluationPayload(diagnostics=j,artifact_refs={'directory':j['directory']}),
                provenance={'job':j['id'],'contract':self.state['contract']})
            self.db.insert_final_record(record)
        for j in self.state['jobs']:
            key=j['id']+':observations'
            if key in seen or not j.get('metrics'):continue
            c=next(c for c in self.state['candidates'] if c['id']==j['candidate'])
            self.db.insert_final_record(EvaluationDatabaseRecord(
                parameter_identity=ParameterIdentity(list(NAMES),[c['parameters'][n] for n in NAMES]),status='success',
                source='wf6.reliable_observations',raw_payload=RawEvaluationPayload(raw_metrics=j['metrics'],diagnostics={'ports':j['ports'],'stage':j['stage']}),
                provenance={'job':key,'contract':self.state['contract']}))

    def start_clock(self):self.last_tick=time.monotonic()

    def tick(self):
        if self.last_tick is None:return
        now=time.monotonic();elapsed=max(0.,now-self.last_tick);self.last_tick=now
        self.state['active_seconds']+=elapsed
        if self.exploration:self.state['exploration_seconds'][self.exploration]+=elapsed
        self.save()

    def can_start(self,estimate: float) -> bool:
        return self.state['active_seconds']+max(estimate,60.)+300.<self.config.search.hours*3600

    def reserve(self,candidate: dict,stage: str,task: dict,exploration: str | None) -> dict:
        if self.state['pending'] is not None:raise ValueError('An unresolved task already owns the worker')
        j=dict(task,id=f"job_{len(self.state['jobs']):05d}",candidate=candidate['id'],stage=stage,
               status='reserved',exploration=exploration,reserved_at=time.time(),elapsed_s=0.)
        self.state['jobs'].append(j);self.state['pending']=j['id'];self.save();return j

    def complete_job(self,j: dict,result: dict):
        j.update(status=result['status'],outcome=result,finished_at=time.time())
        self.state['pending']=None;self.save();self.mirror()

    def close(self):
        self.tick();self.db.close()


@contextmanager
def campaign_lock(root: Path):
    """OS byte lock dies with its owner. Never delete a CST/project lock."""
    import msvcrt
    root.mkdir(parents=True,exist_ok=True)
    with (root/'coordinator.lock').open('a+b') as handle:
        handle.seek(0);handle.write(b'1');handle.flush();handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as exc:raise RuntimeError('WF6 coordinator is already running') from exc
        try:yield
        finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def verify_evidence(raw: Path) -> bool:
    manifest=raw/'manifest.json'
    if not manifest.exists():return False
    records=json.loads(manifest.read_text())
    return bool(records) and all(Path(k).name==k and (raw/k).is_file() and digest(raw/k)==v for k,v in records.items())


def retained_candidates(candidates: list[dict],recent: int,pareto_count: int) -> set[str]:
    keep={c['id'] for c in candidates if c.get('source')=='baseline' or c.get('failure',{}).get('category')=='postprocess_failed'}
    completed=[c for c in candidates if c.get('complete')]
    keep.update(c['id'] for c in completed[-recent:] if recent)
    feasible=[c for c in completed if c.get('feasible')]
    feasible.sort(key=lambda c:(max(c['metrics']['power5'],c['metrics']['power6']),sum(c['metrics'][k] for k in ('power5','power6'))))
    if feasible:keep.add(feasible[0]['id'])
    vectors=[(c,[c['metrics'][k] for k in ('longitudinal','transverse','power5','power6')]) for c in completed if len(c.get('metrics',{}))==4]
    front=[c for c,v in vectors if not any(all(a<=b for a,b in zip(w,v)) and any(a<b for a,b in zip(w,v)) for other,w in vectors if other is not c)]
    keep.update(c['id'] for c in front[:pareto_count]);return keep


def prune_native(config: Config,state: dict) -> list[str]:
    """Delete only owned project subdirectories after permanent evidence verification."""
    root=Path(config.paths.artifact_dir).resolve();marker=root/'owner.json'
    if not marker.exists() or json.loads(marker.read_text()).get('contract')!=state['contract']:
        raise ValueError('Artifact root ownership is not established')
    keep=retained_candidates(state['candidates'],config.runtime.retain_recent,config.runtime.retain_pareto)
    if config.search.observation_mode=='finite_tail_screening':
        from .screening import search_metrics
        ranked=[c for c in state['candidates'] if all(k in search_metrics(config,c) for k in ('longitudinal','transverse'))]
        def screen_order(c):
            m=search_metrics(config,c)
            return (max(1.,m['longitudinal']/config.physics.longitudinal_limit,m['transverse']/config.physics.transverse_limit),
                    max(m.get('power5',float('inf')),m.get('power6',float('inf'))))
        keep.update(c['id'] for c in sorted(ranked,key=screen_order)[:max(1,config.runtime.retain_pareto)])
    keep.update(j['candidate'] for j in state['jobs'] if j['status']=='reserved')
    removed=[]
    for j in state['jobs']:
        if j['candidate'] in keep or j['status']!='complete':continue
        attempt=Path(j['directory']).resolve();target=(attempt/'project').resolve()
        if not target.is_relative_to(root) or target==root or target.name!='project':raise ValueError('Unsafe native retention target')
        if target.exists() and verify_evidence(attempt/'raw'):
            shutil.rmtree(target);removed.append(str(target))
    return removed
