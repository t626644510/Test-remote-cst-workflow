"""Data-driven TRK reports; all displayed values come from saved reductions."""
from __future__ import annotations
import csv
import html
import math
from pathlib import Path
from typing import Any
import numpy as np
from .io import read_json, write_csv, write_json


def plots():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def value(v: Any) -> str:
    if v is None:
        return 'undefined'
    if isinstance(v, float):
        return f'{v:.7g}'
    return html.escape(str(v))


def table(rows: list[dict[str, Any]], keys: list[str]) -> str:
    return '<table><tr>'+''.join(f'<th>{html.escape(k)}</th>' for k in keys)+'</tr>'+''.join(
        '<tr>'+''.join(f'<td>{value(row.get(k))}</td>' for k in keys)+'</tr>' for row in rows)+'</table>'


def page(title: str, body: str) -> str:
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>'+html.escape(title)+
            '</title><style>body{max-width:1150px;margin:30px auto;padding:24px;font:16px/1.6 sans-serif;color:#23364b;background:#f5f7fa}'
            'img{max-width:100%;background:white}table{border-collapse:collapse;width:100%;background:white}'
            'td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}.note{padding:15px;background:#fff1d6}</style>'
            '<h1>'+html.escape(title)+'</h1>'+body+'</html>')


def save_plot(fig, output: Path, name: str, plt) -> None:
    fig.savefig(output/(name+'.png'), dpi=160)
    fig.savefig(output/(name+'.svg'))
    plt.close(fig)


def report(inputs: list[Path], output: Path) -> Path:
    """Render one or multiple reductions without opening CST or editing inputs."""
    if not inputs:
        raise ValueError('At least one analysis directory is required')
    output.mkdir(parents=True, exist_ok=True)
    plt = plots()
    summaries = [read_json(path/'summary.json') for path in inputs]
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), constrained_layout=True)
    rows = []
    details = []
    for index, (source, summary) in enumerate(zip(inputs, summaries)):
        label = summary.get('label', source.name)
        windows = read_json(source/'late_sey.json')
        rolling = windows['rolling']
        times = [w['end_ns'] for w in rolling]
        vals = [w['sey'] if w['sey'] is not None else np.nan for w in rolling]
        axes[0].plot(times, vals, '-o', markersize=3, label=label)
        if rolling:
            axes[0].fill_between(times, [w.get('sey_lower', w['sey']) if w.get('sey_lower', w['sey']) is not None else np.nan for w in rolling],
                                [w.get('sey_upper', w['sey']) if w.get('sey_upper', w['sey']) is not None else np.nan for w in rolling], alpha=.18)
        pop = np.atleast_2d(np.loadtxt(source/'particle_number_vs_time.csv', delimiter=',', skiprows=1))
        axes[1].plot(pop[:, 0], pop[:, 1], label=label)
        final = windows['final_window'] or {}
        rows.append(dict(label=label, status=summary.get('status'), end_ns=summary['stats']['final_time_ns'],
                         combined_sey=summary['combined_sey'], late_sey=final.get('sey'),
                         sey_lower=final.get('sey_lower', final.get('sey')), sey_upper=final.get('sey_upper', final.get('sey')),
                         final_alive=summary['stats']['final'], window_rf=windows['width_rf']))
        prefix = f'case_{index:02d}'
        details.append('<h2>'+html.escape(label)+'</h2>'+table(summary['solids'], ['solid','combined_sey','collision_normalized_A','secondary_normalized_A']))
        generation = source/'solid_generations.csv'
        if generation.exists():
            with generation.open(encoding='utf-8-sig') as f:
                records = list(csv.DictReader(f))
            figg, axg = plt.subplots(figsize=(11, 5), constrained_layout=True)
            for solid in sorted({r['solid'] for r in records}):
                selected = [r for r in records if r['solid'] == solid]
                axg.plot([float(r['collision_generation']) for r in selected], [float(r['sey']) if r['sey'] else np.nan for r in selected], '-o', markersize=3, label=solid)
            axg.set(xlabel='Collision generation g (emission g+1)', ylabel='Charge-weighted SEY', title=label)
            if records:
                axg.legend(fontsize=8)
            axg.axhline(1, color='#888', linestyle='--')
            save_plot(figg, output, prefix+'_generations', plt)
            details.append(f'<img src="{prefix}_generations.png">')
        surface = source/'surface_time/sliding_by_solid_3RF.csv'
        if surface.exists():
            audit = read_json(source/'surface_time/validation.json')
            with surface.open(encoding='utf-8-sig') as f:
                records = list(csv.DictReader(f))
            fs, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
            for solid in sorted({r['solid'] for r in records}):
                selected = [r for r in records if r['solid'] == solid]
                ax.plot([float(r['end_ns']) for r in selected], [float(r['sey']) if r['sey'] else np.nan for r in selected], '-o', markersize=3, label=solid)
            ax.axhline(1, color='#888', linestyle='--')
            ax.set(xlabel='Window end / ns', ylabel='Per-solid weighted SEY', title=label)
            if records:
                ax.legend(fontsize=8)
            save_plot(fs, output, prefix+'_surfaces', plt)
            details.append(f'<p>Geometric attribution validated: {audit["validated"]}. Unknown attribution produces no certified SEY.</p><img src="{prefix}_surfaces.png">'+table(audit['final'], ['solid','sey','sey_lower','sey_upper','collision_count','secondary_count','validated']))
        details.append('<p>Statistical warnings: '+str(len(summary.get('statistical_warnings', [])))+'. Source: '+html.escape(str(source.resolve()))+'</p>')
    axes[0].set(xlabel='Window end / ns', ylabel='Weighted sliding SEY')
    axes[0].axhline(1, color='#888', linestyle='--')
    axes[1].set(xlabel='Time / ns', ylabel='Alive recorded macro-particle trajectories')
    for ax in axes:
        ax.grid(alpha=.2)
        ax.legend()
    save_plot(fig, output, 'comparison', plt)
    write_csv(output/'comparison.csv', rows)
    write_json(output/'report_inputs.json', [str(p.resolve()) for p in inputs])
    body = '<p class="note">Finite saved TRK records. Different end times are not a common steady state. SEY is charge weighted; no collisions means undefined. A bounded scalar is the interval midpoint. Geometric body attribution is a validated reconstruction, not a native time label.</p>'
    body += table(rows, ['label','status','end_ns','combined_sey','late_sey','sey_lower','sey_upper','final_alive','window_rf'])
    body += '<img src="comparison.png"><p><a href="comparison.csv">Summary CSV</a> · <a href="comparison.svg">SVG</a></p>'+''.join(details)
    result = output/'report.html'
    result.write_text(page('WF8.1 TRK multipacting results', body), encoding='utf8')
    return result


def selected_scan_report(root: Path) -> None:
    """Current selected-scan results, including saved aborts and missing outcomes."""
    if not (root/'selection.json').exists():
        return
    plan = read_json(root/'selection.json')
    output = Path(plan.get('report_dir', root/'report'))
    output.mkdir(parents=True, exist_ok=True)
    entries = [(case, root) for case in plan.get('cases', [])]
    if plan.get('reference_root'):
        entries += [(case, Path(plan['reference_root'])) for case in plan.get('reference_cases', [])]
    if len({case['key'] for case, _ in entries}) != len(entries):
        raise ValueError('Duplicate result/reference keys in report')
    rows = []
    for case, location in entries:
        folder = location/'cases'/case['key']
        result = read_json(folder/'result.json') if (folder/'result.json').exists() else {}
        late = read_json(folder/'late_sey.json') if (folder/'late_sey.json').exists() else {}
        final = late.get('final_window') or {}
        rows.append(dict(key=case['key'], source=case['source'], voltage_kV=case.get('voltage_kV', 500*case['factor1'] if 'factor1' in case else None),
                         phase_deg=case.get('phase'), status=result.get('status', 'timeout' if (folder/'timeout.json').exists() else 'pending'),
                         late_3RF_sey=final.get('sey', result.get('late_3RF_sey')), sey_lower=final.get('sey_lower'), sey_upper=final.get('sey_upper'),
                         final_alive=result.get('final'), final_time_ns=result.get('final_time_ns'), solve_s=result.get('solve_s'), result_root=str(location)))
    write_csv(output/'late_3RF_summary.csv', rows)
    plt = plots()
    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    for source in sorted({row['source'] for row in rows}):
        selected = sorted([r for r in rows if r['source'] == source], key=lambda r:(r['voltage_kV'] or 0, r['phase_deg'] or 0))
        line, = ax.plot([r['voltage_kV'] for r in selected], [r['late_3RF_sey'] if r['late_3RF_sey'] is not None else np.nan for r in selected], 'o-', label=source)
        partial = [r for r in selected if r['status'] == 'aborted_saved' and r['late_3RF_sey'] is not None]
        ax.scatter([r['voltage_kV'] for r in partial], [r['late_3RF_sey'] for r in partial], marker='^', s=90, color=line.get_color())
    ax.set(xlabel='Calibrated RF voltage / kV', ylabel='Last available 3 RF weighted SEY')
    ax.axhline(1, color='#888', linestyle='--')
    if rows:
        ax.legend()
    save_plot(fig, output, 'all_sources', plt)
    body = '<p>Only the frozen selected cases are shown. Triangles identify normally aborted saved records. Undefined, uncomputed and timeout values are not zero. Statistics discrepancies are advisory; no steady-state MP conclusion is implied.</p>'
    body += f'<p>Requested solve deadline: {value(plan.get("solve_limit_seconds"))} s. Each case retains its actual timing and abort evidence.</p>'
    body += '<img src="all_sources.png">'+table(rows, ['source','voltage_kV','phase_deg','status','late_3RF_sey','final_alive','final_time_ns'])
    (output/'report.html').write_text(page('WF8.1 selected TRK scan', body), encoding='utf8')
