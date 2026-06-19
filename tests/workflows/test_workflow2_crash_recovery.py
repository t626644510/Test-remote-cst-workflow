"""Focused no-CST regression tests for Workflow 2 crash recovery."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from cst_optimization.checkpoint import CheckpointManager
from cst_optimization.optimization.conditional_gate import (
    AdaptiveConditionalGate,
    GateConfig,
)
from workflows.rfgun_hom_antenna.orchestrator import DualProjectOrchestrator


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_gate_predict_handles_return_std_false_contract() -> None:
    gate = AdaptiveConditionalGate(GateConfig(), ["z_longitudinal"])
    gate._X = [
        np.array([0.0]),
        np.array([1.0]),
        np.array([2.0]),
    ]
    gp = MagicMock()
    gp.predict.return_value = np.array([0.25])
    gate._gps = [gp]

    assert gate.predict(np.array([1.5])) == {"z_longitudinal": 0.25}
    gp.predict.assert_called_once()
    assert gp.predict.call_args.kwargs["return_std"] is False


def test_phase_checkpoint_writes_physical_params_and_notifies(
    tmp_path,
    monkeypatch,
) -> None:
    orch = object.__new__(DualProjectOrchestrator)
    orch._curves_db_dir = str(tmp_path)
    orch._params = SimpleNamespace(names=["angle_deg", "height_mm"])
    orch._phase_checkpoint_callback = MagicMock()

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
    assert record["schema_version"] == 2
    assert record["params"] == {"angle_deg": 75.0, "height_mm": 12.5}
    assert record["solver_ok"] is True
    assert record["has_f2f"] is True
    assert record["has_f2w"] is True
    assert record["has_f2wo"] is False
    assert npz_path.endswith("eval_0007_wakefield.npz")
    with np.load(npz_path, allow_pickle=True) as saved:
        np.testing.assert_allclose(saved["base_marker"], [9.0])
    orch._phase_checkpoint_callback.assert_called_once()


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
