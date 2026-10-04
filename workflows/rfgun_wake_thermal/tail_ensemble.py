"""Local confidence for measured wakes completed by a shared-pole missing tail.

The old validated analysis used manually reviewed peak windows. Here windows
are discovered from this record, never copied from an earlier geometry.
Unstable or bound-controlled tails remain explicitly unresolved. Their values
cannot authorize a qualified below-threshold claim. Search-only reconstructed
estimates retain their uncertainty separately from qualified values.
"""
from __future__ import annotations
import logging
import numpy as np
from scipy.signal import find_peaks,windows as signal_windows
from .measured_tail import C,VERSION,raw_transform,pencil_seeds,fit_tail

LOG=logging.getLogger(__name__)


def reconstruct_measured(s,wake,physics,settings,direction,threshold):
    """Six rank/start explanations, independent prefix holdouts and local peak tests.

    Metrics use ohm or ohm/m. Cross-fit relative range is (max-min)/max;
    the default 10% is a screening tolerance, not a statistical error bound.
    """
    from .reconstruction import FitResult,transverse_norm
    s=np.asarray(s,float);w=np.asarray(wake,float).reshape(len(s),-1)
    channels=4 if direction=='transverse' else 1
    if channels!=w.shape[1] or len(s)<32 or not np.isfinite(w).all() or not np.isfinite(s).all() or np.any(np.diff(s)<=0):
        raise ValueError('Incomplete or nonfinite signed wake bundle')
    if s[-1]<physics.wake_length_m*.98:raise ValueError('Wake tail shorter than configured length')
    if s[0]>-3*physics.sigma_m:raise ValueError('Wake origin/leading bunch missing')
    lo,hi=physics.band_hz
    if np.exp(-.5*(2*np.pi*hi*physics.sigma_m/C)**2)<settings.min_bunch_spectrum:
        return FitResult('uncertain',None,['insufficient_bunch_spectrum'],{}, {})
    norm=lambda z:transverse_norm(z.reshape(-1,2,2)) if channels==4 else abs(z[:,0])
    coarse=np.linspace(lo,hi,settings.spectrum_points)
    raw=raw_transform(s,w,coarse,physics.sigma_m,direction);direct=norm(raw)
    fits=[];models=[];arrays=dict(frequency_hz=coarse,direct=raw)
    resolution=C/(s[-1]-s[0]);reasons=[]
    for start in settings.starts_m:
        ts=np.linspace(start,s[-1],settings.fit_points)
        data=np.column_stack([np.interp(ts,s,w[:,j]) for j in range(channels)])
        effective_ranks=tuple(min(rank,2*settings.max_modes) for rank in settings.pencil_ranks)
        seeds=pencil_seeds(ts,data,effective_ranks,(settings.pole_min_hz,hi+settings.frequency_width_hz),
                           settings.decay_bounds_per_m,settings.pencil_spacing_m,settings.pencil_rows)
        for rank,(f,a) in zip(settings.pencil_ranks,seeds):
            row=dict(start_m=start,rank=rank,valid=False)
            try:
                if len(f)>settings.max_modes:raise ValueError('pole_capacity_exceeded')
                fit=fit_tail(ts,data,f,a,settings.frequency_width_hz,settings.decay_bounds_per_m,settings.max_nfev)
                # A separately fitted prefix must predict the withheld end of the wake.
                # Full-fit poles are NOT passed as holdout seeds (which would leak data).
                prefix=ts<=start+(s[-1]-start)*settings.holdout_fraction
                pf,pa=pencil_seeds(ts[prefix],data[prefix],(min(rank,2*settings.max_modes),),
                    (settings.pole_min_hz,hi+settings.frequency_width_hz),settings.decay_bounds_per_m,
                    settings.pencil_spacing_m,settings.pencil_rows)[0]
                if len(pf)>settings.max_modes:raise ValueError('holdout_pole_capacity_exceeded')
                held=fit_tail(ts[prefix],data[prefix],pf,pa,settings.frequency_width_hz,settings.decay_bounds_per_m,settings.max_nfev)
                holdout=float(np.linalg.norm(held.predict(ts[~prefix])-data[~prefix])/max(np.linalg.norm(data[~prefix]),1e-30))
                valid=fit.success and held.success and fit.error<=settings.max_error and fit.correlation>=settings.min_correlation and holdout<=settings.max_error
                row.update(valid=bool(valid),error=fit.error,correlation=fit.correlation,holdout_error=holdout,
                    optimizer_success=fit.success,holdout_success=held.success,boundary=fit.boundary.tolist(),
                    frequency_hz=fit.frequency_hz.tolist(),alpha_per_m=fit.alpha.tolist(),coefficients=fit.coeff.tolist(),
                    mid_m=fit.mid_m)
                arrays.update({f'fit_{len(fits)}_s_m':ts,f'fit_{len(fits)}_wake':fit.predict(ts)})
                models.append(fit)
            except (ValueError,np.linalg.LinAlgError,FloatingPointError) as exc:
                row['failure']=str(exc);models.append(None)
            fits.append(row)
            LOG.info('%s measured-tail start=%s rank=%s valid=%s error=%s holdout=%s',direction,start,rank,row['valid'],row.get('error'),row.get('holdout_error'))
    if not any(m is not None for m in models):
        return FitResult('uncertain',None,['no_resolvable_poles'],dict(fits=fits,method=VERSION),arrays)
    # Include narrow linewidths and exact pole centres. Evaluate the full measured
    # transform at these frequencies rather than interpolating a coarse FFT.
    extra=[]
    for m in models:
        if m is not None:
            for f,a in zip(m.frequency_hz,m.alpha):
                if lo<=f<=hi:extra.append(np.clip(f+np.linspace(-4,4,41)*a*C/(2*np.pi),lo,hi))
    extra=np.unique(np.concatenate(extra)) if extra else np.array([])
    extra_raw=raw_transform(s,w,extra,physics.sigma_m,direction) if len(extra) else np.empty((0,channels),complex)
    both=np.r_[coarse,extra];order=np.argsort(both);grid,unique=np.unique(both[order],return_index=True)
    measured=np.concatenate((raw,extra_raw))[order][unique];scores=[];bad_scores=[]
    for i,m in enumerate(models):
        if m is None:scores.append(None);bad_scores.append(None);continue
        completed=measured+m.tail(s[-1],grid,physics.sigma_m,direction)
        bad=m.tail(s[-1],grid,physics.sigma_m,direction,np.flatnonzero(m.boundary))
        scores.append(norm(completed));bad_scores.append(norm(bad))
        arrays.update({f'fit_{i}_frequency_hz':grid,f'fit_{i}_impedance':completed})
        fits[i]['peak']=float(scores[-1].max())
    # Discover windows from direct peaks and the poles, merging centres below the
    # measured resolution. Windows partition the WHOLE requested band.
    # Use the fitted pole union for windows; raw rectangular-tail sidelobes are
    # not extra modes. An observed peak far from every pole is still included.
    tapered=norm(raw_transform(ts,data*signal_windows.blackmanharris(len(ts))[:,None],coarse,physics.sigma_m,direction))
    peaks,_=find_peaks(tapered,prominence=max(tapered.max()*settings.peak_prominence_fraction,1e-15))
    centers=sorted(list(coarse[peaks])+[f for m in models if m is not None for f in m.frequency_hz if lo<f<hi])
    clusters=[]
    for f in centers:
        if clusters and f-clusters[-1][-1]<resolution*.5:clusters[-1].append(f)
        else:clusters.append([f])
    centers=np.array([np.mean(x) for x in clusters]);edges=np.r_[lo,(centers[1:]+centers[:-1])/2,hi]
    if not len(centers):edges=np.array([lo,hi])
    windows=[];all_reliable=all(row['valid'] for row in fits);stable_peaks=[]
    for left,right in zip(edges[:-1],edges[1:]):
        mask=(grid>=left)&(grid<=right);observed=float(norm(measured[mask]).max())
        values=[float(a[mask].max()) for a in scores if a is not None]
        contamination=[float(a[mask].max()) for a in bad_scores if a is not None]
        uncontaminated=len(values)==len(fits) and all(b<=settings.bound_tail_fraction*max(v,1e-30) for b,v in zip(contamination,values))
        spread=(max(values)-min(values))/max(max(values),1e-30)
        straddles=min(values)<=threshold<max(values)
        stable=all_reliable and uncontaminated and spread<=settings.peak_spread and not straddles
        decision='exceeds' if observed>threshold or (all_reliable and uncontaminated and min(values)>threshold) else 'below' if stable and max(values)<=threshold else 'unresolved'
        windows.append(dict(band_hz=[float(left),float(right)],peaks=values,direct_peak=observed,
            boundary_tail_peaks=contamination,fit_indices=[i for i,a in enumerate(scores) if a is not None],spread=spread,stable=bool(stable),decision=decision))
        if stable:stable_peaks.append(max(observed,max(values)))
    # Finite-band endpoints need explicit treatment even when fits look stable.
    # Report the in-band endpoints; an out-of-band working mode's smooth
    # decreasing skirt at the lower bound is not an unobserved in-band peak.
    upper_index=max(0,int(np.searchsorted(grid,hi-resolution)))
    edge_rise=any(a is not None and a[-1]>a[upper_index] and a[-1]>.1*threshold for a in scores)
    if not all_reliable:reasons.append('fit_or_holdout_quality')
    if not all(x['stable'] for x in windows):reasons.append('unresolved_peak_windows')
    if edge_rise:reasons.append('band_edge_peak')
    value=max(stable_peaks) if stable_peaks and not reasons else None
    decision='exceeds' if any(x['decision']=='exceeds' for x in windows) else 'below' if value is not None and value<=threshold else 'unresolved'
    legacy=FitResult('valid' if value is not None else 'uncertain',value,reasons,
        dict(method=VERSION,fits=fits,windows=windows,decision=decision,direct_peak=float(direct.max()),
             lower_evidence_exceeds=decision=='exceeds',base_resolution_hz=resolution,
             identifiability='Measured segment retained; local tail stability does not prove unique modes'),arrays)

    from .peak_consensus import summarize
    revised=summarize(legacy.summary(),physics,settings,direction,arrays,threshold)
    return FitResult(revised['status'],revised['value'],revised['reasons'],revised['diagnostics'],arrays)
