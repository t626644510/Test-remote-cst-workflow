"""Whole-band reconstructed-peak estimates with explicit epistemic uncertainty.

Impedances are ohm (longitudinal) or ohm/m (transverse). Ensemble intervals
are sensitivity envelopes, NOT calibrated confidence intervals. The measured
FT is retained only as contradictory evidence, never substituted for a fit.
"""
from __future__ import annotations
import copy
import math
import numpy as np

VERSION = 'local-reconstructed-consensus-v1'


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _diverse(indices, fits):
    return (len({fits[i].get('start_m') for i in indices}) >= 2
            and len({fits[i].get('rank') for i in indices}) >= 2)


def summarize(detail: dict, physics, settings, metric: str, arrays=None, threshold=None) -> dict:
    """Reassess every saved local window without refitting or running CST.

    A majority consensus requires >=4 of six fits, two starts and two ranks.
    Boundary tails exclude a fit only LOCALLY; unsupported/failed windows stay
    in the global estimate and block formal acceptance. All discarded values
    remain in the evidence. No identifiable finite peak means no GP observation.
    """
    result=copy.deepcopy(detail);d=result.setdefault('diagnostics',{})
    fits=d.get('fits',[]);windows=d.get('windows',[])
    if threshold is None:threshold=physics.longitudinal_limit if metric=='longitudinal' else physics.transverse_limit
    lo,hi=physics.band_hz;required=max(4,math.ceil(2*len(fits)/3))
    indices=[i for i,f in enumerate(fits) if _finite(f.get('peak'))]
    output=[];cursor=lo;coverage=bool(windows);reasons=[]
    for window in windows:
        left,right=window['band_hz'];coverage &= abs(left-cursor)<=1 and right>left;cursor=right
        vals=window.get('peaks',[]);bad=window.get('boundary_tail_peaks',[])
        ids=window.get('fit_indices',indices)
        rows=[(i,float(v),float(b)) for i,v,b in zip(ids,vals,bad)
              if i<len(fits) and _finite(v) and _finite(b)]
        clean=[(i,v,b) for i,v,b in rows if b<=settings.bound_tail_fraction*max(v,1e-30)]
        quality=[(i,v,b) for i,v,b in clean if fits[i].get('valid')]
        # Sliding relative-width cluster; only quality-passing independent fits
        # can identify a numerical outlier rather than simply ignore a high peak.
        ordered=sorted(quality,key=lambda row:row[1]);groups=[]
        for start in range(len(ordered)):
            group=[r for r in ordered[start:] if (r[1]-ordered[start][1])/max(r[1],1e-30)<=settings.peak_spread]
            if len(group)>=required and _diverse([r[0] for r in group],fits):groups.append(group)
        group=max(groups,key=lambda g:(len(g),max(r[1] for r in g)),default=[])
        support=group or clean or rows
        qualified=bool(group)
        # Two incompatible majority clusters cannot normally exist, but preserve
        # ambiguity if the requested ensemble changes in a future configuration.
        if groups and max(max(r[1] for r in g) for g in groups)>min(min(r[1] for r in g) for g in groups)/(1-settings.peak_spread):qualified=False
        if not support:
            output.append(dict(band_hz=[left,right],estimate=None,lower=None,upper=None,
                relative_uncertainty=None,qualified=False,unbounded=True,reason='no_finite_reconstruction',fit_indices=[]));continue
        values=np.array([r[1] for r in support]);estimate=float(np.median(values))
        floor=max((max(float(fits[i].get('error',1)),float(fits[i].get('holdout_error',1))) for i,_,_ in support),default=1.)
        rel=max(.02,floor,float((values.max()-values.min())/max(estimate,1e-30)))
        unbounded=not bool(group) and (len(clean)<required or not _diverse([r[0] for r in clean],fits))
        if not qualified:rel=max(rel,.25)
        if unbounded:rel=max(rel,1.)
        lower=max(0.,min(float(values.min()),estimate*(1-rel)))
        upper=max(float(values.max()),estimate*(1+rel))
        # Measured-spectrum contradictions block a below-threshold claim; they
        # do not replace the reconstructed estimate used for GP regression.
        observed=float(window.get('direct_peak',0));contradiction=observed>threshold and upper<=threshold
        straddles=lower<=threshold<upper
        qualified=qualified and not straddles and not contradiction
        output.append(dict(band_hz=[left,right],estimate=estimate,lower=lower,
            upper=None if unbounded else upper,finite_upper_estimate=upper,
            relative_uncertainty=rel,qualified=qualified,unbounded=unbounded,
            decision='exceeds' if observed>threshold or lower>threshold else 'below' if qualified and upper<=threshold else 'unresolved',
            fit_indices=[r[0] for r in support],all_fit_peaks=[dict(index=i,peak=v,boundary_tail=b) for i,v,b in rows],
            excluded_fit_indices=[i for i,_,_ in rows if i not in [r[0] for r in support]],
            direct_evidence_peak=observed,contradictory_evidence=contradiction,threshold_straddled=straddles,reason=None if qualified else 'local_peak_uncertainty'))
    coverage &= abs(cursor-hi)<=1
    # Check upper-band rising peaks using the actual consensus contributors.
    # A rejected boundary-pole fit cannot globally poison otherwise sound windows.
    edge=False
    if arrays is not None and output:
        for i in output[-1]['fit_indices']:
            fk=f'fit_{i}_frequency_hz';zk=f'fit_{i}_impedance'
            if fk not in arrays or zk not in arrays:edge=True;continue
            f=arrays[fk];z=arrays[zk]
            if metric=='transverse':
                z=z.reshape(-1,2,2);g=np.real(np.swapaxes(z.conj(),1,2)@z);v=np.sqrt(np.maximum(0,np.linalg.eigvalsh(g)[:,-1]))
            else:v=np.abs(z[:,0])
            j=max(0,min(len(f)-2,int(np.searchsorted(f,hi-d.get('base_resolution_hz',1),side='right'))-1))
            if v[-1]>v[j] and v[-1]>.1*threshold:edge=True
    else:edge='band_edge_peak' in result.get('reasons',[])
    finite=bool(output) and all(_finite(w['estimate']) for w in output) and coverage
    unbounded=not finite or edge or any(w['unbounded'] for w in output)
    estimate=max(w['estimate'] for w in output) if finite else None
    lower=max((w['lower'] for w in output if w['lower'] is not None),default=None)
    finite_upper=max((w.get('finite_upper_estimate',0) for w in output),default=None)
    upper=finite_upper if not unbounded else None
    rel=max(.02,(finite_upper-estimate)/max(estimate,1e-30)) if finite else None
    if unbounded and finite:rel=max(1.,rel)
    qualified=finite and not edge and all(w['qualified'] for w in output)
    unresolved=[w['band_hz'] for w in output if not w['qualified']]
    if not coverage:reasons.append('incomplete_band_partition')
    if unresolved:reasons.append('unresolved_peak_windows')
    if edge:reasons.append('band_edge_peak')
    if not finite:reasons.append('no_full_band_peak_estimate')
    peak=dict(method=VERSION,estimate=estimate,lower=lower,upper=upper,
        relative_uncertainty=rel,unbounded=unbounded,full_band_coverage=bool(coverage),
        qualified=bool(qualified),contradictory_evidence=any(w.get('contradictory_evidence',False) for w in output),unresolved_windows=unresolved,band_edge_unresolved=bool(edge),
        uncertainty_kind='ensemble sensitivity envelope; not a calibrated probability interval')
    d.update(reconstructed_peak=peak,local_consensus_windows=output,
        decision='exceeds' if any(w.get('decision')=='exceeds' for w in output) else 'below' if qualified and upper<=threshold else 'unresolved')
    result.update(status='valid' if qualified else 'uncertain',value=upper if qualified else None,reasons=reasons)
    return result
