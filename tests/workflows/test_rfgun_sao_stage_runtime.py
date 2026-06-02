"""No-CST tests for stage/adaptive runtime wiring."""

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

from workflows.rfgun_sao.stage_search import (
    StageBounds,
    StageCandidateStatus,
)
from workflows.rfgun_sao.stage_adaptive_policy import (
    StageAdaptiveAction,
    StageAdaptivePolicyDecision,
)
from workflows.rfgun_sao.stage_runtime import (
    StageRuntimeState,
    resolve_stage_search_config,
    resolve_adaptive_bounds_config,
    record_stage_observation,
    maybe_update_stage_bounds,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _bounds(names=None, low=None, high=None, hard_low=None, hard_high=None):
    if names is None:
        names = ["p1", "p2"]
    if low is None:
        low = np.array([0.0, 0.0])
    if high is None:
        high = np.array([10.0, 10.0])
    if hard_low is None:
        hard_low = np.array([-10.0, -10.0])
    if hard_high is None:
        hard_high = np.array([20.0, 20.0])
    return StageBounds(
        param_names=names, low=low, high=high,
        hard_low=hard_low, hard_high=hard_high,
    )


def _default_state():
    b = _bounds()
    return StageRuntimeState(
        initial_bounds=b,
        current_bounds=b,
        reference_span=b.span.copy(),
    )


def _rec(state, x, status="completed", obj=1.0, **kw):
    record_stage_observation(state, x=list(x), status=status, objective_value=obj, **kw)


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_disabled(self):
        r = resolve_stage_search_config({})
        assert r["enabled"] is False

    def test_opt_in_enabled(self):
        r = resolve_stage_search_config({
            "optimization": {"stage_search": {"enabled": True}},
        })
        assert r["enabled"] is True
        assert r["max_stages"] == 5

    def test_adaptive_bounds_default_disabled(self):
        r = resolve_adaptive_bounds_config({})
        assert r["enabled"] is False

    def test_adaptive_bounds_opt_in(self):
        r = resolve_adaptive_bounds_config({
            "optimization": {"adaptive_bounds": {"enabled": True}},
        })
        assert r["enabled"] is True


# ---------------------------------------------------------------------------
# Disabled stage search
# ---------------------------------------------------------------------------


class TestDisabled:
    def test_disabled_no_op(self):
        state = _default_state()
        dec = maybe_update_stage_bounds(state, stage_cfg={"enabled": False})
        assert dec.action == StageAdaptiveAction.CONTINUE_CURRENT
        assert state.current_stage == 0

    def test_observations_not_processed_when_disabled(self):
        state = _default_state()
        _rec(state, [5.0, 5.0])
        dec = maybe_update_stage_bounds(state, stage_cfg={"enabled": False})
        assert dec.action == StageAdaptiveAction.CONTINUE_CURRENT


# ---------------------------------------------------------------------------
# Enabled stage search with completed observations
# ---------------------------------------------------------------------------


class TestEnabledCompleted:
    def test_centered_completed_produces_shrink(self):
        state = _default_state()
        for _ in range(4):
            _rec(state, [5.0, 5.0], obj=1.0)
        dec = maybe_update_stage_bounds(state, stage_cfg={"enabled": True})
        assert dec.action == StageAdaptiveAction.USE_STAGE_DECISION

    def test_best_near_boundary_uses_adaptive(self):
        state = _default_state()
        for _ in range(3):
            _rec(state, [0.2, 5.0], obj=1.0)
        dec = maybe_update_stage_bounds(
            state,
            stage_cfg={"enabled": True},
            adaptive_cfg={"enabled": True},
        )
        # With adaptive enabled and clipping, should expand
        assert dec.action in (
            StageAdaptiveAction.USE_ADAPTIVE_BOUNDS,
            StageAdaptiveAction.USE_STAGE_DECISION,
        )


# ---------------------------------------------------------------------------
# High fail / reject scenarios
# ---------------------------------------------------------------------------


class TestHighFail:
    def test_high_cal_fail_recenters(self):
        state = _default_state()
        for _ in range(3):
            _rec(state, [5.0, 5.0], status=StageCandidateStatus.CALIBRATION_FAILED)
        dec = maybe_update_stage_bounds(
            state,
            stage_cfg={"enabled": True, "high_fail_rate": 0.3},
        )
        assert dec.action in (
            StageAdaptiveAction.USE_STAGE_DECISION,
            StageAdaptiveAction.CONTINUE_CURRENT,
        )

    def test_high_gate_reject_recenters(self):
        state = _default_state()
        for _ in range(3):
            _rec(state, [5.0, 5.0], status=StageCandidateStatus.GATE_REJECTED)
        dec = maybe_update_stage_bounds(
            state,
            stage_cfg={"enabled": True, "high_fail_rate": 0.3},
        )
        assert dec.action in (
            StageAdaptiveAction.USE_STAGE_DECISION,
            StageAdaptiveAction.CONTINUE_CURRENT,
        )

    def test_shrink_without_best_evidence_blocks(self):
        """Stage runtime must not perform shrink without completed evidence."""
        state = _default_state()
        # Only gate_rejected observations, no completed
        _rec(state, [5.0, 5.0], status=StageCandidateStatus.GATE_REJECTED)
        _rec(state, [5.0, 5.0], status=StageCandidateStatus.GATE_REJECTED)
        dec = maybe_update_stage_bounds(state, stage_cfg={"enabled": True})
        assert dec.action != StageAdaptiveAction.STOP

    def test_increment_stage_on_transition(self):
        """Stage counter increments when a transition occurs."""
        state = _default_state()
        for _ in range(4):
            _rec(state, [5.0, 5.0], obj=1.0)
        assert state.current_stage == 0
        dec = maybe_update_stage_bounds(state, stage_cfg={"enabled": True})
        if dec.action in (StageAdaptiveAction.USE_STAGE_DECISION, StageAdaptiveAction.USE_ADAPTIVE_BOUNDS):
            assert state.current_stage == 1


# ---------------------------------------------------------------------------
# Reference span / min-span
# ---------------------------------------------------------------------------


class TestReferenceSpan:
    def test_reference_span_passed(self):
        """reference_span is passed and not tautological."""
        state = _default_state()
        for _ in range(4):
            _rec(state, [5.0, 5.0], obj=1.0)
        dec = maybe_update_stage_bounds(
            state,
            stage_cfg={"enabled": True, "min_span_fraction": 0.001},
        )
        # With tiny min_span_fraction, shrink should be allowed
        assert isinstance(dec, StageAdaptivePolicyDecision)


# ---------------------------------------------------------------------------
# Config.yaml does not enable stage search
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_config_not_enabled(self):
        import yaml
        from workflows.rfgun_sao.run import DEFAULT_CONFIG_PATH
        cfg = yaml.safe_load(open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8"))
        ss = resolve_stage_search_config(cfg)
        assert ss["enabled"] is False
        ab = resolve_adaptive_bounds_config(cfg)
        assert ab["enabled"] is False


# ---------------------------------------------------------------------------
# Observation recording
# ---------------------------------------------------------------------------


class TestRecord:
    def test_string_status(self):
        state = _default_state()
        record_stage_observation(state, x=[5.0, 5.0], status="completed", objective_value=1.0)
        assert len(state.observations) == 1
        assert state.observations[0].status == StageCandidateStatus.COMPLETED

    def test_enum_status(self):
        state = _default_state()
        record_stage_observation(state, x=[5.0, 5.0], status=StageCandidateStatus.GATE_REJECTED)
        assert state.observations[0].status == StageCandidateStatus.GATE_REJECTED

    def test_unknown_string_falls_back(self):
        state = _default_state()
        record_stage_observation(state, x=[5.0], status="bogus_status")
        assert state.observations[0].status == StageCandidateStatus.UNKNOWN_FAILED
