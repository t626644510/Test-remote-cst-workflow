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
# Boundary / quality detection
# ---------------------------------------------------------------------------


def detect_best_boundary_clipping(
    input_data: AdaptiveBoundsInput,
    proximity_fraction: float = 0.05,
) -> dict[str, Any]:
    """Check if the best candidate is near the current bounds.

    Returns a dict with keys ``near_boundary`` (bool),
    ``params_near_boundary_lo`` / ``params_near_boundary_hi`` (lists),
    ``proximity_fraction``, ``is_clipped`` (bool — near boundary +
    proposed is shrinking).
    """
    if input_data.best_x is None:
        return {
            "near_boundary": False,
            "params_near_boundary_lo": [],
            "params_near_boundary_hi": [],
            "is_clipped": False,
            "proximity_fraction": proximity_fraction,
        }

    near_lo: list[str] = []
    near_hi: list[str] = []
    for i, name in enumerate(input_data.param_names):
        span = input_data.current_high[i] - input_data.current_low[i]
        if span <= 0:
            continue
        dist_lo = abs(input_data.best_x[i] - input_data.current_low[i]) / span
        dist_hi = abs(input_data.best_x[i] - input_data.current_high[i]) / span
        if dist_lo < proximity_fraction:
            near_lo.append(name)
        if dist_hi < proximity_fraction:
            near_hi.append(name)

    near = bool(near_lo or near_hi)
    # Clipped = near boundary AND proposed is narrower than current
    is_shrinking = bool(
        np.any(input_data.proposed_low > input_data.current_low)
        or np.any(input_data.proposed_high < input_data.current_high)
    )
    is_clipped = near and is_shrinking

    return {
        "near_boundary": near,
        "params_near_boundary_lo": near_lo,
        "params_near_boundary_hi": near_hi,
        "is_clipped": is_clipped,
        "proximity_fraction": proximity_fraction,
    }


def detect_quality_boundary_clustering(
    input_data: AdaptiveBoundsInput,
    cluster_fraction: float = 0.1,
) -> dict[str, Any]:
    """Check if multiple high-quality points cluster near a boundary.

    Returns a dict with keys ``clustered_near_boundary`` (bool),
    ``clustered_params_lo`` / ``clustered_params_hi`` (lists).
    """
    if not input_data.high_quality_points or len(input_data.high_quality_points) < 2:
        return {
            "clustered_near_boundary": False,
            "clustered_params_lo": [],
            "clustered_params_hi": [],
        }

    clust_lo: set[str] = set()
    clust_hi: set[str] = set()
    for pt in input_data.high_quality_points:
        for i, name in enumerate(input_data.param_names):
            span = input_data.current_high[i] - input_data.current_low[i]
            if span <= 0:
                continue
            dist_lo = abs(pt[i] - input_data.current_low[i]) / span
            dist_hi = abs(pt[i] - input_data.current_high[i]) / span
            if dist_lo < cluster_fraction:
                clust_lo.add(name)
            if dist_hi < cluster_fraction:
                clust_hi.add(name)

    return {
        "clustered_near_boundary": bool(clust_lo or clust_hi),
        "clustered_params_lo": sorted(clust_lo),
        "clustered_params_hi": sorted(clust_hi),
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

    # Enforce min_step: if span < min_step, recenter around the midpoint
    span = clamped_high - clamped_low
    for i in range(len(low)):
        if span[i] < min_step[i]:
            mid = (clamped_low[i] + clamped_high[i]) / 2.0
            half = min_step[i] / 2.0
            clamped_low[i] = max(hard_low[i], mid - half)
            clamped_high[i] = min(hard_high[i], mid + half)
            # If still < min_step after clamping to hard bounds, set to hard bounds
            if clamped_high[i] - clamped_low[i] < min_step[i]:
                clamped_low[i] = hard_low[i]
                clamped_high[i] = min(hard_low[i] + min_step[i], hard_high[i])

    return clamped_low, clamped_high


def apply_symmetric_expand(
    input_data: AdaptiveBoundsInput,
    expand_fraction: float = 0.1,
) -> StageBounds:
    """Expand proposed bounds symmetrically on both sides.

    Expansion is clamped to ``[hard_low, hard_high]`` and respects
    ``min_step``.
    """
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
    """Expand proposed bounds asymmetrically.

    *expand_low* and *expand_high* are per-parameter expansion amounts
    (positive = expand outward).  If None, uses ``span * expand_fraction``.
    """
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
    1. Insufficient evidence (no best_x, no high-quality points)
       → ``STOP_INSUFFICIENT_EVIDENCE``.
    2. Best point near boundary AND proposed is shrinking → anti-clipping:
       - If ONLY one side is clipped → ``ASYMMETRIC_EXPAND`` (expand clipped side).
       - If both sides or symmetric clustering → ``SYMMETRIC_EXPAND``.
       - If no room to expand (hard bounds hit and min_step reached) →
         ``BLOCK_SHRINK``.
    3. High-quality points cluster near boundary → ``ASYMMETRIC_EXPAND`` or
       ``SYMMETRIC_EXPAND`` (depending on clustering pattern).
    4. Proposed is shrinking, no clipping, centered evidence,
       sufficient span → ``PERMIT_SHRINK``.
    5. Proposed is expanding or unchanged → ``NO_CHANGE``.
    6. Catch-all → ``NO_CHANGE``.

    Returns
    -------
    AdaptiveBoundsRecommendation
    """
    import copy

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

    is_shrinking = bool(
        np.any(input_data.proposed_low > input_data.current_low)
        or np.any(input_data.proposed_high < input_data.current_high)
    )

    # 2. Anti-clipping: best near boundary + proposed is shrinking
    if clipping["is_clipped"]:
        return _recommend_anti_clipping(
            input_data, clipping, expand_fraction, diag,
        )

    # 3. Quality clustering near boundary
    if clustering["clustered_near_boundary"]:
        return _recommend_clustering_response(
            input_data, clustering, expand_fraction, diag,
        )

    # 4. Safe shrink
    if is_shrinking:
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
# Internal helpers for recommendation logic
# ---------------------------------------------------------------------------


def _recommend_anti_clipping(
    input_data: AdaptiveBoundsInput,
    clipping: dict[str, Any],
    expand_fraction: float,
    diag: dict[str, Any],
) -> AdaptiveBoundsRecommendation:
    """Respond to boundary clipping — expand the clipped side."""
    lo_clipped = bool(clipping["params_near_boundary_lo"])
    hi_clipped = bool(clipping["params_near_boundary_hi"])

    if lo_clipped and not hi_clipped:
        # Expand only the low side
        expand_low = (input_data.proposed_high - input_data.proposed_low) * expand_fraction
        expand_high = np.zeros(len(input_data.param_names))
        new_bounds = apply_asymmetric_expand(
            input_data, expand_low=expand_low, expand_high=expand_high,
        )
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
            reason=f"Clipped on low side ({clipping['params_near_boundary_lo']}); "
                   "expanding low bounds.",
            recommended_low=new_bounds.low,
            recommended_high=new_bounds.high,
            params_expanded=list(clipping["params_near_boundary_lo"]),
            diagnostics=diag,
        )

    if hi_clipped and not lo_clipped:
        # Expand only the high side
        expand_low = np.zeros(len(input_data.param_names))
        expand_high = (input_data.proposed_high - input_data.proposed_low) * expand_fraction
        new_bounds = apply_asymmetric_expand(
            input_data, expand_low=expand_low, expand_high=expand_high,
        )
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
            reason=f"Clipped on high side ({clipping['params_near_boundary_hi']}); "
                   "expanding high bounds.",
            recommended_low=new_bounds.low,
            recommended_high=new_bounds.high,
            params_expanded=list(clipping["params_near_boundary_hi"]),
            diagnostics=diag,
        )

    # Both sides clipped → symmetric expand
    try:
        new_bounds = apply_symmetric_expand(input_data, expand_fraction=expand_fraction)
        # Check if expansion actually changed bounds
        if np.allclose(new_bounds.low, input_data.proposed_low) and np.allclose(
            new_bounds.high, input_data.proposed_high
        ):
            return AdaptiveBoundsRecommendation(
                action=AdaptiveBoundsAction.BLOCK_SHRINK,
                reason="Both sides clipped but no room to expand (hard bounds / min step).",
                recommended_low=input_data.current_low.copy(),
                recommended_high=input_data.current_high.copy(),
                params_expanded=list(
                    clipping["params_near_boundary_lo"]
                    + clipping["params_near_boundary_hi"]
                ),
                diagnostics=diag,
            )
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.SYMMETRIC_EXPAND,
            reason="Both sides clipped; symmetrically expanding.",
            recommended_low=new_bounds.low,
            recommended_high=new_bounds.high,
            params_expanded=list(
                clipping["params_near_boundary_lo"]
                + clipping["params_near_boundary_hi"]
            ),
            diagnostics=diag,
        )
    except ValueError:
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.BLOCK_SHRINK,
            reason="Both sides clipped but cannot compute expanded bounds.",
            recommended_low=input_data.current_low.copy(),
            recommended_high=input_data.current_high.copy(),
            diagnostics=diag,
        )


def _recommend_clustering_response(
    input_data: AdaptiveBoundsInput,
    clustering: dict[str, Any],
    expand_fraction: float,
    diag: dict[str, Any],
) -> AdaptiveBoundsRecommendation:
    """Respond to quality-point boundary clustering."""
    lo_clustered = bool(clustering["clustered_params_lo"])
    hi_clustered = bool(clustering["clustered_params_hi"])

    if lo_clustered and not hi_clustered:
        expand_low = (input_data.proposed_high - input_data.proposed_low) * expand_fraction
        expand_high = np.zeros(len(input_data.param_names))
        new_bounds = apply_asymmetric_expand(
            input_data, expand_low=expand_low, expand_high=expand_high,
        )
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
            reason="High-quality points clustered on low side; expanding low.",
            recommended_low=new_bounds.low,
            recommended_high=new_bounds.high,
            params_expanded=clustering["clustered_params_lo"],
            diagnostics=diag,
        )

    if hi_clustered and not lo_clustered:
        expand_low = np.zeros(len(input_data.param_names))
        expand_high = (input_data.proposed_high - input_data.proposed_low) * expand_fraction
        new_bounds = apply_asymmetric_expand(
            input_data, expand_low=expand_low, expand_high=expand_high,
        )
        return AdaptiveBoundsRecommendation(
            action=AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
            reason="High-quality points clustered on high side; expanding high.",
            recommended_low=new_bounds.low,
            recommended_high=new_bounds.high,
            params_expanded=clustering["clustered_params_hi"],
            diagnostics=diag,
        )

    new_bounds = apply_symmetric_expand(input_data, expand_fraction=expand_fraction)
    return AdaptiveBoundsRecommendation(
        action=AdaptiveBoundsAction.SYMMETRIC_EXPAND,
        reason="High-quality points clustered near bounds; symmetrically expanding.",
        recommended_low=new_bounds.low,
        recommended_high=new_bounds.high,
        params_expanded=clustering["clustered_params_lo"]
        + clustering["clustered_params_hi"],
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
