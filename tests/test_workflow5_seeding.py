"""Offline baseline migration: preserve native evidence, budget and contracts."""
from dataclasses import asdict, replace
import builtins
import json
from pathlib import Path

import pytest

from workflows.rfgun_hom_target.config import (WorkflowConfig, PathsConfig, ParameterConfig,
    PARAMETER_DEFAULTS, PhysicsConfig, SolverConfig, SearchConfig)
from workflows.rfgun_hom_target import postprocess as pp
from workflows.rfgun_hom_target.runtime import metadata, postprocess_config, result_fingerprint
from workflows.rfgun_hom_target.seeding import archive_lock, import_baseline
from workflows.rfgun_hom_target.storage import CampaignStore, atomic_json, digest, project_manifest
from test_workflow5_physics import write_raw

pytestmark = pytest.mark.no_cst


@pytest.fixture
def archive(tmp_path):
    root = tmp_path / "old"
    root.mkdir()
    (root / "campaign.lock").write_bytes(b"0")
    template = root / "template/model.cst"
    project = root / "evaluations/evaluation_0000/attempt_000/project/model.cst"
    parameters = {"selfangle2": 45., "UpperHeight2": 25., "DownHeight2": 5.,
                  "Lin2": 15., "inner_angle3": 60., "inner_r2": 12.}
    for path in (template, project):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"saved geometry")
        atomic_json(path.with_suffix("") / "Model/3D/ModelHistory.json", {"general": {"length": "mm", "frequency": {"unit": "MHz"}}})
        atomic_json(path.with_suffix("") / "Model/Parameters.json", {"parameters": [dict(name=k,value=v) for k,v in parameters.items()]})
    config = WorkflowConfig(PathsConfig(template, tmp_path / "new"),
        tuple(ParameterConfig(n,lo,hi,u,n) for n,lo,hi,u in PARAMETER_DEFAULTS),
        PhysicsConfig((-100.,100.),z_samples=101,mode_policy="largest_two"),
        solver=SolverConfig(upper_frequency_mhz=1060,coverage_policy="fixed_window",max_mode_count=6,coverage_retries=0),
        search=SearchConfig(max_solves=36))
    previous = config.as_dict()
    previous["physics"].pop("mode_policy")
    previous["search"]["max_solves"] = 37
    atomic_json(root / "config.resolved.json", previous)
    atomic_json(root / "template.json", {"project": str(template), "manifest": project_manifest(template)})
    attempt = project.parents[1]
    evaluation = attempt.parent
    bundle = attempt / "postprocess_000"
    ppconfig = replace(postprocess_config(config, metadata(template)), mode_policy="strict_all")
    modes = [pp.NativeMode(1,1040e6,1000),pp.NativeMode(2,1050e6,500),pp.NativeMode(3,1055e6,1.7)]
    for mode in modes:
        write_raw(bundle / "fields" / f"mode_{mode.mode_number}", mode, ppconfig)
    atomic_json(bundle / "native.json", {"source_project":str(project),"modes":[m.to_dict() for m in modes]})
    atomic_json(bundle / "field_config.json", {**asdict(ppconfig),"band_mhz":[1030,1060]})
    analysis = pp.analyze_bundle(bundle).to_dict()
    atomic_json(bundle / "analysis.json", analysis)
    atomic_json(attempt / "solved.json", {"project_sha256":digest(project),"result_fingerprint":result_fingerprint(project),"mode_count":6})
    atomic_json(evaluation / "evaluation.json", {"current":str(attempt),"project":str(project)})
    record = dict(id="evaluation_0000",source="baseline",status="quality_failed",parameters=parameters,
                  attempt_dir=str(evaluation),modes=analysis,coverage_policy="fixed_window",coverage_verified=False)
    atomic_json(root / "state.json", {"pending":None,"records":[record],"status":"baseline_failed","solve_count":1,"contract":"original"})
    return config, root, template, bundle


def test_policy_migration_recomputes_without_cst_or_consuming_budget(archive, monkeypatch):
    config, root, template, bundle = archive
    before = {p:p.read_bytes() for p in root.rglob("*") if p.is_file()}
    original_import = builtins.__import__
    def guarded(name,*args,**kwargs):
        if name == "cst" or name.startswith("cst."):
            pytest.fail("Seed import must not load CST")
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,"__import__",guarded)
    store = CampaignStore(config.paths.output_dir,"new",36)
    try:
        import_baseline(config,store,template,root)
        assert store.state["solve_count"] == 0
        record = store.state["records"][0]
        assert record["status"] == "valid"
        assert record["modes"]["objective_mode_numbers"] == [1,2]
        assert len(record["modes"]["modes"]) == 3
        assert record["seed_provenance"]["source_contract"] == "original"
        assert (config.paths.output_dir/"seed_provenance.json").exists()
        assert all(p.read_bytes()==data for p,data in before.items())
    finally:
        store.close()


@pytest.mark.parametrize("mutation",["frequency","sampling","budget","template","native","field","busy","pending"])
def test_seed_rejects_incompatible_incomplete_or_active_evidence(archive, mutation):
    config, root, template, bundle = archive
    if mutation == "frequency": config = replace(config,solver=replace(config.solver,upper_frequency_mhz=1061))
    if mutation == "sampling": config = replace(config,physics=replace(config.physics,z_samples=103))
    if mutation == "budget": config = replace(config,search=replace(config.search,max_solves=37))
    if mutation == "template": template.write_bytes(b"modified geometry")
    if mutation == "native": (root/"evaluations/evaluation_0000/attempt_000/project/model.cst").write_bytes(b"changed")
    if mutation == "field": (bundle/"fields/mode_3/energy.csv").write_text("U_J,Q_wall_postprocess\n0,10000\n")
    if mutation == "pending":
        state=json.loads((root/"state.json").read_text()); state["pending"]={"id":"running"}; atomic_json(root/"state.json",state)
    store=CampaignStore(config.paths.output_dir,"new",36)
    try:
        if mutation == "busy":
            with archive_lock(root), pytest.raises((OSError, ValueError)):
                import_baseline(config,store,template,root)
        else:
            with pytest.raises(ValueError): import_baseline(config,store,template,root)
        assert store.state["solve_count"] == 0
        assert not store.state["records"]
    finally:
        store.close()
