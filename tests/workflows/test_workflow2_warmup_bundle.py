"""No-CST tests for Workflow 2 consolidated warm-start bundles."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from cst_optimization.database import save_curves_npz
from workflows.rfgun_hom_antenna.warmup import (
    build_total_warmup_bundle,
    load_workflow2_warmup,
)


class _IdentityMode:
    def compute(self, value: float) -> float:
        return float(value)


class _CurveObjective:
    def __init__(self, name: str, tree_path: str) -> None:
        self.name = name
        self.tree_path = tree_path
        self.mode = _IdentityMode()
        self._reader_factory = None

    def raw_value(self) -> float:
        _, values = self._reader_factory().get_1d_result(self.tree_path)
        return float(np.mean(values))


def _curves(**values: float) -> dict[str, dict[str, np.ndarray]]:
    return {
        name: {
            "xdata": np.array([0.0, 1.0]),
            "ydata_real": np.array([value, value]),
        }
        for name, value in values.items()
    }


def _write_index(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_total_bundle_deduplicates_and_keeps_intentional_partial_row(
    tmp_path,
) -> None:
    cleaned = tmp_path / "cleaned"
    recovery = tmp_path / "raw"
    cleaned.mkdir()
    recovery.mkdir()
    save_curves_npz(
        str(cleaned / "clean.npz"),
        _curves(Longitudinal=0.2, Transverse=0.4),
    )
    save_curves_npz(
        str(recovery / "retry_failed.npz"),
        _curves(Longitudinal=0.9),
    )
    save_curves_npz(
        str(recovery / "duplicate_success.npz"),
        _curves(Longitudinal=0.2, Transverse=0.4),
    )
    save_curves_npz(
        str(recovery / "partial_success.npz"),
        _curves(Longitudinal=0.3),
    )

    cleaned_index = cleaned / "index.cleaned.jsonl"
    recovery_index = recovery / "index.jsonl"
    _write_index(
        cleaned_index,
        [
            {
                "record_type": "evaluation",
                "iter": 1,
                "params": {"p": 1.0},
                "npz_file": "clean.npz",
                "solver_ok": True,
                "has_f2w": True,
                "has_f2wo": True,
            }
        ],
    )
    _write_index(
        recovery_index,
        [
            {
                "record_type": "evaluation",
                "schema_version": 3,
                "iter": 31,
                "attempt": 1,
                "params": {"p": 1.0},
                "npz_file": "retry_failed.npz",
                "solver_ok": False,
                "evaluation_ok": False,
            },
            {
                "record_type": "evaluation",
                "schema_version": 3,
                "iter": 31,
                "attempt": 2,
                "params": {"p": 1.0},
                "npz_file": "duplicate_success.npz",
                "solver_ok": True,
                "evaluation_ok": True,
                "phase_manifest": ["wakefield", "wakefield_offset"],
                "has_f2w": True,
                "has_f2wo": True,
            },
            {
                "record_type": "evaluation",
                "schema_version": 3,
                "iter": 32,
                "attempt": 1,
                "params": {"p": 2.0},
                "npz_file": "partial_success.npz",
                "solver_ok": True,
                "evaluation_ok": True,
                "phase_manifest": ["wakefield"],
                "skipped_phases": ["wakefield_offset"],
                "has_f2w": True,
                "has_f2wo": False,
            },
        ],
    )

    objectives = [
        _CurveObjective("z_longitudinal", "Longitudinal"),
        _CurveObjective("z_transverse", "Transverse"),
    ]
    output = tmp_path / "total"
    built = build_total_warmup_bundle(
        cleaned_index,
        recovery_index,
        output,
        objectives,
        weights=[1.0, 1.0],
        parameter_names=["p"],
    )

    assert built.n_scalar == 2
    assert built.n_full_measurements == 1
    assert built.measured_count("z_longitudinal") == 2
    assert built.measured_count("z_transverse") == 1
    np.testing.assert_allclose(built.X[:, 0], [1.0, 2.0])
    np.testing.assert_allclose(built.scalar_penalties, [0.3, 0.65])
    assert len(list(output.glob("eval_total_*.npz"))) == 2
    assert "retry_failed.npz" not in (output / "index.total.jsonl").read_text(
        encoding="utf-8"
    )

    reloaded = load_workflow2_warmup(
        output / "index.total.jsonl",
        objectives,
        weights=[1.0, 1.0],
        parameter_names=["p"],
    )
    np.testing.assert_allclose(
        reloaded.scalar_penalties,
        built.scalar_penalties,
    )
    assert reloaded.measurement_mask.tolist() == [
        [True, True],
        [True, False],
    ]
