"""Explicit offline preparation of a fresh 48-hour round; never starts CST.

Stage evidence is inherited at identical physics/geometry/reconstruction settings.
Seconds already charged remain in the ancestry ledger, not the new round clock.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
import math
import shutil
import yaml
from .config import Config, load_config
from .io import atomic_json, digest, fingerprint, project_manifest
from .storage import campaign_lock, verify_evidence


def inherit_state(source: dict, contract: str) -> dict:
    """Clone a quiescent journal, preserving failures and per-stage evidence."""
    if source.get('status') not in ('paused', 'budget_exhausted', 'baseline_complete'):
        raise ValueError('Source round is not safely paused/closed')
    if source.get('pending') or source.get('pending_nodes') or any(j['status']=='reserved' or not j.get('applied') for j in source['jobs']):
        raise ValueError('Source journal has unfinished or unapplied work')
    state=deepcopy(source)
    state.update(contract=contract, status='paused', active_seconds=0.,
                 prior_active_seconds=source.get('prior_active_seconds',0.)+source['active_seconds'],
                 round_number=source.get('round_number',1)+1,
                 exploration_seconds={'near':0.,'global':0.}, pending=None)
    for key in ('fleet_contract', 'fleet_clock_at', 'node_health', 'pending_nodes', 'node_seconds'):
        state.pop(key,None)
    # A new fleet migration assigns station endpoints for this new round.
    state.pop('fleet_retry',None)
    for job in state['jobs']:
        job.setdefault('source_contract',source['contract'])
        job['inherited']=True
    state['round_initial_transverse_ids']=[c['id'] for c in source['candidates'] if 'y' in c['stages']]
    return state


def validate_transition(config: Config, old: Config, source: Path) -> None:
    """Require separate storage and identical numerical observation contracts."""
    if config.search.hours!=48.:
        raise ValueError('New rounds must use a 48 hour budget')
    for field in ('physics','reconstruction','bounds','parameter_mapping','results','fixed_parameters'):
        if fingerprint(config.as_dict()[field])!=fingerprint(old.as_dict()[field]):
            raise ValueError('Cannot inherit changed scientific settings: '+field)
    if ('longitudinal_heat' in (config.search.policy,old.search.policy) and config.search.policy!=old.search.policy) or fingerprint(config.search.seed_points)!=fingerprint(old.search.seed_points) or fingerprint(config.search.neighborhood_half_widths)!=fingerprint(old.search.neighborhood_half_widths):
        raise ValueError('Cannot inherit changed search domain/policy')
    if config.search.observation_mode!=old.search.observation_mode:
        raise ValueError('Cannot inherit a changed observation mode')
    if config.search.fixed_radius_mm!=old.search.fixed_radius_mm or tuple(config.runtime.port_parameters)!=tuple(old.runtime.port_parameters):
        raise ValueError('Cannot inherit changed geometry/port interpretation')
    previous=[source.resolve(),Path(old.paths.artifact_dir).resolve()]
    # Protect every ancestor, not just the immediate prior round.
    state=json.loads((source/'state.json').read_text())
    for item in state.get('round_ancestry',[]):
        previous.extend(Path(item[k]).resolve() for k in ('source','artifacts'))
    for destination in (Path(config.paths.output_dir).resolve(),Path(config.paths.artifact_dir).resolve()):
        if any(destination==p or destination.is_relative_to(p) or p.is_relative_to(destination) for p in previous):
            raise ValueError('New round storage overlaps a source round')
        if destination.exists() and any(destination.iterdir()):
            raise ValueError('New round destination must be empty')


def prepare_round(config: Config, config_path: Path, source: Path, prior_external_seconds: float = 0.) -> dict:
    """Prepare one paused round with STOP and verified immutable source ancestry.

    User authorization to start is separate: this function has no live solver
    or process API. A failed preparation leaves evidence in place for review.
    """
    from .campaign import initialize, Campaign
    source=source.resolve()
    old=load_config(source/'effective_config.yaml')
    config.validate(live=True)
    validate_transition(config,old,source)
    with campaign_lock(source):
        original=json.loads((source/'state.json').read_text())
        state=inherit_state(original,'pending')
        if not math.isfinite(prior_external_seconds) or prior_external_seconds<0:
            raise ValueError('External prior runtime must be nonnegative seconds')
        if prior_external_seconds and original.get('external_active_seconds',0.):
            raise ValueError('External prior runtime is already accounted for')
        state['external_active_seconds']=original.get('external_active_seconds',0.)+prior_external_seconds
        source_hash=digest(source/'state.json')
        caches=[]
        for candidate in original['candidates']:
            for stage in candidate['stages'].values():
                if not verify_evidence(Path(stage['raw'])):
                    raise ValueError('Inherited raw evidence failed manifest verification: '+stage['raw'])
            cache=Path(old.paths.artifact_dir)/'evidence'/candidate['id']/f"revision_{candidate['revision']:03d}"
            if cache.exists():
                if not verify_evidence(cache):raise ValueError('Inherited analysis manifest failed: '+str(cache))
                caches.append((cache,Path(config.paths.artifact_dir)/'evidence'/candidate['id']/cache.name))
        # Compare against the saved prior templates, not mutable source path names.
        for stage,path in config.paths.templates.items():
            previous=Path(old.paths.artifact_dir)/'templates'/stage/Path(old.paths.templates[stage]).name
            if project_manifest(Path(path))!=project_manifest(previous):
                raise ValueError('Template content changed: '+stage)
        contract,snapshot=initialize(config)
        state['contract']=contract
        state.setdefault('round_ancestry',[]).append(dict(source=str(source),artifacts=old.paths.artifact_dir,
            state_sha256=source_hash,contract=original['contract'],active_seconds=original['active_seconds'],
            budget_hours=old.search.hours,round_number=original.get('round_number',1)))
        root=Path(config.paths.output_dir)
        with campaign_lock(root):
            (root/'STOP').write_text('Prepared only. Await user audit and explicit start authorization.\n')
            for previous,destination in caches:
                shutil.copytree(previous,destination)
                if not verify_evidence(destination):raise ValueError('Copied analysis evidence failed verification')
            (root/'effective_config.yaml').write_text(yaml.safe_dump({'workflow_6':config.as_dict()},sort_keys=False),encoding='utf-8')
            atomic_json(root/'state.json',state)
            campaign=Campaign(config,config_path.resolve(),contract,snapshot)
            try:campaign.report()
            finally:campaign.store.close()
            proof=dict(status='prepared_paused',round_number=state['round_number'],budget_hours=48.,
                solver_starts=0,source=str(source),source_sha256=source_hash,contract=contract,
                candidates=len(state['candidates']),inherited_jobs=len(state['jobs']),
                active_seconds=0.,prior_active_seconds=state['prior_active_seconds'],
                external_active_seconds=state['external_active_seconds'],output_dir=str(root))
            if digest(source/'state.json')!=source_hash:raise ValueError('Source state changed during preparation')
            atomic_json(root/'round_preparation.json',proof)
            return proof
