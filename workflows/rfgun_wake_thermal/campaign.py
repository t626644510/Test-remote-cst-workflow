"""Serial staged campaign, partial evaluation promotion and bounded port repair."""
from __future__ import annotations
import csv,json,logging,os,shutil,time
from pathlib import Path
import numpy as np
from .config import Config,STAGES,NAMES
from .geometry import Geometry
from .io import atomic_json,copy_verified_project,digest,fingerprint,project_manifest
from .runtime import metadata,effective_settings
from .storage import Store,prune_native
from .search import Controller,METRICS,axis_observed
from .repair import bad_ports,next_ports
from .reconstruction import read_bundle,align_transverse,reconstruct,transverse_norm
from .supervision import launch_worker,check_recovery
from .screening import search_metrics,search_view,screening_admission

LOG=logging.getLogger(__name__)


def baseline_admission(candidate:dict)->dict:
    """Accept a tested pipeline, never confuse it with a feasible cavity.

    A trustworthy exceedance is useful even if a global peak has no precise
    scalar value. Such observations remain absent from GP regression. Entirely
    unresolved wakes, bad holdouts, and missing thermal results block admission.
    """
    evidence={}
    for metric in ('longitudinal','transverse'):
        detail=candidate.get('details',{}).get(metric,{})
        diag=detail.get('diagnostics',{});fits=diag.get('fits',[])
        scalar=metric in candidate.get('metrics',{}) and detail.get('status')=='valid'
        exceeded=diag.get('decision')=='exceeds' and bool(fits) and all(f.get('valid') for f in fits)
        evidence[metric]='scalar' if scalar else 'exceeds_without_scalar' if exceeded else 'unresolved'
    evidence['thermal']='scalar' if all(k in candidate.get('metrics',{}) for k in ('power5','power6')) and candidate.get('details',{}).get('thermal',{}).get('status')=='valid' else 'unresolved'
    return dict(ready=bool(candidate.get('complete') and all(v!='unresolved' for v in evidence.values())),evidence=evidence)


def initialize(config: Config) -> tuple[str,dict]:
    """Immutable four-template snapshot, checked source identity and baseline coordinates."""
    root=Path(config.paths.artifact_dir); root.mkdir(parents=True,exist_ok=True)
    package=Path(__file__).parent
    code={p.name:digest(p) for p in package.glob('*.py')}
    source={s:project_manifest(Path(p)) for s,p in config.paths.templates.items()}
    contract=fingerprint(dict(config=config.as_dict(),code=code,templates=source))
    marker=root/'owner.json'
    if marker.exists() and json.loads(marker.read_text())['contract']!=contract:raise ValueError('Artifact directory belongs to a different contract')
    if not marker.exists() and any(root.iterdir()):raise ValueError('Artifact directory is not empty or owned')
    atomic_json(marker,dict(contract=contract,created_for='WF6',sources=config.paths.templates))
    templates={};coords=[]
    for stage,p in config.paths.templates.items():
        destination=root/'templates'/stage; target=destination/Path(p).name
        if destination.exists():
            if source[stage]!=project_manifest(target):raise ValueError('Immutable template snapshot changed')
        else:target,_=copy_verified_project(Path(p),destination)
        effective_settings(target,stage,config)
        templates[stage]=str(target);coords.append(Geometry(config).collapse(metadata(target)['parameters']))
    if any(any(abs(c[k]-coords[0][k])>1e-8 for k in coords[0]) for c in coords[1:]):raise ValueError('Four template physical coordinates disagree')
    errors=Geometry(config).violations(coords[0])
    if errors:raise ValueError('Template baseline outside new feasible domain: '+'; '.join(errors))
    return contract,dict(templates=templates,baseline=coords[0],source_manifest=source)


def offline_candidate(config: Config,candidate: dict,destination: Path) -> dict:
    """Reconstruct only saved numeric evidence; no CST imports or solver operations."""
    destination.mkdir(parents=True,exist_ok=True);metrics={};details={};stages=candidate['stages']
    previous=json.loads((destination/'analysis.json').read_text()) if (destination/'analysis.json').exists() else {}
    identities={s:r['identity'] for s,r in stages.items()}
    calculation=fingerprint(dict(physics=config.as_dict()['physics'],reconstruction=config.as_dict()['reconstruction'],
        code={name:digest(Path(__file__).with_name(name)) for name in ('reconstruction.py','measured_tail.py','tail_ensemble.py')}))
    def cached(metric,required):
        return (previous.get('calculation')==calculation and metric in previous.get('details',{})
                and all(previous.get('identities',{}).get(s)==identities.get(s) for s in required)
                and (destination/(metric+'.npz')).exists())
    for metric,required in [('longitudinal',['axis']),('transverse',['axis','x','y'])]:
        if cached(metric,required):
            details[metric]=previous['details'][metric]
            if metric in previous['metrics']:metrics[metric]=previous['metrics'][metric]
    if 'axis' in stages and 'longitudinal' not in details:
        axis=read_bundle(Path(stages['axis']['raw']))
        from .measured_tail import raw_transform
        native=axis['impedance_Z'];native_f=axis['frequency_Z']
        calculated=raw_transform(axis['s_m'],axis['wake'][:,2],native_f,config.physics.sigma_m,'longitudinal')[:,0]
        mask=(native_f>=config.physics.band_hz[0])&(native_f<=config.physics.band_hz[1]+1)
        discrepancy=float(np.max(abs(calculated[mask]-native[mask]))/max(float(np.max(abs(native[mask]))),1e-30))
        if discrepancy>config.reconstruction.max_error:
            raise ValueError('Measured Fourier reconstruction disagrees with native complex impedance')
        fit=reconstruct(axis['s_m'],axis['wake'][:,2],config.physics,config.reconstruction,'longitudinal',config.physics.longitudinal_limit)
        fit.diagnostics['native_complex_relative_discrepancy']=discrepancy
        # Keep native spectrum evidence in addition to the independently computed FT.
        band=(axis['frequency_Z']>=config.physics.band_hz[0])&(axis['frequency_Z']<=config.physics.band_hz[1]+1)
        lower=float(np.max(abs(axis['impedance_Z'][band])))
        fit.diagnostics['native_direct_peak']=lower
        if fit.value is not None:fit.value=max(fit.value,lower);metrics['longitudinal']=fit.value
        fit.diagnostics['lower_evidence_exceeds']=lower>config.physics.longitudinal_limit or fit.diagnostics.get('lower_evidence_exceeds',False)
        details['longitudinal']=fit.summary();np.savez_compressed(destination/'longitudinal.npz',**fit.arrays)
    if all(s in stages for s in ('axis','x','y')) and 'transverse' not in details:
        a,x,y=[read_bundle(Path(stages[s]['raw'])) for s in ('axis','x','y')]
        s,k=align_transverse(a,x,y,config.physics.offset_m)
        fit=reconstruct(s,k,config.physics,config.reconstruction,'transverse',config.physics.transverse_limit)
        if fit.value is not None:metrics['transverse']=fit.value
        details['transverse']=fit.summary();np.savez_compressed(destination/'transverse.npz',s_m=s,k=k,**fit.arrays)
    if 'thermal' in stages:
        result=stages['thermal']['result']
        if result.get('status')=='valid':metrics.update({k:result[k] for k in ('power5','power6')})
        details['thermal']=result
    atomic_json(destination/'analysis.json',dict(metrics=metrics,details=details,ports=candidate['ports'],identities=identities,calculation=calculation))
    atomic_json(destination/'manifest.json',{p.name:digest(p) for p in destination.iterdir() if p.is_file() and p.name!='manifest.json'})
    return dict(metrics=metrics,details=details)


class Campaign:
    """Each selected action is a single owned CST stage, with durable budget ownership."""
    def __init__(self,config: Config,config_path: Path,contract: str,snapshot: dict,backend=launch_worker):
        self.config=config;self.config_path=config_path;self.snapshot=snapshot;self.backend=backend
        self.store=Store(config,contract);self.state=self.store.state;self.controller=Controller(config,self.state)
        self.artifacts=Path(config.paths.artifact_dir)
        if not self.state['candidates']:self.new_candidate(snapshot['baseline'],'baseline')

    def new_candidate(self,parameters: dict,source: str) -> dict:
        key=fingerprint(parameters)
        if any(c['key']==key for c in self.state['candidates']):raise ValueError('Duplicate candidate rejected')
        c=dict(id=f"candidate_{len(self.state['candidates']):04d}",parameters=parameters,key=key,source=source,
            ports=[20.,20.],tried_ports=[[20.,20.]],repair_attempts=0,repair_seconds=0.,revision=0,
            stages={},metrics={},details={},complete=False,failed=False,feasible=False)
        self.state['candidates'].append(c);self.store.save();return c

    def estimate(self,stage: str) -> float:
        samples=[j['elapsed_s'] for j in self.state['jobs'] if j['stage']==stage and j['status']=='complete' and j['elapsed_s']>0]
        return float(np.quantile(samples,.75)) if samples else (1800. if stage!='thermal' else 1200.)

    def next_stage(self,c: dict) -> str | None:
        return next((s for s in STAGES if s not in c['stages']),None)

    def gated(self,c: dict,stage: str) -> bool:
        if stage=='axis':return False
        m=search_metrics(self.config,c)
        if m.get('longitudinal',float('inf'))>self.config.physics.longitudinal_limit:return True
        return stage=='thermal' and m.get('transverse',float('inf'))>self.config.physics.transverse_limit

    def select(self) -> tuple[dict,str,str|None]:
        self.controller.fit();eligible=[];total=self.state['active_seconds']
        exposure=self.state['exploration_seconds'];fraction=self.config.search.exploration_fraction
        for c in self.state['candidates']:
            if c['failed'] or c['complete']:continue
            stage=self.next_stage(c)
            if stage is None:continue
            gated=self.gated(c,stage)
            # Baseline may borrow exploration time; subsequent actions repay that debt.
            allow=sum(exposure.values())+self.estimate(stage)<=fraction*(total+self.estimate(stage))
            if gated and not allow:continue
            group=('near' if exposure['near']<=exposure['global'] else 'global') if gated else None
            x=self.controller.encode(c['parameters'])[None,:]
            remaining=sum(self.estimate(s) for s in STAGES if s not in c['stages'])
            score=float(self.controller.score(x,remaining,search_metrics(self.config,c))[0])
            if group=='global':
                # Randomized global partial points compete independently of predicted merit.
                score=float(self.controller.rng.random())/self.estimate(stage)
            # Bootstrap targets are priorities, not fabricated observations or quota exemptions.
            ntrans=sum('transverse' in p['metrics'] for p in self.controller.candidates)
            nheat=sum('power5' in p['metrics'] for p in self.state['candidates'])
            initial=sum(axis_observed(p) for p in self.controller.candidates)<=self.config.search.initial_points
            if initial and (stage in ('x','y') and ntrans<4 or stage=='thermal' and nheat<2):score*=3
            eligible.append((score,c,stage,group))
        parameters,source=self.controller.propose()
        x=self.controller.encode(parameters)[None,:]
        newscore=float(self.controller.score(x,sum(self.estimate(s) for s in STAGES))[0])
        # Initial coverage keeps its promised global coordinates, interleaved with promotions.
        if sum(axis_observed(p) for p in self.controller.candidates)<=self.config.search.initial_points:newscore*=2
        if eligible and max(eligible,key=lambda x:x[0])[0]>=newscore:
            _,c,stage,group=max(eligible,key=lambda x:x[0]);return c,stage,group
        return self.new_candidate(parameters,source),'axis',None

    def task(self,c: dict,stage: str) -> dict:
        identity=fingerprint(dict(contract=self.state['contract'],parameters=c['parameters'],ports=c['ports'],stage=stage))
        for job in self.state['jobs']:
            if job['identity']==identity:
                raise ValueError('Stage already dispatched under this exact identity')
        folder=self.artifacts/'candidates'/c['id']/f"attempt_{len(self.state['jobs']):05d}"
        return dict(identity=identity,directory=str(folder),template=self.snapshot['templates'][stage],
                    parameters=c['parameters'],ports=list(c['ports']),stage=stage)

    def receive(self,c: dict,j: dict,result: dict):
        self.store.complete_job(j,result)
        if result['status']!='complete':
            bad=bad_ports(result.get('error','')) if j['stage']!='thermal' else ()
            ports=next_ports(c['ports'],bad,c['tried_ports'],c['repair_attempts'],c['repair_seconds'],self.config.runtime) if bad else None
            if ports is not None:
                c['repair_attempts']+=1;c['ports']=list(ports);c['tried_ports'].append(list(ports));c['revision']+=1
                c['repair_stage']=j['stage']
                # Original records remain in the journal. A new consistent trio must be evaluated.
                c['stages']={};c['metrics']={};c['details']={}
                LOG.warning('%s port repair %s; invalidating prior combination for subtraction',c['id'],ports)
            else:c['failed']=True;c['failure']=result
            j['applied']=True;self.store.save();return
        c['stages'][j['stage']]=result
        if c.get('repair_stage')==j['stage']:c['repair_stage']=None
        old=dict(c['metrics'])
        try:
            analysis=offline_candidate(self.config,c,self.artifacts/'evidence'/c['id']/f"revision_{c['revision']:03d}")
        except (ValueError,OSError,np.linalg.LinAlgError) as exc:
            # Preserve independently reliable upstream metrics, never turn a fit error into zero.
            analysis=dict(metrics=dict(c['metrics']),details=dict(c['details']))
            key='longitudinal' if j['stage']=='axis' else 'transverse' if j['stage'] in ('x','y') else 'thermal'
            analysis['details'][key]=dict(status='uncertain',reasons=[str(exc)])
            c['analysis_error']=str(exc)
        c.update(analysis)
        c['complete']=all(s in c['stages'] for s in STAGES)
        m=c['metrics'];c['feasible']=m.get('longitudinal',float('inf'))<=self.config.physics.longitudinal_limit and m.get('transverse',float('inf'))<=self.config.physics.transverse_limit
        ranking=search_metrics(self.config,c)
        c['screening_metrics']=ranking if self.config.search.observation_mode=='finite_tail_screening' else {}
        comparable_key='best_screening_comparable' if self.config.search.observation_mode=='finite_tail_screening' else 'best_comparable'
        previous=self.state.get(comparable_key,{})
        self.controller.update_radius(previous,ranking)
        if all(k in ranking for k in METRICS[:2]):
            if not previous or max(ranking[k]/self.controller.limits[i] for i,k in enumerate(METRICS[:2]))<max(previous[k]/self.controller.limits[i] for i,k in enumerate(METRICS[:2])):
                self.state[comparable_key]=dict(ranking)
        self.state['rng']=self.controller.rng.bit_generator.state
        j['metrics']={k:v for k,v in m.items() if k not in old or old[k]!=v}
        j['applied']=True;self.store.save();self.store.mirror();LOG.info('%s %s returned: %s',c['id'],j['stage'],m)

    def recover(self):
        for completed in self.state['jobs']:
            if completed['status']!='reserved' and not completed.get('applied'):
                c=next(c for c in self.state['candidates'] if c['id']==completed['candidate'])
                self.receive(c,completed,completed['outcome'])
        if not self.state['pending']:
            # Explicit resume retries extraction once per invocation, never the solver.
            for c in self.state['candidates']:
                if not c['failed'] or c.get('failure',{}).get('category')!='postprocess_failed':continue
                last=next(j for j in reversed(self.state['jobs']) if j['candidate']==c['id'])
                folder=Path(last['directory'])
                if not (folder/'solved.json').exists():continue
                check_recovery(folder)
                task={k:last[k] for k in ('identity','directory','template','parameters','ports','stage')}
                task['result_filename']=f"worker_result_pp_{len(self.state['jobs']):05d}.json"
                job=self.store.reserve(c,last['stage'],task,None)
                c['failed']=False;self.store.save()
                result=self.backend(self.config_path,job,self.store,self.config.runtime.postprocess_timeout_s+300)
                self.receive(c,job,result)
            return
        j=next(j for j in self.state['jobs'] if j['id']==self.state['pending']);folder=Path(j['directory'])
        c=next(c for c in self.state['candidates'] if c['id']==j['candidate'])
        check_recovery(folder)
        output=folder/j.get('result_filename','worker_result.json')
        if output.exists():result=json.loads(output.read_text())
        elif (folder/'solved.json').exists():
            result=self.backend(self.config_path,j,self.store,self.config.runtime.postprocess_timeout_s+300)
        else:result=dict(status='failed',category='interrupted',error='Unfinished reserved task; no implicit solve replay')
        self.receive(c,j,result)

    def action(self,c: dict,stage: str,exploration: str | None):
        for drive in (self.store.root,self.artifacts):
            if shutil.disk_usage(drive).free<self.config.runtime.minimum_free_gib*2**30:raise RuntimeError('Disk free space below configured reserve')
        if not self.store.can_start(self.estimate(stage)):return False
        repairing=bool(c.get('repair_stage'))
        if repairing and c['repair_seconds']>=self.config.runtime.repair_timeout_s:
            c.update(failed=True,failure={'category':'repair_time_exhausted'});self.store.save();return True
        task=self.task(c,stage);j=self.store.reserve(c,stage,task,exploration)
        self.store.tick();self.store.exploration=exploration;start=time.monotonic()
        LOG.info('Dispatch %s %s ports=%s exploration=%s',c['id'],stage,c['ports'],exploration)
        timeout=self.config.runtime.stage_timeout_s+self.config.runtime.postprocess_timeout_s+600.
        if repairing:timeout=min(timeout,max(1.,self.config.runtime.repair_timeout_s-c['repair_seconds']))
        result=self.backend(self.config_path,j,self.store,timeout)
        elapsed=time.monotonic()-start;j['elapsed_s']=elapsed
        if repairing:c['repair_seconds']+=elapsed
        self.receive(c,j,result)
        j['elapsed_s']=time.monotonic()-start
        self.store.tick();self.store.exploration=None
        return True

    def report(self):
        complete=[c for c in self.state['candidates'] if c['complete'] and len(c['metrics'])==4]
        feasible=[c for c in complete if c['feasible']]
        best=min(feasible,key=lambda c:(max(c['metrics']['power5'],c['metrics']['power6']),c['metrics']['power5']+c['metrics']['power6'])) if feasible else None
        benchmark=all(any(j['stage']==s and j['status']=='complete' for j in self.state['jobs']) for s in STAGES)
        fronts=[c for c in complete if not any(all(other['metrics'][k]<=c['metrics'][k] for k in METRICS) and any(other['metrics'][k]<c['metrics'][k] for k in METRICS) for other in complete if other is not c)]
        report=dict(status=self.state['status'],active_hours=self.state['active_seconds']/3600,
            exploration_seconds=self.state['exploration_seconds'],candidates=len(self.state['candidates']),complete=len(complete),
            best=best,tradeoffs=fronts[:self.config.runtime.retain_pareto],
            desired_targets_reached=bool(best and max(best['metrics']['power5'],best['metrics']['power6'])<=self.config.physics.power_reference_w),
            uncertain=[c['id'] for c in self.state['candidates'] if c['details'] and any(d.get('status')=='uncertain' for d in c['details'].values())],
            failures=[dict(candidate=c['id'],failure=c.get('failure')) for c in self.state['candidates'] if c['failed']],
            estimated_stage_seconds={s:self.estimate(s) for s in STAGES},
            cost_basis='measured stages' if benchmark else 'provisional scheduling estimates; no candidate-count forecast',
            estimated_remaining_full_candidates=max(0,(self.config.search.hours*3600-self.state['active_seconds']))/sum(self.estimate(s) for s in STAGES) if benchmark else None,
            validity='Fixed 35 m wake reconstruction stability only; no unique modal inversion or thermal temperature prediction')
        report['observation_mode']=self.config.search.observation_mode
        if self.config.search.observation_mode=='finite_tail_screening':
            ranked=[search_view(self.config,c) for c in self.state['candidates'] if all(k in search_metrics(self.config,c) for k in METRICS[:2])]
            ranked.sort(key=lambda c:(max(1.,max(c['metrics'][k]/self.controller.limits[i] for i,k in enumerate(METRICS[:2]))),
                max(c['metrics'].get('power5',float('inf')),c['metrics'].get('power6',float('inf')))))
            report['screening_best']=dict(id=ranked[0]['id'],proxy_metrics=ranked[0]['metrics'],qualified_feasibility=False) if ranked else None
            report['screening_limit']='Finite-tail Fourier proxies rank directions; fitted uncertainty remains and no proxy establishes HOM feasibility'
        atomic_json(self.store.root/'report.json',report)
        with (self.store.root/'candidates.csv').open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=['id','source',*NAMES,*METRICS,'ports','complete','feasible','failed','projects'])
            writer.writeheader()
            for c in self.state['candidates']:
                writer.writerow(dict(id=c['id'],source=c['source'],**c['parameters'],**c['metrics'],ports=str(c['ports']),
                    complete=c['complete'],feasible=c['feasible'],failed=c['failed'],projects=';'.join(s.get('project','') for s in c['stages'].values())))

    def run(self,mode: str,diagnostic_stage: str | None=None):
        self.store.start_clock();self.state['status']='running';self.store.save()
        try:
            self.recover()
            baseline=self.state['candidates'][0]
            if diagnostic_stage:
                if diagnostic_stage not in baseline['stages']:self.action(baseline,diagnostic_stage,None)
                self.state['status']='diagnostic_complete';return
            while not baseline['complete'] and not baseline['failed']:
                if (self.store.root/'STOP').exists():self.state['status']='paused';return
                stage=self.next_stage(baseline)
                if not self.action(baseline,stage,'near' if self.gated(baseline,stage) else None):
                    self.state['status']='budget_exhausted';return
            self.state['baseline_admission']=baseline_admission(baseline)
            self.state['accepted']=self.state['baseline_admission']['ready']
            self.state['screening_admission']=screening_admission(baseline) if self.config.search.observation_mode=='finite_tail_screening' else {'ready':False}
            if not self.state['accepted'] and not self.state['screening_admission']['ready']:
                self.state['status']='baseline_needs_review';return
            if mode=='baseline':self.state['status']='baseline_complete';return
            while True:
                if (self.store.root/'STOP').exists():self.state['status']='paused';break
                c,stage,explore=self.select()
                if not self.action(c,stage,explore):self.state['status']='budget_exhausted';break
                self.report()
                removed=prune_native(self.config,self.state)
                if removed:LOG.info('Retired native project directories: %s',removed)
        except BaseException as exc:
            self.state['status']='needs_attention';self.state['error']=f'{type(exc).__name__}: {exc}';raise
        finally:
            self.store.tick();self.store.save();self.report();self.store.close()
