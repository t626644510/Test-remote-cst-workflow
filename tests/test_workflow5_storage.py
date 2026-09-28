"""No-CST tests for consistent snapshots and recoverable campaign persistence."""

import json

import pytest

from cst_optimization.checkpoint import CheckpointManager
from workflows.rfgun_hom_target import storage
from workflows.rfgun_hom_target.storage import (
    BudgetExhausted, CampaignStore, atomic_json, copy_verified_project, digest,
    fingerprint, project_manifest,
)


pytestmark = pytest.mark.no_cst


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "source" / "portable.cst"
    source.parent.mkdir()
    source.write_bytes(b"CST project bytes")
    companion = source.with_suffix("")
    (companion / "Model" / "3D").mkdir(parents=True)
    (companion / "Model" / "3D" / "history.json").write_text('{"saved": true}')
    (companion / "Result").mkdir()
    (companion / "Result" / "fields.bin").write_bytes(b"saved result fields")
    (companion / "Model.lok").write_text("user session lock")
    (companion / "Result" / "active.LOCK").write_text("another user lock")
    return source


@pytest.fixture
def record():
    return dict(id="evaluation_0000", source="baseline", status="valid", worst=123456.,
                objective=.8, parameters=dict(selfangle2=45., UpperHeight2=26.,
                    DownHeight2=4., Lin2=12., inner_angle3=71., inner_r2=12.),
                attempt_dir="portable/evaluations/evaluation_0000")


def test_complete_snapshot_preserves_source_and_leaves_locks_untouched(project, tmp_path):
    originals = {p: (digest(p), p.stat().st_mtime_ns) for p in project.parent.rglob("*") if p.is_file()}
    copied, manifest = copy_verified_project(project, tmp_path / "snapshot")
    assert len(manifest) == 3
    assert project_manifest(copied) == project_manifest(project) == manifest
    assert not list(copied.parent.rglob("*.lok"))
    assert not list(copied.parent.rglob("*.LOCK"))
    assert {p: (digest(p), p.stat().st_mtime_ns) for p in originals} == originals


@pytest.mark.parametrize("inside", [False, True])
def test_snapshot_destination_cannot_overlap_source(project, inside):
    destination = project.with_suffix("") / "copies" if inside else project.parent
    with pytest.raises(ValueError, match="overlap"):
        copy_verified_project(project, destination)


def test_source_change_during_copy_is_detected(project, tmp_path, monkeypatch):
    real_copy = storage.shutil.copy2
    changed = False

    def mutate_after_copy(source, target):
        nonlocal changed
        result = real_copy(source, target)
        if not changed:
            changed = True
            project.write_bytes(b"changed by external writer")
        return result

    monkeypatch.setattr(storage.shutil, "copy2", mutate_after_copy)
    with pytest.raises(RuntimeError, match="Source changed"):
        copy_verified_project(project, tmp_path / "unstable")


def test_existing_campaign_requires_explicit_resume_and_matching_contract(tmp_path):
    root = tmp_path / "campaign"
    first = CampaignStore(root, "contract-A", 40)
    first.close()
    with pytest.raises(ValueError, match="exists"):
        CampaignStore(root, "contract-A", 40)
    with pytest.raises(ValueError, match="fingerprint changed"):
        CampaignStore(root, "contract-B", 40, resume=True)
    with pytest.raises(ValueError, match="No campaign"):
        CampaignStore(tmp_path / "missing", "contract-A", 40, resume=True)


def test_reservation_is_durable_before_solver_start_and_capped(tmp_path):
    root = tmp_path / "campaign"
    first = CampaignStore(root, "contract", 2)
    try:
        assert first.reserve_solve("primary") == 1
        persisted = json.loads(first.path.read_text())
        assert persisted["solve_count"] == 1
        assert persisted["reservations"] == [dict(number=1, attempt="primary")]
    finally:
        first.close()
    resumed = CampaignStore(root, "contract", 2, resume=True)
    try:
        assert resumed.reserve_solve("coverage") == 2
        with pytest.raises(BudgetExhausted):
            resumed.reserve_solve("third")
        assert resumed.state["solve_count"] == 2
        assert len(resumed.state["reservations"]) == 2
    finally:
        resumed.close()


def test_finish_and_mirror_reconciliation_are_idempotent(tmp_path, record):
    root = tmp_path / "campaign"
    store = CampaignStore(root, "contract", 40)
    try:
        store.reserve_solve("primary")
        store.state["pending"] = dict(id=record["id"])
        store.finish(record)
        store.finish(dict(record))
        store.sync_mirrors()
        assert len(store.state["records"]) == 1
        assert store.state["pending"] is None
        assert len(store.db.get_all_records()) == 1
        checkpoint = CheckpointManager(str(root / "campaign.ckpt"))
        assert checkpoint.load()
        assert checkpoint.iteration == 1
        assert len(checkpoint.records) == 1
        assert checkpoint.records[0].solver_ok
        assert checkpoint.records[0].raw_values["worst_impedance_ohm_per_m"] == record["worst"]
    finally:
        store.close()
    resumed = CampaignStore(root, "contract", 40, resume=True)
    try:
        resumed.sync_mirrors()
        assert len(resumed.db.get_all_records()) == 1
        assert len(resumed.checkpoint.records) == 1
    finally:
        resumed.close()


def test_json_commit_survives_failed_mirror_and_resume_repairs_it(tmp_path, record, monkeypatch):
    root = tmp_path / "campaign"
    store = CampaignStore(root, "contract", 40)
    try:
        def unavailable():
            raise OSError("simulated mirror disk interruption")
        monkeypatch.setattr(store, "sync_mirrors", unavailable)
        with pytest.raises(OSError):
            store.finish(record)
        assert json.loads(store.path.read_text())["records"] == [record]
    finally:
        store.close()
    resumed = CampaignStore(root, "contract", 40, resume=True)
    try:
        resumed.sync_mirrors()
        assert len(resumed.db.get_all_records()) == 1
        assert len(resumed.checkpoint.records) == 1
    finally:
        resumed.close()


def test_failed_evaluation_mirror_has_no_surrogate_objective_or_physical_metric(tmp_path, record):
    store = CampaignStore(tmp_path / "campaign", "contract", 40)
    try:
        record.update(status="geometry_failed", worst=None, objective=None, error="invalid shape")
        store.finish(record)
        rows = store.db.get_all_records()
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] != "success"
        assert not row["raw_metrics"]
        assert not row["objective_values"]
        assert row["diagnostics"]["status"] == "geometry_failed"
        assert not store.checkpoint.records[0].solver_ok
        assert store.checkpoint.records[0].raw_values == {}
    finally:
        store.close()


def test_atomic_json_refuses_nan_without_destroying_previous_state(tmp_path):
    path = tmp_path / "state.json"
    atomic_json(path, {"valid": 1})
    with pytest.raises(ValueError):
        atomic_json(path, {"invalid": float("nan")})
    assert json.loads(path.read_text()) == {"valid": 1}


def test_fingerprint_ignores_mapping_order_but_preserves_contract_changes():
    assert fingerprint(dict(a=1, b=2)) == fingerprint(dict(b=2, a=1))
    assert fingerprint(dict(a=1, b=2)) != fingerprint(dict(a=1, b=3))


def test_exclusive_campaign_owner_rejects_second_store_until_first_closes(tmp_path):
    root = tmp_path / "exclusive"
    first = CampaignStore(root, "contract", 40)
    try:
        first.reserve_solve("owned-by-first")
        before = first.path.read_bytes()
        with pytest.raises(ValueError, match="already owned"):
            CampaignStore(root, "contract", 40, resume=True)
        assert first.path.read_bytes() == before
        # Rejecting another owner must not accidentally release the first lock.
        with pytest.raises(ValueError, match="already owned"):
            CampaignStore(root, "contract", 40, resume=True)
    finally:
        first.close()
    reopened = CampaignStore(root, "contract", 40, resume=True)
    try:
        assert reopened.state["solve_count"] == 1
        assert reopened.reserve_solve("owned-by-reopened") == 2
    finally:
        reopened.close()


def test_contract_rejection_releases_acquired_lock_without_changing_campaign(tmp_path):
    root = tmp_path / "contract-rejection"
    original = CampaignStore(root, "contract-A", 40)
    original.reserve_solve("persisted-solve")
    original.close()
    before = (root / "state.json").read_bytes()
    with pytest.raises(ValueError, match="fingerprint changed"):
        CampaignStore(root, "contract-B", 40, resume=True)
    assert (root / "state.json").read_bytes() == before
    # The failed constructor acquired the lock, so reopening demonstrates cleanup.
    recovered = CampaignStore(root, "contract-A", 40, resume=True)
    try:
        assert recovered.state["solve_count"] == 1
        assert recovered.state["contract"] == "contract-A"
    finally:
        recovered.close()
