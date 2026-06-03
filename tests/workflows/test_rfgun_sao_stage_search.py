"""No-CST tests for stage search helpers in workflows/rfgun_sao/stage_search.py."""

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
    StageCandidateStatus,
    StageObservation,
    StageBounds,
    StageSummary,
    StageTransitionAction,
    StageTransitionDecision,
    summarize_stage_observations,
    select_best_completed,
    select_most_feasible_point,
    detect_boundary_proximity,
    decide_stage_transition,
    make_recentered_bounds,
    make_shrunk_bounds,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _bounds(names=None, low=None, high=None):
    if names is None:
        names = ["p1", "p2"]
    if low is None:
        low = np.array([0.0, 0.0])
    if high is None:
        high = np.array([10.0, 10.0])
    return StageBounds(param_names=names, low=low, high=high)


def _obs(x, status=StageCandidateStatus.COMPLETED, obj=1.0,
         gate=True, cal=True, solv=True, retries=0, reused=False):
    return StageObservation(
        x=list(x), status=status, objective_value=obj,
        gate_pass=gate, calibration_pass=cal, solver_ok=solv,
        retry_attempts=retries, reused=reused,
    )


# ---------------------------------------------------------------------------
# StageBounds validation
# ---------------------------------------------------------------------------


class TestStageBounds:
    def test_valid(self):
        b = _bounds()
        assert b.n_params == 2
        assert np.allclose(b.span, [10.0, 10.0])

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="length mismatch"):
            StageBounds(param_names=["p1"], low=np.array([0.0, 0.0]), high=np.array([10.0, 10.0]))

    def test_low_ge_high_raises(self):
        with pytest.raises(ValueError, match="strictly less"):
            StageBounds(param_names=["p1"], low=np.array([10.0]), high=np.array([5.0]))


# ---------------------------------------------------------------------------
# summarize_stage_observations
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_empty(self):
        b = _bounds()
        s = summarize_stage_observations([], b)
        assert s.proposed_count == 0
        assert s.actual_cst_solves_count == 0

    def test_mixed_status(self):
        b = _bounds()
        obs = [
            _obs([1.0, 1.0], obj=0.5),
            _obs([2.0, 2.0], status=StageCandidateStatus.GATE_REJECTED),
            _obs([3.0, 3.0], status=StageCandidateStatus.CALIBRATION_FAILED),
            _obs([4.0, 4.0], status=StageCandidateStatus.SOLVER_FAILED),
            _obs([5.0, 5.0], obj=1.5, reused=True),
        ]
        s = summarize_stage_observations(obs, b)
        assert s.proposed_count == 5
        assert s.database_reused_count == 1
        assert s.actual_cst_solves_count == 4
        assert s.completed_count == 2  # one completed is reused
        assert s.gate_rejected_count == 1
        assert s.calibration_failed_count == 1
        assert s.solver_failed_count == 1
        assert s.best_objective_value == 0.5
        assert s.best_x == [1.0, 1.0]


# ---------------------------------------------------------------------------
# select_best_completed
# ---------------------------------------------------------------------------


class TestSelectBest:
    def test_best_among_completed(self):
        obs = [
            _obs([1.0], obj=2.0),
            _obs([2.0], obj=0.5),
            _obs([3.0], obj=1.0),
        ]
        best = select_best_completed(obs)
        assert best is not None
        val, x = best
        assert val == 0.5
        assert x == [2.0]

    def test_no_completed(self):
        obs = [_obs([1.0], status=StageCandidateStatus.GATE_REJECTED)]
        assert select_best_completed(obs) is None


# ---------------------------------------------------------------------------
# select_most_feasible_point
# ---------------------------------------------------------------------------


class TestMostFeasible:
    def test_prefers_completed_lowest_obj(self):
        obs = [
            _obs([5.0], obj=2.0),
            _obs([1.0], obj=0.5),
            _obs([3.0], status=StageCandidateStatus.GATE_REJECTED),
        ]
        pt = select_most_feasible_point(obs)
        assert pt == [1.0]

    def test_no_completed_falls_to_gate_rejected(self):
        obs = [
            _obs([5.0], status=StageCandidateStatus.GATE_REJECTED),
            _obs([3.0], status=StageCandidateStatus.CALIBRATION_FAILED),
        ]
        pt = select_most_feasible_point(obs)
        assert pt == [5.0]

    def test_no_completed_no_gate_falls_to_cal_failed(self):
        obs = [
            _obs([7.0], status=StageCandidateStatus.CALIBRATION_FAILED),
        ]
        pt = select_most_feasible_point(obs)
        assert pt == [7.0]

    def test_empty_returns_none(self):
        assert select_most_feasible_point([]) is None


# ---------------------------------------------------------------------------
# detect_boundary_proximity
# ---------------------------------------------------------------------------


class TestBoundaryProximity:
    def test_best_near_low(self):
        b = _bounds()
        obs = [_obs([0.1, 5.0], obj=0.5)]
        info = detect_boundary_proximity(obs, b)
        assert info["near_boundary"]
        assert "p1" in info["params_near_boundary"]

    def test_best_center_no_trigger(self):
        b = _bounds()
        obs = [_obs([5.0, 5.0], obj=0.5)]
        info = detect_boundary_proximity(obs, b)
        assert not info["near_boundary"]

    def test_no_completed_returns_false(self):
        b = _bounds()
        obs = [_obs([5.0], status=StageCandidateStatus.GATE_REJECTED)]
        info = detect_boundary_proximity(obs, b)
        assert not info["near_boundary"]


# ---------------------------------------------------------------------------
# decide_stage_transition
# ---------------------------------------------------------------------------


class TestDecideTransition:
    def test_max_stages_stops(self):
        b = _bounds()
        s = StageSummary()
        d = decide_stage_transition(s, b, [], max_stages=5, current_stage=5)
        assert d.action == StageTransitionAction.STOP

    def test_no_evidence_continues(self):
        b = _bounds()
        s = StageSummary()
        d = decide_stage_transition(s, b, [])
        assert d.action == StageTransitionAction.CONTINUE_CURRENT

    def test_high_cal_solv_fail_recenters(self):
        b = _bounds()
        obs = [
            _obs([1.0, 1.0], status=StageCandidateStatus.CALIBRATION_FAILED),
            _obs([2.0, 2.0], status=StageCandidateStatus.CALIBRATION_FAILED),
            _obs([3.0, 3.0], status=StageCandidateStatus.CALIBRATION_FAILED),
        ]
        s = summarize_stage_observations(obs, b)
        d = decide_stage_transition(s, b, obs, high_fail_rate=0.3)
        assert d.action == StageTransitionAction.RECENTER or d.action == StageTransitionAction.SHIFT

    def test_high_gate_rej_recenters(self):
        b = _bounds()
        obs = [
            _obs([1.0, 1.0], status=StageCandidateStatus.GATE_REJECTED),
            _obs([2.0, 2.0], status=StageCandidateStatus.GATE_REJECTED),
            _obs([3.0, 3.0], status=StageCandidateStatus.GATE_REJECTED),
        ]
        s = summarize_stage_observations(obs, b)
        d = decide_stage_transition(s, b, obs, high_fail_rate=0.3)
        assert d.action in (StageTransitionAction.RECENTER, StageTransitionAction.SHIFT)

    def test_best_near_boundary_requests_review(self):
        b = _bounds()
        obs = [
            _obs([0.05, 5.0], obj=0.5),
            _obs([3.0, 5.0], obj=1.0),
            _obs([7.0, 5.0], obj=1.5),
        ]
        s = summarize_stage_observations(obs, b)
        d = decide_stage_transition(s, b, obs, min_completed_fraction=0.2)
        # Best at 0.05 is near low boundary
        assert d.action == StageTransitionAction.REQUEST_ADAPTIVE_REVIEW

    def test_sufficient_completed_shrinks(self):
        b = _bounds()
        obs = [
            _obs([3.0, 3.0], obj=0.5),
            _obs([5.0, 5.0], obj=1.0),
            _obs([7.0, 7.0], obj=1.5),
            _obs([4.0, 4.0], obj=0.8),
        ]
        s = summarize_stage_observations(obs, b)
        d = decide_stage_transition(s, b, obs, min_completed_fraction=0.2)
        assert d.action == StageTransitionAction.SHRINK
        assert d.proposed_bounds is not None

    def test_insufficient_completed_continues(self):
        b = _bounds()
        obs = [
            _obs([5.0, 5.0], obj=1.0),
            _obs([5.0, 5.0], status=StageCandidateStatus.GATE_REJECTED),
        ]
        s = summarize_stage_observations(obs, b)
        d = decide_stage_transition(s, b, obs, min_completed_fraction=0.6,
                                    high_fail_rate=0.8)
        assert d.action == StageTransitionAction.CONTINUE_CURRENT

    def test_accounting_distinguishes_reused(self):
        b = _bounds()
        obs = [
            _obs([1.0], obj=0.5, reused=False),
            _obs([2.0], obj=1.0, reused=True),
            _obs([3.0], status=StageCandidateStatus.GATE_REJECTED),
        ]
        s = summarize_stage_observations(obs, b)
        assert s.proposed_count == 3
        assert s.database_reused_count == 1
        assert s.actual_cst_solves_count == 2

    def test_reused_not_counted_as_solve(self):
        """Database-reused observations do not inflate solve count."""
        b = _bounds()
        obs = [
            _obs([1.0], obj=0.5, reused=False),
            _obs([2.0], obj=1.0, reused=True),
        ]
        s = summarize_stage_observations(obs, b)
        assert s.actual_cst_solves_count == 1


# ---------------------------------------------------------------------------
# make_recentered_bounds / make_shrunk_bounds
# ---------------------------------------------------------------------------


class TestRecenteredBounds:
    def test_recenter_around_best(self):
        b = _bounds()
        obs = [_obs([2.0, 8.0], obj=0.5)]
        nb = make_recentered_bounds(obs, b, shrink_factor=0.5)
        # center around [2, 8], half-span 2.5, clamped to [0, 10]
        assert np.allclose(nb.low, [0.0, 8.0 - 2.5], atol=1e-6)  # p1 clamped to 0
        assert np.allclose(nb.high, [2.0 + 2.5, 10.0], atol=1e-6)  # p2 clamped to 10

    def test_shrink_clamped_to_bounds(self):
        b = _bounds(low=np.array([0.0, 0.0]), high=np.array([10.0, 10.0]))
        obs = [_obs([0.5, 9.5], obj=0.5)]
        nb = make_shrunk_bounds(obs, b, shrink_factor=1.0)
        assert np.all(nb.low >= b.low)
        assert np.all(nb.high <= b.high)

# ---------------------------------------------------------------------------
# F1 �� Semantics hardening
# ---------------------------------------------------------------------------


class TestF1DatabaseReused:
    def test_database_reused_status_counts_as_reused(self):
        """DATABASE_REUSED status without reused=True flag is counted as reused."""
        b = _bounds()
        obs = [
            _obs([1.0], obj=0.5, reused=True),
            StageObservation(
                x=[2.0], status=StageCandidateStatus.DATABASE_REUSED,
                objective_value=1.0, reused=False,
            ),
            _obs([3.0], obj=2.0, reused=False),
        ]
        s = summarize_stage_observations(obs, b)
        assert s.database_reused_count == 2
        assert s.actual_cst_solves_count == 1

    def test_reused_completed_not_inflate_rate(self):
        """Multiple reused completed observations do not push valid_completed_rate > 1.0."""
        b = _bounds()
        obs = [
            _obs([1.0], obj=0.5, reused=True),
            _obs([2.0], obj=1.0, reused=True),
            _obs([3.0], obj=0.8, reused=True),
        ]
        s = summarize_stage_observations(obs, b)
        # All 3 are reused, so solves = 3-3 = 0, but rate denominator = max(0,1) = 1
        assert s.actual_cst_solves_count == 0
        assert s.valid_completed_rate <= 1.0


class TestF1MinSpan:
    def test_min_span_reached_blocks_shrink(self):
        """Min-span reached: shrink is blocked, not returned."""
        b = _bounds()
        # Create a reference span much larger than current bounds
        ref_span = np.array([100.0, 100.0])
        obs = [
            _obs([3.0, 3.0], obj=0.5),
            _obs([5.0, 5.0], obj=1.0),
            _obs([7.0, 7.0], obj=1.5),
            _obs([4.0, 4.0], obj=0.8),
        ]
        s = summarize_stage_observations(obs, b)
        # min_span = 100 * 0.05 = 5, current span = 10, so 10 < 5 is False
        # But need to make min_span > 10 to block: use min_span_fraction=0.2 or ref_span=200
        d = decide_stage_transition(
            s, b, obs,
            reference_span=np.array([200.0, 200.0]),
            min_span_fraction=0.1,  # min_span = 20, current span = 10 -> blocked
            min_completed_fraction=0.2,
        )
        # When min span is reached, shrink is blocked. With all 4 completed
        # and best not near boundary, the policy should still not return SHRINK.
        assert d.action != StageTransitionAction.SHRINK

    def test_min_span_not_reached_allows_shrink(self):
        """Min-span not reached + stable evidence -> shrink allowed."""
        b = _bounds()
        ref_span = np.array([100.0, 100.0])
        obs = [
            _obs([3.0, 3.0], obj=0.5),
            _obs([5.0, 5.0], obj=1.0),
            _obs([7.0, 7.0], obj=1.5),
            _obs([4.0, 4.0], obj=0.8),
        ]
        s = summarize_stage_observations(obs, b)
        # min_span = 100 * 0.01 = 1, current span = 10 > 1 -> shrink allowed
        d = decide_stage_transition(
            s, b, obs,
            reference_span=ref_span,
            min_span_fraction=0.01,
            min_completed_fraction=0.2,
        )
        assert d.action == StageTransitionAction.SHRINK


class TestF1HighFailRate:
    def test_high_gate_reject_recenters_not_shrink(self):
        """High gate reject still triggers RECENTER, not SHRINK."""
        b = _bounds()
        obs = [
            _obs([1.0, 1.0], status=StageCandidateStatus.GATE_REJECTED),
            _obs([2.0, 2.0], status=StageCandidateStatus.GATE_REJECTED),
            _obs([3.0, 3.0], status=StageCandidateStatus.GATE_REJECTED),
        ]
        s = summarize_stage_observations(obs, b)
        d = decide_stage_transition(s, b, obs, high_fail_rate=0.3)
        assert d.action in (StageTransitionAction.RECENTER, StageTransitionAction.SHIFT)

    def test_high_cal_solv_fail_recenters_not_shrink(self):
        """High calibration/solver fail still triggers RECENTER, not SHRINK."""
        b = _bounds()
        obs = [
            _obs([1.0, 1.0], status=StageCandidateStatus.CALIBRATION_FAILED),
            _obs([2.0, 2.0], status=StageCandidateStatus.CALIBRATION_FAILED),
            _obs([3.0, 3.0], status=StageCandidateStatus.SOLVER_FAILED),
        ]
        s = summarize_stage_observations(obs, b)
        d = decide_stage_transition(s, b, obs, high_fail_rate=0.3)
        assert d.action in (StageTransitionAction.RECENTER, StageTransitionAction.SHIFT)


class TestF1BoundaryReview:
    def test_best_near_boundary_requests_review(self):
        """Best near boundary still returns REQUEST_ADAPTIVE_REVIEW."""
        b = _bounds()
        obs = [
            _obs([0.05, 5.0], obj=0.5),
            _obs([3.0, 5.0], obj=1.0),
            _obs([7.0, 5.0], obj=1.5),
        ]
        s = summarize_stage_observations(obs, b)
        d = decide_stage_transition(s, b, obs, min_completed_fraction=0.2)
        assert d.action == StageTransitionAction.REQUEST_ADAPTIVE_REVIEW
