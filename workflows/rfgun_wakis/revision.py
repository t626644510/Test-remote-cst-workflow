"""Reviewed geometry revision without erasing history or resetting the round clock."""
from __future__ import annotations
from pathlib import Path
import argparse,shutil,time
from .campaign import Campaign
from .cad import parameters
from .geometry import Geometry
from .io import read_json,atomic_json,digest
from .state import WriterLock
from .cst_prepare import ProcessIdentity


def verify_parent(root:Path) -> dict:
    """Require a drained, explicitly stopped parent and no surviving owned tree."""
    state=read_json(root/'state.json')
    if state['status']!='paused' or state['pending'] or state.get('prefetch') or not (root/'STOP').exists():
        raise RuntimeError('Geometry revision requires a paused, drained parent with STOP')
    if state['active_seconds']>=state['cap_seconds']:
        raise RuntimeError('Exhausted round cannot gain time through a geometry revision')
    owners=([root/'owner.json'] if (root/'owner.json').exists() else [])+list((root/'jobs').glob('*/*.owner.json'))
    for path in owners:
        saved=read_json(path)
        rows=saved.get('processes',[saved])
        for row in rows:
            identity=ProcessIdentity(**dict(row,command=tuple(row['command'])))
            if identity.alive():raise RuntimeError('Parent still owns live processes: '+str(path))
    return state


def create_revision(config_path:Path,parent_root:Path) -> dict:
    """Start a separate observation domain; seconds already spent carry once.

    Historical geometries with different fixed conductors remain reference
    evidence only. Their objective values are not relabelled as new native data.
    Preparation and GPU overlap charge the union of active wall time, not two
    machine-hours. The parent journal and its STOP are never rewritten here.
    """
    parent_root=parent_root.resolve()
    with WriterLock(parent_root/'coordinator.lock'):
        parent=verify_parent(parent_root);parent_hash=digest(parent_root/'state.json')
        campaign=Campaign(config_path)
        if campaign.root.resolve()==parent_root:raise RuntimeError('Revision needs a distinct output root')
        if campaign.store.cap!=parent['cap_seconds']:raise RuntimeError('Revision must preserve the original round cap')
        source=Path(campaign.config.paths.template)
        baseline=Geometry.from_template(parameters(source))
        campaign.initialize(baseline)
        audit=campaign.root/'audits/geometry_revision';audit.mkdir(parents=True,exist_ok=True)
        for name in ('state.json','config.snapshot.json','provenance.json','report.json'):
            if (parent_root/name).exists():shutil.copy2(parent_root/name,audit/('parent_'+name))
        shutil.copy2(source,audit/'source_template.cst')
        for rel in ('Model/Parameters.json','ModelCache/Model.mif'):
            if (source.with_suffix('')/rel).exists():shutil.copy2(source.with_suffix('')/rel,audit/Path(rel).name)
        record=dict(at=time.time(),parent_root=str(parent_root),parent_state_sha256=parent_hash,
                    carried_active_seconds=parent['active_seconds'],cap_seconds=parent['cap_seconds'],
                    remaining_seconds=parent['cap_seconds']-parent['active_seconds'],
                    imported_native_observations=0,config_digest=campaign.config.digest(),
                    fixed_parameters=campaign.config.fixed_parameters,active_dimensions=len(campaign.config.active_names))
        data=campaign.store.data
        data.update(active_seconds=parent['active_seconds'],search_active_offset=parent['active_seconds'],
                    exploration_seconds=0.,radius=campaign.config.search.radius,status='paused',budget_origin=record)
        (campaign.root/'STOP').write_text('Prepared geometry revision; explicit start required.\n',encoding='utf-8')
        campaign.store.save();campaign.report();atomic_json(campaign.root/'geometry_revision.json',record)
        if digest(parent_root/'state.json')!=parent_hash:raise RuntimeError('Parent changed during reviewed revision')
        return record


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--parent',required=True)
    args=parser.parse_args();print(create_revision(Path(args.config),Path(args.parent)))
