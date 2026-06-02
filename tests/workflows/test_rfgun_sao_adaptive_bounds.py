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


# ---------------------------------------------------------------------------
# detect_best_boundary_clipping
# ---------------------------------------------------------------------------


class TestBoundaryClipping:
    def test_no_best_x(self):
        inp = _input(best_x=None)
        r = detect_best_boundary_clipping(inp)
        assert not r["near_boundary"]

    def test_near_low_boundary(self):
        inp = _input(
            cur_low=np.array([0.0, 0.0]), cur_high=np.array([10.0, 10.0]),
            prop_low=np.array([0.5, 2.0]), prop_high=np.array([8.0, 8.0]),
            best_x=[0.2, 5.0],
        )
        r = detect_best_boundary_clipping(inp, proximity_fraction=0.05)
        assert r["near_boundary"]
        assert "p1" in r["params_near_boundary_lo"]
        assert r["is_clipped"]  # proposed_low=0.5 > current_low=0.0 + best_x=0.2 near low

    def test_not_clipped_when_not_shrinking(self):
        inp = _input(best_x=[0.2, 5.0])
        r = detect_best_boundary_clipping(inp, proximity_fraction=0.05)
        assert r["near_boundary"]
        assert not r["is_clipped"]  # proposed bounds == current bounds


# ---------------------------------------------------------------------------
# detect_quality_boundary_clustering
# ---------------------------------------------------------------------------


class TestQualityClustering:
    def test_no_high_quality(self):
        inp = _input(high_quality=None)
        r = detect_quality_boundary_clustering(inp)
        assert not r["clustered_near_boundary"]

    def test_clustered_low(self):
        inp = _input(
            high_quality=[[0.05, 5.0], [0.08, 5.5]],
        )
        r = detect_quality_boundary_clustering(inp, cluster_fraction=0.1)
        assert r["clustered_near_boundary"]
        assert "p1" in r["clustered_params_lo"]
        assert "p1" not in r["clustered_params_hi"]


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
        high = np.array([5.01, 5.01])  # span = 0.01
        hl = np.array([0.0, 0.0])
        hh = np.array([10.0, 10.0])
        ms = np.array([1.0, 1.0])  # min_step = 1.0 > span
        cl, ch = clamp_to_hard_bounds_and_min_step(low, high, hl, hh, ms)
        assert ch[0] - cl[0] >= ms[0] - 1e-10  # span should be >= min_step


# ---------------------------------------------------------------------------
# apply_symmetric_expand / apply_asymmetric_expand / apply_center_shift
# ---------------------------------------------------------------------------


class TestExpand:
    def test_symmetric(self):
        inp = _input(
            prop_low=np.array([2.0, 2.0]),
            prop_high=np.array([8.0, 8.0]),
        )
        nb = apply_symmetric_expand(inp, expand_fraction=0.2)
        # span = 6, expand = 6 * 0.2 / 2 = 0.6 on each side
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

    def test_center_shift(self):
        inp = _input(
            prop_low=np.array([2.0, 2.0]),
            prop_high=np.array([8.0, 8.0]),
        )
        nb = apply_center_shift(inp, new_center=[3.0, 7.0])
        # span = 6, shifted to center [3, 7]
        assert np.allclose(nb.low, [0.0, 4.0])  # 3-3=0, 7-3=4
        assert np.allclose(nb.high, [6.0, 10.0])  # 3+3=6, 7+3=10


# ---------------------------------------------------------------------------
# recommend_adaptive_bounds
# ---------------------------------------------------------------------------


class TestRecommend:
    def test_insufficient_evidence(self):
        inp = _input(best_x=None, high_quality=None)
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.STOP_INSUFFICIENT_EVIDENCE

    def test_shrink_best_near_low_anti_clip(self):
        """Shrink with best near low -> asymmetric expand low."""
        inp = _shrink_input(best_x=[0.2, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.ASYMMETRIC_EXPAND
        # Low side should be expanded (recommended_low < proposed_low)
        assert r.recommended_low[0] < inp.proposed_low[0]

    def test_shrink_best_near_high_anti_clip(self):
        """Shrink with best near high -> asymmetric expand high."""
        inp = _shrink_input(best_x=[9.8, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.ASYMMETRIC_EXPAND
        assert r.recommended_high[0] > inp.proposed_high[0]

    def test_quality_clustering_triggers_expand(self):
        """High-quality points clustered near boundary triggers expand."""
        inp = _shrink_input(
            best_x=[5.0, 5.0],
            high_quality=[[0.05, 5.0], [0.08, 5.5]],
        )
        r = recommend_adaptive_bounds(inp)
        assert r.action in (AdaptiveBoundsAction.ASYMMETRIC_EXPAND, AdaptiveBoundsAction.SYMMETRIC_EXPAND)

    def test_safe_shrink_permitted(self):
        """Centered best, no clipping, no clustering -> permit shrink."""
        inp = _shrink_input(best_x=[5.0, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.PERMIT_SHRINK

    def test_no_change_when_not_shrinking(self):
        """Proposed == current, no clipping -> no_change."""
        inp = _input(best_x=[5.0, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.NO_CHANGE

    def test_block_shrink_when_no_room(self):
        """Both sides clipped but no hard room -> block_shrink."""
        inp = AdaptiveBoundsInput(
            param_names=["p1"],
            current_low=np.array([0.0]),
            current_high=np.array([10.0]),
            proposed_low=np.array([0.0]),  # not shrinking (== current_low)
            proposed_high=np.array([10.0]),
            best_x=[0.01],
            hard_low=np.array([0.0]),
            hard_high=np.array([10.0]),
            min_step=np.array([0.1]),
        )
        r = recommend_adaptive_bounds(inp)
        assert r.action == AdaptiveBoundsAction.NO_CHANGE  # not shrinking, so no anti-clip

    def test_diagnostics_includes_info(self):
        inp = _shrink_input(best_x=[5.0, 5.0])
        r = recommend_adaptive_bounds(inp)
        assert "clipping" in r.diagnostics
        assert "clustering" in r.diagnostics
