"""Focused no-CST regression tests for Workflow 2 crash recovery."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from cst_optimization.checkpoint import CheckpointManager
from cst_optimization.core.retry import EvaluationRetryHandler, RetryConfig
from cst_optimization.core.solver import SolverResult
from cst_optimization.database import save_curves_npz
from cst_optimization.optimization.conditional_gate import (
    AdaptiveConditionalGate,
    GateConfig,
    GatePhase,
)
from workflows.rfgun_hom_antenna.orchestrator import (
    AttemptProjectManager,
    DualProjectOrchestrator,
    ProjectSpec,
)
from workflows.rfgun_hom_antenna.recovery import (
    build_recovery_seed,
    infer_checkpoint_source_iterations,
    parameter_hash,
)
from workflows.rfgun_hom_antenna.run import (
    _mark_recovery_retryable,
    _recovery_candidate_indices,
    _should_load_warmup,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _IdentityMode:
    def compute(self, value: float) -> float:
        return float(value)


class _CurveObjective:
    def __init__(
        self,
        name: str,
        tree_path: str,
        *,
        use_reference: bool = False,
    ) -> None:
        self.name = name
        self.tree_path = tree_path
        self.mode = _IdentityMode()
        self._reader_factory = None
        if use_reference:
            self._ref_reader_factory = None

    def raw_value(self) -> float:
        reader = self._reader_factory()
        _, values = reader.get_1d_result(self.tree_path)
        value = float(np.mean(values))
        if hasattr(self, "_ref_reader_factory"):
            ref_reader = self._ref_reader_factory()
            _, reference = ref_reader.get_1d_result("ParticleBeam1/Z")
            value += float(np.mean(reference))
        return value


def _curve(values: list[float]) -> dict[str, np.ndarray]:
    return {
        "xdata": np.arange(len(values), dtype=float),
        "ydata_real": np.asarray(values, dtype=float),
    }


def test_gate_predict_normalises_input_and_reads_mean_std_contract() -> None:
    gate = AdaptiveConditionalGate(GateConfig(), ["z_longitudinal"])
    gate._X = [
        np.array([0.0]),
        np.array([1.0]),
        np.array([2.0]),
    ]
    gate._Y = [
        np.array([0.1]),
        np.array([0.2]),
        np.array([0.3]),
    ]
    gate._x_min = np.array([0.0])
    gate._x_max = np.array([2.0])
    gate._models_dirty = False
    gp = MagicMock()
    gp.predict.return_value = (np.array([0.25]), np.array([0.05]))
    gate._gps = [gp]

    assert gate.predict(np.array([1.5])) == {"z_longitudinal": 0.25}
    gp.predict.assert_called_once()
    np.testing.assert_allclose(gp.predict.call_args.args[0], [[0.75]])
    assert gp.predict.call_args.kwargs["return_std"] is True


def test_phase_checkpoint_writes_physical_params_and_notifies(
    tmp_path,
    monkeypatch,
) -> None:
    orch = object.__new__(DualProjectOrchestrator)
    orch._curves_db_dir = str(tmp_path)
    orch._params = SimpleNamespace(names=["angle_deg", "height_mm"])
    orch._phase_checkpoint_callback = MagicMock()
    orch._objectives = []
    orch._obj_project_map = []
    orch._ref_project_map = []
    orch._spec_by_label = {
        "frequency_domain": SimpleNamespace(),
        "wakefield": SimpleNamespace(),
    }
    orch._specs = [
        SimpleNamespace(label="frequency_domain"),
        SimpleNamespace(label="wakefield"),
    ]
    orch.last_attempt = 1

    from cst_optimization.database import start_recording_session
    import cst_optimization.database as database

    start_recording_session()
    monkeypatch.setattr(
        database,
        "collect_curves",
        lambda: {
            "1D Results\\test": {
                "xdata": np.array([1.0, 2.0]),
                "ydata_real": np.array([3.0, 4.0]),
            }
        },
    )
    params = np.array([75.0, 12.5])
    base_npz = tmp_path / "prior_phase.npz"
    np.savez_compressed(base_npz, base_marker=np.array([9.0]))
    npz_path = orch._save_phase_npz(
        params,
        iteration=7,
        phase_label="wakefield",
        completed_phases=["f2f", "frequency_domain", "wakefield"],
        base_npz_path=str(base_npz),
    )

    record = json.loads(
        (tmp_path / "index.jsonl").read_text(encoding="utf-8").strip()
    )
    assert record["record_type"] == "phase"
    assert record["schema_version"] == 3
    assert record["params"] == {"angle_deg": 75.0, "height_mm": 12.5}
    assert record["attempt"] == 1
    assert record["params_hash"]
    assert record["postprocess_ok"] is True
    assert record["evaluation_ok"] is False
    assert record["solver_ok"] is True
    assert record["has_f2f"] is True
    assert record["has_f2w"] is True
    assert record["has_f2wo"] is False
    assert npz_path.endswith("eval_0007_a001_wakefield.npz")
    with np.load(npz_path, allow_pickle=True) as saved:
        np.testing.assert_allclose(saved["base_marker"], [9.0])
    orch._phase_checkpoint_callback.assert_called_once()


def test_v2_parameter_matching_maps_checkpoint_zero_to_iter_22() -> None:
    names = ["angle_deg", "height_mm"]
    checkpoint_values = [
        [float(index), float(index) + 0.5]
        for index in range(8)
    ]
    index_records = [
        {
            "schema_version": 2,
            "iter": 22 + index,
            "params": dict(zip(names, values)),
        }
        for index, values in enumerate(checkpoint_values)
        if index != 6
    ]

    mapping = infer_checkpoint_source_iterations(
        checkpoint_values,
        index_records,
        names,
    )

    assert mapping == {index: 22 + index for index in range(8)}


def test_recovery_seed_merges_same_params_but_does_not_claim_offset(
    tmp_path,
) -> None:
    curves_dir = tmp_path / "raw_curves"
    curves_dir.mkdir()
    f2f_file = curves_dir / "eval_0022_frequency_domain.npz"
    wake_file = curves_dir / "eval_0022_wakefield.npz"
    unrelated_file = curves_dir / "eval_0099_wakefield_offset.npz"
    save_curves_npz(
        str(f2f_file),
        {"S2": _curve([1.0, 2.0]), "S3": _curve([3.0, 4.0])},
    )
    save_curves_npz(
        str(wake_file),
        {"ParticleBeam1/Z": _curve([5.0, 6.0])},
    )
    save_curves_npz(
        str(unrelated_file),
        {
            "ParticleBeam2/X": _curve([7.0]),
            "ParticleBeam2/Y": _curve([8.0]),
        },
    )
    names = ["angle_deg", "height_mm"]
    target = [75.0, 12.5]
    other = [80.0, 15.0]
    records = [
        {
            "schema_version": 2,
            "iter": 22,
            "params": dict(zip(names, target)),
            "npz_file": f2f_file.name,
        },
        {
            "schema_version": 2,
            "iter": 22,
            "params": dict(zip(names, target)),
            "npz_file": wake_file.name,
        },
        {
            "schema_version": 2,
            "iter": 99,
            "params": dict(zip(names, other)),
            "npz_file": unrelated_file.name,
        },
    ]
    index_path = curves_dir / "index.jsonl"
    index_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    objectives = [
        _CurveObjective("antenna_s2", "S2"),
        _CurveObjective("antenna_s3", "S3"),
        _CurveObjective("z_longitudinal", "ParticleBeam1/Z"),
        _CurveObjective(
            "z_transverse",
            "ParticleBeam2/X",
            use_reference=True,
        ),
    ]

    seed = build_recovery_seed(
        index_path=index_path,
        curves_dir=curves_dir,
        parameter_names=names,
        parameter_values=target,
        objectives=objectives,
        obj_project_map=[
            "frequency_domain",
            "frequency_domain",
            "wakefield",
            "wakefield_offset",
        ],
        ref_project_map=["", "", "", "wakefield"],
        phase_order=[
            "frequency_domain",
            "wakefield",
            "wakefield_offset",
        ],
        output_iteration=30,
    )

    assert seed.source_iter == 22
    assert seed.recovered_phases == ["frequency_domain", "wakefield"]
    assert set(seed.objective_manifest) == {
        "antenna_s2",
        "antenna_s3",
        "z_longitudinal",
    }
    assert seed.replay_values == {
        "antenna_s2": 1.5,
        "antenna_s3": 3.5,
        "z_longitudinal": 5.5,
    }
    assert unrelated_file.resolve().as_posix() not in {
        Path(path).resolve().as_posix() for path in seed.source_files
    }
    with np.load(seed.npz_path, allow_pickle=True) as saved:
        assert not any("ParticleBeam2" in key for key in saved.files)


def test_attempt_allocation_never_reuses_existing_attempt(tmp_path) -> None:
    index_path = tmp_path / "index.jsonl"
    index_path.write_text(
        "\n".join(
            [
                json.dumps({"iter": 7, "attempt": 1}),
                json.dumps({"iter": 7, "attempt": 3}),
                json.dumps({"iter": 8, "attempt": 9}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    orch = object.__new__(DualProjectOrchestrator)
    orch._curves_db_dir = str(tmp_path)

    assert orch._allocate_attempt(7) == 4
    assert orch._allocate_attempt(9) == 1


def test_production_recovery_ignores_smoke_only_sources(tmp_path) -> None:
    npz_path = tmp_path / "smoke.npz"
    save_curves_npz(str(npz_path), {"S2": _curve([1.0])})
    index_path = tmp_path / "index.jsonl"
    index_path.write_text(
        json.dumps(
            {
                "iter": 1,
                "params": {"angle_deg": 75.0},
                "npz_file": npz_path.name,
                "smoke_only": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    objective = _CurveObjective("antenna", "S2")
    common = {
        "index_path": index_path,
        "curves_dir": tmp_path,
        "parameter_names": ["angle_deg"],
        "parameter_values": [75.0],
        "objectives": [objective],
        "obj_project_map": ["frequency_domain"],
        "ref_project_map": [""],
        "phase_order": ["frequency_domain"],
    }

    production = build_recovery_seed(**common, output_iteration=2)
    smoke = build_recovery_seed(
        **common,
        output_iteration=3,
        include_smoke_sources=True,
        smoke_only=True,
    )

    assert production.npz_path == ""
    assert smoke.recovered_phases == ["frequency_domain"]


def test_phase_aware_reset_only_cleans_requested_project(tmp_path) -> None:
    orch = object.__new__(DualProjectOrchestrator)
    orch._conn = SimpleNamespace(
        pid=None,
        close=MagicMock(),
    )
    orch._cooldown_s = 0.0
    orch._library_path = "fake"
    wake = SimpleNamespace(
        label="wakefield",
        cst_path=str(tmp_path / "wake.cst"),
        is_pre_filter=False,
    )
    offset = SimpleNamespace(
        label="wakefield_offset",
        cst_path=str(tmp_path / "offset.cst"),
        is_pre_filter=False,
    )
    orch._specs = [wake, offset]
    new_connection = MagicMock()
    new_connection.pid = 123

    with (
        patch(
            "cst_optimization.core.cleanup.kill_all_cst_processes"
        ),
        patch(
            "cst_optimization.core.cleanup.remove_result_folder"
        ) as remove_results,
        patch("cst_optimization.core.cleanup.remove_lock_file"),
        patch(
            "workflows.rfgun_hom_antenna.orchestrator.CSTConnection",
            return_value=new_connection,
        ),
    ):
        orch._reset_connection(cleanup_labels={"wakefield_offset"})

    remove_results.assert_called_once_with(offset.cst_path)


def test_attempt_project_manager_copies_template_per_attempt(tmp_path) -> None:
    template = tmp_path / "F2W.cst"
    template.write_bytes(b"template-cst")
    manager = AttemptProjectManager(
        mode="template_copy",
        workspace_dir=str(tmp_path / "copies"),
    )
    manager.begin_attempt(iteration=7, attempt=2)
    spec = ProjectSpec(cst_path=str(template), label="wakefield")

    working = Path(manager.project_path(spec))

    assert working.name == "F2W_working.cst"
    assert working.parts[-5:] == (
        "eval_0007",
        "attempt_002",
        "wakefield",
        "model",
        "F2W_working.cst",
    )
    assert working.read_bytes() == b"template-cst"
    assert manager.cleanup_path(spec) == str(working)
    assert manager.prepared_paths() == [str(working)]


def test_attempt_project_manager_direct_mode_keeps_config_path(tmp_path) -> None:
    project = tmp_path / "direct.cst"
    manager = AttemptProjectManager(mode="direct", workspace_dir=str(tmp_path))
    manager.begin_attempt(iteration=7, attempt=2)
    spec = ProjectSpec(cst_path=str(project), label="frequency_domain")

    assert manager.project_path(spec) == str(project)
    assert manager.cleanup_path(spec) == str(project)
    assert manager.prepared_paths() == []


def test_template_copy_phase_opens_working_copy_not_template(
    tmp_path,
) -> None:
    template = tmp_path / "F2F.cst"
    template.write_bytes(b"template-cst")
    manager = AttemptProjectManager(
        mode="template_copy",
        workspace_dir=str(tmp_path / "copies"),
    )
    manager.begin_attempt(iteration=3, attempt=1)
    spec = ProjectSpec(
        cst_path=str(template),
        label="frequency_domain",
        is_pre_filter=True,
    )
    opened_paths: list[str] = []

    def open_project(path: str):
        opened_paths.append(path)
        return SimpleNamespace(
            filename=path,
            update_parameters=lambda *args, **kwargs: True,
            save=MagicMock(),
        )

    orch = object.__new__(DualProjectOrchestrator)
    orch._conn = SimpleNamespace(open_project=open_project)
    orch._specs = [spec]
    orch._spec_by_label = {spec.label: spec}
    orch._project_paths = {}
    orch._project_file_manager = manager
    orch._pre_filter_enabled = False
    orch._solver = SimpleNamespace(
        run=lambda project: SolverResult(success=True, elapsed_s=1.0)
    )
    orch._msg = SimpleNamespace(
        capture=MagicMock(),
        clear=MagicMock(),
        has_history_failure=lambda: False,
        write=MagicMock(),
        write_now=MagicMock(),
    )

    with (
        patch(
            "cst_optimization.core.cleanup.remove_result_folder"
        ) as remove_results,
        patch("cst_optimization.core.cleanup.remove_lock_file"),
    ):
        ok = orch._execute_phase_1(
            params=np.array([1.0]),
            param_dict={"x": 1.0},
            iteration=3,
            opened={},
            completed_labels=set(),
            solver_errors=[],
            all_solvers_ok=True,
            _mk_reader=MagicMock(),
            _term_print=MagicMock(),
            n_obj=0,
            raw_values=np.array([]),
        )

    assert ok is True
    assert opened_paths
    assert opened_paths[0] != str(template)
    assert opened_paths[0].endswith("F2F_working.cst")
    remove_results.assert_called_once_with(opened_paths[0])


def test_template_copy_reset_cleans_working_copy_not_template(
    tmp_path,
) -> None:
    template = tmp_path / "offset.cst"
    template.write_bytes(b"template-cst")
    working = tmp_path / "copies" / "offset_working.cst"
    manager = AttemptProjectManager(
        mode="template_copy",
        workspace_dir=str(tmp_path / "copies"),
    )
    manager._current_paths = {"wakefield_offset": str(working)}

    orch = object.__new__(DualProjectOrchestrator)
    orch._conn = SimpleNamespace(pid=None, close=MagicMock())
    orch._cooldown_s = 0.0
    orch._library_path = "fake"
    orch._project_file_manager = manager
    orch._specs = [
        SimpleNamespace(
            label="wakefield_offset",
            cst_path=str(template),
            is_pre_filter=False,
        ),
    ]
    new_connection = MagicMock()
    new_connection.pid = 123

    with (
        patch("cst_optimization.core.cleanup.kill_all_cst_processes"),
        patch(
            "cst_optimization.core.cleanup.remove_result_folder"
        ) as remove_results,
        patch("cst_optimization.core.cleanup.remove_lock_file"),
        patch(
            "workflows.rfgun_hom_antenna.orchestrator.CSTConnection",
            return_value=new_connection,
        ),
    ):
        orch._reset_connection(cleanup_labels={"wakefield_offset"})

    remove_results.assert_called_once_with(str(working))


def test_retry_dynamic_result_paths_provider_overrides_static_paths(
    tmp_path,
) -> None:
    static = tmp_path / "template.cst"
    working = tmp_path / "work" / "copy.cst"
    handler = EvaluationRetryHandler(
        connection=SimpleNamespace(),
        project_path=str(static),
        library_path="fake",
        config=RetryConfig(),
        result_paths_provider=lambda: [str(working)],
    )

    with (
        patch(
            "cst_optimization.core.retry.remove_result_folder"
        ) as remove_results,
        patch("cst_optimization.core.retry.remove_lock_file") as remove_lock,
    ):
        handler._clean_all_result_folders()

    remove_results.assert_called_once_with(str(working))
    remove_lock.assert_called_once_with(str(working.parent))


def test_attempt_allocation_increments_without_index_record(tmp_path) -> None:
    orch = object.__new__(DualProjectOrchestrator)
    orch._curves_db_dir = str(tmp_path)
    orch._iteration_attempt_counts = {}

    assert orch._allocate_attempt(11) == 1
    assert orch._allocate_attempt(11) == 2


def test_attempt_allocation_skips_existing_template_copy_dirs(
    tmp_path,
) -> None:
    (tmp_path / "eval_0011" / "attempt_003").mkdir(parents=True)
    orch = object.__new__(DualProjectOrchestrator)
    orch._curves_db_dir = ""
    orch._iteration_attempt_counts = {}
    orch._project_file_manager = AttemptProjectManager(
        mode="template_copy",
        workspace_dir=str(tmp_path),
    )

    assert orch._allocate_attempt(11) == 4


def test_schema_v3_separates_solver_postprocess_and_evaluation_status(
    tmp_path,
) -> None:
    orch = object.__new__(DualProjectOrchestrator)
    orch._curves_db_dir = str(tmp_path)
    orch._params = SimpleNamespace(names=["angle_deg"])
    orch.last_attempt = 2
    orch._specs = [
        SimpleNamespace(label="frequency_domain", is_pre_filter=True),
    ]

    orch._write_evaluation_index(
        params=np.array([75.0]),
        iteration=31,
        completed_labels={"frequency_domain"},
        skipped_labels=set(),
        npz_path=str(tmp_path / "eval_0031_a002_frequency_domain.npz"),
        objective_manifest=["antenna"],
        solvers_ok=True,
        postprocess_ok=False,
        evaluation_ok=False,
        errors=["missing curve"],
        source_iter=27,
        smoke_only=True,
    )

    record = json.loads(
        (tmp_path / "index.jsonl").read_text(encoding="utf-8")
    )
    assert record["schema_version"] == 3
    assert record["params_hash"] == parameter_hash(["angle_deg"], [75.0])
    assert record["phase_manifest"] == ["frequency_domain"]
    assert record["phases_done"] == ["f2f", "frequency_domain"]
    assert record["solver_ok"] is True
    assert record["solvers_ok"] is True
    assert record["postprocess_ok"] is False
    assert record["evaluation_ok"] is False
    assert record["source_iter"] == 27
    assert record["smoke_only"] is True


def test_prefilter_reject_preserves_f2f_penalty_and_skips_conditionals(
    monkeypatch,
) -> None:
    orch = object.__new__(DualProjectOrchestrator)
    orch._curves_db_dir = ""
    orch._params = SimpleNamespace(
        names=["angle_deg"],
        to_dict=lambda values: {"angle_deg": float(values[0])},
    )
    antenna = _CurveObjective("antenna", "unused")
    conditional = _CurveObjective("z_longitudinal", "unused")
    orch._objectives = [antenna, conditional]
    orch._obj_project_map = ["frequency_domain", "wakefield"]
    orch._ref_project_map = ["", ""]
    f2f = SimpleNamespace(
        label="frequency_domain",
        is_pre_filter=True,
        condition_trigger="",
    )
    wake = SimpleNamespace(
        label="wakefield",
        is_pre_filter=False,
        condition_trigger="antenna",
    )
    orch._specs = [f2f, wake]
    orch._spec_by_label = {
        "frequency_domain": f2f,
        "wakefield": wake,
    }
    orch._project_paths = {"frequency_domain": "unused.cst"}
    orch._cooldown_s = 0.0
    orch._adaptive_gate = None
    orch._opt_logger = None
    orch._gate_predictions = None

    def fake_phase_one(
        params,
        param_dict,
        iteration,
        opened,
        completed_labels,
        solver_errors,
        all_solvers_ok,
        make_reader,
        term_print,
        n_obj,
        raw_values,
    ):
        completed_labels.add("frequency_domain")
        return False

    def fake_capture(
        project_label,
        project_path,
        raw_values,
        make_reader,
        ref_npz_path="",
    ):
        raw_values[0] = 0.25
        return []

    monkeypatch.setattr(orch, "_execute_phase_1", fake_phase_one)
    monkeypatch.setattr(orch, "_capture_project_objectives", fake_capture)
    monkeypatch.setattr("builtins.open", MagicMock())

    penalties = orch.execute(np.array([75.0]), iteration=9)

    np.testing.assert_allclose(penalties, [0.25, 1.0])
    assert orch.last_solvers_ok is True
    assert orch.last_postprocess_ok is True
    assert orch.last_evaluation_ok is True
    assert orch.last_skipped_labels == {"wakefield"}


def test_partial_checkpoint_is_not_a_zero_penalty_warm_start(tmp_path) -> None:
    ckpt = CheckpointManager(str(tmp_path / "workflow_2"))
    partial_idx = ckpt.add_pending(np.array([1.0, 2.0]))
    ckpt.mark_phase_done(partial_idx, ["f2f", "frequency_domain"])

    complete_idx = ckpt.add_pending(np.array([3.0, 4.0]))
    ckpt.mark_completed(
        complete_idx,
        raw_values={"a": 1.0},
        penalties={"a": 0.4},
    )

    X, y = ckpt.get_warm_xy()
    np.testing.assert_allclose(X, [[3.0, 4.0]])
    np.testing.assert_allclose(y, [0.4])


def test_checkpoint_warm_start_uses_normalised_named_weights(tmp_path) -> None:
    ckpt = CheckpointManager(str(tmp_path / "workflow_2"))
    idx = ckpt.add_pending(np.array([1.0, 2.0]))
    ckpt.mark_completed(
        idx,
        raw_values={"a": 1.0, "b": 2.0},
        penalties={"a": 0.2, "b": 0.8},
    )

    X, y = ckpt.get_warm_xy(["a", "b"], [1.0, 3.0])

    np.testing.assert_allclose(X, [[1.0, 2.0]])
    np.testing.assert_allclose(y, [0.65])


def test_gate_bootstrap_masks_skipped_targets_and_forces_two_calibrations(
    monkeypatch,
) -> None:
    gate = AdaptiveConditionalGate(
        GateConfig(calibration_evaluations=2),
        ["z_longitudinal", "z_transverse"],
        parameter_bounds=np.array([[0.0, 10.0]]),
    )
    monkeypatch.setattr(gate, "_rebuild_gps", MagicMock())

    gate.bootstrap(
        np.array([[1.0], [2.0], [3.0]]),
        np.array([[0.1, 0.2], [0.2, 1.0], [0.3, 0.4]]),
        np.array([[True, True], [True, False], [True, True]]),
        np.array([True, False, True]),
    )

    assert gate.phase.value == "warmup"
    assert np.isnan(gate._Y[1][1])

    full_mask = np.ones((3, 2), dtype=bool)
    gate.bootstrap(
        np.array([[1.0], [2.0], [3.0]]),
        np.array([[0.1, 0.2], [0.2, 0.3], [0.3, 0.4]]),
        full_mask,
        np.array([True, True, True]),
    )
    assert gate.phase.value == "gp_gated"
    assert gate.should_validate_next() is True
    # Historical rows may already exceed the old absolute transition count.
    # Two calibration samples alone must not jump directly to FULL_4OBJ.
    gate._eval_count = 22

    penalties = {"z_longitudinal": 0.2, "z_transverse": 0.3}
    measured = {"z_longitudinal": True, "z_transverse": True}
    gate.record_evaluation(
        np.array([4.0]),
        penalties,
        True,
        measured,
        was_validation=True,
        predicted=penalties,
    )
    assert gate.should_validate_next() is True
    gate.record_evaluation(
        np.array([5.0]),
        penalties,
        True,
        measured,
        was_validation=True,
        predicted=penalties,
    )
    assert gate._calibration_remaining == 0
    assert gate.phase is GatePhase.GP_GATED


def test_gate_only_skips_when_bad_prediction_is_confident() -> None:
    gate = AdaptiveConditionalGate(
        GateConfig(gp_skip_threshold=0.5, uncertainty_sigma=2.0),
        ["z_longitudinal", "z_transverse"],
    )
    gate.phase = GatePhase.GP_GATED

    assert gate.should_run_conditional(
        0.1,
        {"z_longitudinal": 0.8, "z_transverse": 0.2},
        {"z_longitudinal": 0.2, "z_transverse": 0.1},
    ) is True
    assert gate.should_run_conditional(
        0.1,
        {"z_longitudinal": 0.8, "z_transverse": 0.2},
        {"z_longitudinal": 0.05, "z_transverse": 0.1},
    ) is False


def test_orchestrator_validation_captures_prediction_before_force_run() -> None:
    orch = object.__new__(DualProjectOrchestrator)
    gate = MagicMock()
    gate.is_warmup = False
    gate.predict_with_uncertainty.return_value = (
        {"z_longitudinal": 0.2, "z_transverse": 0.3},
        {"z_longitudinal": 0.1, "z_transverse": 0.1},
    )
    gate.should_validate_next.return_value = True
    orch._adaptive_gate = gate
    orch._gate_predictions = None
    orch._gate_prediction_std = None
    orch._gate_validation_forced = False

    should_run, reason = orch._conditional_gate_decision(
        np.array([1.0]),
        0.2,
    )

    assert should_run is True
    assert "validate" in reason
    assert orch._gate_validation_forced is True
    assert orch._gate_predictions == {
        "z_longitudinal": 0.2,
        "z_transverse": 0.3,
    }


def test_orchestrator_uses_gate_sliding_db_threshold() -> None:
    orch = object.__new__(DualProjectOrchestrator)
    orch._pre_filter_threshold_db = -25.0
    orch._adaptive_gate = SimpleNamespace(pre_filter_db_threshold=-29.0)

    assert orch._active_pre_filter_threshold() == -29.0


def test_recovery_reopens_failed_permanent_and_keeps_failure_pending(
    tmp_path,
) -> None:
    ckpt = CheckpointManager(str(tmp_path / "workflow_2"))
    pending_idx = ckpt.add_pending(np.array([1.0]))
    failed_idx = ckpt.add_pending(np.array([2.0]))
    ckpt.mark_failed(
        failed_idx,
        error="prior process exhausted retries",
        tier_exhausted=True,
    )

    assert _recovery_candidate_indices(ckpt) == [pending_idx, failed_idx]

    _mark_recovery_retryable(
        ckpt,
        failed_idx,
        error="this process also failed",
        phases_done=["frequency_domain", "wakefield"],
    )

    record = ckpt.records[failed_idx]
    assert record.status == "pending"
    assert record.tier_exhausted is False
    assert record.error == "this process also failed"
    assert record.phases_done == ["frequency_domain", "wakefield"]


def test_recovery_only_defers_cleaned_warmup_loading() -> None:
    path = "D:/Results/wf2_warmup_cleaned/index.cleaned.jsonl"

    assert _should_load_warmup(path, recovery_only=False) is True
    assert _should_load_warmup(path, recovery_only=True) is False
    assert _should_load_warmup("", recovery_only=False) is False


def test_scheduler_uses_supported_recurring_trigger_contract() -> None:
    content = (
        _PROJECT_ROOT / "scripts" / "schedule_workflow2.ps1"
    ).read_text(encoding="utf-8")

    assert "-Daily" not in content
    assert "-RepetitionInterval" in content
    assert "-RepetitionDuration" in content
    assert "--warmup-from-db" in content
    assert "index.cleaned.jsonl" in content


def test_watchdog_resolves_heartbeat_from_runtime_config() -> None:
    content = (
        _PROJECT_ROOT / "scripts" / "watchdog.ps1"
    ).read_text(encoding="utf-8")

    assert "workflows\\rfgun_hom_antenna\\config.yaml" in content
    assert 'logging_cfg.get("output_dir"' in content
    assert 'Join-Path $WorkDir "Results\\workflow_2_heartbeat.txt"' not in content
    assert "--warmup-from-db" in content
    assert "index.cleaned.jsonl" in content
