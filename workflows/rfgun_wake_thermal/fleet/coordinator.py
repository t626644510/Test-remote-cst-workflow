"""Single-writer two-station campaign journal, conservative replay and fallback."""
from __future__ import annotations
from copy import deepcopy
import logging, os, time, subprocess
from pathlib import Path
from typing import Any
from .protocol import Node, fingerprint, read_json, unpack_evidence
from .transport import Transport
from ..campaign import Campaign
from ..storage import Store, verify_evidence
from ..io import atomic_json
from ..search import Controller,make_controller
from ..supervision import process_birth

LOG=logging.getLogger(__name__)


def logical_key(candidate: dict, stage: str) -> str:
    return fingerprint(dict(parameters=candidate['parameters'],ports=candidate['ports'],stage=stage))


class FleetStore(Store):
    """Wall-clock round budget, with independent station effort counters."""
    def start_clock(self):
        now=time.time(); previous=self.state.get('fleet_clock_at')
        # Only an unresolved admitted attempt can keep consuming budget while
        # coordinator is down. A paused empty campaign never accrues idle time.
        if previous and self.state.get('pending_nodes'):
            self.state['active_seconds']+=max(0.,now-previous)
        self.last_tick=time.monotonic();self.state['fleet_clock_at']=now
    def tick(self):
        if self.last_tick is None:return
        now=time.monotonic();dt=max(0.,now-self.last_tick);self.last_tick=now
        self.state['active_seconds']+=dt;self.state['fleet_clock_at']=time.time()
        ids=set(self.state.get('pending_nodes',{}).values())
        groups=[j.get('exploration') for j in self.state['jobs'] if j['id'] in ids and j.get('exploration')]
        # Preserve the existing wall-time exploration definition. Concurrent
        # gated stages share one elapsed interval, rather than double-charge it.
        for group in groups:self.state['exploration_seconds'][group]+=dt/len(groups)
        self.save()
    def complete_job(self,j:dict,result:dict):
        j.update(status=result['status'],outcome=result,finished_at=time.time())
        self.save();self.mirror()


class FleetCampaign(Campaign):
    """Two local-disk workers, central numeric replay, both-station failure policy."""
    def __init__(self,config,config_path:Path,contract:str,snapshot:dict,nodes:list[Node],execution:str):
        self.config=config;self.config_path=config_path;self.snapshot=snapshot
        self.store=FleetStore(config,contract);self.state=self.store.state
        self.controller=make_controller(config,self.state);self.artifacts=Path(config.paths.artifact_dir)
        self.nodes={n.name:n for n in nodes};self.transports={n.name:Transport(n) for n in nodes}
        self.execution=execution;self.excluded_candidate_ids=set()
        if len(nodes)!=2 or len([n for n in nodes if not n.ssh_host])!=1:
            raise ValueError('Exactly one local and one remote station are required')
        if self.state.get('pending'):raise ValueError('Serial stage must finish before fleet entry')
        self.state.setdefault('pending_nodes',{});self.state.setdefault('fleet_retry',[])
        self.state.setdefault('node_seconds',{n.name:0. for n in nodes})

    def choose(self,node:str):
        busy={j['candidate'] for j in self.state['jobs'] if j['id'] in self.state['pending_nodes'].values()}
        queue=self.state['fleet_retry'];priority=self.state.get('priority_transverse',[])
        ordered=sorted(queue,key=lambda q:(priority.index(q['candidate']) if q['candidate'] in priority else len(priority),q['queued_at']))
        for q in ordered:
            if q['node']==node and q['candidate'] not in busy:
                c=next(c for c in self.state['candidates'] if c['id']==q['candidate'])
                return c,q['stage'],q.get('exploration'),q
        self.excluded_candidate_ids=busy|{q['candidate'] for q in queue}
        try:
            c,stage,exploration=self.select()
            return c,stage,exploration,None
        finally:self.excluded_candidate_ids=set()

    def dispatch(self,node:str,c:dict,stage:str,exploration:str|None,retry:dict|None=None)->dict:
        if stage not in self.config.active_stages:raise ValueError('Stage disabled by search policy')
        if node in self.state['pending_nodes']:raise ValueError('Station already has a reserved task')
        if any(j['candidate']==c['id'] for j in self.state['jobs'] if j['id'] in self.state['pending_nodes'].values()):
            raise ValueError('Candidate already in flight on another station')
        key=logical_key(c,stage)
        if any(j.get('node')==node and j.get('logical_key')==key and not j.get('inherited')
               and j.get('status')!='not_started' for j in self.state['jobs']):
            raise ValueError('This station already attempted the exact physical stage')
        if not self.store.can_start(0):raise ValueError('Round admission deadline reached')
        job_id=f"job_{len(self.state['jobs']):05d}";now=time.time()
        task=dict(id=job_id,contract=self.state['contract'],parameters=deepcopy(c['parameters']),ports=list(c['ports']),stage=stage)
        task['identity']=fingerprint({k:task[k] for k in ('contract','parameters','ports','stage')})
        repairing=c.get('repair_stage')==stage
        remaining_repair=self.config.runtime.repair_timeout_s-c['repair_seconds']
        if repairing and remaining_repair<=0:raise ValueError('Candidate repair clock exhausted; do not start another repair')
        task['timeout_s']=min(self.config.runtime.stage_timeout_s+self.config.runtime.postprocess_timeout_s+600,remaining_repair) if repairing else self.config.runtime.stage_timeout_s+self.config.runtime.postprocess_timeout_s+600
        task.update(node=node,execution=self.execution,admit_before=now+min(90.,self.config.search.hours*3600-self.state['active_seconds']),
            station_recovery=True,station_deadline=now+self.config.search.hours*3600-self.state['active_seconds'])
        if repairing:task['repair_budget_s']=remaining_repair
        j=dict(task,candidate=c['id'],status='reserved',logical_key=key,exploration=exploration,
            reserved_at=now,elapsed_s=0.,directory=str(self.artifacts/'fleet_evidence'/job_id/'attempt_00000'),
            template=self.snapshot['templates'][stage],wire=task,repairing=c.get('repair_stage')==stage)
        self.state['jobs'].append(j);self.state['pending_nodes'][node]=job_id
        if retry:self.state['fleet_retry'].remove(retry)
        self.store.save()
        # If delivery outcome is unknown, reservation survives. Poll and repeat
        # the immutable publication; never give its candidate to the other node.
        self.transports[node].publish(f'inbox/{job_id}.json',task)
        LOG.info('Fleet dispatch %s %s %s %s ports=%s',job_id,node,c['id'],stage,c['ports'])
        return j

    def accept(self,j:dict,outcome:dict):
        for key in ('id','node','execution','identity'):
            if outcome.get(key)!=j[key]:raise ValueError('Returned attempt identity mismatch: '+key)
        c=next(c for c in self.state['candidates'] if c['id']==j['candidate'])
        if outcome['status']=='not_started':
            j.update(status='not_started',outcome=outcome,applied=True,elapsed_s=0.)
            self.state['fleet_retry'].append(dict(candidate=c['id'],stage=j['stage'],node=j['node'],
                exploration=j['exploration'],queued_at=time.time(),reason='expired admission, no solver attempt'))
            self.store.save();return
        if outcome.get('quiescent') is not True:raise ValueError('Station exit was not certified')
        if not j.get('received'):
            bundle=Path(j['directory']).parent/'evidence.zip'
            self.transports[j['node']].fetch(outcome['evidence'],bundle)
            unpack_evidence(bundle,Path(j['directory']),outcome['sha256'])
            saved=read_json(Path(j['directory'])/'task.json')
            for key in ('id','identity','stage','ports','parameters'):
                if saved[key]!=j[key]:raise ValueError('Archived task mismatch: '+key)
            j['received']=outcome;self.store.save()
        result=deepcopy(outcome['result'])
        if result['status']=='complete':
            if result.get('identity')!=j['identity'] or result.get('stage')!=j['stage']:
                raise ValueError('Numerical result identity mismatch')
            proof=read_json(Path(j['directory'])/'solved.json')
            if proof.get('identity')!=j['identity']:raise ValueError('Saved solve certificate identity mismatch')
            raw=Path(j['directory'])/'raw'
            if not verify_evidence(raw):raise ValueError('Raw numerical manifest mismatch')
            bundle=read_json(raw/'bundle.json')
            if j['stage']!='thermal':
                for key in ('identity','stage','ports','parameters'):
                    if bundle[key]!=j[key]:raise ValueError('Raw bundle identity mismatch: '+key)
            result.update(raw=str(raw),native_project=result.get('project'),node=j['node'])
            # Remote paths remain explicit native references, never local inputs.
            result['project']=(self.nodes[j['node']].ssh_host+'::'+result['project']) if self.nodes[j['node']].ssh_host else result['project']
        if not j.get('effort_accounted'):
            j['elapsed_s']=outcome['elapsed_s'];self.state['node_seconds'][j['node']]+=j['elapsed_s']
            if j.get('repairing'):c['repair_seconds']+=j['elapsed_s']
            j['effort_accounted']=True;self.store.save()
        self.apply_result(c,j,result)

    def apply_result(self,c:dict,j:dict,result:dict):
        """Only definitive station failures enter the other station's FIFO."""
        if j.get('applied'):return
        if result['status']=='complete':
            c['failed']=False
            super().receive(c,j,result);return
        if result.get('category')=='recovery_deferred':
            self.store.complete_job(j,result);c['failed']=False
            c['recovery_deferred']=dict(job=j['id'],node=j['node'],reason=result['error'])
            j['applied']=True;self.store.save();return
        if j.get('wire',{}).get('station_recovery') and result.get('station_recovery_complete') is not True:
            raise RuntimeError('Station recovery must finish before cross-station fallback')
        if result.get('category') in ('cleanup_failed','ownership_failed'):
            raise RuntimeError('Station safety failure must be diagnosed before fallback')
        if result.get('repair_budget_exhausted'):
            self.store.complete_job(j,result);c.update(failed=True,failure=dict(category='repair_time_exhausted',error=result.get('error','')))
            j['applied']=True;self.store.save();return
        others=[x for x in self.state['jobs'] if x.get('logical_key')==j['logical_key']
            and x.get('node')!=j['node'] and x.get('status')=='failed' and not x.get('inherited')]
        if not others:
            self.store.complete_job(j,result)
            target=next(n for n in self.nodes if n!=j['node'])
            if not any(q['candidate']==c['id'] for q in self.state['fleet_retry']):
                self.state['fleet_retry'].append(dict(candidate=c['id'],stage=j['stage'],node=target,
                    exploration=j.get('exploration'),queued_at=time.time(),reason='other station definitive failure',from_job=j['id']))
            c['failed']=False;j['applied']=True;self.store.save();return
        # Preserve each error; an explicit mesh failure at either station can
        # activate the established bounded repair after both tried this geometry.
        combined=dict(result,error='\n'.join([x['outcome'].get('error','') for x in others]+[result.get('error','')]))
        super().receive(c,j,combined)

    def poll(self)->dict:
        snapshots={};self.state.setdefault('node_health',{})
        for node,transport in self.transports.items():
            try:
                snap=transport.inspect();snapshots[node]=snap
                fresh=time.time()-snap.get('time',0)<60
                healthy=fresh and snap.get('process_matches') and snap.get('status') in ('idle','running')
                if snap.get('execution')!=self.execution:healthy=False
                self.state['node_health'][node]=dict(time=time.time(),healthy=bool(healthy),status=snap.get('status'),
                    heartbeat=snap.get('time'),job=snap.get('job'),error=snap.get('error'),free_bytes=snap.get('free_bytes'))
                jid=self.state['pending_nodes'].get(node)
                if jid:
                    j=next(j for j in self.state['jobs'] if j['id']==jid)
                    outcome=snap.get('outcomes',{}).get(jid)
                    if outcome:
                        self.accept(j,outcome)
                        if j.get('applied'):
                            self.state['pending_nodes'].pop(node);self.store.save();self.report()
                    elif healthy:
                        transport.publish(f'inbox/{jid}.json',j['wire'])
            except (ConnectionError,TimeoutError,OSError,subprocess.TimeoutExpired) as exc:
                self.state['node_health'][node]=dict(time=time.time(),healthy=False,status='unreachable',error=str(exc))
                LOG.warning('Station %s unavailable; preserve pending ownership: %s',node,exc)
        self.store.save();return snapshots

    def report(self):
        super().report()
        path=self.store.root/'report.json';report=read_json(path)
        report['fleet']=dict(pending_nodes=self.state.get('pending_nodes'),retry_queue=self.state.get('fleet_retry'),
            node_health=self.state.get('node_health'),node_hours={k:v/3600 for k,v in self.state.get('node_seconds',{}).items()},
            budget_basis='48h elapsed active round time; parallel node hours reported separately; drain every admitted stage')
        atomic_json(path,report)

    def run_fleet(self):
        if self.state['status']=='budget_exhausted':raise ValueError('Closed round requires user audit')
        self.store.start_clock();self.state['status']='running';self.store.save()
        notified_stop=set()
        try:
            while True:
                self.store.tick();self.poll()
                stop=(self.store.root/'STOP').exists();exhausted=not self.store.can_start(0)
                if stop or exhausted:
                    self.state['status']='draining'
                    # Close physical retry admission while allowing the current solve to drain.
                    for name,transport in self.transports.items():
                        if name in notified_stop:continue
                        try:transport.stop_when_idle();notified_stop.add(name)
                        except (ConnectionError,TimeoutError,OSError,subprocess.TimeoutExpired):
                            LOG.warning('Station %s STOP delivery uncertain; retry next poll',name)
                    if not self.state['pending_nodes']:
                        self.state['status']='budget_exhausted' if exhausted else 'paused';break
                else:
                    for node in self.nodes:
                        health=self.state.get('node_health',{}).get(node,{})
                        if node in self.state['pending_nodes'] or not health.get('healthy') or health.get('status')!='idle':continue
                        if health.get('free_bytes',0)<20*1024**3:continue
                        if not self.store.can_start(0):break
                        c,stage,exp,retry=self.choose(node)
                        self.store.tick()
                        if not self.store.can_start(0):break
                        try:self.dispatch(node,c,stage,exp,retry)
                        except (ConnectionError,TimeoutError,OSError,subprocess.TimeoutExpired) as exc:LOG.warning('Delivery uncertain; reserved task retained: %s',exc)
                atomic_json(self.store.root/'heartbeat.json',dict(time=time.time(),pid=os.getpid(),birth=process_birth(os.getpid()),
                    status=self.state['status'],pending_nodes=self.state['pending_nodes'],active_seconds=self.state['active_seconds']))
                time.sleep(5.)
        except BaseException as exc:
            self.state.update(status='needs_attention',error=f'{type(exc).__name__}: {exc}');raise
        finally:
            self.store.tick();self.store.last_tick=None;self.store.save();self.store.db.close();self.report()
            if not self.state['pending_nodes']:
                for transport in self.transports.values():
                    try:transport.stop_when_idle()
                    except (ConnectionError,TimeoutError,OSError,subprocess.TimeoutExpired):LOG.exception('Could not stop idle station')
            if self.state['status']=='budget_exhausted':
                (self.store.root/'STOP').write_text('Round complete. Await manual user audit and next-round start.\n',encoding='utf-8')
