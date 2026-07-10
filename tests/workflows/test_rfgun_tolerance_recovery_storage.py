from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cst_optimization.evaluation.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    ParameterIdentity,
    RawEvaluationPayload,
)
from cst_optimization.evaluation.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
)
from workflows.rfgun_tolerance.runner import ToleranceSampler


def _record(value: float, status: str) -> EvaluationDatabaseRecord:
    return EvaluationDatabaseRecord(
        parameter_identity=ParameterIdentity(
            param_names=["x"],
            values=[value],
        ),
        status=status,
        raw_payload=RawEvaluationPayload(
            raw_metrics={"resonant_freq": 11.424},
        ),
        source="test",
    )


def test_replace_final_record_is_atomic_on_validation_failure(
    tmp_path: Path,
) -> None:
    database = SQLiteEvaluationDatabase(
        EvaluationDatabaseConfig(
            path=str(tmp_path / "evaluations.db"),
            enabled=True,
        )
    )
    database.open()
    try:
        old_row_id = database.insert_final_record(_record(1.0, "solver_failed"))
        invalid = _record(1.0, "success")
        invalid.parameter_identity = None

        with pytest.raises(ValueError):
            database.replace_final_record(old_row_id, invalid)

        rows = database.get_all_records()
        assert len(rows) == 1
        assert rows[0]["id"] == old_row_id
        assert rows[0]["status"] == "solver_failed"
    finally:
        database.close()


def test_replace_final_record_removes_old_row_after_success(
    tmp_path: Path,
) -> None:
    database = SQLiteEvaluationDatabase(
        EvaluationDatabaseConfig(
            path=str(tmp_path / "evaluations.db"),
            enabled=True,
        )
    )
    database.open()
    try:
        old_row_id = database.insert_final_record(_record(2.0, "solver_failed"))
        new_row_id = database.replace_final_record(
            old_row_id,
            _record(2.0, "success"),
        )

        rows = database.get_all_records()
        assert len(rows) == 1
        assert rows[0]["id"] == new_row_id
        assert rows[0]["status"] == "success"
        assert new_row_id != old_row_id
    finally:
        database.close()


def test_sampler_fills_only_missing_authoritative_record_count() -> None:
    sampler = ToleranceSampler.__new__(ToleranceSampler)
    sampler._cfg = SimpleNamespace(
        max_samples=5,
        min_samples=0,
        batch_size=2,
        project_path="project.cst",
        db_path="evaluations.db",
    )
    sampler._param_names = ["x"]
    sampler._db = SimpleNamespace(
        get_all_records=lambda: [
            {"id": 1, "status": "success", "param_values": [1.0]},
            {"id": 2, "status": "success", "param_values": [2.0]},
            {"id": 3, "status": "solver_failed", "param_values": [3.0]},
        ]
    )
    calls: list[dict[str, object]] = []

    def evaluate(
        index: int,
        values: np.ndarray,
        recovery: bool = False,
        old_row_id: int | None = None,
    ) -> None:
        calls.append(
            {
                "index": index,
                "values": values.tolist(),
                "recovery": recovery,
                "old_row_id": old_row_id,
            }
        )

    sampler._evaluate_one = evaluate
    sampler._sample_batch = lambda count: [
        np.array([10.0 + index]) for index in range(count)
    ]

    evaluated = sampler.run()

    assert evaluated == 3
    assert calls[0]["recovery"] is True
    assert calls[0]["old_row_id"] == 3
    assert [call["recovery"] for call in calls[1:]] == [False, False]
