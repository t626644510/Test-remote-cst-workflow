"""Depth-one CPU preparation alongside GPU evolution, with a single state writer."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import time, uuid
from .failures import classify_failure
from .io import atomic_json,read_json,validate_manifest
from .processes import OwnershipError

class PreparationPipeline:
    """Prefetch at most one next geometry; never admit its field solve implicitly.

    All methods run on the coordinator thread. Worker wall times overlap, but
    only the coordinator's union wall time is charged to the 48-hour budget.
    A STOP drains a running preparation and stores it for explicit resumption.
    """
    def __init__(self,campaign):
        self.campaign=campaign;self.handle=None

    @property
    def job(self):return self.campaign.store.data.get('prefetch')

    def maybe_start(self) -> None:
        """Launch only during actual GPU time stepping, with extra host RAM."""
        import psutil
        c=self.campaign;data=c.store.data;current=data.get('pending')
        if (not c.config.runtime.prefetch or data['status']!='running' or self.job
                or not current or current.get('prefetch_considered') or data.get('pipeline_error')):return
        if '_solve_' not in current.get('phase',''):return
        status=Path(current.get('field_directory',''))/'status.json'
        if not status.is_file() or (status.parent/'field_complete.json').exists():return
        progress=read_json(status)
        if progress.get('phase')!='wake' or not 0<progress.get('step',0)<progress.get('total',0):return
        # A status file survives the worker. Never prefetch from a stale replay.
        request=current.get('phase_requests',{}).get(current['phase'])
        if not request:return
        owner=Path(request).with_suffix('.owner.json')
        if not owner.exists():return
        from .cst_prepare import ProcessIdentity
        if not any(ProcessIdentity(**dict(v,command=tuple(v['command']))).alive()
                   for v in read_json(owner)['processes']):return
        if data['active_seconds']>=c.store.cap or (c.root/'STOP').exists():return
        others=[(i,v) for i,v in enumerate(data['candidates']) if i!=current['candidate_index'] and v['status']=='axis_pending']
        if any(v.get('prepared') for _,v in others):return
        if not others and data.get('dispatch_mode')=='queued_only':return
        if psutil.virtual_memory().available/2**30<c.config.runtime.prefetch_free_ram_gib:return
        c.check_provenance()
        index=others[0][0] if others else c.propose_candidate()
        candidate=data['candidates'][index]
        job=dict(key=candidate['id']+'_axis',candidate_index=index,stage='axis',preparation_only=True,
                 forced_transverse=candidate['forced_transverse'],started=time.time(),attempt=0,phase_requests={})
        current['prefetch_considered']=candidate['id'];data['prefetch']=job;c.store.save()
        self.poll()

    def _request(self) -> Path:
        c=self.campaign;job=self.job;candidate=c.store.data['candidates'][job['candidate_index']]
        name=f'prepare_{job["attempt"]:02}';job['phase']=name
        paths=job['phase_requests']
        if name not in paths:
            path=c.root/'jobs'/job['key']/(name+'.json')
            spec=dict(phase='prepare',parameters=candidate['parameters'],
                output=str(c.bulk/candidate['id']/f'preparation_{job["attempt"]:02}'),
                request_id=uuid.uuid4().hex,config=str(c.config_path),contract=c.config.digest())
            atomic_json(path,spec);paths[name]=str(path);c.store.save()
        return Path(paths[name])

    def poll(self) -> None:
        """Persist completion before releasing the slot; replay does not relaunch."""
        c=self.campaign;data=c.store.data;job=self.job
        if not job or data.get('pipeline_error'):return
        if self.handle is None:
            path=self._request()
            # If interrupted before launching, STOP forbids a new process.
            if data['status']!='running' and not any(path.with_suffix(s).exists() for s in
                    ('.owner.json','.reply.json','.supervision_result.json')):
                data['prefetch']=None;c.store.save();return
            self.handle=c.supervisor.start(path,c.config.runtime.mesh_timeout_s+900)
            self.handle.memory_floor_gib=c.config.runtime.prefetch_running_free_ram_gib
            self.handle.memory_grace_s=0.
        result=c.supervisor.poll(self.handle)
        if result is None:return
        candidate=data['candidates'][job['candidate_index']]
        if result['status']=='completed':
            value=result['result'];prepared=Path(value['prepared'])
            if value['cst']['parameters']!=candidate['parameters']:
                raise OwnershipError('Prefetch parameter identity mismatch')
            validate_manifest(prepared,read_json(prepared/'manifest.json'))
            candidate['prepared']=str(prepared);candidate['cst']=value['cst']
            candidate['preparation_phase_requests']=dict(job['phase_requests'])
            data.setdefault('preparations',[]).append(dict(job,finished=time.time(),status='completed'))
            data['prefetch']=None;self.handle=None;c.store.save();return
        policy=classify_failure('prepare',result.get('traceback',''))
        failure=dict(result,failure_policy=asdict(policy))
        job.setdefault('phase_failures',{})[job['phase']]=failure
        self.handle=None
        if policy.retry_identical and job['attempt']<c.config.runtime.retries and data['status']=='running':
            job['attempt']+=1;c.store.save();return
        candidate.update(status='failed',failed_stage='prepare',prefetch_failure=failure)
        if not any(f['job']['key']==job['key'] for f in data['failures']):
            data['failures'].append(dict(job=dict(job),error=failure,utc_s=time.time()))
        data.setdefault('preparations',[]).append(dict(job,finished=time.time(),status='failed'))
        data['prefetch']=None;c.store.save();c.report()
        recent=data['candidates'][-3:]
        if len(recent)==3 and all(v['status']=='failed' for v in recent):
            raise RuntimeError('Three consecutive candidate preparation failures; stop dispatch')

    def service(self) -> None:
        """An auxiliary lane fault drains foreground physics before surfacing."""
        c=self.campaign
        if c.store.data.get('pipeline_error'):return
        try:self.poll();self.maybe_start()
        except Exception as exc:
            c.store.data['pipeline_error']=dict(at=time.time(),error=repr(exc),job=self.job)
            c.store.drain('safety')

    def wait(self) -> None:
        """Wait for admitted preparation only, never activate another candidate."""
        while self.job and not self.campaign.store.data.get('pipeline_error'):
            self.campaign.tick()
            if self.job:time.sleep(2)
        error=self.campaign.store.data.get('pipeline_error')
        if error:raise OwnershipError('Preparation pipeline requires review: '+error['error'])
