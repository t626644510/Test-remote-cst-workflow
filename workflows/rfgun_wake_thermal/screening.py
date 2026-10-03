"""Explicit finite-tail search proxies, separate from qualified HOM maxima.

The unchanged measured wake's Fourier peak (ohm or ohm/m) provides a comparable
directional surrogate. It can underestimate a narrow resonance: it never proves
physical feasibility. Full tail reconstructions and their uncertainty remain in
the qualified evidence. Do not mix tail lengths within a screening campaign.
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
    return finite_tail_metrics(candidate) if config.search.observation_mode=='finite_tail_screening' else candidate.get('metrics',{})


def search_view(config,candidate:dict)->dict:
    metrics=search_metrics(config,candidate)
    return dict(candidate,metrics=metrics,feasible=(metrics.get('longitudinal',math.inf)<=config.physics.longitudinal_limit
        and metrics.get('transverse',math.inf)<=config.physics.transverse_limit))


def screening_admission(candidate:dict)->dict:
    metrics=finite_tail_metrics(candidate)
    ready=bool(candidate.get('complete') and not candidate.get('failed') and len(metrics)==4
        and candidate.get('details',{}).get('thermal',{}).get('status')=='valid')
    return dict(ready=ready,scope='preliminary finite-tail ranking only',metrics=metrics,
        qualified_feasibility=False,limitation='Narrow HOM peaks may be underestimated; reconstruction uncertainty is retained')
