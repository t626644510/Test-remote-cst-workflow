# Stage search helpers for the RF gun SAO workflow.
# Feasibility-aware multi-stage controller — no runtime wiring yet.
# No CST dependency.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from cst_optimization.evaluation.stage_observation import (
    StageCandidateStatus,
    StageObservation,
)


@dataclass
class StageBounds:
    """Parameter bounds for a stage.

    Parameters
    ----------
    param_names : list[str]
        Ordered parameter names.
    low : np.ndarray
        Lower bounds (length = ``len(param_names)``).
    high : np.ndarray
        Upper bounds (length = ``len(param_names)``).
    hard_low : np.ndarray or None
        Absolute lower bounds (clamped).  Falls back to *low* if None.
    hard_high : np.ndarray or None
        Absolute upper bounds (clamped).  Falls back to *high* if None.
    """
    param_names: list[str]
    low: np.ndarray
    high: np.ndarray
    hard_low: np.ndarray | None = None
    hard_high: np.ndarray | None = None

    def __post_init__(self) -> None:
        if len(self.param_names) != len(self.low) or len(self.param_names) != len(self.high):
            raise ValueError("param_names/low/high length mismatch")
        if np.any(self.low >= self.high):
            raise ValueError("low must be strictly less than high for all parameters")
        if self.hard_low is None:
            self.hard_low = self.low.copy()
        if self.hard_high is None:
            self.hard_high = self.high.copy()
        if len(self.hard_low) != len(self.param_names):
            raise ValueError("hard_low length mismatch")
        if len(self.hard_high) != len(self.param_names):
            raise ValueError("hard_high length mismatch")

    @property
    def span(self) -> np.ndarray:
        return self.high - self.low

    @property
    def n_params(self) -> int:
        return len(self.param_names)


@dataclass
class StageSummary:
    """Aggregate statistics for one stage.

    Parameters
    ----------
    proposed_count : int
        Total candidates proposed by the optimizer.
    database_reused_count : int
        Candidates served from database (no new CST solve).
    actual_cst_solves_count : int
        Candidates that required a CST solve.
    retry_attempts_count : int
        Total retry attempts across all candidates.
    completed_count : int
        Successfully evaluated candidates.
    gate_rejected_count : int
        Candidates rejected by gate after successful measurement.
    calibration_failed_count : int
        Candidates that failed calibration.
    solver_failed_count : int
        Candidates that failed the solver.
    best_objective_value : float or None
        Best weighted scalar among completed candidates.
    best_x : list[float] or None
        Parameter vector of the best completed candidate.
    valid_completed_rate : float
        Fraction of CST-solved candidates that completed.
    reject_failure_rate : float
        Fraction of CST-solved candidates that were rejected or failed.
    """
    proposed_count: int = 0
    database_reused_count: int = 0
    actual_cst_solves_count: int = 0
    retry_attempts_count: int = 0
    completed_count: int = 0
    gate_rejected_count: int = 0
    calibration_failed_count: int = 0
    solver_failed_count: int = 0
    best_objective_value: float | None = None
    best_x: list[float] | None = None
    valid_completed_rate: float = 0.0
    reject_failure_rate: float = 0.0


class StageTransitionAction(str, Enum):
    """Recommended action after evaluating a stage."""
    CONTINUE_CURRENT = "continue_current"
    RECENTER = "recenter"
    SHIFT = "shift"
    SHRINK = "shrink"
    REQUEST_ADAPTIVE_REVIEW = "request_adaptive_review"
    STOP = "stop"


@dataclass
class StageTransitionDecision:
    """Result of a stage transition policy evaluation.

    Parameters
    ----------
    action : StageTransitionAction
        Recommended next action.
    reason : str
        Human-readable justification.
    proposed_center : list[float] or None
        Parameter center for recentering.
    proposed_bounds : StageBounds or None
        Bounds for the next stage.
    diagnostics : dict
        Extra information supporting the decision.
    """
    action: StageTransitionAction = StageTransitionAction.CONTINUE_CURRENT
    reason: str = ""
    proposed_center: list[float] | None = None
    proposed_bounds: StageBounds | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def summarize_stage_observations(
    observations: list[StageObservation],
    bounds: StageBounds,
) -> StageSummary:
    """Aggregate per-candidate observations into a ``StageSummary``.

    Parameters
    ----------
    observations : list[StageObservation]
        All observations for this stage.
    bounds : StageBounds
        Current stage bounds (used for boundary proximity).

    Returns
    -------
    StageSummary
    """
    proposed = len(observations)
    reused = sum(1 for o in observations if o.reused or o.status == StageCandidateStatus.DATABASE_REUSED)
    solves = proposed - reused
    retries = sum(o.retry_attempts for o in observations)
    completed = [o for o in observations if o.status == StageCandidateStatus.COMPLETED]
    gate_rej = [o for o in observations if o.status == StageCandidateStatus.GATE_REJECTED]
    cal_fail = [o for o in observations if o.status == StageCandidateStatus.CALIBRATION_FAILED]
    solv_fail = [o for o in observations if o.status in (
        StageCandidateStatus.SOLVER_FAILED,
        StageCandidateStatus.TRANSIENT_FAILED,
        StageCandidateStatus.UNKNOWN_FAILED,
    )]

    # Best completed
    best_obj: float | None = None
    best_x: list[float] | None = None
    for c in completed:
        if c.objective_value is not None and np.isfinite(c.objective_value):
            if best_obj is None or c.objective_value < best_obj:
                best_obj = c.objective_value
                best_x = list(c.x)

    valid_rate = min(len(completed) / max(solves, 1), 1.0)
    fail_rate = min((len(gate_rej) + len(cal_fail) + len(solv_fail)) / max(solves, 1), 1.0)

    return StageSummary(
        proposed_count=proposed,
        database_reused_count=reused,
        actual_cst_solves_count=solves,
        retry_attempts_count=retries,
        completed_count=len(completed),
        gate_rejected_count=len(gate_rej),
        calibration_failed_count=len(cal_fail),
        solver_failed_count=len(solv_fail),
        best_objective_value=best_obj,
        best_x=best_x,
        valid_completed_rate=valid_rate,
        reject_failure_rate=fail_rate,
    )


# ---------------------------------------------------------------------------
# Candidate selection helpers
# ---------------------------------------------------------------------------


def select_best_completed(
    observations: list[StageObservation],
) -> tuple[float, list[float]] | None:
    """Return ``(best_objective, best_x)`` from completed observations.

    ``None`` if no observation has a finite objective value.
    """
    best: tuple[float, list[float]] | None = None
    for o in observations:
        if o.status != StageCandidateStatus.COMPLETED:
            continue
        if o.objective_value is None or not np.isfinite(o.objective_value):
            continue
        if best is None or o.objective_value < best[0]:
            best = (o.objective_value, list(o.x))
    return best


def select_most_feasible_point(
    observations: list[StageObservation],
) -> list[float] | None:
    """Return the parameter vector of the most feasible candidate.

    Preference order:
    1. Completed with finite objective (lowest objective → best).
    2. Gate-rejected with finite raw data (first by observation order).
    3. Calibration-failed (last resort, first by order).
    Returns ``None`` if no observations.
    """
    if not observations:
        return None

    completed = [o for o in observations if o.status == StageCandidateStatus.COMPLETED
                 and o.objective_value is not None and np.isfinite(o.objective_value)]
    if completed:
        best = min(completed, key=lambda o: o.objective_value)
        return list(best.x)

    gate_rejected = [o for o in observations if o.status == StageCandidateStatus.GATE_REJECTED]
    if gate_rejected:
        return list(gate_rejected[0].x)

    cal_failed = [o for o in observations if o.status == StageCandidateStatus.CALIBRATION_FAILED]
    if cal_failed:
        return list(cal_failed[0].x)

    return list(observations[0].x)


# ---------------------------------------------------------------------------
# Boundary helpers
# ---------------------------------------------------------------------------


def detect_boundary_proximity(
    observations: list[StageObservation],
    bounds: StageBounds,
    proximity_fraction: float = 0.05,
) -> dict[str, Any]:
    """Check if best completed observations are near parameter bounds.

    Returns a dict with keys ``near_boundary`` (bool), ``params_near_boundary``
    (list of parameter names), ``proximity_fraction`` (used threshold).
    """
    best = select_best_completed(observations)
    if best is None:
        return {"near_boundary": False, "params_near_boundary": [], "proximity_fraction": proximity_fraction}

    _, best_x = best
    near: list[str] = []
    for i, name in enumerate(bounds.param_names):
        span = bounds.high[i] - bounds.low[i]
        if span <= 0:
            continue
        dist_to_low = abs(best_x[i] - bounds.low[i]) / span
        dist_to_high = abs(best_x[i] - bounds.high[i]) / span
        if dist_to_low < proximity_fraction or dist_to_high < proximity_fraction:
            near.append(name)

    return {
        "near_boundary": len(near) > 0,
        "params_near_boundary": near,
        "proximity_fraction": proximity_fraction,
    }


# ---------------------------------------------------------------------------
# Stage transition policy
# ---------------------------------------------------------------------------

_DEFAULT_MIN_SPAN_FRACTION = 0.05
_DEFAULT_MIN_COMPLETED_FRACTION = 0.3
_DEFAULT_HIGH_FAIL_RATE = 0.5


def decide_stage_transition(
    summary: StageSummary,
    bounds: StageBounds,
    observations: list[StageObservation],
    *,
    reference_span: np.ndarray | None = None,
    min_span_fraction: float = _DEFAULT_MIN_SPAN_FRACTION,
    min_completed_fraction: float = _DEFAULT_MIN_COMPLETED_FRACTION,
    high_fail_rate: float = _DEFAULT_HIGH_FAIL_RATE,
    max_stages: int = 5,
    current_stage: int = 0,
) -> StageTransitionDecision:
    """Decide the next stage transition based on feasibility evidence.

    Policy rules (in priority order):

    1. **Max stages reached** → ``STOP``.
    2. **No useful evidence** (no CST solves, no completed, no rejected)
       → ``CONTINUE_CURRENT``.
    3. **High fail rate** (calibration/solver/transient) → ``SHIFT`` or
       ``RECENTER`` toward most feasible point, never shrink.
    4. **High gate reject rate**, even if calibration/solver ok →
       ``SHIFT`` or ``RECENTER`` toward feasible gate-pass evidence, never
       shrink immediately.
    5. **Sufficient completed** but **best near boundary** →
       ``REQUEST_ADAPTIVE_REVIEW`` (block shrink, request adaptive bounds).
    6. **Sufficient completed**, feasible region stable, best not near
       boundary, span above min span → ``SHRINK``.
    7. **Insufficient completed** (below ``min_completed_fraction``)
       → ``CONTINUE_CURRENT``.
    8. Catch-all → ``CONTINUE_CURRENT``.

    Parameters
    ----------
    summary : StageSummary
        Aggregate stage statistics.
    bounds : StageBounds
        Current stage bounds.
    observations : list[StageObservation]
        All observations (used for boundary detection and center selection).
    min_span_fraction : float
        Minimum span as fraction of initial span below which shrink is blocked.
    min_completed_fraction : float
        Minimum fraction of CST-solved candidates that must have completed.
    high_fail_rate : float
        Threshold above which fail/reject rate triggers recenter/shift.
    max_stages : int
        Hard limit on stage transitions.
    current_stage : int
        Zero-based stage index.

    Returns
    -------
    StageTransitionDecision
    """
    if reference_span is None:
        reference_span = bounds.span
    diag: dict[str, Any] = {
        "current_stage": current_stage,
        "summary": summary,
    }

    # 1. Max stages
    if current_stage >= max_stages:
        return StageTransitionDecision(
            action=StageTransitionAction.STOP,
            reason=f"Max stages ({max_stages}) reached.",
            diagnostics=diag,
        )

    solves = summary.actual_cst_solves_count

    # 2. No useful evidence
    if solves == 0 and summary.completed_count == 0 and summary.gate_rejected_count == 0:
        return StageTransitionDecision(
            action=StageTransitionAction.CONTINUE_CURRENT,
            reason="No useful evidence yet.",
            diagnostics=diag,
        )

    fail_rate = summary.reject_failure_rate
    most_feasible = select_most_feasible_point(observations)

    # 3. High calibration/solver fail rate
    cal_solv_fail = summary.calibration_failed_count + summary.solver_failed_count
    high_cal_solv = solves > 0 and (cal_solv_fail / solves) > high_fail_rate

    # 4. High gate reject rate
    high_gate_rej = solves > 0 and (summary.gate_rejected_count / solves) > high_fail_rate

    if high_cal_solv:
        diag["high_fail_category"] = "calibration_solver"
        if most_feasible is not None:
            new_bounds = make_recentered_bounds(observations, bounds, center=most_feasible)
            return StageTransitionDecision(
                action=StageTransitionAction.RECENTER,
                reason=f"High calibration/solver fail rate ({fail_rate:.1%}); recentering on most feasible point.",
                proposed_center=most_feasible,
                proposed_bounds=new_bounds,
                diagnostics=diag,
            )
        return StageTransitionDecision(
            action=StageTransitionAction.SHIFT,
            reason=f"High calibration/solver fail rate ({fail_rate:.1%}); no feasible point to recenter on.",
            diagnostics=diag,
        )

    if high_gate_rej:
        diag["high_fail_category"] = "gate"
        if most_feasible is not None:
            new_bounds = make_recentered_bounds(observations, bounds, center=most_feasible)
            return StageTransitionDecision(
                action=StageTransitionAction.RECENTER,
                reason=f"High gate reject rate ({fail_rate:.1%}); recentering on most feasible point.",
                proposed_center=most_feasible,
                proposed_bounds=new_bounds,
                diagnostics=diag,
            )
        return StageTransitionDecision(
            action=StageTransitionAction.SHIFT,
            reason=f"High gate reject rate ({fail_rate:.1%}); no feasible point to recenter on.",
            diagnostics=diag,
        )

    # 5. Check boundary proximity
    boundary_info = detect_boundary_proximity(observations, bounds)
    completed_rate = summary.valid_completed_rate
    diag["boundary_info"] = boundary_info

    if summary.completed_count >= max(3, int(solves * min_completed_fraction)):
        if boundary_info["near_boundary"]:
            return StageTransitionDecision(
                action=StageTransitionAction.REQUEST_ADAPTIVE_REVIEW,
                reason=f"Best point near boundary ({boundary_info['params_near_boundary']}); "
                       "cannot shrink without adaptive bounds review.",
                diagnostics=diag,
            )

        # 6. Shrink if feasible and safe
        min_span = reference_span * min_span_fraction
        if np.all(bounds.span >= min_span) and most_feasible is not None:
            new_bounds = make_shrunk_bounds(observations, bounds, center=most_feasible)
            return StageTransitionDecision(
                action=StageTransitionAction.SHRINK,
                reason="Stable feasible region; shrinking bounds.",
                proposed_center=most_feasible,
                proposed_bounds=new_bounds,
                diagnostics=diag,
            )

    # 7. Insufficient completed
    if summary.completed_count < max(2, int(solves * min_completed_fraction)):
        return StageTransitionDecision(
            action=StageTransitionAction.CONTINUE_CURRENT,
            reason=f"Insufficient completed ({summary.completed_count}/{solves}).",
            diagnostics=diag,
        )

    # 8. Catch-all
    return StageTransitionDecision(
        action=StageTransitionAction.CONTINUE_CURRENT,
        reason="No transition trigger met.",
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Bounds manipulation
# ---------------------------------------------------------------------------


def make_recentered_bounds(
    observations: list[StageObservation],
    current_bounds: StageBounds,
    center: list[float] | None = None,
    shrink_factor: float = 0.5,
) -> StageBounds:
    """Create bounds recentered around *center* (or most feasible point).

    The new span is ``current_span * shrink_factor``, clamped to
    ``[min_span, current_span]``.
    """
    if center is None:
        center_pt = select_most_feasible_point(observations)
        if center_pt is None:
            center_pt = current_bounds.low + current_bounds.span / 2.0
    else:
        center_pt = center

    center_arr = np.asarray(center_pt, dtype=float)
    half_span = current_bounds.span * shrink_factor / 2.0

    new_low = np.maximum(current_bounds.low, center_arr - half_span)
    new_high = np.minimum(current_bounds.high, center_arr + half_span)

    # Ensure low < high
    for i in range(current_bounds.n_params):
        if new_low[i] >= new_high[i]:
            new_low[i] = current_bounds.low[i]
            new_high[i] = current_bounds.high[i]

    return StageBounds(
        param_names=list(current_bounds.param_names),
        low=new_low,
        high=new_high,
        hard_low=current_bounds.hard_low.copy(),
        hard_high=current_bounds.hard_high.copy(),
    )


def make_shrunk_bounds(
    observations: list[StageObservation],
    current_bounds: StageBounds,
    center: list[float] | None = None,
    shrink_factor: float = 0.5,
) -> StageBounds:
    """Shrink bounds toward the best known center.

    Identical to ``make_recentered_bounds`` for now; the distinction allows
    future adaptive-bounds-aware behaviour where shrink may be rejected or
    modified.
    """
    return make_recentered_bounds(
        observations, current_bounds, center=center, shrink_factor=shrink_factor,
    )
