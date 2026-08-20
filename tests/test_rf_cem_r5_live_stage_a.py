"""No-CST safety tests for the explicitly authorized R5 Stage A entry."""

from __future__ import annotations

from pathlib import Path

import pytest

from rf_cem.history_templates import CstHistoryTemplates
from rf_cem.live_r5_stage_a import (
    _field_inventory,
    _graceful_close_without_kill,
    nominal_controls,
    select_nominal_templates,
)


pytestmark = pytest.mark.no_cst


def _templates() -> CstHistoryTemplates:
    return CstHistoryTemplates(
        source="fixture/ModelHistory.json",
        recipe={"solver": {"type": "eigenmode", "settings": {}}},
        units_block="With Units\nEnd With",
        boundary_block="With Boundary\nEnd With",
        frequency_range_block='Solver.FrequencyRange "498", "530"',
        solver_blocks=(
            'ChangeSolverType "HF Eigenmode"',
            'With EigenmodeSolver\n .SetMeshType "Tetrahedral Mesh"\n .SetOrderTet "2"\nEnd With',
            'With Solver\n .AKSMinimumPasses "2"\nEnd With',
            (
                'With EigenmodeSolver\n .SetMeshType "Tetrahedral Mesh"\n'
                ' .SetNumberOfModes "1"\n .SetAccuracy "1e-12"\n'
                ' .SetOrderTet "3"\nEnd With'
            ),
            (
                'With Solver\n .AKSMaximumDF "0.001"\n'
                ' .AKSMinimumPasses "3"\n .AKSMaximumPasses "6"\n'
                ' .AKSMeshIncrement "5"\nEnd With'
            ),
        ),
        source_history_indices={
            "units": [2],
            "boundary": [44],
            "frequency_range": [46],
            "solver": [1, 47, 48, 49, 51],
            "monitors": [],
            "postprocessing": [],
            "result_templates": [],
            "result_exports": [],
        },
    )


def test_nominal_selection_uses_only_recorded_final_blocks() -> None:
    selected = select_nominal_templates(_templates())

    assert selected.source_history_indices["solver"] == [1, 49, 51]
    assert len(selected.solver_blocks) == 3
    assert 'SetOrderTet "2"' not in "\n".join(selected.solver_blocks)
    assert nominal_controls(selected) == {
        "solver_type": "HF Eigenmode",
        "mesh_type": "Tetrahedral Mesh",
        "number_of_modes": "1",
        "order_tet": "3",
        "accuracy": "1e-12",
        "maximum_df": "0.001",
        "minimum_passes": "3",
        "maximum_passes": "6",
        "mesh_increment": "5",
        "frequency_range": {"minimum": "498", "maximum": "530", "unit": "MHz"},
        "length_unit": "mm",
        "history_indices": [1, 49, 51],
    }


def test_nominal_selection_rejects_changed_history() -> None:
    templates = _templates()
    templates.source_history_indices["solver"] = [1, 47, 48, 49, 50]

    with pytest.raises(ValueError, match="missing"):
        select_nominal_templates(templates)


def test_graceful_close_never_calls_force_cleanup() -> None:
    class FakeDE:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeConnection:
        def __init__(self) -> None:
            self._de = FakeDE()
            self.pid = 123

        @property
        def design_environment(self):
            return self._de

    connection = FakeConnection()
    de = connection.design_environment

    report = _graceful_close_without_kill(connection)  # type: ignore[arg-type]

    assert de.closed is True
    assert connection._de is None
    assert report["status"] == "closed"
    assert report["force_kill_attempted"] is False
    assert report["global_sweep_attempted"] is False


def test_field_inventory_hashes_only_materialized_files(tmp_path: Path) -> None:
    fields = tmp_path / "fields"
    fields.mkdir()
    (fields / "e_field.txt").write_text("1 2 3\n", encoding="utf-8")

    inventory = _field_inventory(fields, tmp_path)

    assert len(inventory) == 1
    assert inventory[0]["path"] == "fields/e_field.txt"
    assert inventory[0]["size_bytes"] == (fields / "e_field.txt").stat().st_size
    assert len(inventory[0]["raw_sha256"]) == 64
