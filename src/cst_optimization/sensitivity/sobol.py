"""Sobol' variance-based sensitivity analysis using Saltelli's method.

Computes first-order (S1) and total-effect (ST) indices for each
parameter.  These indices quantify how much each parameter contributes
to the output variance, both alone and through interactions.

Reference: Saltelli et al. (2010), Computer Physics Communications.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.stats import qmc


@dataclass
class SobolResult:
    """Container for Sobol' sensitivity indices.

    Attributes
    ----------
    first_order : dict[str, float]
        First-order index S1 for each parameter.  0 ≤ S1 ≤ 1.
    total_effect : dict[str, float]
        Total-effect index ST for each parameter.  0 ≤ ST ≤ 1.
    parameter_names : list[str]
        Ordered parameter names.
    n_evaluations : int
        Total number of model evaluations performed.
    """

    first_order: dict[str, float]
    total_effect: dict[str, float]
    parameter_names: list[str]
    n_evaluations: int


class SobolSensitivity:
    """Sobol' sensitivity analysis via Saltelli's method.

    Uses ``scipy.stats.qmc.Sobol`` for the outer quasi-Monte Carlo
    sampling.  For *D* parameters and *N* base samples the total
    evaluation count is ``N × (2D + 2)``.

    Parameters
    ----------
    evaluator : callable
        Function ``f(x_array) → float`` where *x* is a 1-D array in
        the physical parameter space.
    bounds : np.ndarray
        ``(D, 2)`` array of ``[low, high]`` bounds.
    param_names : list[str]
        Parameter names (for result dictionary keys).
    n_base_samples : int
        Base sample size *N*.  Rounded up to next power of 2.
    seed : int or None
        Random seed.
    """

    def __init__(
        self,
        evaluator: Callable[[np.ndarray], float],
        bounds: np.ndarray,
        param_names: list[str],
        n_base_samples: int = 1024,
        seed: int | None = None,
    ) -> None:
        self._evaluator = evaluator
        self._bounds = np.asarray(bounds)
        self._param_names = list(param_names)
        self._seed = seed

        n_dims = self._bounds.shape[0]
        # Round to next power of 2 for Sobol'
        n_pow2 = 1
        while n_pow2 < n_base_samples:
            n_pow2 <<= 1
        self._N = n_pow2
        self._D = n_dims

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    def compute(self) -> SobolResult:
        """Run the Saltelli estimator and return Sobol' indices.

        Returns
        -------
        SobolResult
        """
        N, D = self._N, self._D

        # Generate Sobol' sequence for A, B and the cross matrices
        sampler = qmc.Sobol(d=D * (D + 2), scramble=True, seed=self._seed)
        unit = sampler.random(n=N)

        # Partition the unit samples
        A_unit = unit[:, :D]               # (N, D)
        B_unit = unit[:, D : 2 * D]        # (N, D)

        # Map to physical bounds
        lo = self._bounds[:, 0]
        hi = self._bounds[:, 1]
        A = lo + A_unit * (hi - lo)
        B = lo + B_unit * (hi - lo)

        # Evaluate A and B
        f_A = np.empty(N)
        f_B = np.empty(N)
        for i in range(N):
            f_A[i] = self._evaluator(A[i])
            f_B[i] = self._evaluator(B[i])

        total_evals = 2 * N

        S1 = {}
        ST = {}

        for j in range(D):
            # Build A_B^(j): A with column j replaced by B's column j
            A_B = A.copy()
            A_B[:, j] = B[:, j]

            f_AB = np.empty(N)
            for i in range(N):
                f_AB[i] = self._evaluator(A_B[i])

            total_evals += N

            # Saltelli estimators (Eq. 4.18 and 4.20 in Saltelli et al. 2010)
            # S1_j = (1/N Σ f(B)_i * (f(A_B)_i - f(A)_i)) / Var(Y)
            f0 = np.mean(f_A)
            var_Y = np.mean(f_A**2) - f0**2

            if var_Y < 1e-15:
                s1_val = 0.0
                st_val = 0.0
            else:
                s1_val = np.mean(f_B * (f_AB - f_A)) / var_Y
                st_val = 0.5 * np.mean((f_A - f_AB) ** 2) / var_Y

            # Clamp to valid range (sampling error can push slightly outside)
            S1[self._param_names[j]] = float(max(0.0, min(1.0, s1_val)))
            ST[self._param_names[j]] = float(max(0.0, min(1.0, st_val)))

        return SobolResult(
            first_order=S1,
            total_effect=ST,
            parameter_names=self._param_names,
            n_evaluations=total_evals,
        )
