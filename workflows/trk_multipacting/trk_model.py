"""Finite TRK scan analysis: currents in A, time in ns, stored macrocharge in C."""
from __future__ import annotations

import re
from typing import Any
import numpy as np
from .model import Task


def tasks() -> list[Task]:
    """Four independent sources, factor 0:0.1:1, phase 0:30:330 degrees.

    Zero RF amplitude is phase-independent: 484 solves represent 528 grid rows.
    """
    return [Task(f"particle{s}", f/10, p) for s in range(1, 5)
            for f in range(11) for p in ([0] if f == 0 else range(0, 360, 30))]


def logical_grid() -> list[dict[str, Any]]:
    """Record zero-field phase aliases explicitly."""
    return [dict(Task(f"particle{s}", f/10, p).record(),
                 actual_key=Task(f"particle{s}", f/10, 0 if f == 0 else p).key)
            for s in range(1, 5) for f in range(11) for p in range(0, 360, 30)]


def combined_sey(curves: dict[str, Any], *, strict_currents: bool = True) -> dict[str, Any]:
    """Current-weighted yield: incident generation g creates emission g+1.

    Sparse generation bins are zeros only after checking their sums against
    independent total-current records. No integration over generation, no mean
    of ratios. Boundary loss is excluded from the SEE receiving-surface scope.
    """
    prefixes = [f"1D Results\\SEE {kind} Information\\Current\\"
                for kind in ("Collision", "Emission")]
    total_pre = '1D Results\\Total Collision Information\\Current\\'
    surfaces = sorted({p[len(total_pre):] for p,c in curves.items()
                       if p.startswith(total_pre) and np.sum(c['y']) > 0
                       and p[len(total_pre):] != '[Background]: Boundary'})
    totals = [{}, {}]
    total_current = [0., 0.]
    unresolved_generation_curves = []
    statistical_warnings = []
    scope = []
    for surface in surfaces:
        pair = []
        for k, (pre, kind) in enumerate(zip(prefixes, ("Collision", "Emission"))):
            c = curves.get(pre+surface)
            total = curves.get(f"1D Results\\Total {kind} Information\\Current\\{surface}")
            if total is None or total['ylabel'] != 'Current / A':
                raise ValueError(f"Missing total-current check: {kind} {surface}")
            expected = float(np.asarray(total['y']).sum())
            if not np.isfinite(expected) or expected < 0:
                raise ValueError('Invalid total current')
            total_current[k] += expected
            bins: dict[int, float] = {}
            if c is not None:
                x, y = np.asarray(c['x']), np.asarray(c['y'])
                if (c['xlabel'] != 'SEE Generation' or c['ylabel'] != 'Current / A'
                        or x.shape != y.shape or not np.all(np.isfinite(x))
                        or not np.all(np.isfinite(y)) or np.any(y < 0)
                        or not np.all(x == np.round(x)) or len(np.unique(x)) != len(x)):
                    raise ValueError('Invalid generation current')
                bins = dict(zip(x.astype(int), y.astype(float)))
            if c is None and expected > 0:
                # CST omits some short generation curves although the independently
                # saved total is nonzero. Preserve that total; never replace it by 0.
                unresolved_generation_curves.append(f'{kind} {surface}')
            elif not np.isclose(sum(bins.values()), expected, rtol=1e-7, atol=1e-14):
                message = f"Generation current disagrees with total: {kind} {surface}"
                if strict_currents:
                    raise ValueError(message)
                statistical_warnings.append(dict(message=message, reference=expected, generation_sum=sum(bins.values())))
            for generation, value in bins.items():
                totals[k][int(generation)] = totals[k].get(int(generation), 0.) + float(value)
            pair.append(bins)
        if pair[0] and any(g-1 not in pair[0] for g, value in pair[1].items() if value > 0):
            message = f"Secondary generation lacks parent collision: {surface}"
            if strict_currents:
                raise ValueError(message)
            statistical_warnings.append(dict(message=message))
        scope.append(surface)
    # Reject a hidden positive total absent from all generation records.
    for p, c in curves.items():
        pre = '1D Results\\Total Emission Information\\Current\\'
        if p.startswith(pre) and np.sum(c['y']) > 0 and p[len(pre):] not in scope:
            raise ValueError('Unaccounted emitted current')
    rows = []
    for g, inc in ([] if unresolved_generation_curves or statistical_warnings else sorted(totals[0].items())):
        emit = totals[1].get(g+1, 0.)
        rows.append(dict(incident_generation=g, emitted_generation=g+1,
                         incident_A=inc, secondary_A=emit, sey=emit/inc if inc > 0 else None))
    inc, emit = total_current
    return dict(scope=scope, incident_sum_A=inc, secondary_sum_A=emit,
                combined_sey=emit/inc if inc > 0 else None, by_generation=rows,
                unresolved_generation_curves=unresolved_generation_curves, statistical_warnings=statistical_warnings,
                definition='Sum emitted current / sum incident current on SEE receivers; g -> g+1')


def log_statistics(text: str, source: str) -> dict[str, Any]:
    """Parse CST's completed-run statistics; do not equate truncation with decay."""
    if 'Particle Tracking Solver successful.' not in text:
        raise ValueError('No successful tracking completion')
    actual = re.findall(r'Statistics for particle source ([^\r\n]+):', text)
    if actual != [source]:
        raise ValueError(f'Wrong active source: {actual}, expected {source}')
    fields = {'initial': 'Initial particle number', 'secondary': 'Secondary particles created',
              'final': 'Final particle number', 'collided': 'Particles collided',
              'passed': 'Particles passed away', 'blocked': 'Particles blocked in emission',
              'into_solid': 'Particles emitted into solid', 'dying': 'Particles dying in emission model',
              'ionization': 'Ionization particles created', 'steps': 'Total number of timesteps',
              'mesh_cells': 'Number of tetrahedrons'}
    result: dict[str, Any] = {}
    for key, label in fields.items():
        m = re.search(re.escape(label)+r':\s*(\d+)', text)
        if not m:
            raise ValueError(f'Missing solver statistic: {label}')
        result[key] = int(m[1])
    m = re.search(r'Final simulation time\s+([\d.eE+-]+) ns', text)
    if not m:
        raise ValueError('No final tracking time')
    result['final_time_ns'] = float(m[1])
    result['truncated'] = result['final'] > 0
    return result


def _population_exact(a: np.ndarray, stats: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    """Reconstruct recorded TRK trajectory population, NOT transient PIC density.

    Half-open lifetimes [birth, death); terminal survivors are retained only when
    independently confirmed by solver statistics. No extrapolation beyond run end.
    """
    a = np.atleast_2d(a)
    if (a.shape[1] != 8 or not np.all(np.isfinite(a)) or np.any(a[:,3] > a[:,4])
            or len(np.unique(a[:,1])) != len(a)):
        raise ValueError('Invalid or duplicate trajectory lifetimes')
    if len(a) != stats['initial'] + stats['secondary'] + stats['ionization']:
        raise ValueError('Stored trajectory count disagrees with solver')
    if not np.allclose(a[:,5], a[:,6], rtol=0, atol=0):
        raise ValueError('Variable trajectory weight requires time-resolved charge export')
    last = float(a[:,4].max())
    # All-dead runs stop on the next push: last collision precedes logged end.
    # Live truncated runs instead have trajectories at the actual terminal time.
    if last > stats['final_time_ns'] + max(1e-4, stats['final_time_ns']*2e-5):
        raise ValueError('Trajectory extends beyond solver end')
    end = max(last, stats['final_time_ns'])
    deaths = a[:,4].copy()
    if stats['final']:
        if not np.isclose(last, stats['final_time_ns'], rtol=2e-5, atol=1e-4):
            raise ValueError('Surviving trajectories miss solver end')
        survivors = deaths == last
        if int(survivors.sum()) != stats['final']:
            raise ValueError('Terminal survivor count disagrees with solver')
        deaths[survivors] = np.inf
    times = np.unique(np.r_[0., np.linspace(0, end, 1001), a[:,3][a[:,3]>=0], a[:,4]])
    times = times[times >= 0]
    count = np.searchsorted(np.sort(a[:,3]), times, side='right') - np.searchsorted(np.sort(deaths), times, side='right')
    def accumulated(events: np.ndarray) -> np.ndarray:
        order = np.argsort(events)
        weights = np.r_[0., np.cumsum(np.abs(a[order,5]))]
        return weights[np.searchsorted(events[order], times, side='right')]
    charge = accumulated(a[:,3])-accumulated(deaths)
    if count[-1] != stats['final']:
        raise ValueError('Reconstructed final population mismatch')
    return np.c_[times, count, charge], dict(recorded_trajectories=len(a),
        peak_alive=int(count.max()), final_alive=int(count[-1]), end_ns=end,
        note='Recorded finite TRK lifetimes; not PIC transient particle population')


def population(a: np.ndarray, stats: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    """Recorded trajectory count, with native-count bounds at rounded end times.

    Time is ns and macrocharge C. The legacy charge column is an upper bound
    when terminal collision identities cannot be distinguished; its interval
    is explicit in metadata. The final count remains the native solver count.
    """
    from .endpoints import terminal_collision_bounds, adjusted_statistics
    a = np.atleast_2d(a)
    bounds = terminal_collision_bounds(a, stats)
    if bounds is None:
        return _population_exact(a, stats)
    array, checks = _population_exact(a, adjusted_statistics(stats, bounds))
    at_end = array[:, 0] >= bounds['terminal_time_ns']
    array[at_end, 1] -= bounds['ambiguous_terminal_collisions']
    raw_charge = array[-1, 2]
    array[at_end, 2] -= bounds['collision_charge_lower_C']
    checks.update(final_alive=int(stats['final']), peak_alive=int(array[:, 1].max()),
                  terminal_bounds=bounds,
                  terminal_charge_lower_C=float(raw_charge-bounds['collision_charge_upper_C']),
                  terminal_charge_upper_C=float(raw_charge-bounds['collision_charge_lower_C']),
                  terminal_charge_column='Upper bound; terminal collision identities are unknown')
    return array, checks
