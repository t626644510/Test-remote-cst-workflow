"""Checkpoint persistence with per-evaluation status tracking.

Each evaluation point is stored as an ``EvalRecord`` with one of three
statuses — *pending*, *completed*, or *failed_permanent*.  Only records
that exhaust all retry tiers (Tier 3) are marked as permanently failed
and excluded from future retries.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

_logger = logging.getLogger(__name__)

_CHECKPOINT_SUFFIX = ".ckpt"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class EvalRecord:
    """One evaluated (or pending) point in the optimisation history.

    Attributes
    ----------
    x : list[float]
        Physical-space parameter vector.
    status : str
        ``"pending"`` — not yet successfully evaluated.
        ``"completed"`` — all objectives produced finite raw values.
        ``"failed_permanent"`` — Tier-3 retry exhausted, give up.
    phases_done : list[str]
        Completed phase labels, e.g. ``["f2f"]``, ``["f2f","f2w"]``.
        Allows crash recovery to skip already-completed phases.
    f2f_params_hash : str
        Hash of the F2F parameter vector for matching existing .npz data.
    raw_values : dict[str, float]
        Objective name → raw physics value (only for *completed*).
    penalties : dict[str, float]
        Objective name → penalty (only for *completed*).
    solver_ok : bool
        Whether all solvers reported success.
    error : str
        Last error message (empty if *completed*).
    tier_exhausted : bool
        ``True`` when Tier-3 escalation was exhausted.
    timestamp : str
        ISO-format UTC timestamp of the last evaluation attempt.
    """

    x: list[float]
    status: str = "pending"
    phases_done: list[str] = field(default_factory=list)
    f2f_params_hash: str = ""
    raw_values: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    solver_ok: bool = False
    error: str = ""
    tier_exhausted: bool = False
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Checkpoint manager
# ---------------------------------------------------------------------------


class CheckpointManager:
    """Persist optimisation progress to a pickle file on disk.

    Parameters
    ----------
    path : str
        Full path to the checkpoint file (``.ckpt`` suffix added if absent).
    """

    def __init__(self, path: str) -> None:
        if not path.endswith(_CHECKPOINT_SUFFIX):
            path += _CHECKPOINT_SUFFIX
        self._path = path
        self.records: list[EvalRecord] = []
        self.iteration: int = 0
        self.rng_state: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write current state to disk (atomic rename)."""
        tmp = self._path + ".tmp"
        payload = {
            "records": self.records,
            "iteration": self.iteration,
            "rng_state": self.rng_state,
        }
        with open(tmp, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, self._path)
        _logger.debug("Checkpoint saved (%d records) → %s", len(self.records), self._path)

    def load(self) -> bool:
        """Load state from disk.  Returns ``True`` if a checkpoint existed."""
        if not os.path.exists(self._path):
            _logger.info("No checkpoint found at %s — starting fresh", self._path)
            return False
        try:
            with open(self._path, "rb") as fh:
                payload = pickle.load(fh)
            self.records = payload["records"]
            # Migrate old records that lack fields added after the initial pickle
            for r in self.records:
                if not hasattr(r, "phases_done"):
                    r.phases_done = []
                if not hasattr(r, "tier_exhausted"):
                    r.tier_exhausted = False
            self.iteration = payload["iteration"]
            self.rng_state = payload.get("rng_state", {})
            _logger.info(
                "Checkpoint loaded: %d records (iter=%d) from %s",
                len(self.records), self.iteration, self._path,
            )
            return True
        except Exception:
            _logger.exception("Failed to load checkpoint %s — starting fresh", self._path)
            self.records = []
            self.iteration = 0
            self.rng_state = {}
            return False

    def clear(self) -> None:
        """Delete the checkpoint file (normal completion)."""
        try:
            os.remove(self._path)
            _logger.info("Checkpoint cleared: %s", self._path)
        except FileNotFoundError:
            pass
        try:
            os.remove(self._path + ".tmp")
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    @property
    def pending_records(self) -> list[EvalRecord]:
        return [r for r in self.records if r.status == "pending"]

    @property
    def completed_records(self) -> list[EvalRecord]:
        return [r for r in self.records if r.status == "completed"]

    @property
    def failed_permanent_records(self) -> list[EvalRecord]:
        return [r for r in self.records if r.status == "failed_permanent"]

    @property
    def pending_count(self) -> int:
        return sum(1 for r in self.records if r.status == "pending")

    @property
    def completed_count(self) -> int:
        return sum(1 for r in self.records if r.status == "completed")

    # ------------------------------------------------------------------
    # Warm-start helpers
    # ------------------------------------------------------------------

    def get_warm_xy(self) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(X, y)`` arrays from completed records for SAO warm-start.

        Includes records where *phases_done* contains ``"f2f"`` (partial success:
        F2F S-parameters are valid even if wakefield was skipped or failed).
        *y* is the sum of objective penalties (scalar per point).
        """
        usable = [
            r for r in self.records
            if r.status == "completed" or "f2f" in r.phases_done
        ]
        if not usable:
            return np.empty((0, 0)), np.empty((0,))
        X = np.array([r.x for r in usable], dtype=float)
        y = np.array([sum(r.penalties.values()) if r.penalties else 0.0 for r in usable], dtype=float)
        return X, y

    @property
    def partial_records(self) -> list[EvalRecord]:
        """Records with *phases_done* set but not fully completed (for crash recovery)."""
        return [
            r for r in self.records
            if r.status == "pending" and r.phases_done
        ]

    # ------------------------------------------------------------------
    # Record management
    # ------------------------------------------------------------------

    def add_pending(self, x: np.ndarray) -> int:
        """Add a new pending record.  Returns its index."""
        rec = EvalRecord(
            x=x.tolist(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.records.append(rec)
        return len(self.records) - 1

    def mark_phase_done(
        self,
        idx: int,
        phases: list[str],
        params_hash: str = "",
    ) -> None:
        """Record that specific phases have completed (for crash recovery)."""
        rec = self.records[idx]
        rec.phases_done = list(phases)
        if params_hash:
            rec.f2f_params_hash = params_hash
        rec.timestamp = datetime.now(timezone.utc).isoformat()

    def mark_completed(
        self,
        idx: int,
        raw_values: dict[str, float],
        penalties: dict[str, float],
        solver_ok: bool = True,
        phases: list[str] | None = None,
    ) -> None:
        """Mark record *idx* as successfully evaluated."""
        rec = self.records[idx]
        rec.status = "completed"
        rec.raw_values = dict(raw_values)
        rec.penalties = dict(penalties)
        rec.solver_ok = solver_ok
        rec.error = ""
        rec.tier_exhausted = False
        rec.timestamp = datetime.now(timezone.utc).isoformat()
        if phases is not None:
            rec.phases_done = list(phases)

    def mark_failed(
        self,
        idx: int,
        error: str = "",
        tier_exhausted: bool = False,
    ) -> None:
        """Mark record *idx* as failed (or permanently failed if Tier 3 exhausted)."""
        rec = self.records[idx]
        rec.error = error
        rec.tier_exhausted = tier_exhausted
        rec.timestamp = datetime.now(timezone.utc).isoformat()
        if tier_exhausted:
            rec.status = "failed_permanent"
        else:
            rec.status = "pending"  # remains retryable

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"CheckpointManager(path={self._path!r}, "
            f"records={len(self.records)} "
            f"(pending={self.pending_count}, "
            f"completed={self.completed_count}, "
            f"failed_permanent={len(self.failed_permanent_records)}), "
            f"iter={self.iteration})"
        )
