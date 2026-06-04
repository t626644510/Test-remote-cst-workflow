"""No-CST failure skip dry-run diagnostics — FS3.

Evaluates whether a proposed ``parameter_key`` would be skipped under
the FS policy, but never actually skips anything.  All evaluator, retry,
and CST budget commitments are reported as "must run" in dry-run mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from workflows.rfgun_sao.failure_skip_candidates import (
    FailureSkipCandidateConfig,
    find_failure_skip_candidate_for_key,
    load_failure_skip_candidates,
    resolve_failure_skip_config,
)


# ===================================================================
# Dry-run decision model
# ===================================================================


@dataclass(frozen=True)
class FailureSkipDryRunDecision:
    """One dry-run decision for a single parameter key.

    Parameters
    ----------
    enabled : bool
        Whether skip candidate loading is enabled.
    mode : str
        ``disabled``, ``dry_run``, or ``enforce``.
    parameter_key : str or None
        The proposed parameter key.
    would_skip : bool
        Whether FS policy would skip this point (diagnostic only).
    candidate_found : bool
        Whether an eligible candidate was found.
    candidate_decision : str or None
        The candidate's decision string.
    evidence_count : int
        Number of evidence rows for this key.
    source_row_ids : tuple of int
        Evidence DB row IDs.
    blocked_reasons : tuple of str
        Reasons blocking the skip, if any.
    evaluator_must_run : bool
        True in dry_run — evaluator must always be called.
    retry_must_run : bool
        True in dry_run — retry must always be called.
    budget_consumed_normally : bool
        True in dry_run — CST budget consumed normally.
    diagnostics : Mapping
        Extra diagnostic information.
    """
    enabled: bool = False
    mode: str = "disabled"
    parameter_key: str | None = None
    would_skip: bool = False
    candidate_found: bool = False
    candidate_decision: str | None = None
    evidence_count: int = 0
    source_row_ids: tuple[int, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    evaluator_must_run: bool = True
    retry_must_run: bool = True
    budget_consumed_normally: bool = True
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FailureSkipDryRunSummary:
    """Summary of dry-run decisions for multiple proposed points.

    Parameters
    ----------
    enabled : bool
    checked_points : int
    would_skip_count : int
    no_candidate_count : int
    blocked_count : int
    decisions : tuple of FailureSkipDryRunDecision
    by_decision : Mapping
    """
    enabled: bool = False
    checked_points: int = 0
    would_skip_count: int = 0
    no_candidate_count: int = 0
    blocked_count: int = 0
    decisions: tuple[FailureSkipDryRunDecision, ...] = ()
    by_decision: dict[str, int] = field(default_factory=dict)


# ===================================================================
# Dry-run decision helper
# ===================================================================


def evaluate_failure_skip_dry_run_for_key(
    db_path: str | Path,
    parameter_key: str,
    config: FailureSkipCandidateConfig,
) -> FailureSkipDryRunDecision:
    """Evaluate dry-run decision for a single ``parameter_key``.

    Parameters
    ----------
    db_path : str or Path
        Path to the durable evaluation DB.
    parameter_key : str
        The proposed parameter key to check.
    config : FailureSkipCandidateConfig
        Resolved skip candidate config.

    Returns
    -------
    FailureSkipDryRunDecision
    """
    # If disabled, return disabled decision immediately
    if not config.enabled or config.mode == "disabled":
        return FailureSkipDryRunDecision(
            enabled=False, mode="disabled",
            diagnostics={"reason": "failure_skip disabled"},
        )

    # Enforce mode is not implemented in FS3
    if config.mode == "enforce":
        return FailureSkipDryRunDecision(
            enabled=True, mode=config.mode,
            parameter_key=parameter_key,
            would_skip=False,
            candidate_found=False,
            diagnostics={"reason": "enforce mode not implemented in FS3; downgraded to dry-run"},
            evaluator_must_run=True,
            retry_must_run=True,
            budget_consumed_normally=True,
        )

    # Dry-run candidate lookup
    candidate = find_failure_skip_candidate_for_key(db_path, parameter_key, config)

    if candidate is None:
        return FailureSkipDryRunDecision(
            enabled=True, mode=config.mode,
            parameter_key=parameter_key,
            would_skip=False,
            candidate_found=False,
            diagnostics={"reason": "no eligible candidate found"},
        )

    return FailureSkipDryRunDecision(
        enabled=True,
        mode=config.mode,
        parameter_key=parameter_key,
        would_skip=candidate.recommended_skip,
        candidate_found=True,
        candidate_decision=candidate.decision,
        evidence_count=candidate.evidence_count,
        source_row_ids=candidate.source_row_ids,
        blocked_reasons=candidate.blocked_reasons,
        diagnostics={"candidate_policy_version": candidate.policy_version},
    )


def evaluate_failure_skip_dry_run_for_keys(
    db_path: str | Path,
    parameter_keys: Iterable[str],
    config: FailureSkipCandidateConfig,
) -> FailureSkipDryRunSummary:
    """Evaluate dry-run decisions for multiple proposed keys.

    Parameters
    ----------
    db_path : str or Path
    parameter_keys : iterable of str
    config : FailureSkipCandidateConfig

    Returns
    -------
    FailureSkipDryRunSummary
    """
    decisions: list[FailureSkipDryRunDecision] = []
    for pk in parameter_keys:
        decision = evaluate_failure_skip_dry_run_for_key(db_path, pk, config)
        decisions.append(decision)

    would_skip_count = sum(1 for d in decisions if d.would_skip)
    no_candidate_count = sum(1 for d in decisions if not d.candidate_found and d.enabled)
    blocked_count = sum(1 for d in decisions if d.candidate_found and not d.would_skip)

    # Build by_decision summary
    by_decision: dict[str, int] = {}
    for d in decisions:
        key = d.candidate_decision or "no_candidate"
        by_decision[key] = by_decision.get(key, 0) + 1

    return FailureSkipDryRunSummary(
        enabled=config.enabled if decisions else False,
        checked_points=len(decisions),
        would_skip_count=would_skip_count,
        no_candidate_count=no_candidate_count,
        blocked_count=blocked_count,
        decisions=tuple(decisions),
        by_decision=dict(by_decision),
    )


# ===================================================================
# Fake-runtime dry-run harness (FS3.1)
# ===================================================================


@dataclass(frozen=True)
class FakeEvaluationResult:
    """Result of a fake dry-run evaluation.

    Parameters
    ----------
    parameter_key : str or None
    evaluator_called : bool
        Whether the fake evaluator was called.
    retry_called : bool
        Whether a retry wrapper was called (if configured).
    objective_value : float or None
        The return value of the fake evaluator.
    would_skip : bool
        Dry-run would_skip diagnosis.
    candidate_found : bool
    candidate_decision : str or None
    evidence_count : int
    diagnostics : Mapping
    """
    parameter_key: str | None = None
    evaluator_called: bool = False
    retry_called: bool = False
    objective_value: float | None = None
    would_skip: bool = False
    candidate_found: bool = False
    candidate_decision: str | None = None
    evidence_count: int = 0
    diagnostics: dict[str, Any] = field(default_factory=dict)


def run_failure_skip_dry_run_fake_evaluation(
    db_path: str | Path,
    parameter_key: str,
    config: FailureSkipCandidateConfig,
    evaluator: callable,
    retry_wrapper: callable | None = None,
) -> FakeEvaluationResult:
    """Run a fake dry-run evaluation that always calls the evaluator.

    This is a **no-CST test helper only**.  It does not call the real
    CST-based evaluator, retry runtime, or optimizer.

    Parameters
    ----------
    db_path : str or Path
        Path to the durable evaluation DB.
    parameter_key : str
        The proposed parameter key.
    config : FailureSkipCandidateConfig
        Resolved skip candidate config.
    evaluator : callable
        Fake evaluator ``f(x) -> float``.  Called unconditionally.
    retry_wrapper : callable or None
        If provided, ``retry_wrapper(evaluator, **kwargs)`` is called
        instead of direct ``evaluator()``.

    Returns
    -------
    FakeEvaluationResult
    """
    # Dry-run decision
    decision = evaluate_failure_skip_dry_run_for_key(db_path, parameter_key, config)

    # Call evaluator unconditionally
    evaluator_called = False
    retry_called = False
    objective_value = None

    if retry_wrapper is not None:
        # Call through retry wrapper
        obj_val = retry_wrapper(evaluator, parameter_key=parameter_key)
        evaluator_called = True
        retry_called = True
        objective_value = float(obj_val) if obj_val is not None else None
    else:
        # Call evaluator directly
        obj_val = evaluator(parameter_key)
        evaluator_called = True
        objective_value = float(obj_val) if obj_val is not None else None

    return FakeEvaluationResult(
        parameter_key=parameter_key,
        evaluator_called=evaluator_called,
        retry_called=retry_called,
        objective_value=objective_value,
        would_skip=decision.would_skip,
        candidate_found=decision.candidate_found,
        candidate_decision=decision.candidate_decision,
        evidence_count=decision.evidence_count,
        diagnostics=dict(decision.diagnostics) if decision.diagnostics else {},
    )
