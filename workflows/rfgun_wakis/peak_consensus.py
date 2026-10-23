"""Whole-band reconstructed-peak estimates with explicit epistemic uncertainty.

Impedances are ohm (longitudinal) or ohm/m (transverse). Ensemble intervals
are sensitivity envelopes, NOT calibrated confidence intervals. The measured
FT is retained only as contradictory evidence, never substituted for a fit.
"""
from __future__ import annotations
import copy
import math
import numpy as np

VERSION = 'local-reconstructed-quality-v3'
SENSITIVE_MARGIN = .10  # Engineering headroom, not a calibrated confidence level.


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _diverse(indices, fits):
    return (len({fits[i].get('start_m') for i in indices}) >= 2
            and len({fits[i].get('rank') for i in indices}) >= 2)


def _valid_fit(fit: dict, settings) -> bool:
    """Require the saved independent holdout and full-fit quality evidence."""
    return (fit.get('valid') is True and fit.get('optimizer_success') is True
            and fit.get('holdout_success') is True
            and _finite(fit.get('error')) and fit['error'] <= settings.max_error
            and _finite(fit.get('holdout_error')) and fit['holdout_error'] <= settings.max_error
            and _finite(fit.get('correlation')) and fit['correlation'] >= settings.min_correlation)


def summarize(detail: dict, physics, settings, metric: str, arrays=None, threshold=None) -> dict:
    """Reassess every saved local window without refitting or running CST.

    A majority consensus requires >=4 of six fits, two starts and two ranks.
    Quality is independent of the engineering threshold. A bounded-sensitive
    window pools ALL valid clean fits, including disagreeing majority groups.
    Unsupported windows still block acceptance and never receive a GP exemption.
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
        quality=[(i,v,b) for i,v,b in clean if _valid_fit(fits[i],settings)]
        # Sliding relative-width cluster; only quality-passing independent fits
        # can identify a numerical outlier rather than simply ignore a high peak.
        ordered=sorted(quality,key=lambda row:row[1]);groups=[]
        for start in range(len(ordered)):
            group=[r for r in ordered[start:] if (r[1]-ordered[start][1])/max(r[1],1e-30)<=settings.peak_spread]
            if len(group)>=required and _diverse([r[0] for r in group],fits):groups.append(group)
        group=max(groups,key=lambda g:(len(g),max(r[1] for r in g)),default=[])
        consensus=bool(group)
        # Two incompatible majority clusters cannot normally exist, but preserve
        # ambiguity if the requested ensemble changes in a future configuration.
        incompatible=bool(groups) and max(max(r[1] for r in g) for g in groups)>min(min(r[1] for r in g) for g in groups)/(1-settings.peak_spread)
        consensus=consensus and not incompatible
        supported=len(quality)>=required and _diverse([r[0] for r in quality],fits)
        grade='consensus' if consensus else 'bounded_sensitive' if supported else 'unsupported'
        support=group if consensus else quality if supported else (clean or rows)
        qualified=consensus
        if not support:
            output.append(dict(band_hz=[left,right],estimate=None,lower=None,upper=None,
                relative_uncertainty=None,qualified=False,quality='unsupported',unbounded=True,
                reason='no_finite_reconstruction',fit_indices=[]));continue
        values=np.array([r[1] for r in support]);estimate=float(np.median(values))
        floor=max((max(float(fits[i].get('error',1)),float(fits[i].get('holdout_error',1))) for i,_,_ in support),default=1.)
        rel=max(.02,floor,float((values.max()-values.min())/max(estimate,1e-30)))
        unbounded=not supported
        if not qualified:rel=max(rel,.25)
        # Keep the old noisy-trend scale evidence independently of acceptance.
        # It is NOT a physical lower bound. Invalid-but-finite fits may describe
        # an order of magnitude, with the existing >=ln(3) GP noise, but cannot
        # establish bounded engineering acceptance or a quality exemption.
        scale_supported=len(clean)>=required and _diverse([r[0] for r in clean],fits)
        scale_relative=rel if scale_supported else max(rel,1.)
        search_scale_lower=max(0.,min(float(values.min()),estimate*(1-scale_relative)))
        if unbounded:rel=max(rel,1.)
        lower=max(0.,min(float(values.min()),estimate*(1-rel)))
        upper=max(float(values.max()),estimate*(1+rel))
        # Measured-spectrum contradictions block a below-threshold claim; they
        # do not replace the reconstructed estimate used for GP regression.
        observed=float(window.get('direct_peak',0));contradiction=observed>threshold and upper<=threshold
        straddles=lower<=threshold<upper
        decision=('exceeds' if lower>threshold else 'unresolved' if unbounded or observed>threshold or upper>threshold
                  else 'consensus_pass' if consensus else 'envelope_pass' if upper<=(1-SENSITIVE_MARGIN)*threshold
                  else 'unresolved')
        output.append(dict(band_hz=[left,right],estimate=estimate,lower=lower,
            upper=None if unbounded else upper,finite_upper_estimate=upper,
            relative_uncertainty=rel,qualified=qualified,quality=grade,unbounded=unbounded,
            search_scale_lower=search_scale_lower,
            decision=decision,incompatible_majorities=incompatible,
            valid_clean_indices=[i for i,_,_ in quality],
            fit_indices=[r[0] for r in support],all_fit_peaks=[dict(index=i,peak=v,boundary_tail=b) for i,v,b in rows],
            excluded_fit_indices=[i for i,_,_ in rows if i not in [r[0] for r in support]],
            direct_evidence_peak=observed,contradictory_evidence=contradiction,threshold_straddled=straddles,reason=None if qualified else 'local_peak_uncertainty'))
    coverage &= abs(cursor-hi)<=1
    # Check upper-band rising peaks using the actual consensus contributors.
    # A rejected boundary-pole fit cannot globally poison otherwise sound windows.
    edge=False;edge_complete=arrays is not None
    if arrays is not None and output:
        for i in output[-1]['fit_indices']:
            fk=f'fit_{i}_frequency_hz';zk=f'fit_{i}_impedance'
            if fk not in arrays or zk not in arrays:edge=True;edge_complete=False;continue
            f=arrays[fk];z=arrays[zk]
            if metric=='transverse':
                z=z.reshape(-1,2,2);g=np.real(np.swapaxes(z.conj(),1,2)@z);v=np.sqrt(np.maximum(0,np.linalg.eigvalsh(g)[:,-1]))
            elif metric=='transverse_x':v=np.linalg.norm(z,axis=1)
            else:v=np.abs(z[:,0])
            j=max(0,min(len(f)-2,int(np.searchsorted(f,hi-d.get('base_resolution_hz',1),side='right'))-1))
            if v[-1]>v[j] and v[-1]>.1*threshold:edge=True
    else:edge='band_edge_peak' in result.get('reasons',[])
    # Keep the measured edge-rise diagnostic, but let a bounded subsidiary
    # window affect the objective only if it can reach the consensus main peak.
    # No extrapolated claim is made about frequencies outside the fixed band.
    edge_rising=bool(edge)
    main_lower=max((w['lower'] for w in output[:-1] if w['quality']=='consensus'),default=None)
    if (edge and edge_complete and output and output[-1]['upper'] is not None
            and main_lower is not None and output[-1]['upper']<main_lower):edge=False
    finite=bool(output) and all(_finite(w['estimate']) for w in output) and coverage
    unbounded=not finite or edge or any(w['unbounded'] for w in output)
    estimate=max(w['estimate'] for w in output) if finite else None
    lower=max((w['lower'] for w in output if w['lower'] is not None),default=None)
    search_scale_lower=max((w.get('search_scale_lower',0.) for w in output),default=None)
    finite_upper=max((w.get('finite_upper_estimate',0) for w in output),default=None)
    upper=finite_upper if not unbounded else None
    rel=max(.02,(finite_upper-estimate)/max(estimate,1e-30)) if finite else None
    if unbounded and finite:rel=max(1.,rel)
    grade=('unsupported' if not finite or any(w['quality']=='unsupported' for w in output)
           else 'consensus' if all(w['quality']=='consensus' for w in output) else 'bounded_sensitive')
    contradictory=any(w.get('contradictory_evidence',False) for w in output)
    qualified=grade=='consensus' and not unbounded and not contradictory
    unresolved=[w['band_hz'] for w in output if not w['qualified']]
    sensitive=[w for w in output if w['quality']=='bounded_sensitive']
    sensitive_upper=max((w['upper'] for w in sensitive),default=None)
    main_lower=max((w['lower'] for w in output if w['quality']=='consensus'),default=None)
    nondominant=bool(grade=='bounded_sensitive' and not unbounded and not contradictory
                     and main_lower is not None and sensitive_upper is not None and sensitive_upper<main_lower)
    direct_peak=max((w.get('direct_evidence_peak',0) for w in output),default=0.)
    decision=('unresolved' if unbounded else 'exceeds' if lower>threshold
              else 'unresolved' if direct_peak>threshold or upper>threshold or contradictory
              else 'consensus_pass' if grade=='consensus'
              else 'envelope_pass' if sensitive_upper is not None and sensitive_upper<=(1-SENSITIVE_MARGIN)*threshold
              else 'unresolved')
    if not coverage:reasons.append('incomplete_band_partition')
    if unresolved:reasons.append('unresolved_peak_windows')
    if edge:reasons.append('band_edge_peak')
    if not finite:reasons.append('no_full_band_peak_estimate')
    peak=dict(method=VERSION,estimate=estimate,lower=lower,upper=upper,
        relative_uncertainty=rel,unbounded=unbounded,full_band_coverage=bool(coverage),
        qualified=bool(qualified),quality=grade,contradictory_evidence=contradictory,
        unresolved_windows=unresolved,band_edge_unresolved=bool(edge),band_edge_rising=edge_rising,
        sensitive_upper=sensitive_upper,consensus_main_lower=main_lower,
        search_scale_lower=search_scale_lower,
        non_dominant_sensitive=nondominant,direct_evidence_peak=direct_peak,
        acceptance=decision,acceptance_threshold=threshold,sensitive_margin=SENSITIVE_MARGIN,
        uncertainty_kind='ensemble sensitivity envelope; not a calibrated probability interval')
    d.update(reconstructed_peak=peak,local_consensus_windows=output,
        decision=decision)
    result.update(status='valid' if qualified else 'uncertain',value=upper if qualified else None,reasons=reasons)
    return result
