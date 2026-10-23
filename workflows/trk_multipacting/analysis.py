"""No-CST analysis of saved TRK exports: ns, MHz, kV and macrocharge C."""
from __future__ import annotations
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Any
import numpy as np
from .io import read_json, write_json, write_csv, fingerprint
from .trk_model import log_statistics, population, combined_sey
from .trk_late import event_windows, save_windows


def analyze(source: Path, output: Path, *, label: str | None = None,
            frequency_mhz: float | None = None, width_rf: int = 3,
            surfaces: bool = False) -> dict[str, Any]:
    """Read legacy or WF8.1 exports and write new derived artifacts separately.

    Macrocharge weighting defines SEY. Terminal uncertainty is an interval;
    the legacy scalar is its midpoint for plotting, never an exact observation.
    """
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents:
        raise ValueError('Analysis output must differ from the input export directory')
    files = [source/'Model.log', source/'raw_curves.json', source/'trajectory_lifetimes.txt']
    generation = next((source/n for n in ('trajectory_generations.txt', 'trajectory_extra.txt') if (source/n).exists()), None)
    if generation is None:
        raise ValueError('Saved SEE generation records are required; export first')
    files.append(generation)
    field = source/'field_import_0_0.rex'
    if frequency_mhz is None:
        if not field.exists():
            raise ValueError('Provide --frequency-mhz or a saved field_import_0_0.rex')
        files.append(field)
        frequency_mhz = float(ET.parse(field).getroot().find('SimulationProperties').attrib['frequency'])
    if surfaces:
        files.extend(p for p in (source/'surface_time').rglob('*') if p.is_file())
        files.extend([source/'model.gex'] if (source/'model.gex').exists() else (source/'private').glob('*/Result/model.gex'))
    before = fingerprint(files)
    text = files[0].read_text(encoding='utf8', errors='replace')
    sources = re.findall(r'Statistics for particle source ([^\r\n]+):', text)
    if len(sources) != 1:
        raise ValueError('A single saved TRK source result is required')
    stats = log_statistics(text, sources[0])
    a = np.atleast_2d(np.loadtxt(files[2], skiprows=1))
    g = np.atleast_2d(np.loadtxt(generation, skiprows=1))
    curves = read_json(files[1])
    array, checks = population(a, stats)
    windows = event_windows(a, g, stats, curves, frequency_mhz, width_rf, strict_currents=False)
    total = combined_sey(curves, strict_currents=False)
    output.mkdir(parents=True, exist_ok=True)
    save_windows(output, windows)
    write_json(output/'combined_sey.json', total)
    np.savetxt(output/'particle_number_vs_time.csv', array, delimiter=',',
               header='time_ns,alive_recorded_trajectories,sum_abs_macrocharge_C', comments='')
    solid_rows, generation_rows = [], []
    prefix = '1D Results\\Total Collision Information\\Current\\'
    for name, record in curves.items():
        if not name.startswith(prefix):
            continue
        solid = name[len(prefix):]
        incident = float(sum(record['y']))
        emitted = curves.get('1D Results\\Total Emission Information\\Current\\'+solid)
        emission = float(sum(emitted['y'])) if emitted is not None else None
        solid_rows.append(dict(solid=solid, collision_normalized_A=incident, secondary_normalized_A=emission,
                               combined_sey=emission/incident if incident > 0 and emission is not None else None))
        col = curves.get('1D Results\\SEE Collision Information\\Current\\'+solid)
        em = curves.get('1D Results\\SEE Emission Information\\Current\\'+solid)
        bins = dict(zip(em['x'], em['y'])) if em else {}
        if col:
            for gen, value in zip(col['x'], col['y']):
                secondary = bins.get(gen+1, 0.0) if em or emission == 0 else None
                generation_rows.append(dict(solid=solid, collision_generation=int(gen), emission_generation=int(gen+1),
                                            collision_normalized_A=value, secondary_normalized_A=secondary,
                                            sey=secondary/value if value > 0 and secondary is not None else None))
    write_csv(output/'solid_sey.csv', solid_rows)
    write_csv(output/'solid_generations.csv', generation_rows)
    status = 'aborted_saved' if 'Particle Tracking Solver has been aborted.' in text else 'completed'
    summary = dict(label=label or source.name, source=str(source), solver='TRK', source_name=sources[0],
                   status=status, stats=stats, population=checks, frequency_MHz=frequency_mhz,
                   combined_sey=total['combined_sey'], last_3RF=windows['final_window'], window_rf=width_rf,
                   statistical_warnings=total['statistical_warnings']+windows['statistical_warnings'], solids=solid_rows,
                   interpretation='Finite saved TRK trajectories; no self-consistent PIC density or steady-state verdict')
    if surfaces:
        from .surfaces import map_events, reduce_surfaces
        out = output/'surface_time'
        out.mkdir(exist_ok=True)
        events, solids = map_events(source, out, a, g, stats)
        summary['surface_analysis'] = reduce_surfaces(events, solids, a, g, stats, curves, windows, out)
    after = fingerprint(files)
    if before != after:
        raise RuntimeError('Saved inputs changed during analysis; reject mixed snapshots')
    write_json(output/'input_integrity.json', dict(before=before, after=after, unchanged=True))
    write_json(output/'summary.json', summary)
    return summary
