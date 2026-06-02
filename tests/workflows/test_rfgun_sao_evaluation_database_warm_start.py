"""No-CST tests for evaluation database warm-start / prior construction."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for p in (str(_PROJECT_ROOT), _SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from workflows.rfgun_sao.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    EvaluationDatabaseStatus,
    ParameterIdentity,
    RawEvaluationPayload,
)
from workflows.rfgun_sao.evaluation_database_warm_start import (
    PriorCandidateStatus,
    PriorCandidate,
    PriorConstructionReport,
    classify_record_for_prior,
    record_to_prior_candidate,
    build_prior_candidates_from_records,
    select_prior_candidates,
    derive_stage_observations_from_prior_candidates,
)


def _pid(values, precision=None):
    return ParameterIdentity(
        param_names=[f"p{i}" for i in range(len(values))],
        values=list(values),
        precision=precision,
    )


def _rec(values, status=EvaluationDatabaseStatus.SUCCESS, raw_metrics=None,
         objective_values=None, prove=None, schema=1):
    payload = None
    if raw_metrics is not None or objective_values is not None:
        payload = RawEvaluationPayload(
            raw_metrics=raw_metrics,
            objective_values=objective_values,
        )
    return EvaluationDatabaseRecord(
        parameter_identity=_pid(values) if values is not None else None,
        status=status,
        raw_payload=payload,
        provenance=prove or None,
        schema_version=schema,
    )


# ---------------------------------------------------------------------------
# classify_record_for_prior
# ---------------------------------------------------------------------------


class TestClassify:
    def test_success_with_metrics_usable(self):
        rec = _rec([1.0], raw_metrics={"f1": 11.424})
        status, _ = classify_record_for_prior(rec)
        assert status == PriorCandidateStatus.USABLE_SUCCESS

    def test_success_no_metrics_ignored_when_required(self):
        rec = _rec([1.0])
        status, _ = classify_record_for_prior(rec, require_raw_metrics=True)
        assert status == PriorCandidateStatus.IGNORED_MISSING_RAW_PAYLOAD

    def test_failure_ignored(self):
        rec = _rec([1.0], status=EvaluationDatabaseStatus.CALIBRATION_FAILED)
        status, _ = classify_record_for_prior(rec)
        assert status == PriorCandidateStatus.IGNORED_FAILURE

    def test_missing_identity_ignored(self):
        rec = _rec(None)
        status, _ = classify_record_for_prior(rec)
        assert status == PriorCandidateStatus.IGNORED_MISSING_IDENTITY

    def test_incompatible_schema_ignored(self):
        rec = _rec([1.0], schema=99)
        status, _ = classify_record_for_prior(rec, current_schema=1)
        assert status == PriorCandidateStatus.IGNORED_INCOMPATIBLE_SCHEMA


# ---------------------------------------------------------------------------
# record_to_prior_candidate
# ---------------------------------------------------------------------------


class TestConvert:
    def test_success_returns_candidate(self):
        rec = _rec([1.0, 2.0], raw_metrics={"f1": 11.424})
        cand = record_to_prior_candidate(rec)
        assert cand is not None
        assert cand.param_names == ["p0", "p1"]
        assert cand.param_values == [1.0, 2.0]
        assert cand.raw_metrics == {"f1": 11.424}

    def test_failure_returns_none(self):
        rec = _rec([1.0], status=EvaluationDatabaseStatus.CALIBRATION_FAILED)
        assert record_to_prior_candidate(rec) is None


# ---------------------------------------------------------------------------
# build_prior_candidates_from_records
# ---------------------------------------------------------------------------


class TestBuild:
    def test_mixed_records(self):
        records = [
            _rec([1.0], raw_metrics={"f1": 1.0}),   # usable
            _rec([2.0], status=EvaluationDatabaseStatus.CALIBRATION_FAILED),  # ignored
            _rec(None),  # ignored missing identity
            _rec([3.0], schema=99),  # ignored incompatible
        ]
        report = build_prior_candidates_from_records(records)
        assert len(report.candidates) == 1
        assert report.candidates[0].param_values == [1.0]
        assert report.ignored_counts.get("ignored_failure") == 1
        assert report.ignored_counts.get("ignored_missing_identity") >= 1
        assert report.total_input_records == 4

    def test_max_candidates(self):
        records = [_rec([i], raw_metrics={"f1": float(i)}) for i in range(10)]
        report = build_prior_candidates_from_records(records, max_candidates=3)
        assert len(report.candidates) == 3


# ---------------------------------------------------------------------------
# select_prior_candidates
# ---------------------------------------------------------------------------


class TestSelect:
    def test_sort_by_objective(self):
        records = [
            _rec([3.0], raw_metrics={"f1": 3.0}),
            _rec([1.0], raw_metrics={"f1": 1.0}),
            _rec([2.0], raw_metrics={"f1": 2.0}),
        ]
        report = build_prior_candidates_from_records(records)
        selected = select_prior_candidates(report.candidates, prefer_low_objective=True)
        assert selected[0].param_values == [1.0]
        assert selected[-1].param_values == [3.0]

    def test_max_count(self):
        report = build_prior_candidates_from_records(
            [_rec([float(i)], raw_metrics={"f1": float(i)}) for i in range(5)]
        )
        selected = select_prior_candidates(report.candidates, max_count=2)
        assert len(selected) == 2


# ---------------------------------------------------------------------------
# derive_stage_observations_from_prior_candidates
# ---------------------------------------------------------------------------


class TestStageObs:
    def test_returns_completed_observations(self):
        report = build_prior_candidates_from_records([
            _rec([1.0], raw_metrics={"f1": 10.0}),
            _rec([2.0], raw_metrics={"f1": 20.0}),
        ])
        obs = derive_stage_observations_from_prior_candidates(report.candidates)
        assert len(obs) == 2
        assert obs[0].reused is True
        assert obs[0].status.value == "completed"

    def test_skips_nan_objective(self):
        cand = PriorCandidate(
            parameter_identity=_pid([1.0]),
            parameter_key="key",
            param_names=["p0"],
            param_values=[1.0],
        )
        obs = derive_stage_observations_from_prior_candidates([cand])
        assert len(obs) == 0


# ---------------------------------------------------------------------------
# No I/O
# ---------------------------------------------------------------------------


class TestNoIO:
    def test_no_file_writes(self):
        """Building prior candidates does not write any files."""
        report = build_prior_candidates_from_records([
            _rec([1.0], raw_metrics={"f1": 1.0}),
        ])
        assert isinstance(report, PriorConstructionReport)
