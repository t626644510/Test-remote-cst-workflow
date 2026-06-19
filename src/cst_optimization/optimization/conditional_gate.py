"""Adaptive conditional-solver gate with TCP-style sliding window.

Three-phase strategy for Workflow 2:
  Phase A (WARMUP)    — unconditional F2W/F2WO passes to build initial GP data
  Phase B (GP_GATED)  — GP predictions gate F2W execution; TCP window adjusts
                        the dB threshold based on prediction-accuracy feedback
  Phase C (FULL_4OBJ) — full 4-objective BO; window maintained for efficiency

The "TCP sliding window" metaphor:
  - Each consecutive successful GP-prediction validation tightens the dB
    threshold by ``delta_db`` (like TCP cwnd++ on ACK).
  - Each failed validation loosens it (like TCP multiplicative decrease).
  - Too many consecutive failures → GP models are rebuilt from scratch
    and the phase returns to GP_GATED.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums / Config
# ---------------------------------------------------------------------------


class GatePhase(Enum):
    WARMUP = "warmup"
    GP_GATED = "gp_gated"
    FULL_4OBJ = "full_4obj"


@dataclass
class GateConfig:
    """All configurable parameters for the adaptive conditional gate."""

    # ── Phase A: warming-up ──────────────────────────────────────────
    warmup_n_evaluations: int = 10

    # ── Phase B: GP-gated ────────────────────────────────────────────
    gp_skip_threshold: float = 0.5  # theta_skip: predicted penalty below this → run F2W
    validate_every_n: int = 5       # K: unconditional validation every K evaluations
    trust_consecutive: int = 5      # N_trust: tighten window after this many consecutive passes
    max_consecutive_fail: int = 3   # N_max_fail: rebuild GP after this many consecutive failures
    prediction_error_epsilon: float = 0.15  # epsilon_trust: max allowed |pred - meas| for pass

    # ── TCP sliding window ───────────────────────────────────────────
    delta_db: float = 2.0           # delta_dB: step size for tighten/loosen
    db_initial: float = -25.0       # initial dB threshold (permissive)
    db_min: float = -31.0           # tightest dB threshold

    # ── Phase transition thresholds ──────────────────────────────────
    pass_rate_threshold: float = 0.6     # F2W pass rate for B→C transition
    gp_accuracy_threshold: float = 0.85  # prediction accuracy for B→C transition
    pass_rate_critical: float = 0.3      # F2W pass rate triggering emergency fallback

    # ── GP model ─────────────────────────────────────────────────────
    gp_alpha: float = 1e-3          # GP noise level (regularisation)


# ---------------------------------------------------------------------------
# AdaptiveConditionalGate
# ---------------------------------------------------------------------------


class AdaptiveConditionalGate:
    """Three-phase adaptive gate with TCP sliding window for Workflow 2.

    Parameters
    ----------
    config : GateConfig
    objective_names : list[str]
        Names of all 4 Workflow 2 objectives in order:
        [antenna_absorption, antenna_absorption_db, z_longitudinal, z_transverse].
    """

    def __init__(self, config: GateConfig, objective_names: list[str]) -> None:
        self._cfg = config
        self._obj_names = list(objective_names)
        self._n_obj = len(objective_names)

        # ── Phase state ──────────────────────────────────────────────
        self.phase: GatePhase = GatePhase.WARMUP
        self._eval_count: int = 0
        self._f2w_pass_count: int = 0
        self._f2w_total: int = 0
        self._warmup_start_count: int = 0  # eval_count when current WARMUP stint began

        # ── TCP window state ─────────────────────────────────────────
        self.current_db_threshold: float = config.db_initial
        self.consecutive_pass: int = 0
        self.consecutive_fail: int = 0

        # ── GP models (one per objective, lazy-init) ─────────────────
        self._gps: list[GaussianProcessRegressor | None] = [None] * self._n_obj
        self._X: list[np.ndarray] = []     # training inputs
        self._Y: list[np.ndarray] = []     # training targets (penalties, n_obj columns)

        # ── Validation history ───────────────────────────────────────
        self._prediction_errors: list[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_warmup(self) -> bool:
        return self.phase == GatePhase.WARMUP

    @property
    def f2w_pass_rate(self) -> float:
        """Fraction of evaluations where F2W was actually run."""
        if self._f2w_total == 0:
            return 1.0
        return self._f2w_pass_count / self._f2w_total

    @property
    def prediction_accuracy(self) -> float:
        """Mean prediction accuracy (1 - mean relative error) over validation history."""
        if not self._prediction_errors:
            return 0.0
        return float(1.0 - np.mean(self._prediction_errors))

    # ------------------------------------------------------------------
    # Gate decision
    # ------------------------------------------------------------------

    def should_run_conditional(
        self,
        trigger_penalty: float,
        gp_predictions: dict[str, float] | None = None,
    ) -> bool:
        """Decide whether to run a conditional project (F2W / F2WO).

        Parameters
        ----------
        trigger_penalty : float
            The trigger objective's current penalty (e.g. antenna_absorption).
        gp_predictions : dict or None
            GP-predicted penalties for wakefield objectives, keyed by name.
            Only used in GP_GATED and FULL_4OBJ phases.

        Returns
        -------
        bool
            ``True`` → run the conditional solver.
        """
        if self.phase == GatePhase.WARMUP:
            # Phase A: always run — unconditional pass
            return True

        # For GP_GATED and FULL_4OBJ phases:
        # the trigger objective penalty is the primary gate,
        # augmented by GP predictions for wakefield objectives
        if gp_predictions is None:
            # No GP yet — fall back to trigger penalty only
            return trigger_penalty < self._cfg.gp_skip_threshold

        if self.phase == GatePhase.GP_GATED:
            # Conservative: GP says "good" → run to verify
            z_pred = gp_predictions.get("z_longitudinal", 0.0)
            zt_pred = gp_predictions.get("z_transverse", 0.0)
            return (
                z_pred < self._cfg.gp_skip_threshold
                and zt_pred < self._cfg.gp_skip_threshold
            )

        # Phase FULL_4OBJ: aggressive — default is RUN; GP says "bad" → skip
        # Use a stricter threshold to minimise false skips
        bad_threshold = self._cfg.gp_skip_threshold + 0.2
        z_pred = gp_predictions.get("z_longitudinal", 0.0)
        zt_pred = gp_predictions.get("z_transverse", 0.0)
        if z_pred >= bad_threshold and zt_pred >= bad_threshold:
            return False  # GP highly confident both are bad → skip
        return True  # otherwise run

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def record_evaluation(
        self,
        x: np.ndarray,
        penalties: dict[str, float],
        f2w_ran: bool,
    ) -> None:
        """Feed a completed evaluation into the gate for model updating.

        Parameters
        ----------
        x : np.ndarray
            Parameter vector (physical space).
        penalties : dict[str, float]
            Measured penalties keyed by objective name.
        f2w_ran : bool
            Whether F2W was actually solved in this evaluation.
        """
        self._eval_count += 1
        if f2w_ran:
            self._f2w_pass_count += 1
        self._f2w_total += 1

        # Store data point
        y_vec = np.array([penalties.get(name, np.nan) for name in self._obj_names])
        self._X.append(x.copy())
        self._Y.append(y_vec)

        # Phase transition checks
        self._maybe_transition()

    # ------------------------------------------------------------------
    # GP prediction
    # ------------------------------------------------------------------

    def predict(self, x: np.ndarray) -> dict[str, float]:
        """Return GP-predicted penalties for all objectives.

        Returns empty dict if GP models are not yet trained.
        """
        if len(self._X) < 3:
            return {}
        self._ensure_gps_trained()
        result: dict[str, float] = {}
        X_new = x.reshape(1, -1)
        for i, name in enumerate(self._obj_names):
            gp = self._gps[i]
            if gp is not None:
                pred = gp.predict(X_new, return_std=False)
                result[name] = float(pred[0])
        return result

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def should_validate(self) -> bool:
        """Return True if THIS (just-completed) evaluation was a validation sample."""
        if self.phase == GatePhase.WARMUP:
            return False
        if self._cfg.validate_every_n <= 0:
            return False
        return self._eval_count % self._cfg.validate_every_n == 0

    def should_validate_next(self) -> bool:
        """Return True if the NEXT evaluation should be unconditional validation."""
        if self.phase == GatePhase.WARMUP:
            return True  # all warmup evals are unconditional
        if self._cfg.validate_every_n <= 0:
            return False
        return (self._eval_count + 1) % self._cfg.validate_every_n == 0

    def record_validation(
        self,
        predicted: dict[str, float],
        measured: dict[str, float],
    ) -> None:
        """Compare GP predictions against unconditional validation measurements.

        Updates the TCP window (tighten/loosen) based on prediction accuracy.
        """
        errors = []
        for name in self._obj_names:
            p = predicted.get(name, np.nan)
            m = measured.get(name, np.nan)
            if np.isfinite(p) and np.isfinite(m):
                errors.append(abs(p - m))

        if not errors:
            return

        mean_error = float(np.mean(errors))
        self._prediction_errors.append(mean_error)

        if mean_error <= self._cfg.prediction_error_epsilon:
            # ── Validation PASS ──────────────────────────────────────
            self.consecutive_pass += 1
            self.consecutive_fail = 0
            _logger.info(
                "Gate validation PASS (error=%.4f, consecutive_pass=%d/%d)",
                mean_error, self.consecutive_pass, self._cfg.trust_consecutive,
            )
            if self.consecutive_pass >= self._cfg.trust_consecutive:
                self._tighten_window()
                self.consecutive_pass = 0
        else:
            # ── Validation FAIL ──────────────────────────────────────
            self.consecutive_fail += 1
            self.consecutive_pass = 0
            _logger.warning(
                "Gate validation FAIL (error=%.4f > epsilon=%.3f, consecutive_fail=%d/%d)",
                mean_error, self._cfg.prediction_error_epsilon,
                self.consecutive_fail, self._cfg.max_consecutive_fail,
            )
            self._loosen_window()
            if self.consecutive_fail >= self._cfg.max_consecutive_fail:
                _logger.error(
                    "GP prediction accuracy degraded — rebuilding models and "
                    "returning to GP_GATED phase"
                )
                self._rebuild_gps()
                self.phase = GatePhase.GP_GATED
                self.current_db_threshold = self._cfg.db_initial
                self.consecutive_fail = 0
                self.consecutive_pass = 0

    # ------------------------------------------------------------------
    # TCP window control
    # ------------------------------------------------------------------

    def _tighten_window(self) -> None:
        """Tighten the dB threshold by one step (more selective)."""
        new_val = self.current_db_threshold - self._cfg.delta_db
        if new_val >= self._cfg.db_min:
            self.current_db_threshold = new_val
            _logger.info(
                "Gate window TIGHTENED: %.1f → %.1f dB",
                new_val + self._cfg.delta_db, new_val,
            )
        else:
            _logger.info(
                "Gate window at minimum (%.1f dB) — cannot tighten further",
                self.current_db_threshold,
            )

    def _loosen_window(self) -> None:
        """Loosen the dB threshold by one step (more permissive)."""
        if self.current_db_threshold < self._cfg.db_initial:
            self.current_db_threshold += self._cfg.delta_db
            _logger.info(
                "Gate window LOOSENED: %.1f → %.1f dB",
                self.current_db_threshold - self._cfg.delta_db,
                self.current_db_threshold,
            )
        else:
            _logger.info(
                "Gate window at initial (%.1f dB) — cannot loosen further",
                self.current_db_threshold,
            )

    # ------------------------------------------------------------------
    # Internal: GP training
    # ------------------------------------------------------------------

    def _ensure_gps_trained(self) -> None:
        """Train one GP per objective on all available data."""
        if len(self._X) < 3:
            return
        X = np.vstack(self._X)
        # Normalise inputs to [0, 1]
        self._x_min = X.min(axis=0)
        self._x_max = X.max(axis=0)
        x_range = self._x_max - self._x_min
        x_range[x_range == 0] = 1.0
        X_norm = (X - self._x_min) / x_range

        kernel = (
            ConstantKernel(1.0, constant_value_bounds=(1e-3, 1e3))
            * RBF(length_scale=1.0, length_scale_bounds=(1e-3, 100.0))
            + WhiteKernel(noise_level=self._cfg.gp_alpha, noise_level_bounds=(1e-6, 1.0))
        )

        for i in range(self._n_obj):
            y = np.array([row[i] for row in self._Y if np.isfinite(row[i])])
            if len(y) < 3:
                continue
            # Only train on rows where this objective has a valid value
            valid_mask = np.isfinite([row[i] for row in self._Y])
            if valid_mask.sum() < 3:
                continue
            X_valid = X_norm[valid_mask]
            y_valid = np.array([self._Y[j][i] for j in range(len(self._Y)) if valid_mask[j]])
            gp = GaussianProcessRegressor(
                kernel=kernel,
                alpha=self._cfg.gp_alpha,
                n_restarts_optimizer=5,
                normalize_y=True,
            )
            try:
                gp.fit(X_valid, y_valid)
                self._gps[i] = gp
            except Exception:
                _logger.warning("Failed to train GP for objective '%s'", self._obj_names[i])

    def _rebuild_gps(self) -> None:
        """Clear and retrain all GP models from scratch."""
        self._gps = [None] * self._n_obj
        if len(self._X) >= 3:
            self._ensure_gps_trained()

    # ------------------------------------------------------------------
    # Internal: phase transitions
    # ------------------------------------------------------------------

    def _maybe_transition(self) -> None:
        """Check and execute phase transitions based on current state."""
        if self.phase == GatePhase.WARMUP:
            warmup_evals = self._eval_count - self._warmup_start_count
            if warmup_evals >= self._cfg.warmup_n_evaluations:
                _logger.info(
                    "Warmup complete (%d evaluations in stint) — entering GP_GATED phase",
                    warmup_evals,
                )
                self.phase = GatePhase.GP_GATED
                self._rebuild_gps()
            return

        if self.phase == GatePhase.GP_GATED:
            if (
                self.f2w_pass_rate >= self._cfg.pass_rate_threshold
                and self.prediction_accuracy >= self._cfg.gp_accuracy_threshold
                and self._eval_count > self._cfg.warmup_n_evaluations + 10
            ):
                _logger.info(
                    "GP_GATED → FULL_4OBJ (pass_rate=%.2f, accuracy=%.2f)",
                    self.f2w_pass_rate, self.prediction_accuracy,
                )
                self.phase = GatePhase.FULL_4OBJ
                return

            # ── GP_GATED → WARMUP fallback ───────────────────────────
            # If GP predictions degrade severely despite rebuilds, re-enter
            # unconditional warmup to collect fresh training data.
            if (
                self.consecutive_fail >= self._cfg.max_consecutive_fail * 2
                or (
                    self._eval_count > self._cfg.warmup_n_evaluations + 5
                    and self.f2w_pass_rate < self._cfg.pass_rate_critical
                )
            ):
                _logger.warning(
                    "GP_GATED → WARMUP (consecutive_fail=%d, pass_rate=%.2f) — "
                    "re-entering unconditional warmup to rebuild GP training data",
                    self.consecutive_fail, self.f2w_pass_rate,
                )
                self.phase = GatePhase.WARMUP
                self._warmup_start_count = self._eval_count
                self.consecutive_fail = 0
                self.consecutive_pass = 0
                self.current_db_threshold = self._cfg.db_initial
                self._rebuild_gps()
            return

        if self.phase == GatePhase.FULL_4OBJ:
            if self.f2w_pass_rate < self._cfg.pass_rate_critical:
                _logger.warning(
                    "FULL_4OBJ → GP_GATED (pass_rate=%.2f < critical=%.2f)",
                    self.f2w_pass_rate, self._cfg.pass_rate_critical,
                )
                self.phase = GatePhase.GP_GATED
                self.current_db_threshold = self._cfg.db_initial
                self._rebuild_gps()
            return

    # ------------------------------------------------------------------
    # Pre-filter threshold (external accessor for orchestrator)
    # ------------------------------------------------------------------

    @property
    def pre_filter_db_threshold(self) -> float:
        """Current pre-filter dB threshold (from TCP sliding window)."""
        return self.current_db_threshold
