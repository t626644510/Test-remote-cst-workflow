"""Validate already completed native preflight data without repeating a solve.

Only the current source baseline can be imported. Historical WF6 geometry or
different physics cannot enter through this path. Preflight seconds remain
separate from the subsequent 48-hour round, and are reported explicitly.
"""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
from .cad import parameters
from .geometry import Geometry
from .io import digest,read_json,validate_manifest


def validate_baseline(config,baseline: dict,prepared: Path,project: Path,
                      analyses: dict[str,Path]) -> dict:
    """Check retained raw fields, geometry, parameters and current solver code."""
    if set(analyses)!={'axis','x'}:raise ValueError('Both native baseline stages are required')
    validate_manifest(prepared,read_json(prepared/'manifest.json'))
    preparation=read_json(prepared/'preparation.json')
    if digest(project)!=preparation['project_sha256']:
        raise ValueError('Prepared baseline project changed')
    actual=parameters(project);expected=Geometry(config).expand(baseline)
    if any(k not in actual or not math.isclose(v,actual[k],rel_tol=1e-10,abs_tol=1e-8) for k,v in expected.items()):
        raise ValueError('Native baseline parameters do not match')
    if digest(project.with_suffix('')/'ModelCache/Model.mif')!=preparation['geometry_sha256']:
        raise ValueError('Native baseline geometry changed')
    root=Path(__file__).parent
    files=[root/'gpu.py',root/'monitors.py',root/'timestep.py']+sorted((root/'backend').glob('*.py'))
    contract=dict(code={p.name:digest(p) for p in files},physics=config.as_dict()['physics'],upstream=config.runtime.upstream_revision)
    solver=hashlib.sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest()
    results={};certificates={}
    for stage,analysis in analyses.items():
        validate_manifest(analysis,read_json(analysis/'manifest.json'))
        result=read_json(analysis/'result.json');field=Path(result['field_directory'])
        if result['parameters']!=baseline or result['stage']!=stage:raise ValueError('Native result identity mismatch')
        validate_manifest(field,read_json(field/'raw_manifest.json'))
        meta=read_json(field/'field_complete.json')
        if (meta['complete_steps']!=meta['steps'] or meta['stage']!=stage
            or meta['metrics_sha256']!=digest(prepared/'effective_metrics.npz')
            or meta['geometry_sha256']!=preparation['geometry_sha256']
            or meta['solver_contract_sha256']!=solver):raise ValueError('Native field contract mismatch')
        if meta['source_offset_m']!=([0.,0.] if stage=='axis' else [.002,0.]):raise ValueError('Wrong source offset')
        if digest(field/'wake.npz')!=result['raw_sha256']:raise ValueError('Native wake changed')
        certificates[stage]=meta;results[stage]=result
    for key in ('metrics_sha256','geometry_sha256','solver_contract_sha256','dt_s','steps','cpml'):
        if certificates['axis'][key]!=certificates['x'][key]:raise ValueError('Axis/X field mismatch')
    return dict(results=results,prepared=str(prepared),project=str(project),
                evidence={k:dict(path=str(v),sha256=digest(v/'manifest.json')) for k,v in analyses.items()},
                field_seconds=sum(v['solve_seconds'] for v in certificates.values()),
                analysis_seconds=sum(v['seconds'] for v in results.values()))
