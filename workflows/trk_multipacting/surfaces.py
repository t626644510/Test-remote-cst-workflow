"""Offline geometric event attribution, with distances in mm and charges in C.

Saved endpoint-to-CAD matching is a reconstruction, not a native body-ID label.
Native per-solid counts and generation currents validate it before publication.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import re
import xml.etree.ElementTree as ET
import numpy as np
from .endpoints import terminal_collision_bounds
from .io import read_json, write_json, write_csv


def canonical_name(name: str) -> str:
    return re.sub(r'\s*:\s*', ':', name.strip())


def map_events(source: Path, output: Path, a: np.ndarray, generations: np.ndarray,
               stats: dict[str, Any], *, max_distance_mm: float = 2.0,
               min_margin_mm: float = 1e-4) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    """Match known collisions and secondary births; ambiguous terminal IDs stay unknown."""
    try:
        import vtk
        from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    except ImportError as exc:
        raise RuntimeError('Surface attribution requires the trk-surfaces optional dependency') from exc
    if max_distance_mm <= 0 or min_margin_mm < 0:
        raise ValueError('Surface distance/margin must be positive/nonnegative mm')
    geom = source/'surface_time'
    positions = np.atleast_2d(np.loadtxt(geom/'endpoint_positions.txt', skiprows=1))
    if positions.shape != (len(a), 7) or not np.all(np.isfinite(positions)) or not np.array_equal(positions[:, 0], a[:, 0]):
        raise ValueError('Endpoint positions do not match lifetime records')
    models = [source/'model.gex'] if (source/'model.gex').exists() else list((source/'private').glob('*/Result/model.gex'))
    if len(models) != 1:
        raise ValueError('Exactly one saved model.gex is required for material attribution')
    materials = {canonical_name(s.attrib['name'].split('\\', 1)[-1]): s.attrib['material']
                 for s in ET.parse(models[0]).findall('.//Shape')}
    solids = []
    for line in (geom/'solids.txt').read_text(encoding='utf8').splitlines():
        index, name, active = line.strip().split('|')
        name = canonical_name(name)
        material = materials.get(name)
        if material is not None and 'vacuum' not in material.lower() and active.strip().lower() not in ('false', '0'):
            solids.append(dict(index=int(index), name=name, material=material))
    if not solids:
        raise ValueError('No active non-vacuum CAD surfaces')
    gen = generations[:, 1].astype(int)
    alive = (a[:, 4] == a[:, 4].max()) if stats['final'] else np.zeros(len(a), bool)
    collision = ~alive & (a[:, 7] > 1)
    emission = gen > 0
    indexes = np.r_[np.flatnonzero(collision), np.flatnonzero(emission)]
    xyz = np.concatenate([positions[collision, 4:7], positions[emission, 1:4]])
    best = np.full(len(xyz), np.inf)
    second = np.full(len(xyz), np.inf)
    labels = np.full(len(xyz), -1, dtype=int)
    # Only retain two distances per event; memory does not grow as events*solids.
    for column, solid in enumerate(solids):
        reader = vtk.vtkSTLReader()
        reader.SetFileName(str(geom/f"solid_{solid['index']}.stl"))
        reader.Update()
        mesh = reader.GetOutput()
        if mesh.GetNumberOfPoints() == 0:
            raise ValueError(f"Empty CAD mesh: {solid['name']}")
        bounds = np.asarray(mesh.GetBounds()).reshape(3, 2)
        mask = np.all((xyz >= bounds[:, 0]-max_distance_mm) & (xyz <= bounds[:, 1]+max_distance_mm), axis=1)
        idx = np.flatnonzero(mask)
        fn = vtk.vtkImplicitPolyDataDistance()
        fn.SetInput(mesh)
        for start in range(0, len(idx), 100000):
            selected = idx[start:start+100000]
            values = vtk.vtkDoubleArray()
            values.SetNumberOfComponents(1)
            fn.EvaluateFunction(numpy_to_vtk(np.ascontiguousarray(xyz[selected])), values)
            distance = np.abs(vtk_to_numpy(values))
            better = distance < best[selected]
            second[selected] = np.where(better, best[selected], np.minimum(second[selected], distance))
            labels[selected[better]] = column
            best[selected] = np.minimum(best[selected], distance)
    # For omitted surfaces, the expanded bounding box proves distance >= tolerance.
    runnerup_lower = np.minimum(second, max_distance_mm)
    valid = np.isfinite(best) & (best <= max_distance_mm) & (runnerup_lower-best > min_margin_mm)
    labels[~valid] = -1
    events = dict(track_index=indexes, kind=np.r_[np.zeros(collision.sum(), dtype=np.int8), np.ones(emission.sum(), dtype=np.int8)],
                  time_ns=np.r_[a[collision, 4], a[emission, 3]], weight_C=np.abs(a[indexes, 5]), generation=gen[indexes],
                  solid_index=labels, nearest_mm=best, runnerup_lower_mm=runnerup_lower)
    np.savez_compressed(output/'mapped_events.npz', **events)
    write_json(output/'solid_index.json', solids)
    write_json(output/'mapping_quality.json', dict(event_count=len(indexes), unresolved_events=int((~valid).sum()),
               max_distance_mm=max_distance_mm, min_margin_mm=min_margin_mm,
               method='Nearest saved active non-vacuum CAD surface; geometric reconstruction'))
    return events, solids


def reduce_surfaces(events: dict[str, np.ndarray], solids: list[dict[str, Any]],
                    a: np.ndarray, generations: np.ndarray, stats: dict[str, Any], curves: dict[str, Any],
                    windows: dict[str, Any], output: Path) -> dict[str, Any]:
    """Validate native monitor constraints and compute per-solid time-window SEY."""
    normalized = {canonical_name(k): v for k, v in curves.items()}
    seed_charge = float(np.abs(a[generations[:, 1] == 0, 5]).sum())
    if seed_charge <= 0:
        raise ValueError('Missing positive seed macrocharge')
    bounds = terminal_collision_bounds(a, stats)
    checks = []
    deficits = {}
    terminal_weights = np.sort(np.abs(a[(a[:, 4] == a[:, 4].max()) & (a[:, 7] > 1), 5]))
    for col, solid in enumerate(solids):
        for kind, title in ((0, 'Collision'), (1, 'Emission')):
            mask = (events['solid_index'] == col) & (events['kind'] == kind)
            count = int(mask.sum())
            base = f"1D Results\\Total {title} Information\\"
            particles = normalized.get(base+'Particles\\'+solid['name'])
            current = normalized.get(base+'Current\\'+solid['name'])
            native_count = int(round(sum(particles['y']))) if particles is not None else (0 if not count else None)
            deficit = native_count-count if native_count is not None else None
            if kind == 0:
                deficits[col] = deficit
            allowed = bool(bounds and kind == 0 and deficit is not None and 0 <= deficit <= bounds['ambiguous_terminal_collisions'])
            count_ok = deficit == 0 or allowed
            actual = float(events['weight_C'][mask].sum()/seed_charge)
            expected = float(sum(current['y'])) if current is not None else (0.0 if not count else None)
            low = actual
            high = actual
            if allowed and deficit:
                low += float(terminal_weights[:deficit].sum()/seed_charge)
                high += float(terminal_weights[-deficit:].sum()/seed_charge)
            tolerance = max(1e-10, 3e-6*abs(expected or 0.0))
            current_ok = expected is not None and low-tolerance <= expected <= high+tolerance
            generation = normalized.get(f"1D Results\\SEE {title} Information\\Current\\"+solid['name'])
            bins = dict(zip(generation['x'], generation['y'])) if generation is not None else {}
            gen_ok = generation is not None or expected == 0
            differences = []
            for g in set(bins) | set(events['generation'][mask]):
                observed = float(events['weight_C'][mask & (events['generation'] == g)].sum()/seed_charge)
                target = float(bins.get(g, 0.0))
                tol = max(1e-10, 3e-6*abs(target))
                if abs(observed-target) > tol:
                    possible = bool(allowed and deficit and target >= observed-tol and target-observed <= high-actual+tol)
                    gen_ok = gen_ok and possible
                    differences.append(dict(generation=int(g), native_A=target, reconstructed_A=observed, bounded=possible))
            checks.append(dict(solid=solid['name'], kind=title, known_events=count, native_events=native_count,
                               terminal_event_deficit=deficit, native_current_A=expected, known_current_A=actual,
                               count_verified=count_ok, current_verified=current_ok, generation_verified=gen_ok,
                               generation_differences=differences))
    deficit_ok = (all(v is not None and v >= 0 for v in deficits.values())
                  and sum(v for v in deficits.values() if v is not None) == (bounds['ambiguous_terminal_collisions'] if bounds else 0))
    valid = bool(deficit_ok and np.all(events['solid_index'] >= 0)
                 and all(c['count_verified'] and c['current_verified'] and c['generation_verified'] for c in checks))
    rows = []
    for col, solid in enumerate(solids):
        streams = []
        for kind in (0, 1):
            mask = (events['solid_index'] == col) & (events['kind'] == kind)
            order = np.argsort(events['time_ns'][mask])
            streams.append((events['time_ns'][mask][order], np.r_[0.0, np.cumsum(events['weight_C'][mask][order])]))
        for window in windows['rolling']:
            values = []
            for times, weights in streams:
                left, right = np.searchsorted(times, [window['start_ns'], window['end_ns']], side='right')
                values.append((float(weights[right]-weights[left]), int(right-left)))
            inc, count = values[0]
            emit, emitted = values[1]
            low = high = inc
            missing = 0
            if bounds and window['start_ns'] < bounds['terminal_time_ns'] <= window['end_ns'] and deficits.get(col):
                missing = max(0, deficits[col])
                low += float(terminal_weights[:missing].sum())
                high += float(terminal_weights[-missing:].sum())
            lower = emit/high if valid and high > 0 else None
            upper = emit/low if valid and low > 0 else None
            rows.append(dict(solid=solid['name'], start_ns=window['start_ns'], end_ns=window['end_ns'],
                             collision_count=count+missing, secondary_count=emitted,
                             collision_weight_C=inc, secondary_weight_C=emit,
                             collision_weight_lower_C=low, collision_weight_upper_C=high,
                             sey=(lower+upper)/2 if lower is not None and upper is not None else None,
                             sey_lower=lower, sey_upper=upper, validated=valid))
    # Known charges must conserve across surfaces, independently of inferred bounds.
    conserved = all(np.isclose(sum(r['collision_weight_C'] for r in rows if r['end_ns'] == w['end_ns']), w['incident_weight_C'], rtol=1e-9, atol=1e-23)
                    and np.isclose(sum(r['secondary_weight_C'] for r in rows if r['end_ns'] == w['end_ns']), w['secondary_weight_C'], rtol=1e-9, atol=1e-23)
                    for w in windows['rolling'])
    valid = valid and conserved
    if not valid:
        for row in rows:
            row.update(validated=False, sey=None, sey_lower=None, sey_upper=None)
    final = [r for r in rows if windows['final_window'] and r['end_ns'] == windows['final_window']['end_ns']]
    audit = dict(validated=valid, global_known_charge_conserved=conserved, native_count_deficits_verified=deficit_ok,
                 unresolved_events=int((events['solid_index'] < 0).sum()), checks=checks, final=final,
                 terminal_bounds=bounds, method='Saved endpoint-to-CAD reconstruction; native counts/current checks',
                 note='Unverified attribution is retained as evidence but no per-solid SEY is certified')
    write_json(output/'validation.json', audit)
    write_csv(output/'sliding_by_solid_3RF.csv', rows)
    write_csv(output/'last_3RF_by_solid.csv', final)
    return audit
