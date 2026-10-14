"""Local sequential WF7 round with replayable phases and a 48-hour drain cap."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import argparse,csv,json,os,shutil,time,traceback,uuid
from .config import Config,load_config
from .geometry import Geometry
from .io import atomic_json,digest,read_json,manifest,validate_manifest
from .observations import Observation,feasibility,transverse_admission
from .search import Proposer,Sample
from .state import RoundStore,WriterLock
from .processes import Supervisor,OwnershipError
from .cst_prepare import ProcessIdentity
from .failures import classify_failure

class StageFailure(RuntimeError):
    """A bounded stage failed; its previous successful objectives remain valid."""

    def __init__(self,result: dict):
        self.result=result
        self.retry_identical=result['failure_policy']['retry_identical']
        super().__init__(json.dumps(result,ensure_ascii=False))

def code_manifest() -> dict:
    root=Path(__file__).parent
    return manifest(root,sorted(root.rglob('*.py'))+sorted(root.glob('*.bas')))

class Campaign:
    """The coordinator owns search/state; workers own only their assigned phase."""
    def __init__(self,config_path: Path):
        self.config_path=config_path.resolve();self.config=load_config(config_path)
        self.root=Path(self.config.paths.output_dir);self.bulk=Path(self.config.paths.artifact_dir)
        self.root.mkdir(parents=True,exist_ok=True);self.bulk.mkdir(parents=True,exist_ok=True)
        self.store=RoundStore(self.root/'state.json',self.config.digest(),hours=self.config.search.hours)
        self.supervisor=Supervisor(self.config,self.tick)

    def tick(self):
        pending=self.store.data['pending'] or {}
        self.store.tick(exploration=bool(pending.get('forced_transverse')))
        if self.store.data['status']=='running':
            if self.store.data['active_seconds']>=self.store.cap:self.store.drain('budget')
            elif (self.root/'STOP').exists():self.store.drain('user')
        atomic_json(self.root/'heartbeat.json',dict(at=time.time(),pid=os.getpid(),status=self.store.data['status'],
                    active_seconds=self.store.data['active_seconds'],pending=self.store.data['pending']))

    def initialize(self,baseline: dict):
        self.config.validate(live=True)
        if (self.root/'provenance.json').exists():raise RuntimeError('Round already initialized')
        errors=Geometry(self.config).violations(baseline)
        if errors:raise ValueError(errors)
        if self.store.data['candidates'] or self.store.data['active_seconds']:raise RuntimeError('Nonempty round')
        from .cad import parameters
        actual=Geometry.from_template(parameters(Path(self.config.paths.template)))
        if any(abs(actual[k]-baseline[k])>1e-7 for k in actual):raise ValueError('Baseline differs from current source')
        atomic_json(self.root/'config.snapshot.json',self.config.as_dict())
        source=Path(self.config.paths.template)
        atomic_json(self.root/'provenance.json',dict(template=str(source),template_sha256=digest(source),
                     code=code_manifest(),config_digest=self.config.digest(),initialized=time.time(),
                     baseline=baseline,reference_results_used_for_training=False))
        self.store.data['candidates']=[dict(id='candidate_0000',parameters=baseline,observations={},
                    status='axis_pending',forced_transverse=True,proposal={'method':'current_template_baseline'})]
        self.store.save();self.report()

    def check_provenance(self):
        p=read_json(self.root/'provenance.json')
        if p['config_digest']!=self.config.digest() or digest(self.config.paths.template)!=p['template_sha256']:
            raise OwnershipError('Source/config changed; review and migration required')
        if p['code']!=code_manifest():raise OwnershipError('Code changed; explicit reviewed migration required')
        for path in (self.root,self.bulk):
            if shutil.disk_usage(path).free<self.config.runtime.minimum_free_disk_gib*2**30:
                raise RuntimeError('Insufficient disk space for next stage')

    def import_baseline(self,spec: dict):
        """Register validated current-template preflight once, before dispatch."""
        from .bootstrap import validate_baseline
        self.check_provenance();data=self.store.data
        if data['status']!='prepared' or data['active_seconds']:
            raise RuntimeError('Native baseline import requires a fresh prepared round')
        if len(data['candidates'])!=1:raise RuntimeError('Only the initial source baseline may be imported')
        for item in data.get('results',[]):
            if not item.get('preflight'):raise RuntimeError('Cannot import over dispatched work')
        if data['pending'] and not data['pending'].get('preflight'):raise RuntimeError('A live stage is pending')
        candidate=data['candidates'][0]
        validated=validate_baseline(self.config,candidate['parameters'],Path(spec['prepared']),Path(spec['project']),
                                    {k:Path(v) for k,v in spec['analyses'].items()})
        audit=self.root/'native_baseline_import.json'
        if audit.exists():
            previous=read_json(audit)
            if any(previous[k]!=validated[k] for k in validated):raise RuntimeError('Imported native evidence changed')
        else:
            atomic_json(audit,dict(validated,at=time.time(),
                        accounting='Preflight field/analysis costs shown separately; not charged again to the 48 h round'))
        candidate['prepared']=validated['prepared'];candidate['cst']=dict(project=validated['project'],preflight=True)
        for stage,result in validated['results'].items():
            key='candidate_0000_'+stage;path=self.root/'jobs'/key/'stage_result.json'
            if key in data['completed_stage_keys']:continue
            atomic_json(path,dict(result,job_key=key,status='completed',candidate_index=0,origin='validated_native_preflight'))
            data['pending']=dict(key=key,candidate_index=0,stage=stage,preflight=True)
            self.store.save();self.store.register(key,path)
        self.apply_results()

    def phase(self,name: str,request: dict,timeout: float) -> dict:
        """Replay a completed phase response before considering any new process."""
        job=self.store.data['pending'];paths=job.setdefault('phase_requests',{})
        if name not in paths:
            folder=self.root/'jobs'/job['key'];folder.mkdir(parents=True,exist_ok=True)
            path=folder/(name+'.json')
            spec=dict(request,request_id=uuid.uuid4().hex,config=str(self.config_path),contract=self.config.digest())
            atomic_json(path,spec);paths[name]=str(path);self.store.save()
        path=Path(paths[name]);job['phase']=name;self.store.save()
        result=self.supervisor.run(path,timeout)
        if result['status']!='completed':
            # Classify the saved request/reply as well as new worker responses.
            # Preserve the original reply file and traceback for the audit trail.
            policy=classify_failure(read_json(path)['phase'],result.get('traceback',''))
            result=dict(result,failure_policy=asdict(policy))
            job.setdefault('phase_failures',{})[name]=result;self.store.save()
            raise StageFailure(result)
        return result['result']

    def execute_stage(self):
        job=self.store.data['pending'];candidate=self.store.data['candidates'][job['candidate_index']]
        key=job['key'];stage=job['stage'];folder=self.bulk/candidate['id'];folder.mkdir(exist_ok=True)
        stage_result=self.root/'jobs'/key/'stage_result.json'
        if stage_result.exists():self.store.register(key,stage_result);self.apply_results();return
        if not candidate.get('prepared'):
            for attempt in range(self.config.runtime.retries+1):
                try:
                    value=self.phase(f'prepare_{attempt:02}',dict(phase='prepare',parameters=candidate['parameters'],
                         output=str(folder/f'preparation_{attempt:02}')),self.config.runtime.mesh_timeout_s+900)
                    candidate['prepared']=value['prepared'];candidate['cst']=value['cst'];self.store.save();break
                except StageFailure:
                    if attempt==self.config.runtime.retries or self.store.data['status']=='draining':raise
        prepared=Path(candidate['prepared']);validate_manifest(prepared,read_json(prepared/'manifest.json'))
        field=None
        for attempt in range(self.config.runtime.retries+1):
            directory=folder/f'{stage}_{attempt:02}'
            job['field_directory']=str(directory);self.store.save()
            # Completed physics always goes straight to postprocessing, even
            # if integration/result writing or a worker exit was interrupted.
            if (directory/'field_complete.json').exists():field=directory;break
            try:
                self.phase(f'{stage}_solve_{attempt:02}',dict(phase='solve',stage=stage,prepared=str(prepared),
                         output=str(directory)),self.config.runtime.solve_timeout_s+240)
                field=directory;break
            except StageFailure as exc:
                if (directory/'field_complete.json').exists():field=directory;break
                # A detected numerical instability is deterministic evidence,
                # not a reason to spend identical repeat solves.
                if not exc.retry_identical or (directory/'stability_failure.json').exists():raise
                if attempt==self.config.runtime.retries or self.store.data['status']=='draining':raise
        for attempt in range(self.config.runtime.retries+1):
            try:
                result=self.phase(f'{stage}_analysis_{attempt:02}',dict(phase='analyze',stage=stage,
                    parameters=candidate['parameters'],field_directory=str(field),
                    axis_directory=candidate.get('axis_directory'),output=str(field/f'analysis_{attempt:02}')),
                    self.config.runtime.postprocess_timeout_s)
                break
            except StageFailure:
                if attempt==self.config.runtime.retries:raise
        atomic_json(stage_result,dict(result,job_key=key,status='completed',candidate_index=job['candidate_index']))
        self.store.register(key,stage_result);self.apply_results()

    def apply_results(self):
        """Idempotent projection of immutable stage results, including crash replay."""
        for item in self.store.data.get('results',[]):
            path=Path(item['result_path'])
            if digest(path)!=item['result_sha256']:raise OwnershipError('Registered result changed')
            result=read_json(path);candidate=self.store.data['candidates'][result['candidate_index']]
            if result['parameters']!=candidate['parameters']:raise OwnershipError('Candidate result parameter mismatch')
            candidate['observations'].update(result['observations'])
            candidate[result['stage']+'_directory']=result['field_directory']
        for candidate in self.store.data['candidates']:
            obs={k:Observation(**v) for k,v in candidate['observations'].items()}
            if candidate.get('x_directory'):candidate['status']='completed'
            elif candidate.get('axis_directory') and not candidate.get('failed_stage'):
                candidate['status']='x_pending' if transverse_admission(obs.get('longitudinal'),self.config,
                                  forced=candidate['forced_transverse']) else 'axis_only'
            candidate['feasibility']=feasibility(obs,self.config)
        self.store.save();self.report()

    def report(self):
        rows=[]
        for c in self.store.data['candidates']:
            row=dict(id=c['id'],status=c['status'],**c['parameters'])
            for k,v in c['observations'].items():
                row[k]=v['estimate'];row[k+'_qualified']=v['qualified'];row[k+'_upper']=v['upper']
            rows.append(row)
        keys=list(dict.fromkeys(k for r in rows for k in r))
        temporary=self.root/'candidates.csv.tmp'
        with temporary.open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows)
        temporary.replace(self.root/'candidates.csv')
        atomic_json(self.root/'report.json',dict(at=time.time(),active_hours=self.store.data['active_seconds']/3600,
            remaining_hours=max(0,(self.store.cap-self.store.data['active_seconds'])/3600),
            candidates=self.store.data['candidates'],formal_scope='X source column only',
            assumptions='sigma 70 mm; 35 m tail; HOM 550–1462.7348957 MHz; 500 kV peak CW; heuristic power uncertainty >=20%'))

    def next_job(self):
        data=self.store.data
        index=next((i for i,c in enumerate(data['candidates']) if c['status']=='x_pending'),None)
        if index is None:index=next((i for i,c in enumerate(data['candidates']) if c['status']=='axis_pending'),None)
        if index is None:
            samples=[Sample(c['parameters'],{k:Observation(**v) for k,v in c['observations'].items()}) for c in data['candidates']]
            forced=data['exploration_seconds']<self.config.search.exploration_fraction*max(1,data['active_seconds'])
            index=len(data['candidates'])
            parameters,audit=Proposer(self.config).choose(samples,sequence=index,radius=data['radius'],explore=forced,
                              excluded=[c['parameters'] for c in data['candidates']])
            data['candidates'].append(dict(id=f'candidate_{index:04}',parameters=parameters,observations={},
                         status='axis_pending',forced_transverse=forced,proposal=audit));self.store.save()
        candidate=data['candidates'][index];stage='x' if candidate['status']=='x_pending' else 'axis'
        return dict(key=candidate['id']+'_'+stage,candidate_index=index,stage=stage,
                    forced_transverse=candidate['forced_transverse'],started=time.time())

    def run(self):
        with WriterLock(self.root/'coordinator.lock'):
            self.config.validate(live=True);self.check_provenance()
            if (self.root/'STOP').exists():raise RuntimeError('STOP is present; explicit resume must remove it')
            owner_path=self.root/'owner.json'
            if owner_path.exists():
                old=read_json(owner_path);identity=ProcessIdentity(**dict(old,command=tuple(old['command'])))
                if identity.alive():raise OwnershipError('Existing coordinator is alive')
            atomic_json(owner_path,asdict(ProcessIdentity.read(os.getpid())))
            self.apply_results();self.store.activate()
            try:
                while True:
                    self.tick()
                    if self.store.data['pending'] is None:
                        if not self.store.may_dispatch:break
                        self.check_provenance();self.store.begin(self.next_job())
                    job=dict(self.store.data['pending'])
                    try:self.execute_stage()
                    except StageFailure as exc:
                        candidate=self.store.data['candidates'][job['candidate_index']]
                        candidate['failed_stage']=job['stage'];candidate['status']='partial_failed' if candidate['observations'] else 'failed'
                        self.store.fail(job['key'],dict(error=str(exc)));self.report()
                        if len(self.store.data['failures'])>=3:
                            recent=self.store.data['candidates'][-3:]
                            if all(c['status']=='failed' for c in recent):raise RuntimeError('Three consecutive candidate failures; stop dispatch')
                    self.tick()
                self.store.pause();self.report()
            except BaseException:
                self.tick();self.store.data['status']='error';self.store.save()
                atomic_json(self.root/'coordinator_failure.json',dict(at=time.time(),traceback=traceback.format_exc()))
                raise

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('init','run','status','import-baseline'))
    parser.add_argument('--config',required=True);parser.add_argument('--baseline');parser.add_argument('--import-spec')
    args=parser.parse_args();campaign=Campaign(Path(args.config))
    if args.command=='init':campaign.initialize(read_json(args.baseline))
    elif args.command=='import-baseline':campaign.import_baseline(read_json(args.import_spec))
    elif args.command=='run':campaign.run()
    else:print(json.dumps(campaign.store.data,ensure_ascii=False))

if __name__=='__main__':main()
