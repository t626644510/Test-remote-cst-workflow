"""No-CST tests for retry runtime CST adapter (Phase RW2).

Tests the mappers, record builder, evaluate_once adapter, and legacy
retry mutex without requiring a real CST connection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
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
from workflows.rfgun_sao.retry_runtime import (
    RetryRuntimeConfig,
    run_retry_loop_no_cst,
)
from workflows.rfgun_sao.retry_runtime_cst import (
    map_evaluation_status_to_database_status,
    build_record_from_evaluation_result,
    make_cst_retry_evaluate_once,
    check_legacy_retry_mutex,
)
from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pid(values: list[float]) -> ParameterIdentity:
    return ParameterIdentity(
        param_names=[f"p{i}" for i in range(len(values))],
        values=list(values),
    )


def _rec(
    values: list[float] | None,
    status: str = "success",
    retries: int = 0,
    schema: int = 1,
    error_tax: dict | None = None,
) -> EvaluationDatabaseRecord:
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
# Fake evaluator for no-CST testing
# ---------------------------------------------------------------------------


class FakeCstEvaluator:
    """Duck-typed Workflow1Evaluator for no-CST tests.

    Yields pre-defined EvaluationResult instances in sequence.
    """

    def __init__(
        self,
        results: list[EvaluationResult],
        param_names: list[str] | None = None,
    ) -> None:
        self._results = results
        self._call_count = 0
        self._param_names = param_names or [f"p{i}" for i in range(10)]

    @property
    def call_count(self) -> int:
        return self._call_count

    def adapt_for_retry(
        self, params: np.ndarray, iteration: int,
    ) -> EvaluationResult:
        idx = self._call_count % len(self._results) if self._results else 0
        self._call_count += 1
        return self._results[idx]


# ---------------------------------------------------------------------------
# map_evaluation_status_to_database_status
# ---------------------------------------------------------------------------


class TestMapStatus:
    def test_success_maps_to_success(self) -> None:
        assert (
            map_evaluation_status_to_database_status(EvaluationStatus.SUCCESS)
            == EvaluationDatabaseStatus.SUCCESS
        )

    def test_com_lost_maps_to_transient(self) -> None:
        assert (
            map_evaluation_status_to_database_status(EvaluationStatus.COM_LOST)
            == EvaluationDatabaseStatus.TRANSIENT_FAILED
        )

    def test_solver_failed_maps_to_solver_failed(self) -> None:
        assert (
            map_evaluation_status_to_database_status(EvaluationStatus.SOLVER_FAILED)
            == EvaluationDatabaseStatus.SOLVER_FAILED
        )

    def test_physics_invalid_maps_to_solver_failed(self) -> None:
        assert (
            map_evaluation_status_to_database_status(EvaluationStatus.PHYSICS_INVALID)
            == EvaluationDatabaseStatus.SOLVER_FAILED
        )

    def test_unknown_error_maps_to_unknown_failed(self) -> None:
        assert (
            map_evaluation_status_to_database_status(EvaluationStatus.UNKNOWN_ERROR)
            == EvaluationDatabaseStatus.UNKNOWN_FAILED
        )


# ---------------------------------------------------------------------------
# build_record_from_evaluation_result
# ---------------------------------------------------------------------------


class TestBuildRecord:
    def test_success_record_contains_metrics(self) -> None:
        pid = _pid([1.0, 2.0])
        result = EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            error="",
            raw_metrics={"resonant_freq": 11.424, "q0": 18000.0},
            objective_values={"resonant_freq": 11.424},
        )
        record = build_record_from_evaluation_result(pid, result)
        assert record.status == EvaluationDatabaseStatus.SUCCESS
        assert record.parameter_identity == pid
        assert record.raw_payload is not None
        assert record.raw_payload.raw_metrics == {"resonant_freq": 11.424, "q0": 18000.0}
        assert record.raw_payload.objective_values == {"resonant_freq": 11.424}
        assert record.objective_names == ["resonant_freq"]

    def test_failure_record_contains_error_taxonomy(self) -> None:
        pid = _pid([1.0])
        result = EvaluationResult(
            status=EvaluationStatus.SOLVER_FAILED,
            error="Solver did not converge",
        )
        record = build_record_from_evaluation_result(pid, result)
        assert record.status == EvaluationDatabaseStatus.SOLVER_FAILED
        assert record.error_taxonomy is not None
        assert "Solver did not converge" in str(record.error_taxonomy)

    def test_com_lost_record_transient_status(self) -> None:
        pid = _pid([1.0])
        result = EvaluationResult(
            status=EvaluationStatus.COM_LOST,
            error="COM connection lost",
        )
        record = build_record_from_evaluation_result(pid, result)
        assert record.status == EvaluationDatabaseStatus.TRANSIENT_FAILED

    def test_none_identity_preserved(self) -> None:
        result = EvaluationResult(
            status=EvaluationStatus.SUCCESS,
            error="",
        )
        record = build_record_from_evaluation_result(None, result)
        assert record.parameter_identity is None

    def test_retry_count_passed_through(self) -> None:
        pid = _pid([1.0])
        result = EvaluationResult(status=EvaluationStatus.SUCCESS)
        record = build_record_from_evaluation_result(pid, result, retry_count=3)
        assert record.retry_count == 3

    def test_no_metrics_no_crash(self) -> None:
        pid = _pid([1.0])
        result = EvaluationResult(status=EvaluationStatus.SUCCESS)
        record = build_record_from_evaluation_result(pid, result)
        assert record.raw_payload is not None
        assert record.raw_payload.raw_metrics is None


# ---------------------------------------------------------------------------
# make_cst_retry_evaluate_once — integration with run_retry_loop_no_cst
# ---------------------------------------------------------------------------


class TestCstRetryEvaluateOnce:
    def test_initial_success_no_retry(self) -> None:
        """Initial record SUCCESS -> no retry, evaluate_once never called."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SUCCESS, error=""),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="success", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert len(result.attempts) == 0
        assert fake.call_count == 0

    def test_failed_initial_retry_succeeds(self) -> None:
        """Failed initial attempt -> retry loop -> SUCCESS."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SUCCESS, error=""),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert len(result.attempts) == 1
        assert fake.call_count == 1

    def test_solver_failed_then_success(self) -> None:
        """SOLVER_FAILED -> retry eligible -> retry -> SUCCESS."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SOLVER_FAILED, error="solver err"),
            EvaluationResult(status=EvaluationStatus.SUCCESS, error=""),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert len(result.attempts) == 2
        assert fake.call_count == 2
        assert result.attempts[0].status_before == "solver_failed"
        assert result.attempts[1].status_after == "success"
        assert result.attempts[0].tier == 1
        assert result.attempts[1].tier == 2

    def test_com_lost_then_success(self) -> None:
        """COM_LOST -> retry eligible -> retry -> SUCCESS."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.COM_LOST, error="com lost"),
            EvaluationResult(status=EvaluationStatus.SUCCESS, error=""),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert len(result.attempts) == 2

    def test_repeated_solver_failed_max_tier_exhausted(self) -> None:
        """Repeated SOLVER_FAILED -> max_tier exhausted -> terminal failure."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SOLVER_FAILED, error="fail"),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_max_tiers_reached"
        assert len(result.attempts) == 2
        # Not "skipped" — returned as terminal failure
        assert "skip" not in result.stopped_reason

    def test_gate_rejected_no_retry(self) -> None:
        """GATE_REJECTED -> not retried by default."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SOLVER_FAILED, error="gate"),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="gate_rejected", retries=0)
        config = RetryRuntimeConfig(enabled=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is False
        assert result.stopped_reason == "no_retry_gate_rejected"
        assert len(result.attempts) == 0  # not called

    def test_unknown_failed_retry_by_default(self) -> None:
        """UNKNOWN_FAILED is retry-eligible when allow_unknown_retry=True."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.UNKNOWN_ERROR, error="weird"),
            EvaluationResult(status=EvaluationStatus.SUCCESS, error=""),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="unknown_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, allow_unknown_retry=True)
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is True
        assert len(result.attempts) == 2


# ---------------------------------------------------------------------------
# Recovery callback interaction
# ---------------------------------------------------------------------------


class TestCstRetryRecovery:
    def test_recovery_callback_called_on_tier_2(self) -> None:
        """Recovery callback is called on retry attempts."""
        call_tiers: list[int] = []

        def recovery(tier: int, record: EvaluationDatabaseRecord) -> bool:
            call_tiers.append(tier)
            return True

        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SOLVER_FAILED, error="fail"),
            EvaluationResult(status=EvaluationStatus.SUCCESS, error=""),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=3)
        result = run_retry_loop_no_cst(
            initial, evaluate_once,
            config=config, recovery_callback=recovery,
        )
        assert result.succeeded is True
        assert len(call_tiers) == 2  # called before each attempt
        # Tiers should increase: first attempt at tier 1, second at tier 2
        assert call_tiers[0] == 1

    def test_recovery_failure_recorded_but_loop_bounded(self) -> None:
        """Recovery callback exception captured; loop still terminates."""
        call_count = [0]

        def recovery(tier: int, record: EvaluationDatabaseRecord) -> bool:
            call_count[0] += 1
            raise RuntimeError("recovery failed")

        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SOLVER_FAILED, error="fail"),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(enabled=True, max_tier=2)
        result = run_retry_loop_no_cst(
            initial, evaluate_once,
            config=config, recovery_callback=recovery,
        )
        assert result.succeeded is False
        assert len(result.attempts) == 2
        assert "recovery_exception" in result.attempts[0].recovery_label
        assert "recovery_exception" in result.attempts[1].recovery_label


# ---------------------------------------------------------------------------
# use_probably_infeasible_for_skip=False (rejected)
# ---------------------------------------------------------------------------


class TestProbablyInfeasibleGuard:
    def test_probably_infeasible_skip_rejected(self) -> None:
        """use_probably_infeasible_for_skip=True is rejected at runtime."""
        fake = FakeCstEvaluator([
            EvaluationResult(status=EvaluationStatus.SUCCESS, error=""),
        ])
        evaluate_once = make_cst_retry_evaluate_once(fake)
        initial = _rec([1.0], status="solver_failed", retries=0)
        config = RetryRuntimeConfig(
            enabled=True, use_probably_infeasible_for_skip=True,
        )
        result = run_retry_loop_no_cst(initial, evaluate_once, config=config)
        assert result.succeeded is False
        assert result.stopped_reason == "probably_infeasible_skip_not_supported"
        assert fake.call_count == 0  # never called


# ---------------------------------------------------------------------------
# Legacy retry mutex
# ---------------------------------------------------------------------------


class TestLegacyRetryMutex:
    def test_no_config_returns_disabled(self) -> None:
        cfg, msg = check_legacy_retry_mutex(None)
        assert cfg.enabled is False
        assert msg is None

    def test_no_retry_runtime_section_returns_disabled(self) -> None:
        cfg, msg = check_legacy_retry_mutex({"optimization": {}})
        assert cfg.enabled is False
        assert msg is None

    def test_retry_runtime_disabled_no_conflict(self) -> None:
        cfg, msg = check_legacy_retry_mutex({
            "retry_runtime": {"enabled": False},
            "optimization": {"retry": {"enabled": True}},
        })
        assert cfg.enabled is False
        assert msg is None

    def test_retry_runtime_enabled_no_legacy_ok(self) -> None:
        cfg, msg = check_legacy_retry_mutex({
            "retry_runtime": {"enabled": True},
            "optimization": {"retry": {"enabled": False}},
        })
        assert cfg.enabled is True
        assert msg is None

    def test_mutex_triggers_disables_retry_runtime(self) -> None:
        """Legacy retry enabled + retry_runtime enabled -> retry_runtime disabled."""
        cfg, msg = check_legacy_retry_mutex({
            "retry_runtime": {"enabled": True},
            "optimization": {"retry": {"enabled": True}},
        })
        assert cfg.enabled is False
        assert msg is not None
        assert "double retry" in msg

    def test_mutex_no_legacy_section_assumed_disabled(self) -> None:
        """No optimization.retry section means legacy retry disabled."""
        cfg, msg = check_legacy_retry_mutex({
            "retry_runtime": {"enabled": True},
        })
        assert cfg.enabled is True
        assert msg is None

    def test_mutex_with_legacy_enabled_true_default(self) -> None:
        """Legacy retry with no explicit enabled defaults to True."""
        cfg, msg = check_legacy_retry_mutex({
            "retry_runtime": {"enabled": True},
            "optimization": {"retry": {"max_tier1": 3}},
        })
        assert cfg.enabled is False
        assert msg is not None


# ---------------------------------------------------------------------------
# Adapter builds records compatible with taxonomy classification
# ---------------------------------------------------------------------------


class TestAdapterTaxonomyIntegration:
    def test_record_from_adapter_classifies_correctly(self) -> None:
        """The adapter's output records classify correctly via taxonomy."""
        from workflows.rfgun_sao.retry_taxonomy import classify_retry_eligibility

        pid = _pid([1.0])
        result = EvaluationResult(
            status=EvaluationStatus.SOLVER_FAILED,
            error="solver error",
        )
        record = build_record_from_evaluation_result(pid, result, retry_count=0)
        cl = classify_retry_eligibility(record)
        assert cl.action.value == "retry_eligible"
        assert cl.next_tier == 1

    def test_success_record_from_adapter_no_retry(self) -> None:
        from workflows.rfgun_sao.retry_taxonomy import classify_retry_eligibility

        pid = _pid([1.0])
        result = EvaluationResult(status=EvaluationStatus.SUCCESS)
        record = build_record_from_evaluation_result(pid, result)
        cl = classify_retry_eligibility(record)
        assert cl.action.value == "no_retry_success"

    def test_max_tier_record_not_probably_infeasible(self) -> None:
        """Max tier exhaustion does NOT mark probably-infeasible."""
        from workflows.rfgun_sao.retry_taxonomy import classify_retry_eligibility

        pid = _pid([1.0])
        result = EvaluationResult(
            status=EvaluationStatus.SOLVER_FAILED, error="fail",
        )
        record = build_record_from_evaluation_result(pid, result, retry_count=5)
        cl = classify_retry_eligibility(record)
        assert cl.probably_infeasible is False


# ---------------------------------------------------------------------------
# Safety — no forbidden imports / no CST
# ---------------------------------------------------------------------------


class TestSafety:
    def test_no_cst_import_at_module_level(self) -> None:
        """retry_runtime_cst does not import cst.interface or cst.results."""
        import workflows.rfgun_sao.retry_runtime_cst as mod
        src_path = mod.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        forbidden = [
            "cst.interface", "cst.results", "import cst",
            "from cst", "cst_optimization",
        ]
        for item in forbidden:
            assert item not in text, f"should not import {item!r}"

    def test_no_cst_optimization_factory(self) -> None:
        """Module does not import cst_optimization.factory."""
        import workflows.rfgun_sao.retry_runtime_cst as mod
        src_path = mod.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "cst_optimization.factory" not in text

    def test_no_cst_optimization_recovery(self) -> None:
        """Module does not import cst_optimization.workflows.recovery."""
        import workflows.rfgun_sao.retry_runtime_cst as mod
        src_path = mod.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "cst_optimization.workflows.recovery" not in text

    def test_no_file_io(self) -> None:
        """Module does not perform file I/O."""
        import workflows.rfgun_sao.retry_runtime_cst as mod
        src_path = mod.__file__
        with open(src_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        forbidden = [".write", ".read", "open(", "pathlib"]
        for item in forbidden:
            assert item not in text, f"should not perform file I/O ({item!r})"
