"""No-CST tests for stage + adaptive integration policy."""

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
    StageObservation,
    StageSummary,
    StageTransitionAction,
    StageTransitionDecision,
)
from workflows.rfgun_sao.adaptive_bounds import AdaptiveBoundsAction
from workflows.rfgun_sao.stage_adaptive_policy import (
    StageAdaptiveAction,
    StageAdaptivePolicyInput,
    StageAdaptivePolicyDecision,
    combine_stage_and_adaptive_decisions,
    build_adaptive_input_from_stage_decision,
    extract_high_quality_points,
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


def _obs(x, status="completed", obj=1.0):
    return StageObservation(
        x=list(x), status=status,
        objective_value=obj,
        gate_pass=True, calibration_pass=True, solver_ok=True,
    )


def _completed_obs(x_vals, obj_vals):
    return [_obs(x, obj=v) for x, v in zip(x_vals, obj_vals)]


def _policy_inp(
    bounds=None,
    stage_dec=None,
    obs=None,
    hard_low=None,
    hard_high=None,
):
    if bounds is None:
        bounds = _bounds()
    if stage_dec is None:
        stage_dec = StageTransitionDecision(
            action=StageTransitionAction.CONTINUE_CURRENT,
        )
    if obs is None:
        obs = _completed_obs([[5.0, 5.0]], [1.0])
    return StageAdaptivePolicyInput(
        current_bounds=bounds,
        stage_decision=stage_dec,
        observations=obs,
        hard_low=hard_low,
        hard_high=hard_high,
    )


# ---------------------------------------------------------------------------
# extract_high_quality_points
# ---------------------------------------------------------------------------


class TestExtract:
    def test_returns_best_sorted(self):
        obs = _completed_obs([[5.0, 5.0], [2.0, 2.0], [8.0, 8.0]], [5.0, 1.0, 3.0])
        pts = extract_high_quality_points(obs)
        assert pts == [[2.0, 2.0], [8.0, 8.0], [5.0, 5.0]]

    def test_max_count_respected(self):
        obs = _completed_obs([[1.0], [2.0], [3.0], [4.0]], [1.0, 2.0, 3.0, 4.0])
        pts = extract_high_quality_points(obs, max_count=2)
        assert len(pts) == 2

    def test_skips_non_completed(self):
        obs = [
            _obs([1.0], obj=0.5),
            StageObservation(x=[2.0], status="gate_rejected"),
        ]
        pts = extract_high_quality_points(obs)
        assert pts == [[1.0]]


# ---------------------------------------------------------------------------
# build_adaptive_input_from_stage_decision
# ---------------------------------------------------------------------------


class TestBuildAdaptiveInput:
    def test_returns_none_without_best(self):
        inp = _policy_inp(obs=[])
        result = build_adaptive_input_from_stage_decision(inp)
        assert result is None

    def test_returns_valid_input_with_obs(self):
        stage_dec = StageTransitionDecision(
            action=StageTransitionAction.SHRINK,
            proposed_bounds=_bounds(low=np.array([2.0, 2.0]), high=np.array([8.0, 8.0])),
        )
        inp = _policy_inp(stage_dec=stage_dec, obs=_completed_obs([[3.0, 3.0]], [0.5]))
        result = build_adaptive_input_from_stage_decision(inp)
        assert result is not None
        assert len(result.param_names) == 2


# ---------------------------------------------------------------------------
# combine_stage_and_adaptive_decisions
# ---------------------------------------------------------------------------


class TestCombine:
    def test_stop(self):
        dec = StageTransitionDecision(action=StageTransitionAction.STOP, reason="max stages")
        inp = _policy_inp(stage_dec=dec)
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.STOP
        assert r.stage_action == StageTransitionAction.STOP

    def test_continue_current(self):
        dec = StageTransitionDecision(action=StageTransitionAction.CONTINUE_CURRENT)
        inp = _policy_inp(stage_dec=dec)
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.CONTINUE_CURRENT

    def test_recenter_preserved(self):
        dec = StageTransitionDecision(
            action=StageTransitionAction.RECENTER,
            reason="high fail rate",
            proposed_center=[3.0, 3.0],
            proposed_bounds=_bounds(
                low=np.array([1.0, 1.0]), high=np.array([5.0, 5.0]),
            ),
        )
        inp = _policy_inp(stage_dec=dec)
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.USE_STAGE_DECISION

    def test_shrink_centered_permitted(self):
        """SHRINK + centered best → adaptive permits → USE_STAGE_DECISION."""
        dec = StageTransitionDecision(
            action=StageTransitionAction.SHRINK,
            proposed_bounds=_bounds(
                low=np.array([2.0, 2.0]), high=np.array([8.0, 8.0]),
            ),
        )
        inp = _policy_inp(
            stage_dec=dec,
            obs=_completed_obs([[5.0, 5.0]], [1.0]),
        )
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.USE_STAGE_DECISION

    def test_shrink_best_near_low_uses_adaptive(self):
        """SHRINK + best near low → adaptive expands → USE_ADAPTIVE_BOUNDS."""
        dec = StageTransitionDecision(
            action=StageTransitionAction.SHRINK,
            proposed_bounds=_bounds(
                low=np.array([2.0, 2.0]), high=np.array([8.0, 8.0]),
            ),
        )
        inp = _policy_inp(
            stage_dec=dec,
            obs=_completed_obs([[0.2, 5.0]], [1.0]),
        )
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.USE_ADAPTIVE_BOUNDS
        assert r.adaptive_action in (
            AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
            AdaptiveBoundsAction.SYMMETRIC_EXPAND,
        )

    def test_shrink_best_near_high_uses_adaptive(self):
        """SHRINK + best near high → adaptive expands → USE_ADAPTIVE_BOUNDS."""
        dec = StageTransitionDecision(
            action=StageTransitionAction.SHRINK,
            proposed_bounds=_bounds(
                low=np.array([2.0, 2.0]), high=np.array([8.0, 8.0]),
            ),
        )
        inp = _policy_inp(
            stage_dec=dec,
            obs=_completed_obs([[9.8, 5.0]], [1.0]),
        )
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.USE_ADAPTIVE_BOUNDS

    def test_adaptive_review_expands(self):
        """REQUEST_ADAPTIVE_REVIEW with best near boundary and proposed shrink."""
        # Simulate stage wanting to shrink but requesting adaptive review first
        dec = StageTransitionDecision(
            action=StageTransitionAction.REQUEST_ADAPTIVE_REVIEW,
            reason="best near boundary",
            proposed_bounds=_bounds(
                low=np.array([2.0, 2.0]), high=np.array([8.0, 8.0]),
            ),
        )
        inp = _policy_inp(
            stage_dec=dec,
            obs=_completed_obs([[0.2, 5.0]], [1.0]),
        )
        r = combine_stage_and_adaptive_decisions(inp)
        # With best near 0.2 and proposed_low=2 > current_low=0, low is clipped
        assert r.action == StageAdaptiveAction.USE_ADAPTIVE_BOUNDS

    def test_adaptive_review_no_change(self):
        """REQUEST_ADAPTIVE_REVIEW + no clipping → USE_STAGE_DECISION."""
        dec = StageTransitionDecision(
            action=StageTransitionAction.REQUEST_ADAPTIVE_REVIEW,
        )
        inp = _policy_inp(
            stage_dec=dec,
            obs=_completed_obs([[5.0, 5.0]], [1.0]),
        )
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.USE_STAGE_DECISION

    def test_diagnostics_includes_actions(self):
        dec = StageTransitionDecision(action=StageTransitionAction.SHRINK, proposed_bounds=_bounds(
            low=np.array([2.0, 2.0]), high=np.array([8.0, 8.0]),
        ))
        inp = _policy_inp(stage_dec=dec, obs=_completed_obs([[5.0, 5.0]], [1.0]))
        r = combine_stage_and_adaptive_decisions(inp)
        assert "stage_action" in r.diagnostics
        assert "adaptive_action" in r.diagnostics


class TestEdgeCases:
    def test_shrink_no_best_evidence(self):
        """SHRINK with no best evidence → falls back to stage decision."""
        dec = StageTransitionDecision(
            action=StageTransitionAction.SHRINK,
            proposed_bounds=_bounds(
                low=np.array([2.0, 2.0]), high=np.array([8.0, 8.0]),
            ),
        )
        inp = _policy_inp(stage_dec=dec, obs=[])
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.USE_STAGE_DECISION

    def test_adaptive_review_insufficient_evidence(self):
        """REQUEST_ADAPTIVE_REVIEW with no best evidence → CONTINUE."""
        dec = StageTransitionDecision(
            action=StageTransitionAction.REQUEST_ADAPTIVE_REVIEW,
        )
        inp = _policy_inp(stage_dec=dec, obs=[])
        r = combine_stage_and_adaptive_decisions(inp)
        assert r.action == StageAdaptiveAction.CONTINUE_CURRENT
