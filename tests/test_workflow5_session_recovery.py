"""Exact-PID, session correlation and orphan recovery tests without CST."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from workflows.rfgun_hom_target import runtime as rt
from workflows.rfgun_hom_target import session_recovery as recovery
from workflows.rfgun_hom_target.config import (
    PARAMETER_DEFAULTS, ParameterConfig, PathsConfig, PhysicsConfig, WorkflowConfig,
)
from workflows.rfgun_hom_target.search import Campaign
from workflows.rfgun_hom_target.storage import CampaignStore, atomic_json

pytestmark = pytest.mark.no_cst


class Kernel:
    def __init__(self, handle=42, wait=258):
        self.handle, self.wait, self.calls = handle, wait, []
    def OpenProcess(self, access, inherit, pid):
        self.calls.append(("open", access, inherit, pid))
        return self.handle
    def WaitForSingleObject(self, handle, timeout):
        self.calls.append(("wait", handle, timeout))
        return self.wait
    def CloseHandle(self, handle):
        self.calls.append(("close", handle))


@pytest.mark.parametrize("wait,expected", [(258, "alive"), (0, "absent"), (0xFFFFFFFF, "unknown")])
def test_exact_pid_wait_handle_is_closed_and_never_requests_kill_access(wait, expected):
    kernel = Kernel(wait=wait)
    assert recovery._query_windows_pid(12345, kernel, lambda: 0) == expected
    assert kernel.calls == [("open", 0x00100000, False, 12345), ("wait", 42, 0), ("close", 42)]


@pytest.mark.parametrize("error,expected", [(87, "absent"), (5, "unknown"), (0, "unknown")])
def test_missing_process_is_distinct_from_access_denied(error, expected):
    kernel = Kernel(handle=0)
    assert recovery._query_windows_pid(12345, kernel, lambda: error) == expected
    assert kernel.calls == [("open", 0x00100000, False, 12345)]


@pytest.mark.parametrize("pid", [None, True, -1, 0, "123", 2**32])
def test_invalid_pid_is_unknown_without_process_api(pid):
    assert recovery.query_pid(pid) == "unknown"


def session_files(root, session, cleanup=None):
    directory = root / "attempt_000"
    atomic_json(directory / "solve_session.json", session)
    if cleanup is not None:
        atomic_json(directory / "solve_cleanup.json", cleanup)
    return directory


@pytest.mark.parametrize("state", ["alive", "unknown", "unexpected"])
def test_unfinished_session_blocks_without_mutating_records(tmp_path, state):
    directory = session_files(tmp_path, {"pid": 12345, "project": "owned.cst"})
    before = (directory / "solve_session.json").read_bytes()
    with pytest.raises(recovery.SessionRecoveryBlocked):
        recovery.ensure_sessions_inactive(tmp_path, probe=lambda pid: state)
    assert (directory / "solve_session.json").read_bytes() == before


def test_legacy_cleanup_never_bypasses_exact_pid_probe(tmp_path):
    session_files(tmp_path, {"pid": 12345, "project": "owned.cst"}, {"pid": 12345, "success": True})
    calls = []
    with pytest.raises(recovery.SessionRecoveryBlocked):
        recovery.ensure_sessions_inactive(tmp_path, probe=lambda pid: calls.append(pid) or "alive")
    assert calls == [12345]
    recovery.ensure_sessions_inactive(tmp_path, probe=lambda _: "absent")


def test_new_cleanup_requires_uuid_pid_project_and_verified_exit(tmp_path):
    session = {"session_id": "new", "pid": 12345, "project": "owned.cst", "phase": "active"}
    cleanup = {**session, "success": True, "exit_verified": True}
    directory = session_files(tmp_path, session, cleanup)
    recovery.ensure_sessions_inactive(tmp_path, probe=lambda _: pytest.fail("Matching verified cleanup is terminal"))
    for key, value in [("session_id", "old"), ("pid", 123), ("project", "elsewhere.cst"), ("exit_verified", False)]:
        atomic_json(directory / "solve_cleanup.json", {**cleanup, key: value})
        with pytest.raises(recovery.SessionRecoveryBlocked):
            recovery.ensure_sessions_inactive(tmp_path, probe=lambda _: "alive")


def test_opening_without_pid_and_malformed_records_fail_closed(tmp_path):
    directory = session_files(tmp_path, {"session_id": "opening", "pid": None, "phase": "opening"})
    with pytest.raises(recovery.SessionRecoveryBlocked):
        recovery.ensure_sessions_inactive(tmp_path, probe=lambda _: pytest.fail("Cannot query missing PID"))
    (directory / "solve_session.json").write_text("{corrupt", encoding="utf-8")
    with pytest.raises(recovery.SessionRecoveryBlocked, match="Cannot read"):
        recovery.ensure_sessions_inactive(tmp_path)


def test_probe_exception_is_unknown(tmp_path):
    session_files(tmp_path, {"pid": 12345})
    def fail(_): raise OSError("process query failed")
    with pytest.raises(recovery.SessionRecoveryBlocked, match="unknown"):
        recovery.ensure_sessions_inactive(tmp_path, probe=fail)


def make_config(tmp_path):
    return WorkflowConfig(PathsConfig(tmp_path / "template.cst", tmp_path / "run", "library"),
                          tuple(ParameterConfig(*p) for p in PARAMETER_DEFAULTS), PhysicsConfig((-100., 100.)))


def test_python_lock_released_but_cst_alive_preserves_pending_and_budget(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    baseline = dict(selfangle2=45., UpperHeight2=26., DownHeight2=4., Lin2=12., inner_angle3=71., inner_r2=12.)
    store = CampaignStore(config.paths.output_dir, "contract", 40)
    directory = store.root / "evaluations/evaluation_0000"
    store.state["pending"] = {"id": "evaluation_0000", "parameters": baseline,
                              "source": "baseline", "attempt_dir": str(directory)}
    store.reserve_solve("attempt_000")
    pending = dict(store.state["pending"])
    store.close()  # Simulate Python process lock disappearing, not CST exiting.
    session_files(directory, {"pid": 12345, "project": "owned.cst"})
    atomic_json(directory / "evaluation.json", {"phase": "prepare", "parameters": baseline, "attempts": 1,
        "mode_count": 6, "coverage_retries": 0, "transient_retries": 0, "current": str(directory / "attempt_000")})
    obj = rt.CSTEvaluator.__new__(rt.CSTEvaluator)
    obj.config = config
    monkeypatch.setattr(obj, "_prepare", lambda *a: pytest.fail("No new project while prior PID alive"))
    monkeypatch.setattr(recovery, "query_pid", lambda _: "alive")
    resumed = CampaignStore(config.paths.output_dir, "contract", 40, resume=True)
    try:
        report = Campaign(config, resumed, obj).run(baseline)
        assert report["status"] == "orphan_session_pending"
        assert resumed.state["pending"] == pending
        assert report["solve_count"] == 1
        assert resumed.state["records"] == []
    finally:
        resumed.close()


def test_project_close_exception_still_runs_targeted_cleanup_with_matching_uuid(tmp_path, monkeypatch):
    import cst_optimization.core.connection as connection_module
    path = tmp_path / "owned.cst"
    calls = []
    class Project:
        filename = str(path)
        def activate(self): pass
        def close(self, **kwargs):
            calls.append("project_close")
            raise RuntimeError("close COM failure")
    class Connection:
        pid = 12345
        def __init__(self, **kwargs): pass
        def connect(self):
            opening = json.loads((tmp_path / "test_session.json").read_text())
            assert opening["phase"] == "opening" and opening["pid"] is None
        def open_project(self, _): return Project()
        def close(self, **kwargs): pytest.fail("No global cleanup")
        def close_targeted(self, *, pid_override):
            calls.append(("targeted", pid_override))
            return {"success": True, "exit_verified": True}
    monkeypatch.setattr(connection_module, "CSTConnection", Connection)
    monkeypatch.setattr(rt, "query_pid", lambda _: "absent")
    obj = rt.CSTEvaluator.__new__(rt.CSTEvaluator)
    obj.config = make_config(tmp_path)
    with pytest.raises(rt.EvaluationFailure) as error:
        with obj._project(path, tmp_path, "test"):
            pass
    assert error.value.category == "project_close_failed"
    assert calls == ["project_close", ("targeted", 12345)]
    session = json.loads((tmp_path / "test_session.json").read_text())
    cleanup = json.loads((tmp_path / "test_cleanup.json").read_text())
    assert session["session_id"] == cleanup["session_id"]
    assert session["pid"] == cleanup["pid"] == 12345
    assert cleanup["exit_verified"] and cleanup["project_close_error"]


@pytest.mark.parametrize("pid_state", ["alive", "unknown"])
def test_shared_cleanup_success_does_not_override_exact_probe(tmp_path, monkeypatch, pid_state):
    import cst_optimization.core.connection as connection_module
    path = tmp_path / "owned.cst"
    class Connection:
        pid = 12345
        def __init__(self, **kwargs): pass
        def connect(self): pass
        def open_project(self, _):
            return SimpleNamespace(filename=str(path), activate=lambda: None, close=lambda **kwargs: None)
        def close_targeted(self, **kwargs): return {"success": True, "exit_verified": True}
        def close(self, **kwargs): pytest.fail("No global cleanup")
    monkeypatch.setattr(connection_module, "CSTConnection", Connection)
    monkeypatch.setattr(rt, "query_pid", lambda _: pid_state)
    obj = rt.CSTEvaluator.__new__(rt.CSTEvaluator)
    obj.config = make_config(tmp_path)
    with pytest.raises(rt.EvaluationFailure) as error:
        with obj._project(path, tmp_path, "solve"):
            pass
    assert error.value.category == "cleanup_failed"
    certificate = json.loads((tmp_path / "solve_cleanup.json").read_text())
    assert certificate["success"] is False
    assert certificate["exit_verified"] is False
    assert certificate["pid_state"] == pid_state


def test_failed_connect_recovers_only_connection_owned_pid_for_cleanup(tmp_path, monkeypatch):
    import cst_optimization.core.connection as connection_module
    calls = []
    class Connection:
        pid = None
        def __init__(self, **kwargs): pass
        def connect(self):
            self.pid = 12345
            raise RuntimeError("connect interrupted after DE creation")
        def close_targeted(self, *, pid_override):
            calls.append(pid_override)
            return {"success": True, "exit_verified": True}
        def close(self, **kwargs): pytest.fail("No global cleanup")
    monkeypatch.setattr(connection_module, "CSTConnection", Connection)
    monkeypatch.setattr(rt, "query_pid", lambda pid: "absent" if pid == 12345 else pytest.fail("Unowned PID"))
    obj = rt.CSTEvaluator.__new__(rt.CSTEvaluator)
    obj.config = make_config(tmp_path)
    with pytest.raises(RuntimeError, match="connect interrupted"):
        with obj._project(tmp_path / "owned.cst", tmp_path, "prepare"):
            pytest.fail("Failed connect must not expose a project")
    session = json.loads((tmp_path / "prepare_session.json").read_text())
    certificate = json.loads((tmp_path / "prepare_cleanup.json").read_text())
    assert calls == [12345]
    assert session["pid"] == certificate["pid"] == 12345
    assert session["session_id"] == certificate["session_id"]
    assert certificate["success"] and certificate["exit_verified"]
