# Stage/adaptive runtime adapter for the RF gun SAO workflow.
# Opt-in only, disabled by default.  No CST dependency.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from workflows.rfgun_sao.stage_search import (
    StageBounds,
    StageCandidateStatus,
    StageObservation,
    StageSummary,
    StageTransitionAction,
    StageTransitionDecision,
    decide_stage_transition,
    summarize_stage_observations,
)
from workflows.rfgun_sao.stage_adaptive_policy import (
    StageAdaptiveAction,
    StageAdaptivePolicyInput,
    StageAdaptivePolicyDecision,
    combine_stage_and_adaptive_decisions,
    extract_high_quality_points,
)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def resolve_stage_search_config(cfg: dict) -> dict:
    """Resolve stage search config from a YAML config dict.

    Reads ``cfg["optimization"]["stage_search"]``.

    Returns a dict with keys:
    - ``enabled`` (bool, default ``False``)
    - ``max_stages`` (int, default ``5``)
    - ``min_completed_fraction`` (float, default ``0.3``)
    - ``high_fail_rate`` (float, default ``0.5``)
    - ``min_span_fraction`` (float, default ``0.05``)
    """
    opt = cfg.get("optimization", {})
    ss = opt.get("stage_search", {})
    if isinstance(ss, bool):
        if ss:
            return {"enabled": True, "max_stages": 5}
        return {"enabled": False}
    if not isinstance(ss, dict):
        return {"enabled": False}
    return {
        "enabled": bool(ss.get("enabled", False)),
        "max_stages": int(ss.get("max_stages", 5)),
        "min_completed_fraction": float(ss.get("min_completed_fraction", 0.3)),
        "high_fail_rate": float(ss.get("high_fail_rate", 0.5)),
        "min_span_fraction": float(ss.get("min_span_fraction", 0.05)),
    }


def resolve_adaptive_bounds_config(cfg: dict) -> dict:
    """Resolve adaptive bounds config from a YAML config dict.

    Reads ``cfg["optimization"]["adaptive_bounds"]``.

    Returns a dict with keys:
    - ``enabled`` (bool, default ``False``)
    - ``proximity_fraction`` (float, default ``0.05``)
    - ``expand_fraction`` (float, default ``0.1``)
    """
    opt = cfg.get("optimization", {})
    ab = opt.get("adaptive_bounds", {})
    if isinstance(ab, bool):
        if ab:
            return {"enabled": True, "proximity_fraction": 0.05, "expand_fraction": 0.1}
        return {"enabled": False}
    if not isinstance(ab, dict):
        return {"enabled": False}
    return {
        "enabled": bool(ab.get("enabled", False)),
        "proximity_fraction": float(ab.get("proximity_fraction", 0.05)),
        "expand_fraction": float(ab.get("expand_fraction", 0.1)),
    }


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------


@dataclass
class StageRuntimeState:
    """Mutable state for stage/adaptive runtime tracking.

    Parameters
    ----------
    initial_bounds : StageBounds
        Starting parameter bounds.
    current_bounds : StageBounds
        Current stage bounds (may be updated after each stage transition).
    reference_span : np.ndarray
        Reference span for min-span protection.
    current_stage : int
        Zero-based current stage index.
    observations : list
        All observations collected in the current stage.
    last_stage_summary : StageSummary or None
        Summary from the most recent ``decide_stage_transition`` call.
    last_stage_decision : StageTransitionDecision or None
    last_adaptive_policy_decision : StageAdaptivePolicyDecision or None
    """
    initial_bounds: StageBounds
    current_bounds: StageBounds
    reference_span: np.ndarray
    current_stage: int = 0
    observations: list = field(default_factory=list)
    last_stage_summary: StageSummary | None = None
    last_stage_decision: StageTransitionDecision | None = None
    last_adaptive_policy_decision: StageAdaptivePolicyDecision | None = None


# ---------------------------------------------------------------------------
# Observation recording
# ---------------------------------------------------------------------------


def record_stage_observation(
    state: StageRuntimeState,
    *,
    x: list[float],
    status: str | StageCandidateStatus,
    objective_value: float | None = None,
    gate_pass: bool | None = None,
    calibration_pass: bool | None = None,
    solver_ok: bool | None = None,
    retry_attempts: int = 0,
    reused: bool = False,
    error: str = "",
) -> None:
    """Record one evaluation observation into the runtime state.

    No CST dependency.  Accepts both string and ``StageCandidateStatus``
    for *status*.
    """
    if isinstance(status, str):
        try:
            status = StageCandidateStatus(status)
        except ValueError:
            status = StageCandidateStatus.UNKNOWN_FAILED

    obs = StageObservation(
        x=list(x),
        status=status,
        objective_value=objective_value,
        gate_pass=gate_pass,
        calibration_pass=calibration_pass,
        solver_ok=solver_ok,
        retry_attempts=retry_attempts,
        reused=reused,
        error=error,
    )
    state.observations.append(obs)


# ---------------------------------------------------------------------------
# Stage bounds update
# ---------------------------------------------------------------------------


def maybe_update_stage_bounds(
    state: StageRuntimeState,
    *,
    stage_cfg: dict | None = None,
    adaptive_cfg: dict | None = None,
) -> StageAdaptivePolicyDecision:
    """Evaluate whether to transition to a new stage based on observations.

    This is the main runtime adapter: it summarizes observations, runs the
    stage transition decision, optionally runs adaptive bounds review
    (via ``combine_stage_and_adaptive_decisions``), and returns the final
    policy decision.  **It does not mutate the optimizer or live CST path.**

    Parameters
    ----------
    state : StageRuntimeState
        Mutable runtime state.  ``observations`` must be populated.
    stage_cfg : dict or None
        Stage search config (from ``resolve_stage_search_config``).
        If ``enabled`` is ``False`` or missing, returns a no-op decision.
    adaptive_cfg : dict or None
        Adaptive bounds config (from ``resolve_adaptive_bounds_config``).
        Only used when stage search is enabled.

    Returns
    -------
    StageAdaptivePolicyDecision
        The final policy decision.  The caller may use this to update bounds
        or continue.
    """
    if stage_cfg is None:
        stage_cfg = {"enabled": False}
    if adaptive_cfg is None:
        adaptive_cfg = {"enabled": False, "expand_fraction": 0.1, "proximity_fraction": 0.05}

    if not stage_cfg.get("enabled"):
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.CONTINUE_CURRENT,
            reason="Stage search disabled.",
            final_bounds=state.current_bounds,
            diagnostics={"stage_cfg_enabled": False},
        )

    # Summarize
    summary = summarize_stage_observations(state.observations, state.current_bounds)
    state.last_stage_summary = summary

    # Stage transition decision
    stage_dec = decide_stage_transition(
        summary,
        state.current_bounds,
        state.observations,
        reference_span=state.reference_span,
        max_stages=stage_cfg.get("max_stages", 5),
        current_stage=state.current_stage,
        min_completed_fraction=stage_cfg.get("min_completed_fraction", 0.3),
        high_fail_rate=stage_cfg.get("high_fail_rate", 0.5),
        min_span_fraction=stage_cfg.get("min_span_fraction", 0.05),
    )
    state.last_stage_decision = stage_dec

    # Build adaptive policy input
    policy_inp = StageAdaptivePolicyInput(
        current_bounds=state.current_bounds,
        stage_decision=stage_dec,
        observations=state.observations,
        reference_span=state.reference_span,
    )

    # Combine with adaptive review
    adaptive_enabled = adaptive_cfg.get("enabled", False)
    if adaptive_enabled:
        policy_dec = combine_stage_and_adaptive_decisions(
            policy_inp,
            expand_fraction=adaptive_cfg.get("expand_fraction", 0.1),
        )
    else:
        # Without adaptive, map stage decision directly
        policy_dec = _stage_only_policy(policy_inp)

    state.last_adaptive_policy_decision = policy_dec

    # Update state if a transition occurred
    if policy_dec.final_bounds is not None and policy_dec.action in (
        StageAdaptiveAction.USE_STAGE_DECISION,
        StageAdaptiveAction.USE_ADAPTIVE_BOUNDS,
        StageAdaptiveAction.BLOCK_STAGE_SHRINK,
    ):
        state.current_bounds = policy_dec.final_bounds
        # Increment stage counter for non-continue actions
        if policy_dec.action != StageAdaptiveAction.CONTINUE_CURRENT:
            state.current_stage += 1
            # Reset observations for the new stage
            state.observations = []

    return policy_dec


def _stage_only_policy(
    inp: StageAdaptivePolicyInput,
) -> StageAdaptivePolicyDecision:
    """Map stage decision directly without adaptive review."""
    stage = inp.stage_decision
    if stage.action == StageTransitionAction.STOP:
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.STOP,
            reason=f"Stage STOP: {stage.reason}",
            final_bounds=inp.current_bounds,
            stage_action=stage.action,
        )
    if stage.action == StageTransitionAction.CONTINUE_CURRENT:
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.CONTINUE_CURRENT,
            reason=stage.reason or "Stage continue.",
            final_bounds=inp.current_bounds,
            stage_action=stage.action,
        )
    if stage.action in (
        StageTransitionAction.RECENTER,
        StageTransitionAction.SHIFT,
        StageTransitionAction.SHRINK,
    ):
        proposed = stage.proposed_bounds or inp.current_bounds
        return StageAdaptivePolicyDecision(
            action=StageAdaptiveAction.USE_STAGE_DECISION,
            reason=f"Stage {stage.action.value}: {stage.reason}",
            final_bounds=proposed,
            stage_action=stage.action,
        )
    # REQUEST_ADAPTIVE_REVIEW without adaptive enabled → continue
    return StageAdaptivePolicyDecision(
        action=StageAdaptiveAction.CONTINUE_CURRENT,
        reason="Adaptive review not available; continuing.",
        final_bounds=inp.current_bounds,
        stage_action=stage.action,
    )
