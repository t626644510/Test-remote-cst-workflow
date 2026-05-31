"""Surrogate-Assisted Evolutionary Algorithm (SAEA).

Algorithm (with normalisation)
------------------------------
1. Generate initial design via LHS in the **unit cube** [0,1]^D.
2. Denormalise → physical space → evaluate true objectives.
3. Standardise each objective column independently (zero mean, unit variance).
4. For each iteration:
   a. Fit independent GP surrogates on normalised X × standardised F.
   b. Run NSGA-II in [0,1]^D using GP surrogates as cheap evaluators.
   c. Select K promising candidates from the surrogate Pareto front.
   d. Denormalise candidates → evaluate true objectives.
   e. Add to training data, refit per-column standardisers.
5. Return Pareto front in **raw** (physical + un-standardised) space.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel
from sklearn.preprocessing import StandardScaler

from .base import BaseOptimizer, OptimizationResult
from .sampling import constrained_unit_cube_lhs, unit_cube_lhs
from ..parameters.base import ParameterSet
from ..objectives.base import ObjectiveFunction


class SurrogateAssistedEA(BaseOptimizer):
    """Surrogate-Assisted Evolutionary Algorithm (GP + NSGA-II).

    Parameters
    ----------
    parameter_set : ParameterSet
    objectives : list[ObjectiveFunction]
        Multi-objective (≥ 2 objectives recommended).
    seed : int or None
    n_initial : int
        Initial design size (default 30).
    n_iterations : int
        Number of surrogate-assisted iterations (default 20).
    pop_size : int
        NSGA-II population size (default 100).
    n_gen_per_iteration : int
        Generations per NSGA-II inner run (default 50).
    n_candidates_per_iteration : int
        Number of true evaluations per iteration (default 5).
    logger : OptimizationLogger or None
    """

    def __init__(
        self,
        parameter_set: ParameterSet,
        objectives: list[ObjectiveFunction],
        seed: int | None = 42,
        n_initial: int = 30,
        n_iterations: int = 20,
        pop_size: int = 100,
        n_gen_per_iteration: int = 50,
        n_candidates_per_iteration: int = 5,
        logger: Any | None = None,
    ) -> None:
        super().__init__(parameter_set, objectives, seed, logger=logger)
        self._n_initial = n_initial
        self._n_iterations = n_iterations
        self._pop_size = pop_size
        self._n_gen_per_iteration = n_gen_per_iteration
        self._n_candidates = n_candidates_per_iteration
        self._params = parameter_set
        # Kernel for [0,1]^D input space
        n_dims = self.n_parameters
        self._kernel = (
            ConstantKernel(1.0, constant_value_bounds=(1e-3, 1e3))
            * RBF(length_scale=[1.0] * n_dims, length_scale_bounds=(1e-3, 100.0))
            + WhiteKernel(noise_level=1e-3, noise_level_bounds=(1e-6, 1e-1))
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def optimize(
        self,
        evaluator: Callable[[np.ndarray], np.ndarray] | None = None,
        prior_data: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> OptimizationResult:
        """Run the SAEA loop.

        Parameters
        ----------
        evaluator : callable or None
            The true multi-objective evaluator ``f(x_phys) -> np.ndarray``
            returning shape ``(n_objectives,)``.
            If ``None``, uses ``_evaluate_normalized()`` (CST-backed).
        prior_data : (X_phys, F_raw) or None
            Pre-loaded ``(N, D)`` physical-space parameter matrix and
            ``(N, M)`` penalty matrix from a previous run.
            Pre-seeded into training arrays without re-evaluation.

        Returns
        -------
        OptimizationResult
            ``x_opt``, ``pareto_params``, ``history_x`` are in **physical** space.
            ``f_opt``, ``pareto_front``, ``history_f`` are **raw** values.
        """
        params = self._params
        n_dims = self.n_parameters
        n_obj = self.n_objectives

        # ── 0. Prior data pre-loading (resume from previous run) ──────
        X_norm_prior: np.ndarray | None = None
        X_phys_prior: np.ndarray | None = None
        F_raw_prior: np.ndarray | None = None
        n_prior = 0
        if prior_data is not None:
            X_phys_prior, F_raw_prior = prior_data
            X_phys_prior = np.asarray(X_phys_prior, dtype=float)
            F_raw_prior = np.asarray(F_raw_prior, dtype=float)
            if F_raw_prior.ndim == 1:
                F_raw_prior = F_raw_prior.reshape(-1, 1)
            n_prior = len(X_phys_prior)
            X_norm_prior = np.empty((n_prior, n_dims))
            for i in range(n_prior):
                X_norm_prior[i] = params.normalize(params.validate(X_phys_prior[i]))
            n_initial = max(2, self._n_initial - n_prior)
            _logger = logging.getLogger(__name__)
            _logger.info(
                "Pre-loaded %d prior evaluations; LHS reduced to %d",
                n_prior, n_initial,
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

        if params.constraints is not None:
            X_norm = constrained_unit_cube_lhs(
                n_initial, n_dims, params, seed=self._seed,
            )
        else:
            X_norm = unit_cube_lhs(n_initial, n_dims, seed=self._seed)

        if warm_start is not None and len(warm_start) == n_dims:
            X_norm[0] = params.normalize(params.validate(warm_start))

        X_phys = np.empty((n_initial, n_dims))
        F_raw = np.empty((n_initial, n_obj))
        for i in range(n_initial):
            x_p = params.denormalize(X_norm[i])
            X_phys[i] = x_p
            F_raw[i] = evaluator(x_p) if evaluator else self._evaluate_normalized()

        X_norm = np.asarray(X_norm, dtype=float)
        X_phys = np.asarray(X_phys, dtype=float)
        F_raw = np.asarray(F_raw, dtype=float)

        # ── 1.5 Prepend prior data (if resuming) ─────────────────────
        total_initial = n_initial
        if n_prior > 0:
            X_norm = np.vstack([X_norm_prior, X_norm])
            X_phys = np.vstack([X_phys_prior, X_phys])
            F_raw = np.vstack([F_raw_prior, F_raw])
            total_initial += n_prior

        # Log initial evaluations (prior + LHS)
        for i in range(total_initial):
            self._log_eval(iteration=i, x=X_phys[i], f=F_raw[i],
                           solver_ok=True, error="")

        # ── 2. Per-objective standardisation ───────────────────────────
        # One StandardScaler per objective column — refit each iteration
        def _fit_scalers(F: np.ndarray) -> list[StandardScaler]:
            return [StandardScaler().fit(F[:, j].reshape(-1, 1)) for j in range(n_obj)]

        def _transform(F: np.ndarray, scalers: list[StandardScaler]) -> np.ndarray:
            out = np.empty_like(F)
            for j in range(n_obj):
                out[:, j] = scalers[j].transform(F[:, j].reshape(-1, 1)).ravel()
            return out

        # ── 3. SAEA iterations ────────────────────────────────────────
        eval_count = total_initial
        for iteration in range(self._n_iterations):
            # Refit scalers on all accumulated raw data
            scalers = _fit_scalers(F_raw)
            F_std = _transform(F_raw, scalers)

            # Fit one GP per objective (normalised X, standardised y)
            gp_models = []
            for j in range(n_obj):
                gp = GaussianProcessRegressor(
                    kernel=self._kernel,
                    n_restarts_optimizer=3,
                    random_state=self._seed + iteration if self._seed else None,
                )
                gp.fit(X_norm, F_std[:, j])
                gp_models.append(gp)

            # Run surrogate-assisted NSGA-II in unit cube [0,1]^D
            candidates_x_norm, candidates_f_std = self._surrogate_nsga2(gp_models)

            if params.constraints is not None and len(candidates_x_norm) > 0:
                feasible_mask = np.array([
                    params.is_feasible(params.denormalize(c))
                    for c in candidates_x_norm
                ])
                if np.any(feasible_mask):
                    candidates_x_norm = candidates_x_norm[feasible_mask]
                    candidates_f_std = candidates_f_std[feasible_mask]

            # Select diverse candidates (returned in normalised space)
            selected_norm = self._select_candidates(candidates_x_norm, candidates_f_std)

            # True evaluation of selected candidates
            from .logging import extract_gp_params
            for x_sel_norm in selected_norm:
                x_sel_phys = params.denormalize(x_sel_norm)

                # Log decision
                y_best = float(np.mean(F_raw.min(axis=0)))
                self._log_decision(
                    iteration=eval_count, x_proposed=x_sel_phys,
                    acquisition_value=0.0,
                    y_best=y_best,
                    gp_params=extract_gp_params(gp_models[0]) if gp_models else None,
                )

                f_true = (
                    evaluator(x_sel_phys)
                    if evaluator
                    else self._evaluate_normalized()
                )
                X_norm = np.vstack([X_norm, x_sel_norm.reshape(1, -1)])
                X_phys = np.vstack([X_phys, x_sel_phys.reshape(1, -1)])
                F_raw = np.vstack([F_raw, f_true.reshape(1, -1)])

                self._log_eval(iteration=eval_count, x=x_sel_phys, f=f_true,
                               solver_ok=True, error="")
                eval_count += 1

        # ── 4. Pareto front in raw (physical, un-standardised) space ──
        pareto_idx = self._non_dominated_idx(F_raw)
        pareto_front = F_raw[pareto_idx]
        pareto_params = X_phys[pareto_idx]

        ideal = np.min(F_raw, axis=0)
        distances = np.linalg.norm(F_raw - ideal, axis=1)
        best_idx = int(np.argmin(distances))

        return OptimizationResult(
            x_opt=X_phys[best_idx],
            f_opt=F_raw[best_idx],
            pareto_front=pareto_front,
            pareto_params=pareto_params,
            history_x=[X_phys[i] for i in range(len(X_phys))],
            history_f=[F_raw[i] for i in range(len(F_raw))],
            n_evaluations=len(X_phys),
            metadata={"algorithm": "SAEA", "normalized": True},
        )

    # ------------------------------------------------------------------
    # Internal: surrogate NSGA-II (unit cube [0,1]^D)
    # ------------------------------------------------------------------

    def _surrogate_nsga2(
        self,
        gp_models: list[GaussianProcessRegressor],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run NSGA-II using GP surrogates in [0,1]^D.

        Returns the final population's X (in [0,1]^D) and F (standardised).
        """
        try:
            from pymoo.algorithms.moo.nsga2 import NSGA2
            from pymoo.core.problem import Problem
            from pymoo.optimize import minimize as pymoo_minimize
            from pymoo.operators.sampling.rnd import FloatRandomSampling
            from pymoo.operators.crossover.sbx import SBX
            from pymoo.operators.mutation.pm import PM
        except ImportError:
            raise ImportError(
                "pymoo is required for SAEA. Install with: pip install pymoo"
            )

        n_dims = self.n_parameters
        n_obj = len(gp_models)
        surrogates = gp_models

        class SurrogateProblem(Problem):
            def __init__(inner_self):
                super().__init__(
                    n_var=n_dims,
                    n_obj=n_obj,
                    xl=np.zeros(n_dims),    # [0,1]^D
                    xu=np.ones(n_dims),
                )

            def _evaluate(inner_self, x, out, *args, **kwargs):
                F = np.empty((x.shape[0], n_obj))
                for j in range(n_obj):
                    F[:, j] = surrogates[j].predict(x)
                out["F"] = F

        problem = SurrogateProblem()

        algorithm = NSGA2(
            pop_size=self._pop_size,
            sampling=FloatRandomSampling(),
            crossover=SBX(prob=0.9, eta=15),
            mutation=PM(eta=20),
            eliminate_duplicates=True,
        )

        res = pymoo_minimize(
            problem,
            algorithm,
            ("n_gen", self._n_gen_per_iteration),
            seed=self._seed,
            verbose=False,
        )

        return res.X, res.F

    # ------------------------------------------------------------------
    # Internal: candidate selection
    # ------------------------------------------------------------------

    def _select_candidates(
        self, candidates_x: np.ndarray, candidates_f: np.ndarray
    ) -> np.ndarray:
        """Select *K* diverse candidates from the surrogate-evaluated set.

        Uses k-means clustering on the objective space to pick
        well-spread points along the surrogate Pareto front.
        """
        n_available = len(candidates_x)
        k = min(self._n_candidates, n_available)
        if k >= n_available:
            return candidates_x.copy()

        if np.allclose(candidates_f, candidates_f[0], rtol=1e-12):
            idx = self._rng.choice(n_available, size=k, replace=False)
            return candidates_x[idx]

        try:
            from sklearn.cluster import KMeans

            kmeans = KMeans(n_clusters=k, random_state=self._seed, n_init=10)
            labels = kmeans.fit_predict(candidates_f)

            selected = np.empty((k, candidates_x.shape[1]))
            for cluster_idx in range(k):
                members = np.where(labels == cluster_idx)[0]
                if len(members) == 0:
                    selected[cluster_idx] = candidates_x[self._rng.choice(n_available)]
                    continue
                centroid = kmeans.cluster_centers_[cluster_idx]
                dists = np.linalg.norm(candidates_f[members] - centroid, axis=1)
                best_in_cluster = members[np.argmin(dists)]
                selected[cluster_idx] = candidates_x[best_in_cluster]
            return selected
        except Exception:
            idx = self._rng.choice(n_available, size=k, replace=False)
            return candidates_x[idx]

    # ------------------------------------------------------------------
    # Internal: Pareto utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _non_dominated_idx(F: np.ndarray) -> np.ndarray:
        """Return indices of non-dominated rows in *F* (minimisation)."""
        n = len(F)
        dominated = np.zeros(n, dtype=bool)
        for i in range(n):
            if dominated[i]:
                continue
            for j in range(n):
                if i == j or dominated[j]:
                    continue
                if np.all(F[i] <= F[j]) and np.any(F[i] < F[j]):
                    dominated[j] = True
                elif np.all(F[j] <= F[i]) and np.any(F[j] < F[i]):
                    dominated[i] = True
                    break
        return np.where(~dominated)[0]
