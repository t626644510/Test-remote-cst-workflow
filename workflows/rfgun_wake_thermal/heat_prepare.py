"""Prepare an isolated WF6.1 fleet in a paused state, without launching workers."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json
import shutil
import yaml
from .config import Config
from .campaign import initialize
from .io import atomic_json, digest, fingerprint
from .fleet.protocol import Node, execution_identity
from .fleet.coordinator import FleetCampaign


def prepare(config: Config, config_path: Path, nodes: list[Node], reference: Path) -> dict:
    """Create a zero-cost 48 h journal; old geometries remain reference-only.

    No CST API, subprocess, worker launch, or remote publication is performed.
    The STOP file requires a subsequent explicit user-authorized start.
    """
    config.validate(live=True)
    if config.search.policy!='longitudinal_heat' or config.search.hours!=48.:
        raise ValueError('Fresh WF6.1 preparation requires the 48 h heat policy')
    if len(nodes)!=2 or len([n for n in nodes if not n.ssh_host])!=1 or len({n.name for n in nodes})!=2:
        raise ValueError('Exactly one local and one remote node required')
    reference=reference.resolve()
    old=json.loads(reference.read_text(encoding='utf-8-sig'))
    # This is a read-only snapshot, not journal migration. Unreconciled old
    # station tasks are recorded and must be inspected before a future start.
    root=Path(config.paths.output_dir);bulk=Path(config.paths.artifact_dir)
    for destination in (root,bulk):
        if destination.exists() and any(destination.iterdir()):raise ValueError('WF6.1 destinations must be empty')
        if reference.is_relative_to(destination.resolve()):raise ValueError('Destination overlaps reference')
    reference_hash=digest(reference)
    root.mkdir(parents=True,exist_ok=True)
    (root/'STOP').write_text('Prepared only; manual user authorization required to start.\n',encoding='utf-8')
    contract,snapshot=initialize(config)
    if not any(snapshot['baseline']==p for p in config.search.seed_points):
        # Parameter transforms have floating roundoff; test physically in mm/degrees.
        if not any(all(abs(snapshot['baseline'][k]-p[k])<1e-8 for k in p) for p in config.search.seed_points):
            raise ValueError('Prepared templates must match one of the two fixed-coordinate seeds')
    execution=execution_identity(config)
    manifest=dict(execution=execution,nodes=[asdict(n) for n in nodes],source_contract=contract)
    campaign=FleetCampaign(config,config_path,contract,snapshot,nodes,fingerprint(execution))
    try:
        reference_dir=root/'reference_only';reference_dir.mkdir()
        shutil.copy2(reference,reference_dir/'wf6_state.json')
        campaign.state.update(status='paused',workflow='WF6.1',round_number=1,
            fleet_contract=fingerprint(manifest),historical_observations=[],
            reference_history=dict(source=str(reference),sha256=reference_hash,
                archived=str(reference_dir/'wf6_state.json'),candidate_count=len(old['candidates']),
                source_status=old.get('status'),source_pending_nodes=old.get('pending_nodes',{}),
                source_active_seconds=old['active_seconds'],source_prior_active_seconds=old.get('prior_active_seconds',0.),
                use='Parameter seeds and manual reference only; no old observations projected into reduced GP'))
        for point in config.search.seed_points:campaign.new_candidate(dict(point),'wf61_seed')
        atomic_json(root/'fleet_contract.json',manifest)
        (root/'effective_config.yaml').write_text(yaml.safe_dump({'workflow_6':config.as_dict()},sort_keys=False),encoding='utf-8')
        campaign.store.save();campaign.report()
        if digest(reference)!=reference_hash:raise ValueError('Reference changed during preparation')
        audit=dict(status='prepared_paused',contract=contract,execution=fingerprint(execution),
                   stop=True,jobs=0,active_seconds=0.,solver_starts=0,reference_unchanged=True,
                   start_requires='Manual authorization, both-station identity and old-task ownership/quiescence checks',
                   seed_candidates=[c['id'] for c in campaign.state['candidates']])
        atomic_json(root/'preparation.json',audit)
        return audit
    finally:campaign.store.db.close()
