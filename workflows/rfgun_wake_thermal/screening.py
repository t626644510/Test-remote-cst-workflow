"""Search metrics separated from qualified whole-band acceptance.

Reconstructed-peak mode uses local ensemble estimates with uncertainty, in ohm
or ohm/m. Legacy finite-tail mode is retained for reproducibility only. Neither
an unresolved peak nor a direct FT comparison proves physical feasibility.
"""
from __future__ import annotations
import math


def finite_tail_metrics(candidate:dict)->dict:
    """Use the same proxy for every impedance, even when its fit is reliable."""
    values={k:v for k,v in candidate.get('metrics',{}).items() if k in ('power5','power6')}
    for metric in ('longitudinal','transverse'):
        detail=candidate.get('details',{}).get(metric,{})
        diag=detail.get('diagnostics',{})
        value=diag.get('direct_peak')
        # This field only exists after full-band, finite, unit-checked reconstruction.
        if isinstance(value,(int,float)) and math.isfinite(value) and value>=0:
            values[metric]=float(value)
    return values


def search_metrics(config,candidate:dict)->dict:
    if config.search.observation_mode=='reconstructed_peak_screening':return reconstructed_metrics(candidate)
    return finite_tail_metrics(candidate) if config.search.observation_mode=='finite_tail_screening' else candidate.get('metrics',{})


def search_view(config,candidate:dict)->dict:
    metrics=search_metrics(config,candidate)
    uncertainty=reconstruction_uncertainty(candidate) if config.search.observation_mode=='reconstructed_peak_screening' else {}
    feasible=all(stage_below(config,candidate,k) for k in ('longitudinal','transverse'))
    if config.search.policy=='longitudinal_heat':
        feasible=stage_below(config,candidate,'longitudinal')
    return dict(candidate,metrics=metrics,metric_uncertainty=uncertainty,feasible=feasible)


def reconstruction_uncertainty(candidate:dict)->dict:
    """Return persisted reconstruction envelopes; never infer them from direct FT."""
    return {k:d['diagnostics']['reconstructed_peak'] for k,d in candidate.get('details',{}).items()
            if k in ('longitudinal','transverse') and d.get('diagnostics',{}).get('reconstructed_peak')}


def reconstructed_metrics(candidate:dict)->dict:
    """Whole-band reconstructed peak estimates in ohm or ohm/m, thermal in W."""
    result={k:v for k,v in candidate.get('metrics',{}).items() if k in ('power5','power6')}
    for k,u in reconstruction_uncertainty(candidate).items():
        v=u.get('estimate')
        if u.get('method')=='local-reconstructed-consensus-v1' and u.get('full_band_coverage') and isinstance(v,(int,float)) and math.isfinite(v) and v>=0:result[k]=v
    return result


def ranking_metrics(config,candidate:dict)->dict:
    """Penalize peak uncertainty consistently in sorting and local search centers.

    An unbounded interval remains unresolved even though its estimate can guide
    exploration. The finite penalty is a search heuristic, never an upper bound.
    """
    result=dict(search_metrics(config,candidate))
    if config.search.observation_mode=='reconstructed_peak_screening':
        for k,u in reconstruction_uncertainty(candidate).items():
            if k in result:result[k]=max(result[k],u.get('upper') or result[k]*(1+u['relative_uncertainty']))
    return result


def stage_below(config,candidate:dict,metric:str)->bool:
    limit=config.physics.longitudinal_limit if metric=='longitudinal' else config.physics.transverse_limit
    if config.search.observation_mode=='reconstructed_peak_screening':
        u=reconstruction_uncertainty(candidate).get(metric,{})
        return bool(u.get('full_band_coverage') and not u.get('unbounded',True) and not u.get('contradictory_evidence',False)
                    and u.get('upper') is not None and u['upper']<=limit)
    return search_metrics(config,candidate).get(metric,math.inf)<=limit


def screening_admission(candidate:dict,config=None)->dict:
    reconstructed=config is not None and config.search.observation_mode=='reconstructed_peak_screening'
    metrics=reconstructed_metrics(candidate) if reconstructed else finite_tail_metrics(candidate)
    ready=bool(candidate.get('complete') and not candidate.get('failed') and len(metrics)==4
        and candidate.get('details',{}).get('thermal',{}).get('status')=='valid')
    return dict(ready=ready,scope='uncertain reconstructed-peak screening' if reconstructed else 'preliminary finite-tail ranking only',metrics=metrics,
        qualified_feasibility=False,limitation='Unresolved windows prevent formal acceptance; ensemble uncertainty is not a calibrated error bound')
