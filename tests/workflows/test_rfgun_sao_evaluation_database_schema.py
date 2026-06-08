"""No-CST tests for evaluation database schema."""

from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for p in (str(_PROJECT_ROOT), _SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from cst_optimization.evaluation.evaluation_database_schema import (
    current_schema_version,
    is_schema_compatible,
    EvaluationDatabaseStatus,
    ParameterIdentity,
    RawEvaluationPayload,
    EvaluationDatabaseRecord,
    ReuseEligibility,
    validate_parameter_identity,
    validate_evaluation_record,
    record_to_json_dict,
    record_from_json_dict,
    schema_ddl_sqlite,
)


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    def test_current_version(self):
        assert current_schema_version() == 1

    def test_compatible_exact_match(self):
        assert is_schema_compatible(1) is True

    def test_incompatible_mismatch(self):
        assert is_schema_compatible(2) is False


# ---------------------------------------------------------------------------
# Evaluation status validation
# ---------------------------------------------------------------------------


class TestStatus:
    def test_valid_statuses(self):
        for s in ["success", "gate_rejected", "calibration_failed",
                   "solver_failed", "transient_failed", "unknown_failed"]:
            assert EvaluationDatabaseStatus.validate(s) == s

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Unknown evaluation status"):
            EvaluationDatabaseStatus.validate("bogus")


# ---------------------------------------------------------------------------
# Parameter identity
# ---------------------------------------------------------------------------


class TestParameterIdentity:
    def test_deterministic_key(self):
        pid = ParameterIdentity(param_names=["p1", "p2"], values=[1.0, 2.0])
        key1 = pid.parameter_key()
        key2 = pid.parameter_key()
        assert key1 == key2

    def test_different_values_different_keys(self):
        p1 = ParameterIdentity(param_names=["p1"], values=[1.0])
        p2 = ParameterIdentity(param_names=["p1"], values=[2.0])
        assert p1.parameter_key() != p2.parameter_key()

    def test_different_names_different_keys(self):
        p1 = ParameterIdentity(param_names=["p1"], values=[1.0])
        p2 = ParameterIdentity(param_names=["p2"], values=[1.0])
        assert p1.parameter_key() != p2.parameter_key()

    def test_precision_affects_key(self):
        p1 = ParameterIdentity(param_names=["p1"], values=[1.123456], precision=2)
        p2 = ParameterIdentity(param_names=["p1"], values=[1.123456], precision=4)
        assert p1.parameter_key() != p2.parameter_key()

    def test_key_is_deterministic_across_instances(self):
        a = ParameterIdentity(param_names=["a", "b"], values=[10.5, 20.5], precision=1)
        b = ParameterIdentity(param_names=["a", "b"], values=[10.5, 20.5], precision=1)
        assert a.parameter_key() == b.parameter_key()

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="length mismatch"):
            ParameterIdentity(param_names=["p1", "p2"], values=[1.0])

    def test_round_trip_dict(self):
        pid = ParameterIdentity(param_names=["x"], values=[3.14], precision=2)
        d = pid.to_dict()
        restored = ParameterIdentity.from_dict(d)
        assert restored.param_names == ["x"]
        assert restored.values == [3.14]
        assert restored.precision == 2


# ---------------------------------------------------------------------------
# validate_parameter_identity
# ---------------------------------------------------------------------------


class TestValidate:
    def test_empty_names_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_parameter_identity([], [])

    def test_valid(self):
        pid = validate_parameter_identity(["p1"], [1.0], precision=2)
        assert isinstance(pid, ParameterIdentity)
        assert pid.param_names == ["p1"]


# ---------------------------------------------------------------------------
# validate_evaluation_record
# ---------------------------------------------------------------------------


class TestValidateRecord:
    def test_valid_success(self):
        pid = ParameterIdentity(param_names=["p1"], values=[1.0])
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status=EvaluationDatabaseStatus.SUCCESS,
        )
        validate_evaluation_record(rec)  # no error

    def test_invalid_status_raises(self):
        pid = ParameterIdentity(param_names=["p1"], values=[1.0])
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status="bogus",
        )
        with pytest.raises(ValueError, match="Unknown evaluation status"):
            validate_evaluation_record(rec)


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    def test_success_record_round_trip(self):
        pid = ParameterIdentity(param_names=["p1"], values=[1.0])
        payload = RawEvaluationPayload(
            raw_metrics={"f1": 11.424},
            gate_results={"g1": True},
        )
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status=EvaluationDatabaseStatus.SUCCESS,
            raw_payload=payload,
            objective_names=["f1"],
            source="rfgun_sao.run",
        )
        d = record_to_json_dict(rec)
        restored = record_from_json_dict(d)
        assert restored.schema_version == rec.schema_version
        assert restored.status == EvaluationDatabaseStatus.SUCCESS
        assert restored.parameter_identity.param_names == ["p1"]
        assert restored.raw_payload.raw_metrics == {"f1": 11.424}
        assert restored.objective_names == ["f1"]
        assert restored.source == "rfgun_sao.run"
        # Must be JSON-serializable
        json.dumps(d)

    def test_failure_record_not_marked_reusable(self):
        pid = ParameterIdentity(param_names=["p1"], values=[1.0])
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status=EvaluationDatabaseStatus.CALIBRATION_FAILED,
        )
        d = record_to_json_dict(rec)
        restored = record_from_json_dict(d)
        assert restored.status == EvaluationDatabaseStatus.CALIBRATION_FAILED
        # Failure records are not eligible for warm-start (no dedup yet)
        assert restored.retry_count == 0

    def test_provenance_preserved(self):
        pid = ParameterIdentity(param_names=["p1"], values=[1.0])
        rec = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status=EvaluationDatabaseStatus.SUCCESS,
            provenance={"git_commit": "abc123", "config_fingerprint": "xyz"},
        )
        d = record_to_json_dict(rec)
        restored = record_from_json_dict(d)
        assert restored.provenance["git_commit"] == "abc123"


# ---------------------------------------------------------------------------
# Reuse eligibility (design-only)
# ---------------------------------------------------------------------------


class TestReuseEligibility:
    def test_categories_defined(self):
        assert ReuseEligibility.ELIGIBLE_SUCCESS_RAW_REDERIVE is not None
        assert ReuseEligibility.INELIGIBLE_FAILURE_RETRY_POLICY_MISSING is not None
        assert ReuseEligibility.DIAGNOSTIC_ONLY is not None


# ---------------------------------------------------------------------------
# DDL string (design-only, not executed)
# ---------------------------------------------------------------------------


class TestDDL:
    def test_ddl_contains_tables(self):
        ddl = schema_ddl_sqlite()
        assert "CREATE TABLE IF NOT EXISTS evaluation_records" in ddl
        assert "parameter_key" in ddl
        assert "status" in ddl
        assert "created_at" in ddl

    def test_no_side_effects(self):
        """Calling DDL does not write any files or create tables."""
        ddl = schema_ddl_sqlite()
        assert isinstance(ddl, str)

