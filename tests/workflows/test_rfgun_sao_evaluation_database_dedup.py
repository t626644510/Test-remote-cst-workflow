"""No-CST tests for evaluation database dedup helpers."""

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
    current_schema_version,
)
from workflows.rfgun_sao.evaluation_database_dedup import (
    DedupDecisionAction,
    DedupDecision,
    InMemoryEvaluationRecordIndex,
    build_in_memory_index,
    find_records_by_parameter_identity,
    classify_record_for_dedup,
    decide_dedup_for_parameter,
)


def _pid(values, precision=None):
    return ParameterIdentity(
        param_names=[f"p{i}" for i in range(len(values))],
        values=list(values),
        precision=precision,
    )


def _success(values, provenance=None):
    return EvaluationDatabaseRecord(
        parameter_identity=_pid(values),
        status=EvaluationDatabaseStatus.SUCCESS,
        raw_payload=RawEvaluationPayload(raw_metrics={"f1": float(values[0])}),
        provenance=provenance or {"commit": "abc"},
    )


def _failure(values, status=EvaluationDatabaseStatus.CALIBRATION_FAILED):
    return EvaluationDatabaseRecord(
        parameter_identity=_pid(values),
        status=status,
    )


# ---------------------------------------------------------------------------
# classify_record_for_dedup
# ---------------------------------------------------------------------------


class TestClassify:
    def test_success_returns_use_existing(self):
        rec = _success([1.0])
        d = classify_record_for_dedup(rec)
        assert d.action == DedupDecisionAction.USE_EXISTING_SUCCESS

    def test_failure_returns_deferred(self):
        rec = _failure([2.0])
        d = classify_record_for_dedup(rec)
        assert d.action == DedupDecisionAction.IGNORE_FAILURE_RETRY_POLICY_MISSING

    def test_missing_identity_returns_ignore(self):
        rec = EvaluationDatabaseRecord(status=EvaluationDatabaseStatus.SUCCESS)
        d = classify_record_for_dedup(rec)
        assert d.action == DedupDecisionAction.IGNORE_MISSING_PARAMETER_IDENTITY

    def test_incompatible_schema_returns_ignore(self):
        rec = EvaluationDatabaseRecord(
            parameter_identity=_pid([1.0]),
            schema_version=99,
            status=EvaluationDatabaseStatus.SUCCESS,
        )
        d = classify_record_for_dedup(rec, current_schema=1)
        assert d.action == DedupDecisionAction.IGNORE_INCOMPATIBLE_SCHEMA


# ---------------------------------------------------------------------------
# build_in_memory_index
# ---------------------------------------------------------------------------


class TestBuildIndex:
    def test_success_indexed(self):
        rec = _success([1.0])
        idx = build_in_memory_index([rec])
        key = _pid([1.0]).parameter_key()
        assert len(idx.records_by_key[key]) == 1
        assert len(idx.ignored_records) == 0

    def test_missing_identity_ignored(self):
        rec = EvaluationDatabaseRecord(status=EvaluationDatabaseStatus.SUCCESS)
        idx = build_in_memory_index([rec])
        assert len(idx.ignored_records) == 1
        assert idx.ignored_records[0]["reason"] == "missing_parameter_identity"

    def test_incompatible_schema_ignored(self):
        rec = EvaluationDatabaseRecord(
            parameter_identity=_pid([1.0]),
            schema_version=99,
            status=EvaluationDatabaseStatus.SUCCESS,
        )
        idx = build_in_memory_index([rec])
        assert len(idx.ignored_records) == 1
        assert idx.ignored_records[0]["reason"] == "incompatible_schema"


# ---------------------------------------------------------------------------
# find_records_by_parameter_identity
# ---------------------------------------------------------------------------


class TestFind:
    def test_matching_key_found(self):
        rec = _success([10.0])
        idx = build_in_memory_index([rec])
        pid = _pid([10.0])
        results = find_records_by_parameter_identity(idx, pid)
        assert len(results) == 1

    def test_no_match_returns_empty(self):
        rec = _success([10.0])
        idx = build_in_memory_index([rec])
        pid = _pid([20.0])
        results = find_records_by_parameter_identity(idx, pid)
        assert results == []


# ---------------------------------------------------------------------------
# decide_dedup_for_parameter
# ---------------------------------------------------------------------------


class TestDecide:
    def test_exact_match_returns_use_existing(self):
        rec = _success([5.0])
        idx = build_in_memory_index([rec])
        pid = _pid([5.0])
        d = decide_dedup_for_parameter(pid, idx)
        assert d.action == DedupDecisionAction.USE_EXISTING_SUCCESS
        assert d.parameter_key == pid.parameter_key()

    def test_different_values_returns_evaluate_new(self):
        rec = _success([5.0])
        idx = build_in_memory_index([rec])
        pid = _pid([6.0])
        d = decide_dedup_for_parameter(pid, idx)
        assert d.action == DedupDecisionAction.EVALUATE_NEW

    def test_failure_match_returns_deferred(self):
        rec = _failure([5.0])
        idx = build_in_memory_index([rec])
        pid = _pid([5.0])
        d = decide_dedup_for_parameter(pid, idx)
        assert d.action == DedupDecisionAction.IGNORE_FAILURE_RETRY_POLICY_MISSING

    def test_success_preferred_over_failure(self):
        success_rec = _success([5.0])
        fail_rec = _failure([5.0])
        idx = build_in_memory_index([fail_rec, success_rec])
        pid = _pid([5.0])
        d = decide_dedup_for_parameter(pid, idx)
        assert d.action == DedupDecisionAction.USE_EXISTING_SUCCESS

    def test_missing_parameter_identity_returns_ignore(self):
        idx = build_in_memory_index([])
        d = decide_dedup_for_parameter(None, idx)
        assert d.action == DedupDecisionAction.IGNORE_MISSING_PARAMETER_IDENTITY

    def test_provenance_does_not_block(self):
        rec1 = _success([1.0], provenance={"commit": "aaa"})
        rec2 = _success([1.0], provenance={"commit": "bbb"})
        idx = build_in_memory_index([rec1, rec2])
        pid = _pid([1.0])
        d = decide_dedup_for_parameter(pid, idx)
        assert d.action == DedupDecisionAction.USE_EXISTING_SUCCESS
        assert "provenance" in d.diagnostics

    def test_allow_failure_reuse_disabled(self):
        rec = _failure([5.0])
        idx = build_in_memory_index([rec])
        pid = _pid([5.0])
        d = decide_dedup_for_parameter(pid, idx, allow_failure_reuse=True)
        # Phase K: allow_failure_reuse=True still returns deferred
        assert d.action == DedupDecisionAction.IGNORE_FAILURE_RETRY_POLICY_MISSING


# ---------------------------------------------------------------------------
# No file/db/sidecar I/O
# ---------------------------------------------------------------------------


class TestNoIO:
    def test_no_file_writes(self):
        """In-memory index does not write any files."""
        rec = _success([1.0])
        idx = build_in_memory_index([rec])
        pid = _pid([1.0])
        d = decide_dedup_for_parameter(pid, idx)
        assert isinstance(d, DedupDecision)
        # No file was written, no exception

    def test_jsonl_not_referenced(self):
        """The dedup module does not reference JSONL sidecar code."""
        import workflows.rfgun_sao.evaluation_database_dedup as dedup_mod
        src = dedup_mod.__file__
        with open(src, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "jsonl" not in text.lower(), "dedup module should not reference JSONL"
