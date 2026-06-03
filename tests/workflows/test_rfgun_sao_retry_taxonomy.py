"""No-CST tests for retry taxonomy helpers."""

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
from workflows.rfgun_sao.retry_taxonomy import (
    RetryFailureClass,
    RetryEligibilityAction,
    RetryTier,
    RetryPolicy,
    RetryClassification,
    is_diagnostic_only_record,
    classify_failure_record,
    classify_retry_eligibility,
    suggest_next_retry_tier,
    should_escalate_to_probably_infeasible,
    summarize_retry_classifications,
)


def _pid(values):
    return ParameterIdentity(
        param_names=[f"p{i}" for i in range(len(values))],
        values=list(values),
    )


def _rec(values, status="success", retries=0, schema=1, error_tax=None):
    rec = EvaluationDatabaseRecord(
        parameter_identity=_pid(values) if values is not None else None,
        status=status,
        retry_count=retries,
        schema_version=schema,
    )
    if error_tax is not None:
        rec.error_taxonomy = error_tax
    return rec


# ---------------------------------------------------------------------------
# classify_failure_record
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    def test_success(self):
        r = _rec([1.0], status="success")
        assert classify_failure_record(r) == RetryFailureClass.SUCCESS

    def test_gate_rejected(self):
        r = _rec([1.0], status="gate_rejected")
        assert classify_failure_record(r) == RetryFailureClass.GATE_REJECTED

    def test_calibration_failed(self):
        r = _rec([1.0], status="calibration_failed")
        assert classify_failure_record(r) == RetryFailureClass.CALIBRATION_FAILED

    def test_solver_failed(self):
        r = _rec([1.0], status="solver_failed")
        assert classify_failure_record(r) == RetryFailureClass.SOLVER_FAILED

    def test_transient_failed(self):
        r = _rec([1.0], status="transient_failed")
        assert classify_failure_record(r) == RetryFailureClass.TRANSIENT_FAILED

    def test_unknown_failed(self):
        r = _rec([1.0], status="unknown_failed")
        assert classify_failure_record(r) == RetryFailureClass.UNKNOWN_FAILED

    def test_diagnostic_only_by_status(self):
        r = _rec([1.0], status="diagnostic_only")
        assert classify_failure_record(r) == RetryFailureClass.DIAGNOSTIC_ONLY

    def test_diagnostic_only_by_taxonomy(self):
        r = _rec([1.0], status="unknown_failed", error_tax={"category": "diagnostic_only"})
        assert classify_failure_record(r) == RetryFailureClass.DIAGNOSTIC_ONLY

    def test_incompatible_schema(self):
        r = _rec([1.0], status="success", schema=99)
        assert classify_failure_record(r) == RetryFailureClass.INCOMPATIBLE_SCHEMA

    def test_missing_identity(self):
        r = EvaluationDatabaseRecord(status="calibration_failed")
        assert classify_failure_record(r) == RetryFailureClass.MISSING_PARAMETER_IDENTITY

    def test_unsupported_status(self):
        r = _rec([1.0], status="bogus_status")
        assert classify_failure_record(r) == RetryFailureClass.UNSUPPORTED_STATUS


# ---------------------------------------------------------------------------
# classify_retry_eligibility
# ---------------------------------------------------------------------------


class TestRetryEligibility:
    def test_success_no_retry(self):
        r = _rec([1.0], status="success")
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.NO_RETRY_SUCCESS

    def test_gate_rejected_no_retry_default(self):
        r = _rec([1.0], status="gate_rejected")
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.NO_RETRY_GATE_REJECTED

    def test_calibration_failed_retry_eligible(self):
        r = _rec([1.0], status="calibration_failed", retries=0)
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.RETRY_ELIGIBLE
        assert cl.next_tier == 1

    def test_solver_failed_retry_eligible(self):
        r = _rec([1.0], status="solver_failed", retries=1)
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.RETRY_ELIGIBLE
        assert cl.next_tier == 2

    def test_transient_failed_retry_eligible(self):
        r = _rec([1.0], status="transient_failed")
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.RETRY_ELIGIBLE

    def test_unknown_failed_retry_eligible_default(self):
        r = _rec([1.0], status="unknown_failed")
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.RETRY_ELIGIBLE

    def test_unknown_failed_no_retry_when_disabled(self):
        policy = RetryPolicy(allow_unknown_retry=False)
        r = _rec([1.0], status="unknown_failed")
        cl = classify_retry_eligibility(r, policy=policy)
        assert cl.action != RetryEligibilityAction.RETRY_ELIGIBLE

    def test_max_tiers_reached_not_permanent(self):
        policy = RetryPolicy(max_tier=3)
        r = _rec([1.0], status="calibration_failed", retries=3)
        cl = classify_retry_eligibility(r, policy=policy)
        assert cl.action == RetryEligibilityAction.NO_RETRY_MAX_TIERS_REACHED
        assert cl.probably_infeasible is False

    def test_single_failure_not_probably_infeasible(self):
        r = _rec([1.0], status="calibration_failed")
        cl = classify_retry_eligibility(r)
        assert cl.probably_infeasible is False

    def test_diagnostic_only_no_retry(self):
        r = _rec([1.0], status="diagnostic_only")
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.NO_RETRY_DIAGNOSTIC_ONLY

    def test_incompatible_schema_no_retry(self):
        r = _rec([1.0], status="success", schema=99)
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.NO_RETRY_INCOMPATIBLE_SCHEMA

    def test_missing_identity_no_retry(self):
        r = EvaluationDatabaseRecord(status="calibration_failed")
        cl = classify_retry_eligibility(r)
        assert cl.action == RetryEligibilityAction.NO_RETRY_MISSING_IDENTITY

    def test_unknown_failed_is_not_diagnostic_only(self):
        """Normal UNKNOWN_FAILED without diagnostic marker is not diagnostic_only."""
        r = _rec([1.0], status="unknown_failed")
        assert is_diagnostic_only_record(r) is False
        fc = classify_failure_record(r)
        assert fc == RetryFailureClass.UNKNOWN_FAILED


# ---------------------------------------------------------------------------
# suggest_next_retry_tier
# ---------------------------------------------------------------------------


class TestSuggestTier:
    def test_success_returns_none(self):
        r = _rec([1.0], status="success")
        assert suggest_next_retry_tier(r) is None

    def test_cal_failed_returns_tier_1(self):
        r = _rec([1.0], status="calibration_failed", retries=0)
        assert suggest_next_retry_tier(r) == 1

    def test_solver_failed_returns_tier_2(self):
        r = _rec([1.0], status="solver_failed", retries=1)
        assert suggest_next_retry_tier(r) == 2

    def test_max_tier_clamped(self):
        policy = RetryPolicy(max_tier=2)
        r = _rec([1.0], status="solver_failed", retries=0)
        assert suggest_next_retry_tier(r, policy=policy) == 1
        r2 = _rec([1.0], status="solver_failed", retries=2)
        assert suggest_next_retry_tier(r2, policy=policy) is None


# ---------------------------------------------------------------------------
# should_escalate_to_probably_infeasible
# ---------------------------------------------------------------------------


class TestProbablyInfeasible:
    def test_default_returns_false(self):
        assert should_escalate_to_probably_infeasible([]) is False

    def test_single_failure_false(self):
        r = _rec([1.0], status="calibration_failed")
        assert should_escalate_to_probably_infeasible([r]) is False

    def test_enabled_but_threshold_not_met(self):
        policy = RetryPolicy(
            enable_permanent_infeasible=True,
            permanent_failure_threshold=5,
        )
        records = [_rec([1.0], status="calibration_failed") for _ in range(3)]
        assert should_escalate_to_probably_infeasible(records, policy=policy) is False


# ---------------------------------------------------------------------------
# summarize_retry_classifications
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_counts_by_action(self):
        records = [
            _rec([1.0], status="success"),
            _rec([2.0], status="calibration_failed"),
            _rec([3.0], status="solver_failed"),
            _rec([4.0], status="calibration_failed"),
        ]
        counts = summarize_retry_classifications(records)
        assert counts.get("retry_eligible", 0) == 3
        assert counts.get("no_retry_success", 0) == 1


# ---------------------------------------------------------------------------
# No I/O / JSONL separation
# ---------------------------------------------------------------------------


class TestNoIO:
    def test_no_file_writes(self):
        """Retry taxonomy helpers do not write any files."""
        r = _rec([1.0], status="solver_failed")
        cl = classify_retry_eligibility(r)
        assert isinstance(cl, RetryClassification)

# ---------------------------------------------------------------------------
# N1 ¡ª Semantics hardening
# ---------------------------------------------------------------------------


class TestN1ProbablyInfeasible:
    def mk(self, values, status, schema=1):
        return _rec(values, status=status, schema=schema)

    def test_default_returns_false(self):
        assert should_escalate_to_probably_infeasible([]) is False

    def test_threshold_met_positive(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=3)
        history = [self.mk([1.0], "calibration_failed") for _ in range(3)]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is True

    def test_default_policy_still_false(self):
        """Default policy returns False even with repeated failures."""
        history = [self.mk([1.0], "calibration_failed") for _ in range(5)]
        assert should_escalate_to_probably_infeasible(history) is False

    def test_threshold_one_does_not_escalate_single_failure(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=1)
        history = [self.mk([1.0], "calibration_failed")]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_mixed_parameter_keys_return_false(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        history = [
            self.mk([1.0], "calibration_failed"),
            self.mk([2.0], "calibration_failed"),
        ]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_mixed_failure_classes_return_false(self):
        """Mixed cal_fail + solver_fail with same identity are both allowed."""
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        history = [
            self.mk([1.0], "calibration_failed"),
            self.mk([1.0], "calibration_failed"),
        ]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is True

    def test_transient_in_history_false(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        history = [
            self.mk([1.0], "calibration_failed"),
            self.mk([1.0], "transient_failed"),
        ]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_gate_rejected_in_history_false(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        history = [
            self.mk([1.0], "calibration_failed"),
            self.mk([1.0], "gate_rejected"),
        ]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_success_in_history_false(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        history = [
            self.mk([1.0], "calibration_failed"),
            self.mk([1.0], "success"),
        ]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_diagnostic_only_status_false(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        history = [
            self.mk([1.0], "calibration_failed"),
            self.mk([1.0], "diagnostic_only"),
        ]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_diagnostic_only_error_taxonomy_false(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        r = _rec([1.0], status="unknown_failed", error_tax={"category": "diagnostic_only"})
        history = [self.mk([1.0], "calibration_failed"), r]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_missing_identity_false(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        r = EvaluationDatabaseRecord(status="calibration_failed")
        history = [self.mk([1.0], "calibration_failed"), r]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_incompatible_schema_false(self):
        policy = RetryPolicy(enable_permanent_infeasible=True, permanent_failure_threshold=2)
        history = [
            self.mk([1.0], "calibration_failed"),
            self.mk([1.0], "calibration_failed", schema=99),
        ]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is False

    def test_max_tiers_not_probably_infeasible(self):
        r = _rec([1.0], status="calibration_failed", retries=3)
        cl = classify_retry_eligibility(r)
        assert cl.probably_infeasible is False

    def test_unknown_not_diagnostic(self):
        r = _rec([1.0], status="unknown_failed")
        assert is_diagnostic_only_record(r) is False

    def test_unknown_escalates_when_enabled(self):
        """Unknown failures can escalate when allow_unknown_retry=True."""
        policy = RetryPolicy(
            enable_permanent_infeasible=True,
            permanent_failure_threshold=2,
            allow_unknown_retry=True,
        )
        history = [self.mk([1.0], "unknown_failed") for _ in range(2)]
        assert should_escalate_to_probably_infeasible(history, policy=policy) is True


class TestN1JsonlNotReferenced:
    def test_retry_taxonomy_does_not_reference_jsonl(self):
        """Retry taxonomy module does not import or reference Phase C JSONL."""
        import workflows.rfgun_sao.retry_taxonomy as rt
        src = rt.__file__
        with open(src, "r", encoding="utf-8") as fh:
            text = fh.read()
        forbidden = ["records.py", "resolve_records_config", ".jsonl",
                     "evaluation_records"]
        for item in forbidden:
            assert item not in text, f"retry taxonomy should not reference {item!r}"
