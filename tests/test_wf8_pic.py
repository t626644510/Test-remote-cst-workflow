"""WF8 no-CST task, integration, missing-data and export regressions."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflows.pic_multipacting.model import Task, active_source_macro, analyze, logical_grid, tasks
from workflows.pic_multipacting.run import export_curves, load_curves, remove_case_work, verify_run
from workflows.pic_multipacting.dispatch import pending_keys, validate_groups

pytestmark = pytest.mark.no_cst


def curve(y, x=None, ylabel="Current / A"):
    y = np.asarray(y, float)
    return dict(x=np.arange(len(y), dtype=float) if x is None else np.asarray(x, float),
                y=y, xlabel="Time / ns", ylabel=ylabel)


def pair(name, inc, out):
    return {f"1D Results\\Collision Information\\Current\\{name}": curve(inc),
            f"1D Results\\Emission Information\\Current\\[SEE]\\{name}": curve(out)}


def test_grid_zero_aliases_and_endpoints():
    actual, logical = tasks(), logical_grid()
    keys = {t.key for t in actual}
    assert len(actual) == len(keys) == 861
    assert len(logical) == 1008
    assert sum(r["equivalent_reference"] for r in logical) == 147
    assert all(r["actual_key"] in keys for r in logical)
    assert {t.phase for t in actual} == set(range(0, 360, 45))
    assert {t.factor1 for t in actual} == {0, .2, .4, .6, .8, 1}
    assert sum(t.factor1 == 0 for t in actual) == 21


def test_switch_is_primary_source_only():
    macro = active_source_macro("particle20")
    assert macro.count('"True"') == 1
    assert macro.count('"False"') == 20
    assert '"particle20", "True"' in macro
    assert "[SEE]" not in macro
    with pytest.raises(ValueError):
        active_source_macro("other")


def test_charge_weighting_not_mean_of_ratios():
    curves = pair("a", np.ones(21), -np.ones(21) * 2)
    curves.update(pair("b", np.ones(21) * 3, -np.ones(21) * 1.5))
    result = analyze(curves, ["a", "b"])
    combined = next(r for r in result["rows"] if r["surface"] == "combined_paired_receivers"
                    and r["start_ns"] == 5 and r["requested_end_ns"] == 20)
    assert combined["sey"] == pytest.approx(.875)
    assert combined["incident_C"] == pytest.approx(60e-9, abs=1e-18)


def test_no_collision_not_zero_sey():
    h = "1D Results\\Collision Information\\Energy\\empty"
    result = analyze({h: dict(x=[0, 5], y=[0, 0])}, ["empty"])
    assert result["no_collision_samples"] == ["empty"]
    assert result["rows"] == []


def test_nested_component_result_path():
    c = pair("els\\component1\\solid1", np.ones(21), -.7 * np.ones(21))
    a = analyze(c, ["els/component1\\solid1"])
    assert not a["issues"]
    assert a["rows"][0]["sey"] == pytest.approx(.7)


def test_zero_secondary_evidence_and_missing_pair():
    c = pair("a", np.ones(21), np.zeros(21))
    c.pop("1D Results\\Emission Information\\Current\\[SEE]\\a")
    assert "a" in analyze(c, ["a"])["issues"]
    c["1D Results\\Emission Information\\Energy\\[SEE]\\a"] = dict(x=[0, 5], y=[0, 0])
    assert analyze(c, ["a"])["rows"][0]["sey"] == 0


def test_sign_nonmonotonic_and_early_end():
    c = pair("a", np.ones(13), -np.ones(13))
    a = analyze(c, ["a"])
    last = next(r for r in a["rows"] if r["start_ns"] == 5 and r["requested_end_ns"] == 20)
    assert last["end_ns"] == 12 and not last["window_complete"]
    # Actual CST endpoint is a numpy scalar below 20 ns; metadata must serialize.
    json.dumps(a, allow_nan=False)
    c["1D Results\\Collision Information\\Current\\a"]["x"][3] = 0
    assert "a" in analyze(c, ["a"])["issues"]
    assert "a" in analyze(pair("a", -np.ones(21), -np.ones(21)), ["a"])["issues"]


def test_single_source_and_particle_record():
    c = {"1D Results\\Emission Information\\Current\\[Sources]\\particle5": curve([-1, 0]),
         "1D Results\\Solver Statistics [PIC]\\Particle vs. Time": curve([1, 0], [0, 20], "Particles")}
    assert verify_run(c, Task("particle5", 1, 0)) == 20
    c["1D Results\\Emission Information\\Current\\[Sources]\\particle6"] = curve([-1, 0])
    with pytest.raises(ValueError, match="Wrong active"):
        verify_run(c, Task("particle5", 1, 0))


def test_lossless_export(tmp_path):
    class Item:
        xlabel, ylabel = "Time / ns", "Current / A"
        def get_xdata(self):
            return [0, .01, 20]
        def get_ydata(self):
            return [0, -1e-9, -.25]
    class Reader:
        def list_tree_items(self):
            return ["1D Results\\Emission Information\\Current\\[SEE]\\a", "irrelevant"]
        def get_result_item(self, *args):
            return Item()
    curves = export_curves(Reader(), tmp_path)
    loaded = load_curves(tmp_path)
    assert set(curves) == set(loaded)
    for p in curves:
        assert np.array_equal(curves[p]["y"], loaded[p]["y"])


def test_cleanup_restricted_to_working(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    with pytest.raises(ValueError):
        remove_case_work(tmp_path, template)
    working = tmp_path / "working"
    working.mkdir()
    remove_case_work(tmp_path, working)
    assert template.exists() and not working.exists()


def test_parallel_dedup_across_workers(tmp_path):
    validate_groups([list(range(8)), list(range(8, 16))])
    keys = [t.key for t in tasks()]
    record = tmp_path / "workers/worker2/cases" / keys[0] / "result.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"status":"failed"}')
    assert pending_keys(tmp_path, set(), 2) == keys[1:3]
    with pytest.raises(ValueError, match="nonoverlapping"):
        validate_groups([[0, 1], [1, 2]])


@pytest.mark.parametrize("stop_after_first", [False, True])
def test_idle_worker_queue_and_graceful_stop(tmp_path, monkeypatch, stop_after_first):
    import importlib
    d = importlib.import_module("workflows.pic_multipacting.dispatch")
    assigned = []

    class Child:
        def __init__(self, args, **kwargs):
            cfg = json.loads(Path(args[args.index("--config") + 1]).read_text())
            self.directory = Path(cfg["output"])
            self.key = args[-1]
            self.pid = 100 + len(assigned)
            self.ticks = 1 if self.directory.name == "worker1" else 6
            self.returncode = None
            assigned.append((self.directory.name, self.key))
            if stop_after_first:
                (tmp_path / "STOP").touch()

        def poll(self):
            if self.returncode is None:
                self.ticks -= 1
                if self.ticks <= 0:
                    record = self.directory / "cases" / self.key / "result.json"
                    record.parent.mkdir(parents=True, exist_ok=True)
                    record.write_text('{"status":"complete"}')
                    self.returncode = 0
            return self.returncode

        def wait(self):
            while self.poll() is None:
                pass
            return self.returncode

    monkeypatch.setattr(d.subprocess, "Popen", Child)
    monkeypatch.setattr(d.time, "sleep", lambda _: None)
    monkeypatch.setattr(d, "summarize", lambda _: None)
    monkeypatch.setattr(d, "plot_summary", lambda _: None)
    config = dict(output=str(tmp_path), template="fixture", field_project="field",
                  receivers=[], cpu_groups=[[0], [1]])
    selected = {t.key for t in tasks()[:6]}
    d.dispatch(config, selected, None)
    state = json.loads((tmp_path / "state.json").read_text())
    assert not (tmp_path / "RUNNING.json").exists()
    if stop_after_first:
        assert len(assigned) == 1
        assert state["status"] == "paused"
        assert state["remaining"] == 5
    else:
        assert {key for _, key in assigned} == selected
        assert len(assigned) == len(selected)
        assert sum(worker == "worker1" for worker, _ in assigned) > 3
        assert state["status"] == "complete"
        d.dispatch(config, selected, None)
        assert len(assigned) == 6  # Resume must not reassign an already completed key.


def test_affinity_guard_rejects_reused_root_pid(tmp_path, monkeypatch):
    from workflows.pic_multipacting import hardware
    class Process:
        pid = 123
        def __init__(self, born):
            self.born = born
        def create_time(self):
            return self.born
        def children(self):
            pytest.fail("Reused PID must not be traversed or pinned")
    monkeypatch.setattr(hardware.psutil, "Process", lambda _: Process(1))
    sampler = hardware.Sampler(123, None, [0])
    monkeypatch.setattr(hardware.psutil, "Process", lambda _: Process(2))
    sampler._run()
