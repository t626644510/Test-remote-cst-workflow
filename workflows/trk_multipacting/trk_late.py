"""Finite TRK event windows and selected-scan report; ns, MHz, kV, C.

Event weights, not unweighted trajectory counts, define effective SEY. This
reconstructs recorded TRK tracks, not self-consistent PIC electron density.
"""
from __future__ import annotations
import csv
import html
import json
from pathlib import Path
from typing import Any
import numpy as np
from .trk_model import population


def _event_windows_exact(a: np.ndarray, generations: np.ndarray, stats: dict[str, Any],
                  curves: dict[str, Any], frequency_mhz: float, width_rf: int = 3, strict_currents: bool = True) -> dict[str, Any]:
    """Validate endpoint events against CST totals and return weighted RF windows.

    Windows are (start, end], ns; RF period = 1000/frequency_MHz. Source weights
    are normalized by the seed macrocharge only to compare with a 1 A source.
    SEY itself is independent of this common normalization. No collision => None.
    """
    a=np.atleast_2d(a); g=np.atleast_2d(generations)
    _,checks=population(a,stats)
    if g.shape != (len(a),2) or not np.array_equal(a[:,0],g[:,0]):
        raise ValueError('Generation and lifetime record mismatch')
    if not np.isfinite(frequency_mhz) or frequency_mhz<=0 or width_rf<=0:
        raise ValueError('Invalid RF frequency/window')
    gen=g[:,1]
    if not np.all(np.isfinite(gen)) or np.any(gen<0) or np.any(gen!=np.floor(gen)):
        raise ValueError('Invalid generations')
    birth=a[:,3];death=a[:,4];q=np.abs(a[:,5]);last=float(death.max())
    end=last if stats['final'] else max(last,stats['final_time_ns'])
    alive=(death==last) if stats['final'] else np.zeros(len(a),bool)
    into_solid=(a[:,7]==1)&~alive
    coll=~alive&~into_solid;emit=gen>0
    if (int(into_solid.sum())!=stats['into_solid'] or not np.all(birth[into_solid]==death[into_solid])
            or int(coll.sum())!=stats['collided'] or int(emit.sum())!=stats['secondary']
            or int((gen==0).sum())!=stats['initial']
            or any(stats[k] for k in ['passed','blocked','dying','ionization'])):
        raise ValueError('Unresolved trajectory endpoint classification; no inferred SEY')
    scale=float(q[gen==0].sum())
    if scale<=0:raise ValueError('No positive seed weight')
    validation={}
    warnings=[]
    for kind,mask in [('Collision',coll),('Emission',emit)]:
        total=sum(sum(v['y']) for k,v in curves.items() if f'Total {kind} Information\\Current\\' in k)
        value=float(q[mask].sum()/scale)
        if not np.isclose(value,total,rtol=3e-6,atol=1e-10):
            message=f'{kind} endpoint weights do not match CST currents'
            if strict_currents:raise ValueError(message)
            warnings.append(dict(message=message,reference=total,trajectory=value))
        bins={}
        for k,v in curves.items():
            if f'SEE {kind} Information\\Current\\' in k:
                for x,y in zip(v['x'],v['y']):bins[int(x)]=bins.get(int(x),0.)+y
        # Compare all emitted/collided generations, including zero or omitted bins.
        for generation in set(bins)|set(gen[mask].astype(int)):
            if not np.isclose(q[mask&(gen==generation)].sum()/scale,bins.get(generation,0.),rtol=3e-6,atol=1e-10):
                message=f'{kind} generation {generation} mismatch'
                if strict_currents:raise ValueError(message)
                warnings.append(dict(message=message,reference=bins.get(generation,0.),
                                     trajectory=float(q[mask&(gen==generation)].sum()/scale)))
        validation[kind]=dict(reference_current_A=total,reconstructed_current_A=value,events=int(mask.sum()))
    period=1000/frequency_mhz;width=width_rf*period
    def accumulate(events: np.ndarray,weights: np.ndarray,t: float) -> float:
        order=np.argsort(events);times=events[order];sums=np.r_[0.,np.cumsum(weights[order])]
        return float(sums[np.searchsorted(times,t,side='right')])
    # Pre-sort once: windows cost O(log N), not repeated full-trajectory scans.
    def series(mask: np.ndarray,event_time: np.ndarray):
        order=np.argsort(event_time[mask]);ts=event_time[mask][order]
        sums=np.r_[0.,np.cumsum(q[mask][order])]
        return ts,sums
    ct,cq=series(coll,death);et,eq=series(emit,birth)
    births=np.sort(birth);deaths=np.sort(death[~alive])
    def count(t):return int(np.searchsorted(births,t,'right')-np.searchsorted(deaths,t,'right'))
    def window(hi):
        lo=hi-width;ci=np.searchsorted(ct,[lo,hi],'right');ei=np.searchsorted(et,[lo,hi],'right')
        inc=float(cq[ci[1]]-cq[ci[0]]);out=float(eq[ei[1]]-eq[ei[0]])
        return dict(start_ns=lo,end_ns=float(hi),incident_events=int(ci[1]-ci[0]),
                    secondary_events=int(ei[1]-ei[0]),incident_weight_C=inc,secondary_weight_C=out,
                    sey=out/inc if inc>0 else None,N_start=count(lo),N_end=count(hi))
    times=np.unique(np.r_[np.arange(width,end,period),end]) if end>=width else np.array([])
    rolling=[window(float(t)) for t in times]
    return dict(frequency_MHz=frequency_mhz,period_ns=period,width_rf=width_rf,
                final_window=rolling[-1] if rolling else None,rolling=rolling,validation=validation,
                population=checks,window_complete=end>=width,statistical_warnings=warnings,
                current_check_policy='strict' if strict_currents else 'advisory',
                definition='Sum secondary birth weights / sum actual collision endpoint weights in (start,end]; seeds excluded; surviving tracks are not collisions')


def save_windows(directory: Path, result: dict[str, Any]) -> None:
    """Save late-window evidence plus raw rolling 3 RF values for every case."""
    (directory/'late_sey.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    if result['rolling']:
        with (directory/'rolling_3RF.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(result['rolling'][0]));w.writeheader();w.writerows(result['rolling'])


def selected_report(root: Path) -> None:
    """Render the frozen selection using actual statuses, without case-specific text."""
    from .report import selected_scan_report
    selected_scan_report(root)


def event_windows(a: np.ndarray, generations: np.ndarray, stats: dict[str, Any],
                  curves: dict[str, Any], frequency_mhz: float, width_rf: int = 3,
                  strict_currents: bool = True) -> dict[str, Any]:
    """Charge-weighted RF windows with explicit terminal uncertainty intervals."""
    from .endpoints import terminal_collision_bounds, adjusted_statistics
    a = np.atleast_2d(a)
    bounds = terminal_collision_bounds(a, stats)
    result = _event_windows_exact(a, generations,
        adjusted_statistics(stats, bounds) if bounds else stats,
        curves, frequency_mhz, width_rf, strict_currents=False if bounds else strict_currents)
    for row in result['rolling']:
        row.update(sey_lower=row['sey'], sey_upper=row['sey'],
                   incident_weight_lower_C=row['incident_weight_C'],
                   incident_weight_upper_C=row['incident_weight_C'])
    if bounds:
        result['terminal_bounds'] = bounds
        result['population']['final_alive'] = int(stats['final'])
        result['current_check_policy'] = 'advisory_with_terminal_bounds'
        result['statistical_warnings'].append(dict(message='Terminal collisions have unknown identities; SEY is bounded', **bounds))
        for row in result['rolling']:
            if not (row['start_ns'] < bounds['terminal_time_ns'] <= row['end_ns']):
                continue
            low = row['incident_weight_C'] + bounds['collision_charge_lower_C']
            high = row['incident_weight_C'] + bounds['collision_charge_upper_C']
            lower = row['secondary_weight_C']/high if high > 0 else None
            upper = row['secondary_weight_C']/low if low > 0 else None
            row.update(incident_weight_lower_C=low, incident_weight_upper_C=high,
                       sey_lower=lower, sey_upper=upper,
                       sey=(lower+upper)/2 if lower is not None and upper is not None else None,
                       incident_events=row['incident_events']+bounds['ambiguous_terminal_collisions'],
                       N_end=int(stats['final']))
    return result
