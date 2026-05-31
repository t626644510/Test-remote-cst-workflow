"""Adaptive parameter bound control during optimisation.

Two-phase strategy:

Phase 1 — LHS coarse scan with bounds shrinking:
    When the rejection rate of initial LHS samples exceeds a threshold,
    shrink all parameter bounds toward the best valid point (or nominal
    values) and re-sample.  Repeat until the rejection rate is acceptable
    or the maximum number of shrink rounds is reached.

Phase 2 — Post-SAO boundary proximity expansion:
    After SAO completes, check whether the optimum lies near any
    parameter boundary.  If so, expand that boundary so a subsequent
    re-optimisation can explore beyond the original constraint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .sampling import unit_cube_lhs, constrained_unit_cube_lhs
from ..parameters.base import ParameterSet

_logger = logging.getLogger(__name__)


@dataclass
class AdaptiveBoundsConfig:
    """Configuration for ``AdaptiveBoundsController``.

    Attributes
    ----------
    enabled : bool
        Master switch.  When ``False`` the controller is a no-op.
    rejection_threshold : float
        Phase-1 trigger: shrink when the fraction of rejected samples
        exceeds this value (0.0–1.0).
    shrink_factor : float
        Multiplier applied to the distance from *center* to each bound
        on every shrink round.  E.g. 0.7 shrinks span to 70 %.
    max_shrink_rounds : int
        Maximum number of consecutive shrink rounds in Phase 1.
    min_span_ratio : float
        Lower bound on parameter span relative to original bounds.
        E.g. 0.1 means bounds will never shrink below 10 % of original.
    boundary_proximity : float
        Phase-2 trigger: a parameter is "near" a bound when
        ``|x_opt_i - bound_edge| / span_i < boundary_proximity``.
    expand_factor : float
        Multiplier applied to span when expanding a single bound.
        E.g. 1.5 widens the span by 50 % (centered on current midpoint).
    max_span_ratio : float
        Upper bound on parameter span relative to original bounds.
        E.g. 2.0 means bounds will never expand beyond 200 % of original.
    """

    enabled: bool = True
    rejection_threshold: float = 0.4
    shrink_factor: float = 0.7
    max_shrink_rounds: int = 3
    min_span_ratio: float = 0.1
    boundary_proximity: float = 0.1
    expand_factor: float = 1.5
    max_span_ratio: float = 2.0


class AdaptiveBoundsController:
    """Two-phase adaptive parameter bound control.

    Parameters
    ----------
    parameter_set : ParameterSet
        The parameter set whose bounds will be manipulated.
    nominal_values : np.ndarray
        Fallback center for shrinking when no valid sample exists.
    config : AdaptiveBoundsConfig
    seed : int or None
        RNG seed for LHS sampling.
    """

    def __init__(
        self,
        parameter_set: ParameterSet,
        nominal_values: np.ndarray,
        config: AdaptiveBoundsConfig | None = None,
        seed: int | None = 42,
    ) -> None:
        self._params = parameter_set
        self._nominal = np.asarray(nominal_values, dtype=float)
        self._config = config or AdaptiveBoundsConfig()
        self._seed = seed
        self._rng = np.random.default_rng(seed)

        # Capture original bounds on first use so shrink/expand have a reference.
        if parameter_set.original_bounds is None:
            parameter_set.capture_original_bounds()

    @property
    def enabled(self) -> bool:
        """``True`` when adaptive bounds control is active."""
        return self._config.enabled

    # ------------------------------------------------------------------
    # Phase 1 — adaptive LHS with shrinking
    # ------------------------------------------------------------------

    def run_adaptive_lhs(
        self,
        n_samples: int,
        evaluate: Callable[[np.ndarray], float],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        """Run LHS with adaptive bound shrinking.

        Parameters
        ----------
        n_samples : int
            Number of LHS samples per round.
        evaluate : callable
            ``f(x_phys) -> float``.  A return value ≥ 1.0 is counted as
            "rejected" (the sentinel for failed/infeasible evaluations).

        Returns
        -------
        X_norm : np.ndarray
            Normalised samples in [0, 1]^D from the final round.
        X_phys : np.ndarray
            Physical-space samples.
        y_raw : np.ndarray
            Objective values (raw).
        info : dict
            Diagnostics: ``rounds``, ``rejection_rates``,
            ``bounds_history``.
        """
        cfg = self._config
        params = self._params
        n_dims = params.n_parameters
        rejection_threshold = cfg.rejection_threshold
        info: dict[str, Any] = {
            "rounds": 1,
            "rejection_rates": [],
            "bounds_history": [params.bounds.copy()],
        }
        all_X_norm: list[np.ndarray] = []
        all_X_phys: list[np.ndarray] = []
        all_y_raw: list[float] = []

        for round_idx in range(cfg.max_shrink_rounds):
            # Generate LHS in unit cube
            if params.constraints is not None:
                X_norm = constrained_unit_cube_lhs(
                    n_samples, n_dims, params, seed=self._seed + round_idx if self._seed else None,
                )
            else:
                X_norm = unit_cube_lhs(
                    n_samples, n_dims, seed=self._seed + round_idx if self._seed else None,
                )

            X_phys = np.empty((n_samples, n_dims))
            y_raw = np.empty(n_samples)
            rejected = 0

            for i in range(n_samples):
                x_p = params.denormalize(X_norm[i])
                X_phys[i] = x_p
                val = evaluate(x_p)
                y_raw[i] = val
                if val >= 1.0:
                    rejected += 1

            rejection_rate = rejected / n_samples
            info["rejection_rates"].append(rejection_rate)
            info["rounds"] = round_idx + 1

            all_X_norm.append(X_norm)
            all_X_phys.append(X_phys)
            all_y_raw.extend(float(v) for v in y_raw)

            _logger.info(
                "Adaptive LHS round %d/%d: rejection_rate=%.2f (threshold=%.2f), bounds span range [%.3g, %.3g]",
                round_idx + 1, cfg.max_shrink_rounds, rejection_rate,
                rejection_threshold,
                float(np.min(params.bounds[:, 1] - params.bounds[:, 0])),
                float(np.max(params.bounds[:, 1] - params.bounds[:, 0])),
            )

            if rejection_rate <= rejection_threshold:
                _logger.info(
                    "Adaptive LHS: rejection rate acceptable at round %d", round_idx + 1,
                )
                break

            if round_idx == cfg.max_shrink_rounds - 1:
                _logger.warning(
                    "Adaptive LHS: max shrink rounds (%d) reached; stopping with rejection_rate=%.2f",
                    cfg.max_shrink_rounds, rejection_rate,
                )
                break

            # Find best valid point as shrink center
            valid_mask = y_raw < 1.0
            if np.any(valid_mask):
                center = X_phys[valid_mask][np.argmin(y_raw[valid_mask])]
                center_source = "best_valid"
            else:
                center = self._nominal.copy()
                center_source = "nominal"
            _logger.info(
                "Adaptive LHS: shrinking toward %s point", center_source,
            )

            params.shrink_toward(center, cfg.shrink_factor, cfg.min_span_ratio)
            info["bounds_history"].append(params.bounds.copy())

        # Stack all samples
        X_phys_all = np.vstack(all_X_phys) if all_X_phys else np.empty((0, n_dims))
        X_norm_all = params.normalize(X_phys_all.T).T if len(X_phys_all) > 0 else np.empty((0, n_dims))
        y_raw_all = np.array(all_y_raw, dtype=float)

        return X_norm_all, X_phys_all, y_raw_all, info

    # ------------------------------------------------------------------
    # Phase 2 — boundary proximity expansion
    # ------------------------------------------------------------------

    def check_boundary_proximity(self, x_opt_phys: np.ndarray) -> list[int]:
        """Return indices of parameters whose optimum is near a bound.

        "Near" means the distance to the closer bound is less than
        ``boundary_proximity * span``.

        Parameters
        ----------
        x_opt_phys : np.ndarray
            Optimal parameter vector in physical space.

        Returns
        -------
        list[int]
            Parameter indices that should be expanded.
        """
        cfg = self._config
        params = self._params
        to_expand: list[int] = []

        for i in range(params.n_parameters):
            lo, hi = params.get_bound(i)
            span = hi - lo
            if span <= 0:
                continue
            x_i = float(x_opt_phys[i])
            dist_lo = (x_i - lo) / span
            dist_hi = (hi - x_i) / span
            proximity = cfg.boundary_proximity
            near_bound = dist_lo < proximity or dist_hi < proximity
            _logger.debug(
                "Boundary check param %d '%s': x=%.4g, bounds=[%.4g, %.4g], "
                "dist_lo=%.3f, dist_hi=%.3f, near=%s",
                i, params.names[i], x_i, lo, hi, dist_lo, dist_hi, near_bound,
            )
            if near_bound:
                to_expand.append(i)

        if to_expand:
            _logger.info(
                "Boundary proximity triggered for params: %s",
                [params.names[i] for i in to_expand],
            )

        return to_expand

    def expand_parameter_bounds(self, indices: list[int]) -> bool:
        """Expand bounds for the given parameter indices.

        Returns ``True`` if any bound was actually changed.
        """
        cfg = self._config
        changed = False
        for i in indices:
            old_lo, old_hi = self._params.get_bound(i)
            new_lo, new_hi = self._params.expand_bound(
                i, cfg.expand_factor, cfg.max_span_ratio,
            )
            if new_lo != old_lo or new_hi != old_hi:
                changed = True
                _logger.info(
                    "Expanded bounds for '%s': [%.4g, %.4g] → [%.4g, %.4g]",
                    self._params.names[i], old_lo, old_hi, new_lo, new_hi,
                )
        return changed
