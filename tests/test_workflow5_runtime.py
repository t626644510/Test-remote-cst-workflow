"""No-CST lifecycle tests: ownership, units, budgets and crash recovery."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cst_optimization.core.solver import SolverResult
from workflows.rfgun_hom_target.config import (
    GeometryConfig, ParameterConfig, PARAMETER_DEFAULTS, PathsConfig,
    PhysicsConfig, ResultsConfig, SearchConfig, SolverConfig, WorkflowConfig,
)
from workflows.rfgun_hom_target import runtime as rt
from workflows.rfgun_hom_target.postprocess import NativeMode

pytestmark = pytest.mark.no_cst


@pytest.fixture
def cfg(tmp_path):
    return WorkflowConfig(
        PathsConfig(tmp_path / "template.cst", tmp_path / "output", "configured-library"),
        tuple(ParameterConfig(n, lo, hi, unit, n) for n, lo, hi, unit in PARAMETER_DEFAULTS),
        PhysicsConfig((-100., 100.)),
    )


def evaluator(cfg):
    instance = rt.CSTEvaluator.__new__(rt.CSTEvaluator)
    instance.config = cfg
    instance.template = cfg.paths.template_path
    instance.info = {"length_unit": "mm", "frequency_unit": "MHz"}
    instance.pp = SimpleNamespace()
    return instance


@pytest.mark.parametrize("unit,lo,hi", [("Hz", "1030000000", "1070000000"), ("kHz", "1030000", "1070000"), ("MHz", "1030", "1070"), ("GHz", "1.03", "1.07")])
def test_solver_converts_units_preserves_mesh_and_uses_lower_limit(cfg, unit, lo, hi):
    code = rt.solver_vba(cfg, unit, 12)
    assert f'Solver.FrequencyRange "{lo}", "{hi}"' in code
    assert f'.SetFrequencyTarget "True", "{lo}"' in code
    assert '.SetNumberOfModes "12"' in code
    assert '.SetModesInFrequencyRange "False"' in code
    assert '.SetCalculateExternalQFactor "True"' in code
    assert "Reset" not in code and "Mesh" not in code and "Adapt" not in code


def test_solver_rejects_lower_limit_skipping_objective_band(cfg):
    cfg = replace(cfg, solver=replace(cfg.solver, target_frequency_mhz=1040))
    with pytest.raises(ValueError, match="skip"):
        rt.solver_vba(cfg, "MHz", 6)


def test_coverage_requires_every_mode_and_strict_upper_guard():
    assert rt.coverage_complete([NativeMode(i, (1030 + i * 6) * 1e6, 100) for i in range(1, 7)], 6, 1060)
    assert not rt.coverage_complete([NativeMode(i, (1030 + i * 5) * 1e6, 100) for i in range(1, 7)], 6, 1060)
    assert not rt.coverage_complete([NativeMode(1, 1040e6, 100), NativeMode(6, 1080e6, 100)], 6, 1060)
    assert not rt.coverage_complete([], 6, 1060)


def test_interval_exhaustion_can_return_fewer_requested_modes_with_sentinel(cfg):
    native = [NativeMode(1, 1040e6, 100), NativeMode(2, 1050e6, 100), NativeMode(3, 1065e6, 100)]
    assert rt.coverage_complete(native, 6, 1060)
    assert not rt.coverage_complete(native, 2, 1060)
    assert cfg.physics.frequency_max_mhz == 1060
    assert cfg.solver.upper_frequency_mhz == 1070


def test_solver_guard_does_not_expand_physical_acceptance_band(cfg, tmp_path, monkeypatch):
    obj, _, _ = evaluation_harness(cfg, monkeypatch)
    observed_bands = []
    def analyze(project, path, out, pp, band, **kwargs):
        observed_bands.append(band)
        return SimpleNamespace(quality_ok=True, worst_impedance_ohm_per_m=90000.,
                               to_dict=lambda: {"quality_ok": True})
    monkeypatch.setattr(rt, "collect_and_analyze", analyze)
    assert obj({"x": 1.}, tmp_path / "evaluation", lambda _: 1)["status"] == "valid"
    assert observed_bands == [(1030., 1060.)]


def test_baseline_converts_geometry_units_and_parameter_aliases(cfg, monkeypatch):
    renamed = replace(cfg.parameters[-1], cst_name="bend_radius")
    cfg = replace(cfg, parameters=(*cfg.parameters[:-1], renamed))
    saved = {p.cst_name: 2. for p in cfg.parameters}
    monkeypatch.setattr(rt, "metadata", lambda _: {"length_unit": "cm", "parameters": saved})
    values = rt.read_baseline(cfg.paths.template_path, cfg)
    assert values["inner_r2"] == 20
    assert values["selfangle2"] == 2


def test_postprocessing_rejects_frequency_unit_mismatch(cfg):
    with pytest.raises(ValueError, match="differs"):
        rt.postprocess_config(cfg, {"frequency_unit": "GHz", "length_unit": "mm"})


@pytest.mark.parametrize("wrong_project", [False, True])
def test_session_only_closes_owned_project_and_recorded_pid(cfg, tmp_path, monkeypatch, wrong_project):
    import cst_optimization.core.connection as connection_module
    calls = []
    path = tmp_path / "owned.cst"

    class Project:
        filename = str(tmp_path / "unexpected.cst" if wrong_project else path)
        def activate(self): calls.append("activate")
        def close(self, *, save): calls.append(("project_close", save))

    class Connection:
        pid = 12345
        def __init__(self, **kwargs): calls.append(("connection", kwargs))
        def connect(self): calls.append("connect")
        def open_project(self, value): calls.append(("open", value)); return Project()
        def close(self, *args, **kwargs): pytest.fail("Generic/global cleanup is forbidden")
        def close_targeted(self, **kwargs): calls.append(("targeted", kwargs)); return {"success": True}

    monkeypatch.setattr(connection_module, "CSTConnection", Connection)
    monkeypatch.setattr(rt, "query_pid", lambda _: "absent")
    obj = evaluator(cfg)
    if wrong_project:
        with pytest.raises(rt.EvaluationFailure, match="unexpected"):
            with obj._project(path, tmp_path, "test"):
                pytest.fail("Unexpected CST project must not be exposed")
    else:
        with obj._project(path, tmp_path, "test"):
            calls.append("body")
    assert ("connection", {"library_path": "configured-library", "mode": "new"}) in calls
    assert ("project_close", False) in calls
    assert ("targeted", {"pid_override": 12345}) in calls


@pytest.mark.parametrize("stage", ["before_solver", "after_solver"])
def test_save_failure_never_produces_solved_evidence(cfg, tmp_path, monkeypatch, stage):
    import cst_optimization.core.solver as solver_module
    obj = evaluator(cfg)
    path = tmp_path / "candidate.cst"
    path.write_bytes(b"project")
    calls = []

    class Project:
        def execute_vba(self, *args, **kwargs): calls.append("settings")
        def save(self, *, include_results):
            calls.append(("save", include_results))
            return include_results is False and stage == "after_solver"
        def get_messages(self): return "Eigenmode solver successful" if "solve" in calls else ""

    @contextmanager
    def project(*args): yield Project()

    class Runner:
        def __init__(self, **kwargs): pass
        def run(self, project): calls.append("solve"); return SolverResult(True)

    monkeypatch.setattr(obj, "_project", project)
    monkeypatch.setattr(solver_module, "SolverRunner", Runner)
    def reserve(_): calls.append("reserve"); return 1
    with pytest.raises(rt.EvaluationFailure, match="save|saved") as error:
        obj._solve(path, tmp_path, 6, reserve)
    assert error.value.category == "save_failed"
    assert not (tmp_path / "solved.json").exists()
    assert ("reserve" in calls) == (stage == "after_solver")
    if stage == "after_solver":
        assert calls.index("reserve") < calls.index("solve")


def evaluation_harness(cfg, monkeypatch, *, cover_at=6, transient_failures=0):
    obj = evaluator(cfg)
    events = []
    state = {"count": 0, "failures": transient_failures}

    def prepare(parameters, directory):
        events.append(("prepare", directory.name))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "project").mkdir()
        path = directory / "project/candidate.cst"
        path.write_bytes(b"fresh candidate")
        return path

    def solve(path, directory, count, reserve):
        events.append(("solve", count))
        reserve(str(directory))
        if state["failures"]:
            state["failures"] -= 1
            raise rt.EvaluationFailure("RPC connection lost", "com", transient=True)
        state["count"] = count
        rt.atomic_json(directory / "solved.json", {"project_sha256": rt.digest(path), "mode_count": count})

    def modes(path, pp):
        count = state["count"]
        step = 40 / count if count >= cover_at else 10 / count
        return [NativeMode(i, (1030 + i * step) * 1e6, 100) for i in range(1, count + 1)]

    @contextmanager
    def project(*args): yield object()

    processed = SimpleNamespace(quality_ok=True, worst_impedance_ohm_per_m=90000.,
                                to_dict=lambda: {"quality_ok": True, "modes": []})
    monkeypatch.setattr(obj, "_prepare", prepare)
    monkeypatch.setattr(obj, "_solve", solve)
    monkeypatch.setattr(obj, "_project", project)
    monkeypatch.setattr(rt, "read_native_modes", modes)
    monkeypatch.setattr(rt, "collect_and_analyze", lambda *args, **kwargs: processed)
    return obj, events, state


def test_coverage_doubles_mode_count_using_fresh_copies_and_budget(cfg, tmp_path, monkeypatch):
    obj, events, _ = evaluation_harness(cfg, monkeypatch, cover_at=24)
    reservations = []
    result = obj({"x": 1.}, tmp_path / "evaluation", lambda attempt: reservations.append(attempt))
    assert result["status"] == "valid"
    assert [value for kind, value in events if kind == "solve"] == [6, 12, 24]
    assert len(set(reservations)) == 3


def test_coverage_cap_rejects_incomplete_results(cfg, tmp_path, monkeypatch):
    obj, events, _ = evaluation_harness(cfg, monkeypatch, cover_at=48)
    result = obj({"x": 1.}, tmp_path / "evaluation", lambda _: 1)
    assert result["status"] == "coverage_failed"
    assert [value for kind, value in events if kind == "solve"] == [6, 12, 24]


@pytest.mark.parametrize("failures,expected", [(1, "valid"), (2, "com")])
def test_transient_retry_is_bounded_and_uses_fresh_copy(cfg, tmp_path, monkeypatch, failures, expected):
    obj, events, _ = evaluation_harness(cfg, monkeypatch, transient_failures=failures)
    result = obj({"x": 1.}, tmp_path / "evaluation", lambda _: 1)
    assert result["status"] == expected
    assert [value for kind, value in events if kind == "prepare"] == ["attempt_000", "attempt_001"]


def test_postprocessing_resume_never_repeats_saved_solve(cfg, tmp_path, monkeypatch):
    obj, events, _ = evaluation_harness(cfg, monkeypatch)
    good = rt.collect_and_analyze
    monkeypatch.setattr(rt, "collect_and_analyze", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("field export failed")))
    directory = tmp_path / "evaluation"
    result = obj({"x": 1.}, directory, lambda _: 1)
    assert result["status"] == "postprocess_failed"
    monkeypatch.setattr(rt, "collect_and_analyze", good)
    result = obj({"x": 1.}, directory, lambda _: pytest.fail("Saved solve must not consume budget again"))
    assert result["status"] == "valid"
    assert sum(kind == "solve" for kind, _ in events) == 1


def test_complete_result_replay_does_not_spend_another_solve(cfg, tmp_path, monkeypatch):
    obj, events, _ = evaluation_harness(cfg, monkeypatch)
    directory = tmp_path / "evaluation"
    first = obj({"x": 1.}, directory, lambda _: 1)
    replay = obj({"x": 1.}, directory, lambda _: pytest.fail("Completed result must replay after journal-commit crash"))
    assert replay == first
    assert sum(kind == "solve" for kind, _ in events) == 1


def test_crash_after_solved_marker_recovers_without_second_solve(cfg, tmp_path, monkeypatch):
    obj, events, _ = evaluation_harness(cfg, monkeypatch)
    directory = tmp_path / "evaluation"
    original_write = rt.atomic_json
    crashed = False

    def crash_before_phase_update(path, value):
        nonlocal crashed
        if path.name == "evaluation.json" and value.get("phase") == "solved" and not crashed:
            crashed = True
            raise KeyboardInterrupt()
        return original_write(path, value)

    monkeypatch.setattr(rt, "atomic_json", crash_before_phase_update)
    with pytest.raises(KeyboardInterrupt):
        obj({"x": 1.}, directory, lambda _: 1)
    monkeypatch.setattr(rt, "atomic_json", original_write)
    result = obj({"x": 1.}, directory, lambda _: pytest.fail("Existing solved.json is reusable after phase-write crash"))
    assert result["status"] == "valid"
    assert sum(kind == "solve" for kind, _ in events) == 1


def test_saved_project_tamper_cannot_replay_success(cfg, tmp_path, monkeypatch):
    obj, events, _ = evaluation_harness(cfg, monkeypatch)
    directory = tmp_path / "evaluation"
    first = obj({"x": 1.}, directory, lambda _: 1)
    Path(first["project"]).write_bytes(b"different project")
    with pytest.raises(ValueError, match="fingerprint"):
        obj({"x": 1.}, directory, lambda _: pytest.fail("Tamper must not silently trigger another solve"))
    assert sum(kind == "solve" for kind, _ in events) == 1


def test_geometry_rebuild_failure_stops_before_solve(cfg, tmp_path, monkeypatch):
    obj = evaluator(cfg)
    @contextmanager
    def project(*args):
        yield SimpleNamespace(update_parameters=lambda *a, **kw: False,
                              save=lambda **kw: pytest.fail("Failed geometry must not be saved"))
    monkeypatch.setattr(obj, "_project", project)
    monkeypatch.setattr(rt, "copy_verified_project", lambda *a: (tmp_path / "candidate.cst", {}))
    parameters = {p.name: (p.lower + p.upper) / 2 for p in cfg.parameters}
    with pytest.raises(rt.EvaluationFailure) as error:
        obj._prepare(parameters, tmp_path)
    assert error.value.category == "geometry_failed"


def test_stale_success_messages_do_not_certify_current_solver(cfg, tmp_path, monkeypatch):
    import cst_optimization.core.solver as solver_module
    obj = evaluator(cfg)
    path = tmp_path / "candidate.cst"
    path.write_bytes(b"project")
    @contextmanager
    def project(*args):
        yield SimpleNamespace(execute_vba=lambda *a, **kw: None, save=lambda **kw: True,
                              get_messages=lambda: "Eigenmode solver successful")
    monkeypatch.setattr(obj, "_project", project)
    monkeypatch.setattr(solver_module, "SolverRunner", lambda **kw: SimpleNamespace(run=lambda _: SolverResult(True)))
    with pytest.raises(rt.EvaluationFailure, match="successful evidence"):
        obj._solve(path, tmp_path, 6, lambda _: 1)
    assert not (tmp_path / "solved.json").exists()


def test_raw_rpc_setup_exception_retries_one_fresh_copy(cfg, tmp_path, monkeypatch):
    obj, events, _ = evaluation_harness(cfg, monkeypatch)
    original_solve = obj._solve
    calls = 0
    def solve(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("RPC server disconnected during solver setup")
        return original_solve(*args)
    monkeypatch.setattr(obj, "_solve", solve)
    result = obj({"x": 1.}, tmp_path / "evaluation", lambda _: 1)
    assert result["status"] == "valid"
    assert calls == 2
    assert [value for kind, value in events if kind == "prepare"] == ["attempt_000", "attempt_001"]


def test_postprocess_cleanup_failure_is_fatal_not_retryable_field_export(cfg, tmp_path, monkeypatch):
    obj, _, _ = evaluation_harness(cfg, monkeypatch)
    @contextmanager
    def project(*args):
        yield object()
        raise rt.EvaluationFailure("Owned CST process remains alive", "cleanup_failed")
    monkeypatch.setattr(obj, "_project", project)
    result = obj({"x": 1.}, tmp_path / "evaluation", lambda _: 1)
    assert result["status"] == "cleanup_failed"
    assert result["worst"] is None
