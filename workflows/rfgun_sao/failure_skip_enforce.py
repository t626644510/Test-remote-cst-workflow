"""No-CST failure skip enforce helper — FS4.

Evaluates whether a proposed ``parameter_key`` should be *enforced* as a
skip under the FS policy.  In enforce mode, the evaluator is not called
and no CST budget is consumed.  This module provides the decision model
and a fake-runtime harness for no-CST call-count testing.

DB synthetic-row writing is **not implemented** because v1 schema validation
rejects custom status values.  SE1 schema extension is required before live
enforce (FS5) can record synthetic skip rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from workflows.rfgun_sao.failure_skip_candidates import (
    FailureSkipCandidateConfig,
    find_failure_skip_candidate_for_key,
)


# ===================================================================
# Enforce decision model
# ===================================================================


@dataclass(frozen=True)
class FailureSkipEnforceDecision:
    """Result of evaluating whether to enforce a skip for a parameter key.

    Parameters
    ----------
    enabled : bool
    mode : str
    parameter_key : str or None
    enforce_skip : bool
        Whether to actually skip (true only in enforce mode with eligible
        candidate).
    candidate_found : bool
    candidate_decision : str or None
    evidence_count : int
    source_row_ids : tuple of int
    source_run_ids : tuple of str
    blocked_reasons : tuple of str
    evaluator_must_run : bool
        True when skip is not enforced.
    retry_must_run : bool
        True when skip is not enforced.
    budget_consumed : bool
        False when skip is enforced (no CST solve).
    synthetic_status : str or None
        Synthetic row status if one were written.
    skip_reason : str or None
        Human-readable reason for the skip.
    diagnostics : Mapping
    """
    enabled: bool = False
    mode: str = "disabled"
    parameter_key: str | None = None
    enforce_skip: bool = False
    candidate_found: bool = False
    candidate_decision: str | None = None
    evidence_count: int = 0
    source_row_ids: tuple[int, ...] = ()
    source_run_ids: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    evaluator_must_run: bool = True
    retry_must_run: bool = True
    budget_consumed: bool = True
    synthetic_status: str | None = None
    skip_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ===================================================================
# Enforce decision helper
# ===================================================================


def evaluate_failure_skip_enforce_for_key(
    db_path: str | Path,
    parameter_key: str,
    config: FailureSkipCandidateConfig,
) -> FailureSkipEnforceDecision:
    """Evaluate whether to enforce a skip for *parameter_key*.

    Parameters
    ----------
    db_path : str or Path
    parameter_key : str
    config : FailureSkipCandidateConfig

    Returns
    -------
    FailureSkipEnforceDecision
    """
    # Disabled or dry_run → no enforce
    if not config.enabled or config.mode != "enforce":
        return FailureSkipEnforceDecision(
            enabled=config.enabled,
            mode=config.mode,
            parameter_key=parameter_key,
            enforce_skip=False,
            diagnostics={"reason": f"mode={config.mode} does not enforce"},
        )

    # Look up candidate
    candidate = find_failure_skip_candidate_for_key(db_path, parameter_key, config)

    if candidate is None:
        return FailureSkipEnforceDecision(
            enabled=True, mode="enforce",
            parameter_key=parameter_key,
            enforce_skip=False,
            diagnostics={"reason": "no eligible candidate found"},
        )

    # Check if candidate is enforce-eligible
    if candidate.decision == "enforce_eligible" and candidate.recommended_skip:
        return FailureSkipEnforceDecision(
            enabled=True,
            mode="enforce",
            parameter_key=parameter_key,
            enforce_skip=True,
            candidate_found=True,
            candidate_decision=candidate.decision,
            evidence_count=candidate.evidence_count,
            source_row_ids=candidate.source_row_ids,
            source_run_ids=candidate.source_run_ids,
            evaluator_must_run=False,
            retry_must_run=False,
            budget_consumed=False,
            synthetic_status="skipped_failure_reuse",
            skip_reason=f"enforce skip: {candidate.evidence_count} evidence rows",
            diagnostics={
                "policy_version": candidate.policy_version,
                "source_row_ids": list(candidate.source_row_ids),
            },
        )

    # Candidate exists but not eligible
    return FailureSkipEnforceDecision(
        enabled=True, mode="enforce",
        parameter_key=parameter_key,
        enforce_skip=False,
        candidate_found=True,
        candidate_decision=candidate.decision,
        evidence_count=candidate.evidence_count,
        source_row_ids=candidate.source_row_ids,
        blocked_reasons=candidate.blocked_reasons,
        diagnostics={"reason": f"candidate not eligible: {candidate.decision}"},
    )


# ===================================================================
# Fake-runtime enforce harness (FS4)
# ===================================================================


@dataclass(frozen=True)
class FakeEnforceEvaluationResult:
    """Result of a fake enforce evaluation.

    Parameters
    ----------
    parameter_key : str or None
    enforce_skip : bool
    evaluator_called : bool
    retry_called : bool
    objective_value : float or None
    synthetic_status : str or None
    decision : str or None
    diagnostics : Mapping
    """
    parameter_key: str | None = None
    enforce_skip: bool = False
    evaluator_called: bool = False
    retry_called: bool = False
    objective_value: float | None = None
    synthetic_status: str | None = None
    decision: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


def run_failure_skip_enforce_fake_evaluation(
    db_path: str | Path,
    parameter_key: str,
    config: FailureSkipCandidateConfig,
    evaluator: callable,
    retry_wrapper: callable | None = None,
) -> FakeEnforceEvaluationResult:
    """Run a fake enforce evaluation.

    If enforce_skip=True, the evaluator is **not** called.
    If enforce_skip=False, the evaluator is called exactly once.

    This is a **no-CST test helper only**.  No real CST, no real retry
    runtime, no optimizer wiring.

    Parameters
    ----------
    db_path : str or Path
    parameter_key : str
    config : FailureSkipCandidateConfig
    evaluator : callable
    retry_wrapper : callable or None

    Returns
    -------
    FakeEnforceEvaluationResult
    """
    decision = evaluate_failure_skip_enforce_for_key(db_path, parameter_key, config)

    if decision.enforce_skip:
        # Skip: do NOT call evaluator or retry
        return FakeEnforceEvaluationResult(
            parameter_key=parameter_key,
            enforce_skip=True,
            evaluator_called=False,
            retry_called=False,
            objective_value=None,
            synthetic_status=decision.synthetic_status,
            decision=decision.candidate_decision,
            diagnostics={
                "mode": decision.mode,
                "evidence_count": decision.evidence_count,
                "source_row_ids": list(decision.source_row_ids),
                "reason": decision.skip_reason,
            },
        )

    # Not skipping: call evaluator normally
    evaluator_called = False
    retry_called = False
    objective_value = None

    if retry_wrapper is not None:
        obj_val = retry_wrapper(evaluator, parameter_key=parameter_key)
        evaluator_called = True
        retry_called = True
        objective_value = float(obj_val) if obj_val is not None else None
    else:
        obj_val = evaluator(parameter_key)
        evaluator_called = True
        objective_value = float(obj_val) if obj_val is not None else None

    return FakeEnforceEvaluationResult(
        parameter_key=parameter_key,
        enforce_skip=False,
        evaluator_called=evaluator_called,
        retry_called=retry_called,
        objective_value=objective_value,
        decision=decision.candidate_decision,
        diagnostics={
            "mode": decision.mode,
            "reason": decision.diagnostics.get("reason", "no_skip"),
        },
    )
