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
    uncertainty_sigma: float = 2.0  # skip only when lower confidence bound is bad
    calibration_evaluations: int = 2  # forced live checks after historical bootstrap


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

    def __init__(
        self,
        config: GateConfig,
        objective_names: list[str],
        parameter_bounds: np.ndarray | None = None,
    ) -> None:
        self._cfg = config
        self._obj_names = list(objective_names)
        self._n_obj = len(objective_names)
        self._parameter_bounds = (
            None
            if parameter_bounds is None
            else np.asarray(parameter_bounds, dtype=float).copy()
        )
        if (
            self._parameter_bounds is not None
            and (
                self._parameter_bounds.ndim != 2
                or self._parameter_bounds.shape[1] != 2
            )
        ):
            raise ValueError("parameter_bounds must have shape (n_parameters, 2)")

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
        self._models_dirty: bool = True
        self._x_min: np.ndarray | None = None
        self._x_max: np.ndarray | None = None
        self._calibration_remaining: int = 0

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
        gp_uncertainty: dict[str, float] | None = None,
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

        if not gp_predictions:
            # Missing model evidence is uncertainty, not permission to skip.
            return True

        threshold = self._cfg.gp_skip_threshold
        if self.phase == GatePhase.FULL_4OBJ:
            threshold += 0.2

        uncertainty = gp_uncertainty or {}
        for name in ("z_longitudinal", "z_transverse"):
            mean = gp_predictions.get(name, np.nan)
            std = uncertainty.get(name, np.inf)
            if not np.isfinite(mean) or not np.isfinite(std):
                continue
            lower_confidence_bound = (
                float(mean) - self._cfg.uncertainty_sigma * float(std)
            )
            if lower_confidence_bound >= threshold:
                return False
        return True

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def record_evaluation(
        self,
        x: np.ndarray,
        penalties: dict[str, float],
        f2w_ran: bool,
        measurement_mask: dict[str, bool] | None = None,
        *,
        was_validation: bool = False,
        predicted: dict[str, float] | None = None,
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

        # Scalar optimisation may use finite penalties for skipped phases.
        # Objective GPs must only ingest physically measured targets.
        y_vec = np.array(
            [
                (
                    penalties.get(name, np.nan)
                    if measurement_mask is None
                    or measurement_mask.get(name, False)
                    else np.nan
                )
                for name in self._obj_names
            ],
            dtype=float,
        )
        self._X.append(x.copy())
        self._Y.append(y_vec)
        self._models_dirty = True

        if was_validation and f2w_ran:
            self.record_validation(predicted or {}, penalties)
            if self._calibration_remaining > 0:
                self._calibration_remaining -= 1

        # Phase transition checks
        self._maybe_transition()

    def bootstrap(
        self,
        X: np.ndarray,
        penalty_matrix: np.ndarray,
        measurement_mask: np.ndarray,
        f2w_ran: np.ndarray,
        *,
        calibration_evaluations: int | None = None,
    ) -> None:
        """Seed the gate from historical physical measurements.

        Historical rows initialise GP training and pass-rate counters without
        fabricating validation accuracy.  A small number of subsequent live
        evaluations is forced for calibration.
        """
        X = np.asarray(X, dtype=float)
        penalty_matrix = np.asarray(penalty_matrix, dtype=float)
        measurement_mask = np.asarray(measurement_mask, dtype=bool)
        f2w_ran = np.asarray(f2w_ran, dtype=bool).ravel()
        if X.ndim != 2:
            raise ValueError("X must have shape (n_samples, n_parameters)")
        expected = (len(X), self._n_obj)
        if penalty_matrix.shape != expected:
            raise ValueError(
                f"penalty_matrix shape must be {expected}, got "
                f"{penalty_matrix.shape}"
            )
        if measurement_mask.shape != expected:
            raise ValueError(
                f"measurement_mask shape must be {expected}, got "
                f"{measurement_mask.shape}"
            )
        if len(f2w_ran) != len(X):
            raise ValueError("f2w_ran length must match X")

        self._X = [row.copy() for row in X]
        masked_penalties = np.where(measurement_mask, penalty_matrix, np.nan)
        self._Y = [row.copy() for row in masked_penalties]
        self._eval_count = len(X)
        self._f2w_total = len(X)
        self._f2w_pass_count = int(np.count_nonzero(f2w_ran))
        self._prediction_errors = []
        self.consecutive_pass = 0
        self.consecutive_fail = 0
        self.current_db_threshold = self._cfg.db_initial

        requested_calibration = (
            self._cfg.calibration_evaluations
            if calibration_evaluations is None
            else int(calibration_evaluations)
        )
        measured_per_objective = np.count_nonzero(measurement_mask, axis=0)
        if len(X) >= 3 and np.all(measured_per_objective >= 3):
            self.phase = GatePhase.GP_GATED
            self._calibration_remaining = max(0, requested_calibration)
            self._warmup_start_count = 0
        else:
            self.phase = GatePhase.WARMUP
            self._calibration_remaining = 0
            self._warmup_start_count = self._eval_count
        self._rebuild_gps()

    # ------------------------------------------------------------------
    # GP prediction
    # ------------------------------------------------------------------

    def predict(self, x: np.ndarray) -> dict[str, float]:
        """Return GP-predicted penalties for all objectives.

        Returns empty dict if GP models are not yet trained.
        """
        means, _ = self.predict_with_uncertainty(x)
        return means

    def predict_with_uncertainty(
        self,
        x: np.ndarray,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Return GP means and standard deviations in penalty units."""
        if len(self._X) < 3:
            return {}, {}
        self._ensure_gps_trained()
        means: dict[str, float] = {}
        uncertainty: dict[str, float] = {}
        X_new = self._normalise_inputs(
            np.asarray(x, dtype=float).reshape(1, -1)
        )
        for i, name in enumerate(self._obj_names):
            gp = self._gps[i]
            if gp is not None:
                pred, std = gp.predict(X_new, return_std=True)
                means[name] = float(pred[0])
                uncertainty[name] = float(std[0])
        return means, uncertainty

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
        if self._calibration_remaining > 0:
            return True
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
        if not self._models_dirty and any(gp is not None for gp in self._gps):
            return
        X = np.vstack(self._X)
        X_norm = self._normalise_inputs(X, fit=True)
        self._gps = [None] * self._n_obj

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
        self._models_dirty = False

    def _normalise_inputs(
        self,
        X: np.ndarray,
        *,
        fit: bool = False,
    ) -> np.ndarray:
        """Use one physical-to-unit transform for both GP fit and predict."""
        X = np.asarray(X, dtype=float)
        if self._parameter_bounds is not None:
            x_min = self._parameter_bounds[:, 0]
            x_max = self._parameter_bounds[:, 1]
        else:
            if fit or self._x_min is None or self._x_max is None:
                self._x_min = np.min(X, axis=0)
                self._x_max = np.max(X, axis=0)
            x_min = self._x_min
            x_max = self._x_max
        span = np.asarray(x_max - x_min, dtype=float)
        span[span == 0] = 1.0
        return (X - x_min) / span

    def _rebuild_gps(self) -> None:
        """Clear and retrain all GP models from scratch."""
        self._gps = [None] * self._n_obj
        self._models_dirty = True
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
                and len(self._prediction_errors) >= self._cfg.trust_consecutive
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
