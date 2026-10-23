"""WF6.1: eight free coordinates, longitudinal constraint and CW loss search.

Reconstructed longitudinal impedance is in ohm. Losses are in W at the configured
peak cavity voltage (500 kV, CW beta=1). Historical geometries with different
fixed coordinates are reference-only; they are never projected into the 8-D GP.
"""
from __future__ import annotations
import csv
from pathlib import Path
import numpy as np
from scipy.special import ndtr
from .config import NAMES
from .io import atomic_json
from .search import Controller
from .screening import search_metrics, reconstruction_uncertainty, stage_below

OBJECTIVES = ('longitudinal', 'power5', 'power6')


def formal_longitudinal(config, candidate: dict) -> bool:
    """Require qualified whole-band reconstruction and the formal ohm limit."""
    u = reconstruction_uncertainty(candidate).get('longitudinal', {})
    return bool(u.get('qualified') and candidate.get('metrics', {}).get('longitudinal', float('inf'))
                <= config.physics.longitudinal_limit and stage_below(config, candidate, 'longitudinal'))


def heat_rank(candidate: dict) -> tuple:
    """Minimize worst branch W; total W breaks ties. No saturation at 150 W."""
    m = candidate.get('metrics', {})
    a, b = m.get('power5', float('inf')), m.get('power6', float('inf'))
    return max(a, b), a+b


class HeatController(Controller):
    """Three GPs on eight free coordinates within two explicit neighborhoods."""
    def pool(self, center=None):
        result = []
        half = np.array([self.config.search.neighborhood_half_widths[n] for n in self.names])/self.width
        centers = [self.encode(p) for p in self.config.search.seed_points]
        for _ in range(100):
            for base in centers:
                lo, hi = np.maximum(0., base-half), np.minimum(1., base+half)
                count = max(2, self.config.search.pool//len(centers))
                points = self.rng.uniform(lo, hi, (count, len(self.names)))
                if center is not None and np.all(center >= lo) and np.all(center <= hi):
                    n = count//2
                    points[:n] = self.rng.uniform(np.maximum(lo, center-self.state['radius']),
                                                 np.minimum(hi, center+self.state['radius']), (n,len(self.names)))
                result.extend(x for x in points if not self.geometry.violations(self.decode(x)))
            if len(result) >= self.config.search.pool: break
        if not result: raise ValueError('No feasible WF6.1 neighborhood points')
        return np.asarray(result[:self.config.search.pool])

    def score(self, x, cost, observed=None, observed_uncertainty=None):
        pred = self.predictions(x)
        for key, value in (observed or {}).items():
            if key not in OBJECTIVES: continue
            limit = self.config.physics.longitudinal_limit if key == 'longitudinal' else self.config.physics.power_reference_w
            ratio = value/limit
            rel = (observed_uncertainty or {}).get(key, {}).get('relative_uncertainty', 0.)
            pred[key] = (np.full(len(x),np.log1p(ratio)), np.full(len(x),np.log1p(ratio*(1+rel))-np.log1p(ratio)))
        mean, std = pred['longitudinal']
        probability = ndtr((np.log(2.)-mean)/np.maximum(std,1e-9))
        feasible = [c for c in self.state['candidates'] if formal_longitudinal(self.config,c)
                    and all(k in c.get('metrics',{}) for k in OBJECTIVES)]
        if feasible:
            best = min(heat_rank(c)[0] for c in feasible)/self.config.physics.power_reference_w
            samples = []
            for key in ('power5','power6'):
                mu, sig = pred[key]
                samples.append(np.expm1(np.clip(mu[None,:]+sig[None,:]*self.rng.standard_normal((64,len(x))),-10,20)))
            improvement = np.maximum(0., best-np.maximum(*samples)).mean(axis=0)
            return (improvement+1e-4)*probability/max(cost,1.)
        # Seek longitudinal feasibility while preferring likely lower heat.
        heat = np.maximum(*(pred[k][0]-.7*pred[k][1] for k in ('power5','power6')))
        return probability*np.exp(-np.clip(heat,-5,10))/max(cost,1.)

    def propose(self):
        existing = self.state['candidates']
        best = sorted([c for c in existing if formal_longitudinal(self.config,c)],key=heat_rank)
        center = self.encode(best[0]['parameters']) if best else None
        pool = self.pool(center)
        if existing:
            old = np.asarray([self.encode(c['parameters']) for c in existing])
            distance = np.min(np.linalg.norm(pool[:,None,:]-old[None,:,:],axis=2),axis=1)
            keep = distance > 1e-6
            pool, distance = pool[keep], distance[keep]
        else: distance = np.ones(len(pool))
        if not len(pool): raise ValueError('WF6.1 deduplicated pool exhausted')
        observed = sum('longitudinal' in search_metrics(self.config,c) for c in existing)
        explore = observed < self.config.search.initial_points or len(self.models)<3 or self.rng.random()<.2
        index = int(np.argmax(distance if explore else self.score(pool,1.)))
        self.state['rng'] = self.rng.bit_generator.state
        return self.decode(pool[index]), 'wf61_neighborhood_maximin' if explore else 'wf61_constrained_heat_ei'

    def update_radius(self, old, new, old_uncertainty=None, new_uncertainty=None):
        # Do not contract on failures, unresolved wakes, or overlapping envelopes.
        if not all(k in old and k in new for k in OBJECTIVES): return
        a = (old_uncertainty or {}).get('longitudinal',{})
        b = (new_uncertainty or {}).get('longitudinal',{})
        if not all(u.get('qualified') and not u.get('unbounded',True) and u.get('upper') is not None
                   and u['upper'] <= self.config.physics.longitudinal_limit for u in (a,b)): return
        before, after = max(old['power5'],old['power6']), max(new['power5'],new['power6'])
        margin = self.config.search.native_relative_noise
        if after*(1+margin) < before*(1-margin): improve=True
        elif after*(1-margin) > before*(1+margin): improve=False
        else:return
        self.state['improving'] = self.state['improving']+1 if improve else 0
        self.state['not_improving'] = 0 if improve else self.state['not_improving']+1
        if self.state['improving'] >= 3:
            self.state['radius']=min(self.config.search.max_radius,self.state['radius']*1.3);self.state['improving']=0
        if self.state['not_improving'] >= 6:
            self.state['radius']=max(self.config.search.min_radius,self.state['radius']*.7);self.state['not_improving']=0


def select_action(campaign):
    """Two seeds first, then axis→thermal promotions and diverse nearby proposals."""
    cfg, state, ctl = campaign.config, campaign.state, campaign.controller
    excluded = getattr(campaign,'excluded_candidate_ids',set())
    available = [c for c in state['candidates'] if c['id'] not in excluded and not c['failed'] and not c['complete']]
    repairs = [c for c in available if c.get('repair_stage')]
    if repairs: return repairs[0],campaign.next_stage(repairs[0]),None
    for point in cfg.search.seed_points:
        c = next((c for c in state['candidates'] if c['parameters']==point),None)
        if c is None: return campaign.new_candidate(dict(point),'wf61_seed'),'axis',None
        if c in available and 'axis' not in c['stages']: return c,'axis',None
    ctl.fit()
    # Promote finite noncontradictory screening envelopes <=1.5 kohm normally.
    # Formal reporting remains stricter: all reconstruction windows qualified.
    ready = [c for c in available if 'axis' in c['stages'] and 'thermal' not in c['stages']
             and stage_below(cfg,c,'longitudinal')]
    if ready:
        c = max(ready,key=lambda c:float(ctl.score(ctl.encode(c['parameters'])[None,:],campaign.estimate('thermal'),
                         search_metrics(cfg,c),reconstruction_uncertainty(c))[0]))
        return c,'thermal',None
    # Bounded runtime allowance prevents uncertain longitudinal fits from entirely
    # excluding potentially useful heat observations; never grants formal feasibility.
    pending = [c for c in available if 'axis' in c['stages'] and 'thermal' not in c['stages']
               and 'longitudinal' in search_metrics(cfg,c)]
    cost = campaign.estimate('thermal')
    exp = state['exploration_seconds']
    if pending and sum(exp.values())+cost <= cfg.search.exploration_fraction*(state['active_seconds']+cost):
        group = 'near' if exp['near'] <= exp['global'] else 'global'
        return pending[0],'thermal',group
    new, source = ctl.propose()
    return campaign.new_candidate(new,source),'axis',None


def report(campaign):
    """Publish multiple formal heat candidates separately from uncertain estimates."""
    cfg, state = campaign.config, campaign.state
    complete = [c for c in state['candidates'] if c['complete']]
    formal = sorted([c for c in complete if formal_longitudinal(cfg,c) and all(k in c['metrics'] for k in OBJECTIVES)],key=heat_rank)
    screening = sorted([c for c in complete if stage_below(cfg,c,'longitudinal') and all(k in c['metrics'] for k in ('power5','power6'))],key=heat_rank)
    result = dict(workflow='WF6.1',status=state['status'],search_policy=cfg.search.policy,
                  active_hours=state['active_seconds']/3600,budget_hours=cfg.search.hours,
                  candidates=len(state['candidates']),complete=len(complete),formal_feasible=len(formal),
                  best=formal[0] if formal else None,feasible_candidates=formal,
                  screening_candidates=screening,transverse_evaluated=False,
                  desired_targets_reached=bool(formal and heat_rank(formal[0])[0]<=cfg.physics.power_reference_w),
                  completion_policy='continue below 150 W; 48 h shared clock; drain current stages; manual next round',
                  fixed_parameters=cfg.fixed_parameters,active_parameters=list(cfg.active_names),
                  reference_only=state.get('reference_history',{}),
                  node_seconds=state.get('node_seconds',{}),prior_active_hours=state.get('prior_active_seconds',0)/3600,
                  pending_nodes=state.get('pending_nodes',{}),failures=[c['id'] for c in state['candidates'] if c['failed']])
    atomic_json(campaign.store.root/'report.json',result)
    with (campaign.store.root/'candidates.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        cols=['id','source',*NAMES,*OBJECTIVES,'longitudinal_estimate','longitudinal_upper','complete','feasible','failed','projects']
        writer=csv.DictWriter(stream,fieldnames=cols);writer.writeheader()
        for c in state['candidates']:
            u=reconstruction_uncertainty(c).get('longitudinal',{})
            writer.writerow(dict(id=c['id'],source=c['source'],**c['parameters'],
                                 **{k:v for k,v in c['metrics'].items() if k in OBJECTIVES},
                                 longitudinal_estimate=u.get('estimate'),longitudinal_upper=u.get('upper'),
                                 complete=c['complete'],feasible=c['feasible'],failed=c['failed'],
                                 projects=';'.join(s.get('project','') for s in c['stages'].values())))
