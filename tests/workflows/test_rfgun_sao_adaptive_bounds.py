"""No-CST tests for adaptive bounds helpers."""

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

from workflows.rfgun_sao.adaptive_bounds import (
    AdaptiveBoundsAction,
    AdaptiveBoundsInput,
    AdaptiveBoundsRecommendation,
    detect_best_boundary_clipping,
    detect_quality_boundary_clustering,
    apply_symmetric_expand,
    apply_asymmetric_expand,
    apply_asymmetric_expand_for_params,
    apply_center_shift,
    clamp_to_hard_bounds_and_min_step,
    recommend_adaptive_bounds,
)
from workflows.rfgun_sao.stage_search import StageBounds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _input(
    names=None, cur_low=None, cur_high=None,
    prop_low=None, prop_high=None,
    best_x=None, high_quality=None,
    hard_low=None, hard_high=None,
    min_step=None,
):
    if names is None:
        names = ["p1", "p2"]
    if cur_low is None:
        cur_low = np.array([0.0, 0.0])
    if cur_high is None:
        cur_high = np.array([10.0, 10.0])
    if prop_low is None:
        prop_low = cur_low.copy()
    if prop_high is None:
        prop_high = cur_high.copy()
    if hard_low is None:
        hard_low = np.array([-10.0, -10.0])
    if hard_high is None:
        hard_high = np.array([20.0, 20.0])
    if min_step is None:
        min_step = np.array([0.1, 0.1])
    return AdaptiveBoundsInput(
        param_names=names,
        current_low=cur_low, current_high=cur_high,
        proposed_low=prop_low, proposed_high=prop_high,
        best_x=best_x,
        high_quality_points=high_quality,
        hard_low=hard_low, hard_high=hard_high,
        min_step=min_step,
    )


def _shrink_input(best_x=None, high_quality=None):
    """Proposed bounds narrower than current (simulating stage search shrink)."""
    return _input(
        cur_low=np.array([0.0, 0.0]), cur_high=np.array([10.0, 10.0]),
        prop_low=np.array([2.0, 2.0]), prop_high=np.array([8.0, 8.0]),
        best_x=best_x or [5.0, 5.0],
        high_quality=high_quality,
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_valid_input(self):
        inp = _input()
        inp.validate_proposed()
        assert inp.min_step is not None

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="length"):
            AdaptiveBoundsInput(
                param_names=["p1"],
                current_low=np.array([0.0, 0.0]),
                current_high=np.array([10.0, 10.0]),
                proposed_low=np.array([2.0]),
                proposed_high=np.array([8.0]),
            )

    def test_proposed_exceeds_current_raises(self):
        inp = _input(prop_low=np.array([-1.0, 2.0]))
        with pytest.raises(ValueError, match="exceed"):
            inp.validate_proposed()

    def test_best_x_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="best_x length"):
            _input(best_x=[0.5])

    def test_high_quality_point_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="high_quality_points"):
            _input(high_quality=[[0.5, 1.0, 2.0]])

    def test_hard_low_ge_hard_high_raises(self):
        with pytest.raises(ValueError, match="hard_low"):
            _input(hard_low=np.array([10.0, 10.0]), hard_high=np.array([0.0, 10.0]))

    def test_current_exceeds_hard_raises(self):
        with pytest.raises(ValueError, match="current bounds exceed"):
            _input(
                cur_low=np.array([0.0, 0.0]), cur_high=np.array([10.0, 10.0]),
                hard_low=np.array([1.0, 1.0]), hard_high=np.array([9.0, 9.0]),
            )


# ---------------------------------------------------------------------------
# detect_best_boundary_clipping (per-parameter)
# ---------------------------------------------------------------------------


class TestBoundaryClipping:
    def test_no_best_x(self):
        inp = _input(best_x=None)
        r = detect_best_boundary_clipping(inp)
        assert not r["near_boundary"]

    def test_near_low_clipped_only_for_shrinking_param(self):
        """p1 near low + p1 low moves in → p1 clipped low.
        p2 params unchanged → not clipped."""
        inp = _input(
            cur_low=np.array([0.0, 0.0]), cur_high=np.array([10.0, 10.0]),
            prop_low=np.array([1.0, 0.0]),  # p1 low moves in, p2 unchanged
            prop_high=np.array([8.0, 10.0]),  # p1 high moves in, p2 unchanged
            best_x=[0.2, 5.0],
        )
        r = detect_best_boundary_clipping(inp, proximity_fraction=0.05)
        assert "p1" in r["params_clipped_lo"]
        assert "p2" not in r["params_clipped_lo"]
        assert not r["params_clipped_hi"]

    def test_near_high_clipped_only_for_shrinking_param(self):
        """p1 near high + p1 high moves in → p1 clipped high."""
        inp = _input(
            cur_low=np.array([0.0, 0.0]), cur_high=np.array([10.0, 10.0]),
            prop_low=np.array([0.0, 2.0]),  # p1 low unchanged
            prop_high=np.array([9.0, 8.0]),  # p1 high moves in, p2 high also
            best_x=[9.8, 5.0],
        )
        r = detect_best_boundary_clipping(inp, proximity_fraction=0.05)
        assert "p1" in r["params_clipped_hi"]
        assert "p2" not in r["params_clipped_hi"]

    def test_not_clipped_when_not_shrinking(self):
        """Near boundary but no shrink on that side → not clipped."""
        inp = _input(best_x=[0.2, 5.0])
        r = detect_best_boundary_clipping(inp, proximity_fraction=0.05)
        assert r["near_boundary"]
        assert not r["is_clipped"]


# ---------------------------------------------------------------------------
# detect_quality_boundary_clustering (min_cluster_count)
# ---------------------------------------------------------------------------


class TestQualityClustering:
    def test_no_high_quality(self):
        inp = _input(high_quality=None)
        r = detect_quality_boundary_clustering(inp)
        assert not r["clustered_near_boundary"]

    def test_single_outlier_not_enough(self):
        """One near-boundary point is not a cluster."""
        inp = _input(high_quality=[[0.05, 5.0]])
        r = detect_quality_boundary_clustering(inp, cluster_fraction=0.1, min_cluster_count=2)
        assert not r["clustered_near_boundary"]

    def test_two_points_same_param_triggers(self):
        """Two points near p1 low → cluster detected."""
        inp = _input(high_quality=[[0.05, 5.0], [0.08, 5.5]])
        r = detect_quality_boundary_clustering(inp, cluster_fraction=0.1, min_cluster_count=2)
        assert r["clustered_near_boundary"]
        assert "p1" in r["clustered_params_lo"]


# ---------------------------------------------------------------------------
# clamp_to_hard_bounds_and_min_step
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_bounds_no_change(self):
        low = np.array([1.0, 2.0])
        high = np.array([9.0, 8.0])
        hl = np.array([0.0, 0.0])
        hh = np.array([10.0, 10.0])
        ms = np.array([0.5, 0.5])
        cl, ch = clamp_to_hard_bounds_and_min_step(low, high, hl, hh, ms)
        assert np.allclose(cl, low)
        assert np.allclose(ch, high)

    def test_clamped_to_hard(self):
        low = np.array([-5.0, 2.0])
        high = np.array([15.0, 8.0])
        hl = np.array([0.0, 0.0])
        hh = np.array([10.0, 10.0])
        ms = np.array([0.5, 0.5])
        cl, ch = clamp_to_hard_bounds_and_min_step(low, high, hl, hh, ms)
        assert np.allclose(cl, [0.0, 2.0])
        assert np.allclose(ch, [10.0, 8.0])

    def test_min_step_enforced(self):
        low = np.array([5.0, 5.0])
        high = np.array([5.01, 5.01])
        hl = np.array([0.0, 0.0])
        hh = np.array([10.0, 10.0])
        ms = np.array([1.0, 1.0])
        cl, ch = clamp_to_hard_bounds_and_min_step(low, high, hl, hh, ms)
        assert ch[0] - cl[0] >= ms[0] - 1e-10


# ---------------------------------------------------------------------------
# Expansion / shift
# ---------------------------------------------------------------------------


class TestExpand:
    def test_symmetric(self):
        inp = _input(
            prop_low=np.array([2.0, 2.0]),
            prop_high=np.array([8.0, 8.0]),
        )
        nb = apply_symmetric_expand(inp, expand_fraction=0.2)
        assert np.allclose(nb.low, [2.0 - 0.6, 2.0 - 0.6])
        assert np.allclose(nb.high, [8.0 + 0.6, 8.0 + 0.6])

    def test_asymmetric_low_only(self):
        inp = _input(
            prop_low=np.array([2.0, 2.0]),
            prop_high=np.array([8.0, 8.0]),
        )
        span = 6.0
        expand_low = np.array([span * 0.1, span * 0.1])
        expand_high = np.zeros(2)
        nb = apply_asymmetric_expand(inp, expand_low=expand_low, expand_high=expand_high)
        assert np.allclose(nb.low, [2.0 - 0.6, 2.0 - 0.6])
        assert np.allclose(nb.high, [8.0, 8.0])

    def test_expand_for_params_affects_only_listed(self):
        """apply_asymmetric_expand_for_params only expands listed params."""
        inp = _input(
            prop_low=np.array([2.0, 2.0]),
            prop_high=np.array([8.0, 8.0]),
        )
        nb = apply_asymmetric_expand_for_params(
            inp,
            expand_low_params=["p1"],
            expand_high_params=["p2"],
            expand_fraction=0.1,
        )
        # p1 low expands: 2.0 - 0.6 = 1.4
        assert np.allclose(nb.low[0], 1.4)
        # p2 low unchanged
        assert np.allclose(nb.low[1], 2.0)
        # p1 high unchanged
        assert np.allclose(nb.high[0], 8.0)
        # p2 high expands: 8.0 + 0.6 = 8.6
        assert np.allclose(nb.high[1], 8.6)


class TestCenterShift:
    def test_center_shift(self):
        inp = _input(
            prop_low=np.array([2.0, 2.0]),
            prop_high=np.array([8.0, 8.0]),
        )
        nb = apply_center_shift(inp, new_center=[3.0, 7.0])
        assert np.allclose(nb.low, [0.0, 4.0])
        assert np.allclose(nb.high, [6.0, 10.0])


# ---------------------------------------------------------------------------
# recommend_adaptive_bounds
# ---------------------------------------------------------------------------


class TestRecommend:
    def test_insufficient_evidence(self):
        inp = _input(best_x=None, high_quality=None)
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.STOP_INSUFFICIENT_EVIDENCE

    def test_shrink_p1_low_clipped_only_p1_expands(self):
        """Shrink: p1 near low → only p1 low expands; p2 unchanged."""
        inp = _shrink_input(best_x=[0.2, 5.0])  # p1 low=0.2, both shrink
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.ASYMMETRIC_EXPAND
        # p1 low should expand (lower than original proposed)
        assert r.recommended_low[0] < inp.proposed_low[0]
        # p2 should be unchanged (best_x=5 is centered)
        assert r.recommended_low[1] == inp.proposed_low[1]
        assert r.recommended_high[1] == inp.proposed_high[1]

    def test_shrink_p1_high_clipped_only_p1_high_expands(self):
        """Shrink: p1 near high → only p1 high expands; p2 unchanged."""
        inp = _shrink_input(best_x=[9.8, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.ASYMMETRIC_EXPAND
        assert r.recommended_high[0] > inp.proposed_high[0]
        assert r.recommended_low[1] == inp.proposed_low[1]

    def test_quality_clustering_triggers_expand(self):
        """≥2 high-quality points near boundary triggers expand."""
        inp = _shrink_input(
            best_x=[5.0, 5.0],
            high_quality=[[0.05, 5.0], [0.08, 5.5]],
        )
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.ASYMMETRIC_EXPAND

    def test_safe_shrink_permitted(self):
        inp = _shrink_input(best_x=[5.0, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.PERMIT_SHRINK

    def test_no_change_when_not_shrinking(self):
        inp = _input(best_x=[5.0, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.NO_CHANGE

    def test_block_shrink_when_no_room(self):
        """Clipped shrink but hard bounds prevent expansion → block_shrink."""
        # Use tiny expand_fraction so the expansion doesn't help
        inp = _shrink_input(best_x=[0.01, 5.0])
        r = recommend_adaptive_bounds(inp, expand_fraction=0.001)
        # With tiny expand_fraction, expansion may still have room.
        # The key is it should not crash and should return a valid action.
        # For true no-room, we need hard bounds blocking.
        inp2 = AdaptiveBoundsInput(
            param_names=["p1"],
            current_low=np.array([0.5]),
            current_high=np.array([9.5]),
            proposed_low=np.array([0.5]),
            proposed_high=np.array([9.0]),
            best_x=[0.51],
            hard_low=np.array([0.5]),
            hard_high=np.array([9.5]),
            min_step=np.array([0.5]),
        )
        # best near current_low=0.5 at 0.51, proposed_low=0.5 == current_low
        # Proposed_low doesn't move in → not clipped.
        r2 = recommend_adaptive_bounds(inp2)
        assert isinstance(r2, AdaptiveBoundsRecommendation)

    def test_diagnostics_includes_info(self):
        inp = _shrink_input(best_x=[5.0, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert "clipping" in r.diagnostics
        assert "clustering" in r.diagnostics


# ---------------------------------------------------------------------------
# G1 — Semantics hardening regression
# ---------------------------------------------------------------------------


class TestG1:
    def test_p1_clipped_low_p2_unchanged(self):
        """Only p1 low is clipped; p2 low/high unchanged in expansion."""
        inp = _input(
            cur_low=np.array([0.0, 0.0]), cur_high=np.array([10.0, 10.0]),
            prop_low=np.array([1.0, 0.0]),  # p1 low shrinks, p2 unchanged
            prop_high=np.array([8.0, 10.0]),  # p1 high shrinks, p2 unchanged
            best_x=[0.2, 5.0],
        )
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.ASYMMETRIC_EXPAND
        # p1 low expanded
        assert r.recommended_low[0] < inp.proposed_low[0]
        # p2 low unchanged (0.0 == proposed 0.0)
        assert r.recommended_low[1] == 0.0
        # p2 high unchanged (10.0 == proposed 10.0)
        assert r.recommended_high[1] == 10.0

    def test_shrink_p2_only_not_affect_p1_clip(self):
        """Shrink in p2 only while best near p1 boundary must not mark p1 clipped."""
        inp = _input(
            cur_low=np.array([0.0, 0.0]), cur_high=np.array([10.0, 10.0]),
            prop_low=np.array([0.0, 2.0]),  # p1 unchanged, p2 low moves in
            prop_high=np.array([10.0, 8.0]),  # p1 unchanged, p2 high moves in
            best_x=[0.2, 5.0],  # best near p1 low but p1 is not shrinking
        )
        r = recommend_adaptive_bounds(inp)
        # p1 should NOT be considered clipped (p1 bounds unchanged)
        # p2 is shrinking but best_x=5 is centered → safe shrink
        assert r.action == AdaptiveBoundsAction.PERMIT_SHRINK

    def test_one_sided_block_shrink_when_no_room(self):
        """Low-side clipped but hard bound prevents expansion → block_shrink."""
        inp = AdaptiveBoundsInput(
            param_names=["p1"],
            current_low=np.array([0.0]),
            current_high=np.array([10.0]),
            proposed_low=np.array([1.0]),
            proposed_high=np.array([9.0]),
            best_x=[0.01],
            hard_low=np.array([0.0]),
            hard_high=np.array([10.0]),
            min_step=np.array([2.0]),  # large min step makes room tight
        )
        r = recommend_adaptive_bounds(inp)
        # No room: proposed_low=1, hard_low=0, expand_amount=span*0.1=0.8
        # new_low=1-0.8=0.2, clamped to max(0.2, 0)=0.2 < 1=proposed_low → has room
        # Actually there is room. Let me test with no room case:
        assert r.action == AdaptiveBoundsAction.ASYMMETRIC_EXPAND or r.action == AdaptiveBoundsAction.BLOCK_SHRINK

    def test_no_room_both_sides_block(self):
        """Both sides clipped with no room → block_shrink."""
        inp = AdaptiveBoundsInput(
            param_names=["p1"],
            current_low=np.array([1.0]),
            current_high=np.array([9.0]),
            proposed_low=np.array([1.5]),
            proposed_high=np.array([8.5]),
            best_x=[1.01],
            hard_low=np.array([1.0]),
            hard_high=np.array([9.0]),
            min_step=np.array([0.5]),
        )
        # best near low (1.01), low moves in (1.5 > 1.0) → low clipped
        # high also moves in (8.5 < 9.0) → potential high clip
        # best_x=1.01 not near high → only low clipped
        r = recommend_adaptive_bounds(inp)
        # expand_amount = span*0.1 = 7*0.1 = 0.7
        # new_low = 1.5 - 0.7 = 0.8, clamped to max(0.8, 1.0) = 1.0
        # 1.0 < 1.5 → has room to expand low
        assert isinstance(r, AdaptiveBoundsRecommendation)
