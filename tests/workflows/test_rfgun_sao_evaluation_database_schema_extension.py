"""No-CST tests for SE1 schema extension hooks for failure skip records.

All tests are pure no-CST.  No subprocess, no taskkill, no OS calls.
"""

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
    EvaluationDatabaseStatus,
    current_schema_version,
)
from workflows.rfgun_sao.evaluation_database_skip_records import (
    SKIPPED_FAILURE_REUSE,
    SKIPPED_PROBABLY_INFEASIBLE,
    EvaluationDatabaseSchemaCapabilities,
    EvaluationSkipRecordPayload,
    build_skip_record_db_fields,
    get_schema_capabilities,
    is_extended_evaluation_status,
    is_failure_skip_evidence_source_status,
    is_reusable_success_status,
    is_skip_status,
    is_success_status,
    validate_skip_record_payload,
)


# ===================================================================
# Status helpers
# ===================================================================


class TestStatusHelpers:
    def test_success_reusable_true(self):
        assert is_reusable_success_status("success") is True

    def test_skipped_failure_reuse_not_reusable(self):
        assert is_reusable_success_status(SKIPPED_FAILURE_REUSE) is False

    def test_skipped_probably_infeasible_not_reusable(self):
        assert is_reusable_success_status(SKIPPED_PROBABLY_INFEASIBLE) is False

    def test_skip_statuses_recognized(self):
        assert is_skip_status(SKIPPED_FAILURE_REUSE)
        assert is_skip_status(SKIPPED_PROBABLY_INFEASIBLE)
        assert not is_skip_status("success")
        assert not is_skip_status("solver_failed")

    def test_extended_status_recognized(self):
        assert is_extended_evaluation_status(SKIPPED_FAILURE_REUSE)
        assert is_extended_evaluation_status(SKIPPED_PROBABLY_INFEASIBLE)
        assert not is_extended_evaluation_status("success")

    def test_success_is_success(self):
        assert is_success_status("success")

    def test_skip_not_success(self):
        assert not is_success_status(SKIPPED_FAILURE_REUSE)
        assert not is_success_status(SKIPPED_PROBABLY_INFEASIBLE)

    def test_failure_status_evidence_source(self):
        assert is_failure_skip_evidence_source_status("solver_failed")
        assert is_failure_skip_evidence_source_status("gate_rejected")

    def test_success_not_evidence_source(self):
        assert not is_failure_skip_evidence_source_status("success")

    def test_skip_not_evidence_source(self):
        assert not is_failure_skip_evidence_source_status(SKIPPED_FAILURE_REUSE)
        assert not is_failure_skip_evidence_source_status(SKIPPED_PROBABLY_INFEASIBLE)


# ===================================================================
# Payload validation
# ===================================================================


class TestPayloadValidation:
    def test_valid_payload(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc123",
            source_row_ids=(1, 2),
            evidence_count=2,
            skip_reason="2 solver failures at same key",
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert valid, reasons
        assert len(reasons) == 0

    def test_missing_parameter_key_invalid(self):
        payload = EvaluationSkipRecordPayload()
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "parameter_key_required" in reasons

    def test_missing_source_row_ids_invalid(self):
        payload = EvaluationSkipRecordPayload(parameter_key="abc")
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "source_row_ids_required_for_enforce_skip" in reasons

    def test_environment_fault_flag_warns(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc",
            source_row_ids=(1,),
            skip_reason="test",
            environment_fault_flag=True,
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "environment_fault_flag_should_be_false_for_enforce_skip" in reasons

    def test_evaluator_called_must_be_false(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,),
            skip_reason="test", evaluator_called=True,
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "evaluator_called_must_be_false_for_enforce_skip" in reasons

    def test_retry_called_must_be_false(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,),
            skip_reason="test", retry_called=True,
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "retry_called_must_be_false_for_enforce_skip" in reasons

    def test_invalid_status_rejected(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,),
            skip_reason="test", status="invalid_skip",
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert any("invalid_skip_status" in r for r in reasons)


# ===================================================================
# DB field mapping
# ===================================================================


class TestDBFieldMapping:
    def test_maps_status_and_source(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1, skip_reason="test",
        )
        fields = build_skip_record_db_fields(payload)
        assert fields["status"] == SKIPPED_FAILURE_REUSE
        assert fields["source"] == "failure_skip_enforce"

    def test_maps_diagnostics(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1, 2),
            evidence_count=2, skip_reason="test",
        )
        fields = build_skip_record_db_fields(payload)
        diag = fields["diagnostics"]
        assert diag["record_kind"] == "skip"
        assert diag["evidence_count"] == 2
        assert diag["source_row_ids"] == [1, 2]
        assert diag["evaluator_called"] is False
        assert diag["retry_called"] is False
        assert diag["budget_consumed"] is False

    def test_maps_error_taxonomy(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1,
            skip_reason="test", failure_taxonomy_version=1,
            environment_fault_flag=False,
        )
        fields = build_skip_record_db_fields(payload)
        et = fields["error_taxonomy"]
        assert et["failure_taxonomy_version"] == 1
        assert et["environment_fault_flag"] is False

    def test_no_fabricated_success_metrics(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1, skip_reason="test",
        )
        fields = build_skip_record_db_fields(payload)
        assert fields["raw_metrics"] is None
        assert fields["objective_values"] is None


# ===================================================================
# Schema capability
# ===================================================================


class TestSchemaCapability:
    def test_v1_requires_migration(self):
        caps = get_schema_capabilities(1)
        assert caps.schema_version == 1
        assert caps.requires_migration_for_skip_rows is True
        assert caps.supports_skip_statuses is False
        assert caps.supports_skip_audit_fields is True
        assert caps.supports_extra_json is True

    def test_v1_validation_rejects_skip_status(self):
        with pytest.raises(ValueError, match="Unknown evaluation status"):
            EvaluationDatabaseStatus.validate(SKIPPED_FAILURE_REUSE)

    def test_v1_validation_accepts_success(self):
        EvaluationDatabaseStatus.validate("success")  # no error

    def test_unknown_version_conservative(self):
        caps = get_schema_capabilities(99)
        assert caps.requires_migration_for_skip_rows is True
        assert caps.supports_skip_statuses is False
        assert caps.supports_skip_audit_fields is False


# ===================================================================
# Global safety
# ===================================================================


class TestGlobalSafety:
    def test_no_subprocess(self):
        import workflows.rfgun_sao.evaluation_database_skip_records as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "import subprocess" not in text
        assert "from subprocess" not in text

    def test_no_os_system(self):
        import workflows.rfgun_sao.evaluation_database_skip_records as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "os.system" not in text

    def test_no_taskkill(self):
        import workflows.rfgun_sao.evaluation_database_skip_records as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "taskkill" not in text
        assert "Stop-Process" not in text

    def test_no_cst_import(self):
        import workflows.rfgun_sao.evaluation_database_skip_records as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        forbidden = ["cst.interface", "cst.results", "import cst", "from cst"]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"


# ===================================================================
# SE1.1 payload validation hardening
# ===================================================================


class TestSE11Hardening:
    """Extended validation checks for skip record payload."""

    def test_missing_skip_reason_invalid(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1,
            skip_reason="",
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "skip_reason_required" in reasons

    def test_evidence_count_zero_invalid(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=0,
            skip_reason="test",
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "evidence_count_required_for_enforce_skip" in reasons

    def test_evidence_count_mismatch_invalid(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1, 2), evidence_count=3,
            skip_reason="test",
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "evidence_count_source_row_ids_mismatch" in reasons

    def test_budget_consumed_true_invalid(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1,
            skip_reason="test", budget_consumed=True,
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "budget_consumed_must_be_false_for_enforce_skip" in reasons

    def test_skip_decision_not_enforced_invalid(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1,
            skip_reason="test", skip_decision="would_skip",
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "skip_decision_must_be_enforced_skip" in reasons

    def test_skip_policy_version_zero_invalid(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1,), evidence_count=1,
            skip_reason="test", skip_policy_version=0,
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert not valid
        assert "skip_policy_version_must_be_positive" in reasons

    def test_valid_payload_evidence_count_matches(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1, 2),
            evidence_count=2, skip_reason="2 failures at same key",
        )
        valid, reasons = validate_skip_record_payload(payload)
        assert valid, reasons
        assert len(reasons) == 0

    def test_mapper_validates_and_raises_on_invalid(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="",  # missing
            source_row_ids=(1,), evidence_count=1, skip_reason="test",
        )
        with pytest.raises(ValueError, match="Cannot build DB fields from invalid payload"):
            build_skip_record_db_fields(payload)

    def test_mapper_valid_for_valid_payload(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1, 2),
            evidence_count=2, skip_reason="test",
        )
        fields = build_skip_record_db_fields(payload)
        assert fields["status"] == SKIPPED_FAILURE_REUSE
        assert fields["source"] == "failure_skip_enforce"

    def test_mapper_includes_all_audit_fields(self):
        payload = EvaluationSkipRecordPayload(
            parameter_key="abc", source_row_ids=(1, 2),
            source_run_ids=("r1", "r2"),
            evidence_count=2, skip_reason="test",
            failure_taxonomy_version=1,
            operator_override_id="op_1",
        )
        fields = build_skip_record_db_fields(payload)
        diag = fields["diagnostics"]
        assert diag["skip_reason"] == "test"
        assert diag["evidence_count"] == 2
        assert diag["source_row_ids"] == [1, 2]
        assert diag["source_run_ids"] == ["r1", "r2"]
        assert diag["evaluator_called"] is False
        assert diag["retry_called"] is False
        assert diag["budget_consumed"] is False
        et = fields["error_taxonomy"]
        assert et["environment_fault_flag"] is False
        prov = fields["provenance"]
        assert prov["operator_override_id"] == "op_1"
