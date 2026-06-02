# Stage + Adaptive integration policy for the RF gun SAO workflow.
# Composes stage search transition decisions with adaptive bounds review.
# No CST dependency, no runtime wiring yet.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from workflows.rfgun_sao.adaptive_bounds import (
    AdaptiveBoundsAction,
    AdaptiveBoundsInput,
    AdaptiveBoundsRecommendation,
    detect_best_boundary_clipping,
    detect_quality_boundary_clustering,
    recommend_adaptive_bounds,
)
from workflows.rfgun_sao.stage_search import (
    StageBounds,
    StageObservation,
    StageSummary,
    StageTransitionAction,
    StageTransitionDecision,
    detect_boundary_proximity,
    select_best_completed,
)


class StageAdaptiveAction(str, Enum):
    """Final action combining stage and adaptive decisions."""
    USE_STAGE_DECISION = "use_stage_decision"
    USE_ADAPTIVE_BOUNDS = "use_adaptive_bounds"
    BLOCK_STAGE_SHRINK = "block_stage_shrink"
    CONTINUE_CURRENT = "continue_current"
    STOP = "stop"


@dataclass
class StageAdaptivePolicyInput:
    """Input for the stage+adaptive integration policy.

    Parameters
    ----------
    current_bounds : StageBounds
        Current stage bounds.
    stage_decision : StageTransitionDecision
        Decision from ``decide_stage_transition``.
    observations : list[StageObservation]
        All observations in the current stage.
    hard_low : np.ndarray or None
        Absolute lower bounds for adaptive review (falls back to
        ``current_bounds.hard_low``).
    hard_high : np.ndarray or None
        Absolute upper bounds for adaptive review (falls back to
        ``current_bounds.hard_high``).
    min_step : np.ndarray or None
        Minimum step for adaptive review (falls back to
        ``current_bounds.span * 0.01``).
    reference_span : np.ndarray or None
        Reference span for min-span check in stage decision
        (falls back to ``current_bounds.span``).
    """
    current_bounds: StageBounds
    stage_decision: StageTransitionDecision
    observations: list[StageObservation]
    hard_low: np.ndarray | None = None
    hard_high: np.ndarray | None = None
    min_step: np.ndarray | None = None
    reference_span: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.hard_low is None:
            self.hard_low = self.current_bounds.hard_low.copy()
        if self.hard_high is None:
            self.hard_high = self.current_bounds.hard_high.copy()
        if self.min_step is None:
            self.min_step = self.current_bounds.span * 0.05
        if self.reference_span is None:
            self.reference_span = self.current_bounds.span.copy()


@dataclass
class StageAdaptivePolicyDecision:
    """Result of combining stage and adaptive decisions.

    Parameters
    ----------
    action : StageAdaptiveAction
        Final recommended action.
    reason : str
        Human-readable justification.
    final_bounds : StageBounds
        Bounds to use for the next stage.
    stage_action : StageTransitionAction or None
        Original stage transition action.
    adaptive_action : AdaptiveBoundsAction or None
        Adaptive bounds action, if called.
    diagnostics : dict
        Extra information.
    """
    action: StageAdaptiveAction = StageAdaptiveAction.CONTINUE_CURRENT
    reason: str = ""
    final_bounds: StageBounds | None = None
    stage_action: StageTransitionAction | None = None
    adaptive_action: AdaptiveBoundsAction | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Best / high-quality point extraction
# ---------------------------------------------------------------------------


def extract_high_quality_points(
    observations: list[StageObservation],
    max_count: int = 5,
) -> list[list[float]]:
    """Return up to *max_count* completed parameter vectors with finite objective.

    Sorted by objective (best first).
    """
    completed = []
    for o in observations:
        status_str = o.status.value if hasattr(o.status, "value") else str(o.status)
        if (status_str == "completed"
                and o.objective_value is not None
                and np.isfinite(o.objective_value)):
            completed.append(o)
    completed.sort(key=lambda o: o.objective_value)
    return [list(o.x) for o in completed[:max_count]]


# ---------------------------------------------------------------------------
# Adaptive input builder
# ---------------------------------------------------------------------------


def build_adaptive_input_from_stage_decision(
    inp: StageAdaptivePolicyInput,
    *,
    expand_fraction: float = 0.1,
) -> AdaptiveBoundsInput | None:
    """Build an ``AdaptiveBoundsInput`` from a stage transition decision.

    Returns ``None`` if the stage decision does not provide useful proposed
    bounds or if observations lack a best candidate.
    """
    stage = inp.stage_decision
    best_x = select_best_completed(inp.observations)
    if best_x is None:
        return None

    # Determine proposed bounds
    if stage.proposed_bounds is not None:
        proposed_bounds = stage.proposed_bounds
    else:
        proposed_bounds = inp.current_bounds

    high_quality = extract_high_quality_points(inp.observations)

    return AdaptiveBoundsInput(
        param_names=list(inp.current_bounds.param_names),
        current_low=inp.current_bounds.low.copy(),
        current_high=inp.current_bounds.high.copy(),
        proposed_low=proposed_bounds.low.copy(),
        proposed_high=proposed_bounds.high.copy(),
        best_x=list(best_x[1]),
        high_quality_points=high_quality if high_quality else None,
        hard_low=inp.hard_low.copy(),
        hard_high=inp.hard_high.copy(),
        min_step=inp.min_step.copy(),
    )


# ---------------------------------------------------------------------------
# Main integration policy
# ---------------------------------------------------------------------------


def combine_stage_and_adaptive_decisions(
    inp: StageAdaptivePolicyInput,
    *,
    expand_fraction: float = 0.1,
) -> StageAdaptivePolicyDecision:
    """Combine a stage transition decision with adaptive bounds review.

    Rules
    -----
    1. **STOP** → final STOP.
    2. **CONTINUE_CURRENT** → final CONTINUE_CURRENT (no adaptive review).
    3. **RECENTER / SHIFT** (high fail/reject) → preserve stage intent;
       do not force adaptive shrink.
    4. **SHRINK** → run adaptive review:
       - PERMIT_SHRINK → final USE_STAGE_DECISION
       - ASYMMETRIC_EXPAND / SYMMETRIC_EXPAND → final USE_ADAPTIVE_BOUNDS
       - BLOCK_SHRINK → final BLOCK_STAGE_SHRINK
       - STOP_INSUFFICIENT_EVIDENCE → final CONTINUE_CURRENT
    5. **REQUEST_ADAPTIVE_REVIEW** → run adaptive review:
       - If adaptive returns expansion → final USE_ADAPTIVE_BOUNDS
       - If adaptive returns insufficient evidence → final CONTINUE_CURRENT
       - If adaptive returns BLOCK_SHRINK / NO_CHANGE / PERMIT_SHRINK →
         final USE_STAGE_DECISION (stage requested review, adaptive had no
         improvement to propose).
    """
    stage = inp.stage_decision
    diag: dict[str, Any] = {
        "stage_action": stage.action.value,
        "stage_reason": stage.reason,
    }

    # 1. STOP
    if stage.action == StageTransitionAction.STOP:
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.STOP,
            reason=f"Stage STOP: {stage.reason}",
            final_bounds=inp.current_bounds,
            stage_action=stage.action,
            diagnostics=diag,
        )

    # 2. CONTINUE_CURRENT
    if stage.action == StageTransitionAction.CONTINUE_CURRENT:
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.CONTINUE_CURRENT,
            reason=f"Stage CONTINUE: {stage.reason}",
            final_bounds=inp.current_bounds,
            stage_action=stage.action,
            diagnostics=diag,
        )

    # 3. RECENTER / SHIFT — preserve stage intent
    if stage.action in (
        StageTransitionAction.RECENTER,
        StageTransitionAction.SHIFT,
    ):
        proposed = stage.proposed_bounds or inp.current_bounds
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.USE_STAGE_DECISION,
            reason=f"Stage {stage.action.value}: {stage.reason}",
            final_bounds=proposed,
            stage_action=stage.action,
            diagnostics=diag,
        )

    # 4. SHRINK — run adaptive review
    if stage.action == StageTransitionAction.SHRINK:
        return _handle_stage_shrink(inp, diag)

    # 5. REQUEST_ADAPTIVE_REVIEW
    if stage.action == StageTransitionAction.REQUEST_ADAPTIVE_REVIEW:
        return _handle_adaptive_review(inp, diag)

    # Catch-all
    return StageAdaptivePolicyDecision(
        action=StageAdaptiveAction.CONTINUE_CURRENT,
        reason=f"Unhandled stage action {stage.action.value}.",
        final_bounds=inp.current_bounds,
        stage_action=stage.action,
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Internal handlers
# ---------------------------------------------------------------------------


def _handle_stage_shrink(
    inp: StageAdaptivePolicyInput,
    diag: dict[str, Any],
) -> StageAdaptivePolicyDecision:
    """Evaluate a stage SHRINK decision against adaptive bounds."""
    adaptive_inp = build_adaptive_input_from_stage_decision(inp)
    if adaptive_inp is None:
        # Cannot build adaptive input — proceed with stage decision
        proposed = inp.stage_decision.proposed_bounds or inp.current_bounds
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.USE_STAGE_DECISION,
            reason="Stage SHRINK (no best evidence for adaptive review).",
            final_bounds=proposed,
            stage_action=StageTransitionAction.SHRINK,
            diagnostics=diag,
        )

    adaptive_rec = recommend_adaptive_bounds(adaptive_inp)
    diag["adaptive_action"] = adaptive_rec.action.value
    diag["adaptive_reason"] = adaptive_rec.reason

    if adaptive_rec.action == AdaptiveBoundsAction.PERMIT_SHRINK:
        proposed = inp.stage_decision.proposed_bounds or inp.current_bounds
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.USE_STAGE_DECISION,
            reason=f"Stage SHRINK permitted by adaptive: {adaptive_rec.reason}",
            final_bounds=proposed,
            stage_action=StageTransitionAction.SHRINK,
            adaptive_action=adaptive_rec.action,
            diagnostics=diag,
        )

    if adaptive_rec.action in (
        AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
        AdaptiveBoundsAction.SYMMETRIC_EXPAND,
    ):
        new_bounds = StageBounds(
            param_names=list(inp.current_bounds.param_names),
            low=adaptive_rec.recommended_low.copy(),
            high=adaptive_rec.recommended_high.copy(),
            hard_low=inp.hard_low.copy(),
            hard_high=inp.hard_high.copy(),
        )
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.USE_ADAPTIVE_BOUNDS,
            reason=f"Stage SHRINK overridden by adaptive: {adaptive_rec.reason}",
            final_bounds=new_bounds,
            stage_action=StageTransitionAction.SHRINK,
            adaptive_action=adaptive_rec.action,
            diagnostics=diag,
        )

    if adaptive_rec.action == AdaptiveBoundsAction.BLOCK_SHRINK:
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.BLOCK_STAGE_SHRINK,
            reason=f"Stage SHRINK blocked by adaptive: {adaptive_rec.reason}",
            final_bounds=inp.current_bounds,
            stage_action=StageTransitionAction.SHRINK,
            adaptive_action=adaptive_rec.action,
            diagnostics=diag,
        )

    # Insufficient evidence, no change, or other fallback
    proposed = inp.stage_decision.proposed_bounds or inp.current_bounds
    return StageAdaptivePolicyDecision(
        action=StageAdaptiveAction.USE_STAGE_DECISION,
        reason=f"Stage SHRINK (adaptive fallback: {adaptive_rec.action.value}).",
        final_bounds=proposed,
        stage_action=StageTransitionAction.SHRINK,
        adaptive_action=adaptive_rec.action,
        diagnostics=diag,
    )


def _handle_adaptive_review(
    inp: StageAdaptivePolicyInput,
    diag: dict[str, Any],
) -> StageAdaptivePolicyDecision:
    """Evaluate a stage REQUEST_ADAPTIVE_REVIEW decision."""
    adaptive_inp = build_adaptive_input_from_stage_decision(inp)
    if adaptive_inp is None:
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.CONTINUE_CURRENT,
            reason="Stage requested adaptive review but no best evidence available.",
            final_bounds=inp.current_bounds,
            stage_action=StageTransitionAction.REQUEST_ADAPTIVE_REVIEW,
            diagnostics=diag,
        )

    adaptive_rec = recommend_adaptive_bounds(adaptive_inp)
    diag["adaptive_action"] = adaptive_rec.action.value
    diag["adaptive_reason"] = adaptive_rec.reason

    if adaptive_rec.action in (
        AdaptiveBoundsAction.ASYMMETRIC_EXPAND,
        AdaptiveBoundsAction.SYMMETRIC_EXPAND,
    ):
        new_bounds = StageBounds(
            param_names=list(inp.current_bounds.param_names),
            low=adaptive_rec.recommended_low.copy(),
            high=adaptive_rec.recommended_high.copy(),
            hard_low=inp.hard_low.copy(),
            hard_high=inp.hard_high.copy(),
        )
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.USE_ADAPTIVE_BOUNDS,
            reason=f"Adaptive review: {adaptive_rec.reason}",
            final_bounds=new_bounds,
            stage_action=StageTransitionAction.REQUEST_ADAPTIVE_REVIEW,
            adaptive_action=adaptive_rec.action,
            diagnostics=diag,
        )

    # Adaptive had no improvement
    return StageAdaptivePolicyDecision(
        action=StageAdaptiveAction.USE_STAGE_DECISION,
        reason=f"Adaptive review: no change needed ({adaptive_rec.action.value}).",
        final_bounds=inp.current_bounds,
        stage_action=StageTransitionAction.REQUEST_ADAPTIVE_REVIEW,
        adaptive_action=adaptive_rec.action,
        diagnostics=diag,
    )
