"""Replay-safe adaptive local radius from comparable RF sensitivity envelopes.

The merit is dimensionless; RF inputs retain ohm, ohm/metre and 500 kV CW W.
These heuristic envelopes are not calibrated confidence intervals. Overlap,
unknown bounds, contradictions and failed simulations never count as losses.
"""
from __future__ import annotations
from typing import Mapping
import numpy as np
from .config import Config
from .observations import METRICS, Observation

AXIS_METRICS=('longitudinal','heat_1','heat_2','leak_2','leak_3')
REQUIRED=('longitudinal','heat_1','heat_2')

def bounded(observation: Observation | None) -> bool:
    """Require actual native finite envelopes, never the unbounded rank penalty."""
    return bool(observation and observation.search_eligible and not observation.contradictory
                and observation.lower is not None and observation.upper is not None)

def reference(observations: Mapping[str,Observation]) -> dict | None:
    """Capture at least L and both heat metrics, allowing an unmeasured X stage."""
    if not all(bounded(observations.get(k)) for k in REQUIRED):return None
    return {k:observations[k].as_dict() for k in AXIS_METRICS if bounded(observations.get(k))}

def merit_bounds(observations: Mapping[str,Observation], keys: list[str], config: Config) -> tuple[float,float]:
    from .search import utility
    # Missing metrics use the same neutral values on both sides; they cannot
    # create a fictitious improvement and are never persisted as observations.
    neutral=dict(zip(METRICS,(config.physics.longitudinal_limit,0.,0.,0.,
                             config.physics.leakage_limit_w,config.physics.leakage_limit_w)))
    endpoints=[]
    for endpoint in ('lower','upper'):
        values=dict(neutral)
        values.update({k:getattr(observations[k],endpoint) for k in keys})
        endpoints.append(float(utility(np.array([values[k] for k in METRICS]),config)))
    return tuple(endpoints)

def update_trust(state: dict, candidate: dict, config: Config) -> None:
    """Apply one axis comparison per proposal; replay and stale pipelines are safe."""
    if not candidate.get('axis_directory'):return
    trust=state.setdefault('trust',dict(generation=0,successes=0,failures=0,processed=[],events=[]))
    key=candidate['id']
    if key in trust['processed']:return
    proposal=candidate.get('proposal',{});ref=proposal.get('trust_reference')
    before=state['radius'];event=dict(candidate=key,radius_before=before,radius_after=before)
    obs={k:Observation(**v) for k,v in candidate['observations'].items()}
    if not ref:event['decision']='no_reference'
    elif proposal.get('trust_generation',0)!=trust['generation']:event['decision']='stale_radius_generation'
    elif not all(bounded(obs.get(k)) for k in ref):event['decision']='incomparable_bounds'
    else:
        old={k:Observation(**v) for k,v in ref.items()}
        a=merit_bounds(old,list(ref),config);b=merit_bounds(obs,list(ref),config)
        event.update(metrics=list(ref),reference_merit=list(a),candidate_merit=list(b))
        if b[1]<a[0]-1e-12:
            event['decision']='disjoint_improvement';trust['successes']+=1;trust['failures']=0
        elif b[0]>a[1]+1e-12:
            event['decision']='disjoint_worsening';trust['failures']+=1;trust['successes']=0
        else:event['decision']='overlapping_envelopes'
        settings=config.search
        if trust['successes']>=settings.radius_successes:
            state['radius']=min(settings.max_radius,before*settings.radius_expand)
        elif trust['failures']>=settings.radius_failures:
            state['radius']=max(settings.min_radius,before*settings.radius_contract)
        if state['radius']!=before:
            trust['generation']+=1;trust['successes']=trust['failures']=0
            event['radius_after']=state['radius']
    trust['processed'].append(key);trust['events'].append(event)
