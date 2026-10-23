"""Twelve-coordinate double-bend pilot, using the existing fourteen-coordinate worker.

Projection P=2R(1-cos(theta)) is in mm; angles are degrees. Collapsing the two
bend coordinates assumes the user's template equivalence, not a general EM law.
Historical out-of-domain observations inform the surrogate, never acceptance.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import logging
import math
from pathlib import Path
import shutil
import warnings

import numpy as np
from scipy.spatial.distance import cdist
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.preprocessing import StandardScaler

from cst_optimization.parameters.base import ParameterSet, ParamRange
from cst_optimization.parameters.geometry import GeometryParameter
from cst_optimization.optimization.acquisition import ExpectedImprovement
from cst_optimization.optimization.sampling import latin_hypercube_sampling
from .geometry import GeometryConstraints
from .postprocess import analyze_bundle
from .search import CandidatePlanner
from .storage import atomic_json, digest, fingerprint, project_manifest
from .distributed.protocol import owner_lock, read_json
from .distributed.coordinator import equivalent_metrics

NAMES = ('selfangle1', 'UpperHeight1', 'DownHeight1', 'Lin1', 'projection1', 'FolkHeight',
         'selfangle2', 'UpperHeight2', 'DownHeight2', 'Lin2', 'projection2', 'FolkHeight2')
LOG = logging.getLogger(__name__)


def collapse(parameters: dict[str, float]) -> dict[str, float]:
    """Reflect antenna 1 signs and compute both double-bend projections, mm."""
    p = {k: float(parameters[k]) for k in NAMES if not k.startswith('projection')}
    p['projection1'] = -2 * parameters['inner_r'] * (1-math.cos(math.radians(parameters['inner_angle'])))
    p['projection2'] = 2 * parameters['inner_r2'] * (1-math.cos(math.radians(parameters['inner_angle3'])))
    return {k: p[k] for k in NAMES}


class CompositePlanner(CandidatePlanner):
    """Six explicit probes, a result barrier, then a bounded asynchronous EI stage."""

    def __init__(self, config, state: dict, plan: dict):
        super().__init__(config, state)
        if config.geometry.antenna_count != 2 or config.geometry.bend_segments != 2:
            raise ValueError('Composite pilot requires two double-bend antennas')
        self.plan = plan
        self.radii = plan['bend_radii_mm']
        if len(self.radii) != 2 or not all(isinstance(r, (float, int)) and not isinstance(r, bool)
                and math.isfinite(r) and r > config.geometry.conductor_radius_mm for r in self.radii):
            raise ValueError('Need two finite bend radii larger than conductor radius (mm)')
        if type(plan['adaptive_points']) is not int or plan['adaptive_points'] < 0:
            raise ValueError('adaptive_points must be a nonnegative integer')
        by_name = {p.name: p for p in config.parameters}
        self.space = ParameterSet([GeometryParameter(n, ParamRange(
            config.geometry.minimum_centerline_projection_mm if n.startswith('projection') else by_name[n].lower,
            config.geometry.flange_radius_mm if n.startswith('projection') else by_name[n].upper),
            unit='deg' if n.startswith('selfangle') else 'mm') for n in NAMES])
        self.bounds = np.array([[config.geometry.minimum_centerline_projection_mm, config.geometry.flange_radius_mm]
            if n.startswith('projection') else [by_name[n].lower, by_name[n].upper] for n in NAMES])
        probes = plan['first_wave']
        if not probes or len({p['id'] for p in probes}) != len(probes):
            raise ValueError('Need uniquely identified probe points')
        keys = []
        for row in probes:
            self.expand(row['parameters'])
            keys.append(self.key(row['parameters']))
        if len(set(keys)) != len(keys):
            raise ValueError('Duplicate composite probes')
        # Verify the chosen inverse mapping covers both ends, not just probe values.
        for limit in self.bounds[4]:
            sample = dict(probes[0]['parameters'], projection1=float(limit), projection2=float(limit))
            self.expand(sample)

    def unit(self, p: dict) -> np.ndarray:
        """Unclipped affine normalization also preserves out-of-domain history."""
        return (np.array([p[n] for n in NAMES])-self.bounds[:, 0])/np.diff(self.bounds).ravel()

    def expand(self, p: dict) -> dict:
        """Canonical inverse at fixed configurable R; antenna 1 keeps negative signs."""
        if set(p) != set(NAMES) or not all(math.isfinite(float(v)) for v in p.values()):
            raise ValueError('Composite candidate needs twelve finite coordinates')
        if np.any(self.unit(p) < -1e-12) or np.any(self.unit(p) > 1+1e-12):
            raise ValueError('Composite point outside search bounds')
        result = {k: float(v) for k, v in p.items() if not k.startswith('projection')}
        for i, (radius, angle_name, radius_name, sign) in enumerate(zip(self.radii,
                ('inner_angle', 'inner_angle3'), ('inner_r', 'inner_r2'), (-1, 1)), 1):
            argument = 1-float(p[f'projection{i}'])/(2*radius)
            if not -1 <= argument <= 1:
                raise ValueError('Projection cannot be represented by configured radius')
            result[angle_name] = sign*math.degrees(math.acos(argument))
            result[radius_name] = sign*radius
        if any(not v.lower <= result[v.name] <= v.upper for v in self.config.parameters):
            raise ValueError('Inverse mapping exceeds configured CST parameter bounds')
        violations = self.geometry.violations(result)
        if violations:
            raise ValueError('; '.join(violations))
        return result

    def complete(self) -> bool:
        """Attempt slots are bounded independently of the global solve permits."""
        return len(self.state.get('jobs', {})) >= len(self.plan['first_wave'])+self.plan['adaptive_points']

    def can_dispatch(self) -> bool:
        jobs = list(self.state.get('jobs', {}).values())
        if self.complete():
            return False
        count = len(self.plan['first_wave'])
        return len(jobs) < count or all(j['state'] == 'finished' for j in jobs[:count])

    def valid_training_data(self) -> tuple[np.ndarray, np.ndarray]:
        rows = [r for r in self.state['records'] if r['status'] in ('valid', 'history_outside_domain')
                and r.get('objective') is not None and math.isfinite(r['objective'])]
        return np.array([self.unit(collapse(r['parameters'])) for r in rows]), np.array([r['objective'] for r in rows])

    def ask_async(self, baseline: dict, pending: list[dict]) -> tuple[dict, str]:
        if not self.can_dispatch():
            raise ValueError('Probe barrier or search-plan limit prevents dispatch')
        jobs = list(self.state.get('jobs', {}).values())
        seen = {self.key(collapse(r['parameters'])) for r in self.state['records']+jobs}
        if len(jobs) < len(self.plan['first_wave']):
            probe = self.plan['first_wave'][len(jobs)]
            if self.key(probe['parameters']) in seen:
                raise ValueError('Planned probe duplicates historical or dispatched composite point')
            return self.expand(probe['parameters']), 'probe_'+probe['id']
        valid = [r for r in self.state['records'] if r['status'] == 'valid']
        best = min(valid, key=lambda r: r['objective'])
        center = self.unit(collapse(best['parameters']))
        pool, params = [], []
        radius = self.state['radius']
        for _ in range(max(1, self.config.search.candidate_draws//512)):
            batch = latin_hypercube_sampling(np.tile([0., 1.], (12, 1)), 512,
                seed=int(self.rng.integers(0, 2**31-1)))
            local = self.rng.random(len(batch)) < self.config.search.local_fraction
            lo, hi = np.maximum(0., center-radius), np.minimum(1., center+radius)
            batch[local] = lo+batch[local]*(hi-lo)
            for u in batch:
                p = dict(zip(NAMES, self.bounds[:, 0]+u*np.diff(self.bounds).ravel()))
                if self.key(p) in seen:
                    continue
                if pending and min(np.linalg.norm(u-self.unit(collapse(j['parameters']))) for j in pending) < .05:
                    continue
                try:
                    full = self.expand(p)
                except ValueError:
                    continue
                pool.append(u)
                params.append(full)
                seen.add(self.key(p))
                if len(pool) >= self.config.search.candidate_pool:
                    break
            if len(pool) >= self.config.search.candidate_pool:
                break
        if not pool:
            raise ValueError('No unseen feasible composite candidates')
        x, y = self.valid_training_data()
        pool = np.asarray(pool)
        index = int(np.argmax(cdist(pool, x).min(axis=1))) if len(x) else 0
        source = 'adaptive_maximin_fallback'
        if len(y) >= 3:
            try:
                scaler = StandardScaler().fit(y[:, None])
                target = scaler.transform(y[:, None]).ravel()
                gp = GaussianProcessRegressor(kernel=ConstantKernel(1., (.05, 20.))*Matern(1., (.15, 10.), nu=1.5)
                    + WhiteKernel(.02, (1e-4, .3)), alpha=1e-8,
                    random_state=int(self.rng.integers(0, 2**31-1)), n_restarts_optimizer=2)
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    gp.fit(x, target)
                # Only the best FEASIBLE observation defines improvement (unitless J).
                incumbent = float(scaler.transform([[best['objective']]])[0, 0])
                ei = ExpectedImprovement(xi=.01/float(scaler.scale_[0]))
                utility = np.array([ei.evaluate(u, gp, incumbent) for u in pool])
                if not np.isfinite(utility).all():
                    raise ValueError('Non-finite EI')
                index = int(np.argmax(utility))
                source = 'adaptive_composite_ei'
            except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                LOG.warning('Composite GP fallback: %s', exc)
        self.state['rng_state'] = self.rng.bit_generator.state
        return params[index], source


def import_history(config, store, source: Path, plan: dict) -> None:
    """Recompute saved raw fields; preserve their original 14D coordinates and provenance.

    No native CST result is trusted after manual inspection. All GP rows are
    backed by the copied raw field bundles, checked against stored metrics.
    Old solve counts are provenance only; this is a separately authorized budget.
    """
    if store.state['records'] or store.state['solve_count']:
        raise ValueError('Composite history import requires an empty new campaign')
    planner = CompositePlanner(config, store.state, plan)
    with owner_lock(source/'campaign.lock'):
        source_digest = digest(source/'state.json')
        previous = read_json(source/'config.resolved.json')
        current = config.as_dict()
        for key in ('physics', 'solver', 'results', 'parameters'):
            if previous[key] != current[key]:
                raise ValueError('Historical numerical contract mismatch: '+key)
        manifest = read_json(source/'template.json')['manifest']
        if manifest != project_manifest(config.paths.template_path):
            raise ValueError('Historical template differs from current frozen template')
        rows = []
        for record in read_json(source/'state.json')['records']:
            if record['status'] != 'valid':
                continue
            bundles = sorted(Path(record['attempt_dir']).glob('attempt_*/postprocess_*/field_config.json'))
            if not bundles:
                raise ValueError('Historical raw evidence is missing: '+record['id'])
            destination = store.root/'history'/record['id']
            if destination.exists():
                raise ValueError('Partial history import exists; use a new output directory')
            shutil.copytree(bundles[-1].parent, destination)
            replay = json.loads(json.dumps(analyze_bundle(destination).to_dict()))
            if (not replay['quality_ok'] or not equivalent_metrics(replay['modes'], record['modes']['modes'])
                    or replay['native_modes'] != record['modes']['native_modes']
                    or not math.isclose(replay['worst_impedance_ohm_per_m'], record['worst'], rel_tol=1e-8)):
                raise ValueError('Historical raw replay differs: '+record['id'])
            eligible = planner.geometry.feasible(record['parameters'])
            unit = planner.unit(collapse(record['parameters']))
            eligible = eligible and bool(np.all(unit >= -1e-12) and np.all(unit <= 1+1e-12))
            rows.append({**record, 'id':'history_'+record['id'], 'history_import':True,
                'source':'composite_history', 'attempt_dir':str(destination),
                'status':'valid' if eligible else 'history_outside_domain',
                'history_state_sha256':source_digest, 'raw_replay_verified':True})
        if digest(source/'state.json') != source_digest:
            raise ValueError('Historical state changed during import')
        if not any(r['status'] == 'valid' for r in rows):
            raise ValueError('Need a feasible historical reference')
        store.state['records'] = rows
        store.state['history_provenance'] = dict(source=str(source), state_sha256=source_digest,
            template_manifest_sha256=fingerprint(manifest), new_budget=store.max_solves,
            raw_field_replay=True, native_results_reused=False)
        store.save()
        store.sync_mirrors()
