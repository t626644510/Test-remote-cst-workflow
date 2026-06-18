"""Surrogate-Assisted Optimisation (SAO) using Gaussian Process regression.

Algorithm
---------
1. Generate initial design via LHS in the **unit cube** [0,1]^D.
2. Denormalise to physical space → evaluate true objective.
3. Standardise objective values to zero mean, unit variance.
4. Fit GP surrogate in normalised input × standardised output space.
5. Maximise acquisition function (in normalised space) → pick next point.
6. Denormalise → evaluate true objective.
7. Refit scaler, update GP, repeat until budget exhausted.

All normalisation/standardisation is internal — the evaluator and logs
always see raw physical values.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel
from sklearn.preprocessing import StandardScaler

from .base import BaseOptimizer, OptimizationResult
from .sampling import unit_cube_lhs, constrained_unit_cube_lhs
from .acquisition import AcquisitionFunction, ExpectedImprovement
from .adaptive_bounds import AdaptiveBoundsController
from ..parameters.base import ParameterSet
from ..objectives.base import ObjectiveFunction


class SurrogateAssistedOptimizer(BaseOptimizer):
    """GP-based Surrogate-Assisted Optimisation (single-objective).

    Parameters
    ----------
    parameter_set : ParameterSet
    objectives : list[ObjectiveFunction]
        Must contain exactly **one** objective for SAO.
    seed : int or None
    acquisition : AcquisitionFunction or None
        Defaults to ``ExpectedImprovement(xi=0.01)``.
    n_initial : int
        Number of initial design points (default 20).
    n_iterations : int
        Number of acquisition-driven iterations (default 50).
    kernel : sklearn GP kernel or None
        Defaults to ``C(1.0) * RBF() + WhiteKernel()`` with bounds
        appropriate for [0,1]^D input space.
    logger : OptimizationLogger or None
    """

    def __init__(
        self,
        parameter_set: ParameterSet,
        objectives: list[ObjectiveFunction],
        seed: int | None = 42,
        acquisition: AcquisitionFunction | None = None,
        n_initial: int = 20,
        n_iterations: int = 50,
        kernel=None,
        logger: Any | None = None,
    ) -> None:
        if len(objectives) != 1:
            raise ValueError(
                "SurrogateAssistedOptimizer supports only single-objective. "
                "For multi-objective use SurrogateAssistedEA."
            )
        super().__init__(parameter_set, objectives, seed, logger=logger)
        self._n_initial = n_initial
        self._n_iterations = n_iterations
        self._acquisition = acquisition or ExpectedImprovement(xi=0.01)
        self._params = parameter_set

        if kernel is None:
            n_dims = self.n_parameters
            kernel = (
                ConstantKernel(1.0, constant_value_bounds=(1e-3, 1e3))
                * RBF(
                    length_scale=[1.0] * n_dims,
                    length_scale_bounds=(1e-3, 100.0),
                )
                + WhiteKernel(noise_level=1e-3, noise_level_bounds=(1e-6, 1e-1))
            )
        self._kernel = kernel

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def optimize(
        self,
        evaluator: Callable[[np.ndarray], float] | None = None,
        bounds_controller: AdaptiveBoundsController | None = None,
        prior_data: tuple[np.ndarray, np.ndarray] | None = None,
        n_initial_extra: int = 0,
    ) -> OptimizationResult:
        """Run the SAO loop.

        Parameters
        ----------
        evaluator : callable or None
            The true objective evaluator ``f(x_phys_array) -> float``.
            Always receives physical-space vectors.
            If ``None``, ``_evaluate_normalized()[0]`` is used (CST-backed).
        bounds_controller : AdaptiveBoundsController or None
            Optional two-phase adaptive bounds controller.
        prior_data : (X_phys, y_raw) or None
            Pre-loaded ``(N, D)`` physical-space parameter matrix and
            ``(N,)`` scalar penalty vector from a previous run.
            These are pre-seeded into the GP training arrays without
            re-evaluation, giving the GP a stronger prior.  When provided,
            the number of LHS initial points is reduced accordingly.

        Returns
        -------
        OptimizationResult
            ``x_opt`` and ``history_x`` are in **physical** space;
            ``f_opt`` and ``history_f`` are **raw** (un-standardised) values.
        """
        params = self._params
        n_dims = self.n_parameters

        # ── 0. Prior data pre-loading (resume from previous run) ──────
        X_norm_prior: np.ndarray | None = None
        X_phys_prior: np.ndarray | None = None
        y_raw_prior: np.ndarray | None = None
        n_prior = 0
        if prior_data is not None:
            X_phys_prior, y_raw_prior = prior_data
            X_phys_prior = np.asarray(X_phys_prior, dtype=float)
            y_raw_prior = np.asarray(y_raw_prior, dtype=float).ravel()
            n_prior = len(X_phys_prior)
            X_norm_prior = np.empty((n_prior, n_dims))
            for i in range(n_prior):
                X_norm_prior[i] = params.normalize(params.validate(X_phys_prior[i]))
            n_initial = max(2, self._n_initial - n_prior + n_initial_extra)
            _logger = logging.getLogger(__name__)
            _logger.info(
                "Pre-loaded %d prior evaluations; LHS set to %d "
                "(base=%d - prior=%d + extra=%d)",
                n_prior, n_initial, self._n_initial, n_prior, n_initial_extra,
            )
        else:
            n_initial = self._n_initial

        # ── 1. Initial design in unit cube ────────────────────────────
        warm_start = None
        if evaluator is not None and hasattr(evaluator, "warm_start"):
            try:
                warm_start = np.asarray(evaluator.warm_start, dtype=float)
            except Exception:
                warm_start = None

        if bounds_controller is not None and bounds_controller.enabled:
            # ── Phase 1: adaptive LHS with bounds shrinking ────────
            X_norm, X_phys, y_raw, bounds_info = bounds_controller.run_adaptive_lhs(
                n_samples=n_initial,
                evaluate=lambda x_p: (
                    evaluator(x_p) if evaluator
                    else self._evaluate_normalized()[0]
                ),
            )
            # Ensure warm_start is present in the first position if provided
            if warm_start is not None and len(warm_start) == n_dims:
                ws_norm = params.normalize(params.validate(warm_start))
                ws_phys = params.denormalize(ws_norm)
                ws_y = (
                    evaluator(ws_phys) if evaluator
                    else self._evaluate_normalized()[0]
                )
                X_norm = np.vstack([ws_norm.reshape(1, -1), X_norm])
                X_phys = np.vstack([ws_phys.reshape(1, -1), X_phys])
                y_raw = np.insert(y_raw, 0, ws_y)

            X_norm = np.asarray(X_norm, dtype=float)
            X_phys = np.asarray(X_phys, dtype=float)
            y_raw = np.asarray(y_raw, dtype=float)
        else:
            # ── Original LHS path ──────────────────────────────────
            if params.constraints is not None:
                X_norm = constrained_unit_cube_lhs(
                    n_initial, n_dims, params, seed=self._seed,
                )
            else:
                X_norm = unit_cube_lhs(n_initial, n_dims, seed=self._seed)

            if warm_start is not None and len(warm_start) == n_dims:
                X_norm[0] = params.normalize(params.validate(warm_start))

            X_phys = np.empty((n_initial, n_dims))
            y_raw = np.empty(n_initial)
            for i in range(n_initial):
                x_p = params.denormalize(X_norm[i])
                X_phys[i] = x_p
                y_raw[i] = evaluator(x_p) if evaluator else self._evaluate_normalized()[0]

            X_norm = np.asarray(X_norm, dtype=float)
            X_phys = np.asarray(X_phys, dtype=float)
            y_raw = np.asarray(y_raw, dtype=float)

        # ── 1.5 Prepend prior data (if resuming) ─────────────────────
        total_initial = n_initial
        if n_prior > 0:
            X_norm = np.vstack([X_norm_prior, X_norm])
            X_phys = np.vstack([X_phys_prior, X_phys])
            y_raw = np.concatenate([y_raw_prior, y_raw])
            total_initial += n_prior

        # Log initial evaluations (prior + LHS)
        for i in range(total_initial):
            self._log_eval(iteration=i, x=X_phys[i], f=np.array([y_raw[i]]),
                           solver_ok=True, error="")


        # ── 2. Fit output scaler + GP ──────────────────────────────────
        y_scaler = StandardScaler()
        y_std = y_scaler.fit_transform(y_raw.reshape(-1, 1)).ravel()

        # ── 3. Iterate ────────────────────────────────────────────────
        for iteration in range(self._n_iterations):
            iter_num = total_initial + iteration

            # Fit GP on normalised X + standardised y
            gp = GaussianProcessRegressor(
                kernel=self._kernel,
                n_restarts_optimizer=5,
                random_state=self._seed + iteration if self._seed else None,
            )
            gp.fit(X_norm, y_std)

            y_best_std = float(np.min(y_std))

            # Acquisition maximisation in unit cube [0,1]^D
            n_candidates = max(5000, 1000 * n_dims)
            candidates_norm = self._rng.uniform(0.0, 1.0, size=(n_candidates, n_dims))

            # ── Filter infeasible candidates (geometric constraints) ─
            if params.constraints is not None:
                feasible_mask = np.array([
                    params.is_feasible(params.denormalize(c))
                    for c in candidates_norm
                ])
                n_feasible = int(np.sum(feasible_mask))
                if n_feasible < 10:
                    # Too few feasible — resample until we have enough
                    extra = self._rng.uniform(0.0, 1.0, size=(n_candidates, n_dims))
                    extra_mask = np.array([
                        params.is_feasible(params.denormalize(c))
                        for c in extra
                    ])
                    candidates_norm = np.vstack([
                        candidates_norm[feasible_mask], extra[extra_mask],
                    ])
                else:
                    candidates_norm = candidates_norm[feasible_mask]

            acq_vals = np.array([
                self._acquisition.evaluate(c, gp, y_best_std)
                for c in candidates_norm
            ])
            best_idx = int(np.argmax(acq_vals))
            x_next_norm = candidates_norm[best_idx]

            # Denormalise → physical → evaluate
            x_next_phys = params.denormalize(x_next_norm)
            y_next_raw = evaluator(x_next_phys) if evaluator else self._evaluate_normalized()[0]

            # Log decision
            from ..diagnostics import extract_gp_params
            self._log_decision(
                iteration=iter_num, x_proposed=x_next_phys,
                acquisition_value=float(acq_vals[best_idx]),
                y_best=float(np.min(y_raw)),
                gp_params=extract_gp_params(gp),
            )

            # Append
            X_norm = np.vstack([X_norm, x_next_norm])
            X_phys = np.vstack([X_phys, x_next_phys])
            y_raw = np.append(y_raw, y_next_raw)

            # Log evaluation (raw values)
            self._log_eval(iteration=iter_num, x=x_next_phys,
                           f=np.array([y_next_raw]), solver_ok=True, error="")

            # Refit output scaler on all accumulated data
            y_std = y_scaler.fit_transform(y_raw.reshape(-1, 1)).ravel()

        # ── 4. Return result in raw (physical) space ───────────────────
        best_idx_phys = int(np.argmin(y_raw))
        x_opt = X_phys[best_idx_phys]

        metadata: dict[str, Any] = {"algorithm": "SAO", "normalized": True}

        # ── Phase 2: boundary proximity check ──────────────────────────
        if bounds_controller is not None and bounds_controller.enabled:
            to_expand = bounds_controller.check_boundary_proximity(x_opt)
            if to_expand:
                bounds_controller.expand_parameter_bounds(to_expand)
                metadata["bounds_expanded"] = to_expand
                metadata["expanded_bounds"] = params.bounds.copy()
                metadata["expanded_param_names"] = [
                    params.names[i] for i in to_expand
                ]

        return OptimizationResult(
            x_opt=x_opt,
            f_opt=np.array([y_raw[best_idx_phys]]),
            history_x=[X_phys[i] for i in range(len(X_phys))],
            history_f=[np.array([y_raw[i]]) for i in range(len(y_raw))],
            n_evaluations=len(X_phys),
            metadata=metadata,
        )
