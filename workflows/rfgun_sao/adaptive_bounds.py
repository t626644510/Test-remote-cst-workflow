# Adaptive bounds helpers for the RF gun SAO workflow.
# Protection layer for stage search — prevents premature local optimum trapping.
# No CST dependency, no runtime wiring yet.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from workflows.rfgun_sao.stage_search import StageBounds


# ---------------------------------------------------------------------------
# Action taxonomy
# ---------------------------------------------------------------------------


class AdaptiveBoundsAction(str, Enum):
    """Recommended action after reviewing proposed bounds."""
    NO_CHANGE = "no_change"
    SYMMETRIC_EXPAND = "symmetric_expand"
    ASYMMETRIC_EXPAND = "asymmetric_expand"
    SHIFT_CENTER = "shift_center"
    BLOCK_SHRINK = "block_shrink"
    PERMIT_SHRINK = "permit_shrink"
    STOP_INSUFFICIENT_EVIDENCE = "stop_insufficient_evidence"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class AdaptiveBoundsInput:
    """Input data for adaptive bounds review.

    Parameters
    ----------
    param_names : list[str]
        Ordered parameter names.
    current_low : np.ndarray
        Current stage lower bounds.
    current_high : np.ndarray
        Current stage upper bounds.
    proposed_low : np.ndarray
        Next-stage nominal lower bounds from stage search.
    proposed_high : np.ndarray
        Next-stage nominal upper bounds from stage search.
    hard_low : np.ndarray or None
        Absolute lower bounds.  Falls back to *current_low* if None.
    hard_high : np.ndarray or None
        Absolute upper bounds.  Falls back to *current_high* if None.
    min_step : np.ndarray or None
        Minimum span per parameter.  Falls back to
        ``(hard_high - hard_low) * 0.01`` if None.
    best_x : list[float] or None
        Best completed candidate parameter vector.
    high_quality_points : list[list[float]] or None
        Multiple high-quality completed candidates (for clustering detection).
    pass_fail_spatial : dict or None
        Spatial evidence of pass/fail regions (reserved for future use).
    stage_improvement : float or None
        Objective improvement between stages (negative = worsening).
    """
    param_names: list[str]
    current_low: np.ndarray
    current_high: np.ndarray
    proposed_low: np.ndarray
    proposed_high: np.ndarray
    hard_low: np.ndarray | None = None
    hard_high: np.ndarray | None = None
    min_step: np.ndarray | None = None
    best_x: list[float] | None = None
    high_quality_points: list[list[float]] | None = None
    pass_fail_spatial: dict | None = None
    stage_improvement: float | None = None

    def __post_init__(self) -> None:
        n = len(self.param_names)
        for arr, name in [
            (self.current_low, "current_low"),
            (self.current_high, "current_high"),
            (self.proposed_low, "proposed_low"),
            (self.proposed_high, "proposed_high"),
        ]:
            if len(arr) != n:
                raise ValueError(f"{name} length {len(arr)} != param_names length {n}")

        if self.hard_low is None:
            self.hard_low = self.current_low.copy()
        if self.hard_high is None:
            self.hard_high = self.current_high.copy()
        if len(self.hard_low) != n:
            raise ValueError("hard_low length mismatch")
        if len(self.hard_high) != n:
            raise ValueError("hard_high length mismatch")
        if self.min_step is None:
            self.min_step = (self.hard_high - self.hard_low) * 0.01
        if len(self.min_step) != n:
            raise ValueError("min_step length mismatch")

        if self.best_x is not None and len(self.best_x) != n:
            raise ValueError(
                f"best_x length {len(self.best_x)} != param_names length {n}",
            )
        if self.high_quality_points is not None:
            for i, pt in enumerate(self.high_quality_points):
                if len(pt) != n:
                    raise ValueError(
                        f"high_quality_points[{i}] length {len(pt)} "
                        f"!= param_names length {n}",
                    )

        # Validate value ordering
        if np.any(self.hard_low >= self.hard_high):
            raise ValueError("hard_low must be strictly less than hard_high for all parameters")
        if np.any(self.current_low >= self.current_high):
            raise ValueError("current_low must be strictly less than current_high")
        if np.any(self.min_step <= 0):
            raise ValueError("min_step must be positive for all parameters")
        if np.any(self.current_low < self.hard_low) or np.any(self.current_high > self.hard_high):
            raise ValueError("current bounds exceed hard bounds")

    def validate_proposed(self) -> None:
        """Validate that proposed bounds are within current bounds."""
        if np.any(self.proposed_low < self.current_low) or np.any(self.proposed_high > self.current_high):
            raise ValueError("Proposed bounds exceed current bounds.")
        if np.any(self.proposed_low >= self.proposed_high):
            raise ValueError("proposed_low >= proposed_high for some parameters.")


# ---------------------------------------------------------------------------
# Review helpers
# ---------------------------------------------------------------------------


def _normalize_input(input_data: AdaptiveBoundsInput) -> dict[str, Any]:
    """Basic validation and initial diagnostics."""
    input_data.validate_proposed()
    diag: dict[str, Any] = {
        "n_params": len(input_data.param_names),
        "params": input_data.param_names,
    }
    return diag


# ---------------------------------------------------------------------------
# Per-parameter boundary / quality detection
# ---------------------------------------------------------------------------


def detect_best_boundary_clipping(
    input_data: AdaptiveBoundsInput,
    proximity_fraction: float = 0.05,
) -> dict[str, Any]:
    """Check per-parameter whether the best candidate is clipped by proposed shrink.

    Returns a dict with:
    - ``near_boundary`` (bool)
    - ``params_near_boundary_lo`` / ``params_near_boundary_hi``
    - ``params_clipped_lo`` / ``params_clipped_hi`` (per-param: best near
      bound AND that side's proposed bound moves inward)
    - ``is_clipped`` (bool — any param has a clipped side)
    """
    if input_data.best_x is None:
        return {
            "near_boundary": False,
            "params_near_boundary_lo": [],
            "params_near_boundary_hi": [],
            "params_clipped_lo": [],
            "params_clipped_hi": [],
            "is_clipped": False,
            "proximity_fraction": proximity_fraction,
        }

    near_lo: list[str] = []
    near_hi: list[str] = []
    clipped_lo: list[str] = []
    clipped_hi: list[str] = []

    for i, name in enumerate(input_data.param_names):
        span = input_data.current_high[i] - input_data.current_low[i]
        if span <= 0:
            continue
        dist_lo = abs(input_data.best_x[i] - input_data.current_low[i]) / span
        dist_hi = abs(input_data.best_x[i] - input_data.current_high[i]) / span
        near_low = dist_lo < proximity_fraction
        near_high = dist_hi < proximity_fraction

        # Per-parameter shrink detection
        low_moves_in = bool(input_data.proposed_low[i] > input_data.current_low[i])
        high_moves_in = bool(input_data.proposed_high[i] < input_data.current_high[i])

        if near_low:
            near_lo.append(name)
            if low_moves_in:
                clipped_lo.append(name)
        if near_high:
            near_hi.append(name)
            if high_moves_in:
                clipped_hi.append(name)

    return {
        "near_boundary": bool(near_lo or near_hi),
        "params_near_boundary_lo": near_lo,
        "params_near_boundary_hi": near_hi,
        "params_clipped_lo": clipped_lo,
        "params_clipped_hi": clipped_hi,
        "is_clipped": bool(clipped_lo or clipped_hi),
        "proximity_fraction": proximity_fraction,
    }


def detect_quality_boundary_clustering(
    input_data: AdaptiveBoundsInput,
    cluster_fraction: float = 0.1,
    min_cluster_count: int = 2,
) -> dict[str, Any]:
    """Check if at least *min_cluster_count* high-quality points cluster near a boundary.

    Returns a dict with keys ``clustered_near_boundary`` (bool),
    ``clustered_params_lo`` / ``clustered_params_hi`` (sorted lists).
    A parameter boundary is considered clustered only if at least
    *min_cluster_count* distinct points (not observations) fall within
    ``cluster_fraction`` of that boundary.
    """
    if not input_data.high_quality_points or len(input_data.high_quality_points) < min_cluster_count:
        return {
            "clustered_near_boundary": False,
            "clustered_params_lo": [],
            "clustered_params_hi": [],
        }

    count_lo: dict[str, int] = {}
    count_hi: dict[str, int] = {}
    for pt in input_data.high_quality_points:
        for i, name in enumerate(input_data.param_names):
            span = input_data.current_high[i] - input_data.current_low[i]
            if span <= 0:
                continue
            dist_lo = abs(pt[i] - input_data.current_low[i]) / span
            dist_hi = abs(pt[i] - input_data.current_high[i]) / span
            if dist_lo < cluster_fraction:
                count_lo[name] = count_lo.get(name, 0) + 1
            if dist_hi < cluster_fraction:
                count_hi[name] = count_hi.get(name, 0) + 1

    clust_lo = sorted(n for n, c in count_lo.items() if c >= min_cluster_count)
    clust_hi = sorted(n for n, c in count_hi.items() if c >= min_cluster_count)

    return {
        "clustered_near_boundary": bool(clust_lo or clust_hi),
        "clustered_params_lo": clust_lo,
        "clustered_params_hi": clust_hi,
    }


# ---------------------------------------------------------------------------
# Bound manipulation helpers
# ---------------------------------------------------------------------------


def clamp_to_hard_bounds_and_min_step(
    low: np.ndarray,
    high: np.ndarray,
    hard_low: np.ndarray,
    hard_high: np.ndarray,
    min_step: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Clamp bounds to hard limits and enforce minimum step.

    Returns ``(clamped_low, clamped_high)``.
    """
    clamped_low = np.maximum(low, hard_low)
    clamped_high = np.minimum(high, hard_high)

    span = clamped_high - clamped_low
    for i in range(len(low)):
        if span[i] < min_step[i]:
            mid = (clamped_low[i] + clamped_high[i]) / 2.0
            half = min_step[i] / 2.0
            clamped_low[i] = max(hard_low[i], mid - half)
            clamped_high[i] = min(hard_high[i], mid + half)
            if clamped_high[i] - clamped_low[i] < min_step[i]:
                clamped_low[i] = hard_low[i]
                clamped_high[i] = min(hard_low[i] + min_step[i], hard_high[i])

    return clamped_low, clamped_high


def _has_room_to_expand_low(
    param_idx: int,
    input_data: AdaptiveBoundsInput,
    expand_amount: float,
) -> bool:
    """Check if there is room to expand a parameter's low side."""
    current_low = input_data.proposed_low[param_idx]
    new_low = current_low - expand_amount
    clamped = max(new_low, input_data.hard_low[param_idx])
    return clamped < current_low


def _has_room_to_expand_high(
    param_idx: int,
    input_data: AdaptiveBoundsInput,
    expand_amount: float,
) -> bool:
    """Check if there is room to expand a parameter's high side."""
    current_high = input_data.proposed_high[param_idx]
    new_high = current_high + expand_amount
    clamped = min(new_high, input_data.hard_high[param_idx])
    return clamped > current_high


def apply_asymmetric_expand_for_params(
    input_data: AdaptiveBoundsInput,
    *,
    expand_low_params: list[str] | None = None,
    expand_high_params: list[str] | None = None,
    expand_fraction: float = 0.05,
) -> StageBounds:
    """Expand proposed bounds **only** for the specified params/sides.

    Parameters not listed retain their proposed (or current) bounds.
    """
    n = len(input_data.param_names)
    expand_low_arr = np.zeros(n)
    expand_high_arr = np.zeros(n)

    name_to_idx = {name: i for i, name in enumerate(input_data.param_names)}

    span = input_data.proposed_high - input_data.proposed_low

    if expand_low_params:
        for name in expand_low_params:
            i = name_to_idx.get(name)
            if i is not None:
                expand_low_arr[i] = span[i] * expand_fraction

    if expand_high_params:
        for name in expand_high_params:
            i = name_to_idx.get(name)
            if i is not None:
                expand_high_arr[i] = span[i] * expand_fraction

    new_low = input_data.proposed_low - expand_low_arr
    new_high = input_data.proposed_high + expand_high_arr

    clamped_low, clamped_high = clamp_to_hard_bounds_and_min_step(
        new_low, new_high,
        input_data.hard_low, input_data.hard_high,
        input_data.min_step,
    )

    return StageBounds(
        param_names=list(input_data.param_names),
        low=clamped_low, high=clamped_high,
        hard_low=input_data.hard_low.copy(),
        hard_high=input_data.hard_high.copy(),
    )


def apply_symmetric_expand(
    input_data: AdaptiveBoundsInput,
    expand_fraction: float = 0.1,
) -> StageBounds:
    """Expand proposed bounds symmetrically on both sides.

    Each side is expanded by ``span * expand_fraction / 2``.
    """
    n = len(input_data.param_names)
    span = input_data.proposed_high - input_data.proposed_low
    expand = span * expand_fraction / 2.0
    new_low = input_data.proposed_low - expand
    new_high = input_data.proposed_high + expand
    clamped_low, clamped_high = clamp_to_hard_bounds_and_min_step(
        new_low, new_high,
        input_data.hard_low, input_data.hard_high,
        input_data.min_step,
    )
    return StageBounds(
        param_names=list(input_data.param_names),
        low=clamped_low, high=clamped_high,
        hard_low=input_data.hard_low.copy(),
        hard_high=input_data.hard_high.copy(),
    )


def apply_asymmetric_expand(
    input_data: AdaptiveBoundsInput,
    expand_low: np.ndarray | None = None,
    expand_high: np.ndarray | None = None,
    expand_fraction: float = 0.05,
) -> StageBounds:
    """Expand proposed bounds asymmetrically (legacy API — expands all params)."""
    span = input_data.proposed_high - input_data.proposed_low
    if expand_low is None:
        expand_low = span * expand_fraction
    if expand_high is None:
        expand_high = span * expand_fraction
    new_low = input_data.proposed_low - expand_low
    new_high = input_data.proposed_high + expand_high
    clamped_low, clamped_high = clamp_to_hard_bounds_and_min_step(
        new_low, new_high,
        input_data.hard_low, input_data.hard_high,
        input_data.min_step,
    )
    return StageBounds(
        param_names=list(input_data.param_names),
        low=clamped_low, high=clamped_high,
        hard_low=input_data.hard_low.copy(),
        hard_high=input_data.hard_high.copy(),
    )


def apply_center_shift(
    input_data: AdaptiveBoundsInput,
    new_center: list[float],
) -> StageBounds:
    """Shift proposed bounds to center on *new_center* while preserving span.

    Result is clamped to ``[hard_low, hard_high]``.
    """
    center_arr = np.asarray(new_center, dtype=float)
    half_span = (input_data.proposed_high - input_data.proposed_low) / 2.0

    new_low = center_arr - half_span
    new_high = center_arr + half_span

    clamped_low, clamped_high = clamp_to_hard_bounds_and_min_step(
        new_low, new_high,
        input_data.hard_low, input_data.hard_high,
        input_data.min_step,
    )

    return StageBounds(
        param_names=list(input_data.param_names),
        low=clamped_low, high=clamped_high,
        hard_low=input_data.hard_low.copy(),
        hard_high=input_data.hard_high.copy(),
    )


# ---------------------------------------------------------------------------
# Main recommendation
# ---------------------------------------------------------------------------


def recommend_adaptive_bounds(
    input_data: AdaptiveBoundsInput,
    *,
    proximity_fraction: float = 0.05,
    expand_fraction: float = 0.1,
) -> AdaptiveBoundsRecommendation:
    """Review proposed stage bounds and recommend an adaptive action.

    Policy priority:
    1. Insufficient evidence → ``STOP_INSUFFICIENT_EVIDENCE``.
    2. Per-parameter anti-clipping: if a param's best is near boundary **and**
       that side's proposed bound moves inward → expand the clipped side.
       If no room → ``BLOCK_SHRINK`` for that side.
    3. Quality clustering: ≥2 high-quality points near same param boundary →
       expand.
    4. Shrinking with no clipping, centered evidence → ``PERMIT_SHRINK``.
    5. Not shrinking, no clipping → ``NO_CHANGE``.
    """
    _normalize_input(input_data)

    n = len(input_data.param_names)
    diag: dict[str, Any] = {
        "n_params": n,
        "params": input_data.param_names,
    }

    # 1. Insufficient evidence
    if input_data.best_x is None and not input_data.high_quality_points:
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.STOP_INSUFFICIENT_EVIDENCE,
            reason="No best_x or high-quality points for adaptive review.",
            recommended_low=input_data.current_low.copy(),
            recommended_high=input_data.current_high.copy(),
            diagnostics=diag,
        )

    clipping = detect_best_boundary_clipping(
        input_data, proximity_fraction=proximity_fraction,
    )
    clustering = detect_quality_boundary_clustering(input_data)
    diag["clipping"] = clipping
    diag["clustering"] = clustering

    # 2. Anti-clipping (per-parameter)
    clipped_lo: list[str] = clipping.get("params_clipped_lo", [])
    clipped_hi: list[str] = clipping.get("params_clipped_hi", [])
    if clipped_lo or clipped_hi:
        return _recommend_anti_clipping_by_param(
            input_data, clipped_lo, clipped_hi, clipping, expand_fraction, diag,
        )

    # 3. Quality clustering
    if clustering["clustered_near_boundary"]:
        return _recommend_clustering_response(
            input_data, clustering, expand_fraction, diag,
        )

    # 4. Per-parameter shrink detection for safe-shrink check
    any_shrinking = bool(
        np.any(input_data.proposed_low > input_data.current_low)
        or np.any(input_data.proposed_high < input_data.current_high)
    )
    if any_shrinking:
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.PERMIT_SHRINK,
            reason="Proposed shrink is safe: best point centered, no clipping.",
            recommended_low=input_data.proposed_low.copy(),
            recommended_high=input_data.proposed_high.copy(),
            diagnostics=diag,
        )

    # 5/6. No change needed
    return AdaptiveBoundsRecommendation(
        action=AdaptiveBoundsAction.NO_CHANGE,
        reason="Proposed bounds are within safe range.",
        recommended_low=input_data.proposed_low.copy(),
        recommended_high=input_data.proposed_high.copy(),
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _recommend_anti_clipping_by_param(
    input_data: AdaptiveBoundsInput,
    clipped_lo: list[str],
    clipped_hi: list[str],
    clipping: dict[str, Any],
    expand_fraction: float,
    diag: dict[str, Any],
) -> AdaptiveBoundsRecommendation:
    """Per-parameter anti-clipping: only expand clipped params, on clipped sides."""
    # Check room
    name_to_idx = {name: i for i, name in enumerate(input_data.param_names)}
    span = input_data.proposed_high - input_data.proposed_low

    no_room_lo: list[str] = []
    no_room_hi: list[str] = []
    can_expand_lo: list[str] = []
    can_expand_hi: list[str] = []

    for name in clipped_lo:
        i = name_to_idx[name]
        amt = span[i] * expand_fraction
        if _has_room_to_expand_low(i, input_data, amt):
            can_expand_lo.append(name)
        else:
            no_room_lo.append(name)

    for name in clipped_hi:
        i = name_to_idx[name]
        amt = span[i] * expand_fraction
        if _has_room_to_expand_high(i, input_data, amt):
            can_expand_hi.append(name)
        else:
            no_room_hi.append(name)

    # If no room on any clipped side → block shrink
    if not can_expand_lo and not can_expand_hi:
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.BLOCK_SHRINK,
            reason=f"Clipped but no room to expand: low=({no_room_lo}), high=({no_room_hi}).",
            recommended_low=input_data.current_low.copy(),
            recommended_high=input_data.current_high.copy(),
            params_expanded=list(clipped_lo + clipped_hi),
            diagnostics=diag,
        )

    # Partial room: expand what we can
    new_bounds = apply_asymmetric_expand_for_params(
        input_data,
        expand_low_params=can_expand_lo if can_expand_lo else None,
        expand_high_params=can_expand_hi if can_expand_hi else None,
        expand_fraction=expand_fraction,
    )

    all_expanded = sorted(set(can_expand_lo + can_expand_hi))
    reason_parts = []
    if can_expand_lo:
        reason_parts.append(f"low ({can_expand_lo})")
    if can_expand_hi:
        reason_parts.append(f"high ({can_expand_hi})")
    if no_room_lo or no_room_hi:
        reason_parts.append(f"blocked-no-room low=({no_room_lo}) high=({no_room_hi})")

    return AdaptiveBoundsRecommendation(
        action=AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
        reason=f"Clipped; expanding {'; '.join(reason_parts)}.",
        recommended_low=new_bounds.low,
        recommended_high=new_bounds.high,
        params_expanded=all_expanded,
        diagnostics=diag,
    )


def _recommend_clustering_response(
    input_data: AdaptiveBoundsInput,
    clustering: dict[str, Any],
    expand_fraction: float,
    diag: dict[str, Any],
) -> AdaptiveBoundsRecommendation:
    """Respond to quality-point boundary clustering."""
    clust_lo: list[str] = clustering.get("clustered_params_lo", [])
    clust_hi: list[str] = clustering.get("clustered_params_hi", [])

    if clust_lo and not clust_hi:
        new_bounds = apply_asymmetric_expand_for_params(
            input_data,
            expand_low_params=clust_lo,
            expand_high_params=None,
            expand_fraction=expand_fraction,
        )
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
            reason=f"High-quality points clustered low ({clust_lo}); expanding low.",
            recommended_low=new_bounds.low,
            recommended_high=new_bounds.high,
            params_expanded=clust_lo,
            diagnostics=diag,
        )

    if clust_hi and not clust_lo:
        new_bounds = apply_asymmetric_expand_for_params(
            input_data,
            expand_low_params=None,
            expand_high_params=clust_hi,
            expand_fraction=expand_fraction,
        )
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
            reason=f"High-quality points clustered high ({clust_hi}); expanding high.",
            recommended_low=new_bounds.low,
            recommended_high=new_bounds.high,
            params_expanded=clust_hi,
            diagnostics=diag,
        )

    # Both sides
    new_bounds = apply_asymmetric_expand_for_params(
        input_data,
        expand_low_params=clust_lo,
        expand_high_params=clust_hi,
        expand_fraction=expand_fraction,
    )
    return AdaptiveBoundsRecommendation(
        action=AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
        reason=f"Points clustered low ({clust_lo}) and high ({clust_hi}); expanding.",
        recommended_low=new_bounds.low,
        recommended_high=new_bounds.high,
        params_expanded=sorted(set(clust_lo + clust_hi)),
        diagnostics=diag,
    )


@dataclass
class AdaptiveBoundsRecommendation:
    """Recommendation from adaptive bounds review.

    Parameters
    ----------
    action : AdaptiveBoundsAction
        Recommended action.
    reason : str
        Human-readable justification.
    recommended_low : np.ndarray
        Recommended lower bounds for next stage.
    recommended_high : np.ndarray
        Recommended upper bounds for next stage.
    params_expanded : list[str] or None
        Parameters that were expanded or shifted.
    diagnostics : dict
        Extra information supporting the recommendation.
    """
    action: AdaptiveBoundsAction = AdaptiveBoundsAction.NO_CHANGE
    reason: str = ""
    recommended_low: np.ndarray | None = None
    recommended_high: np.ndarray | None = None
    params_expanded: list[str] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
