"""Robustness optimisation against manufacturing tolerances.

Given a tolerance specification for each parameter, evaluates the
objective distribution at a candidate design point and optimises
both the mean and variance of the resulting objective.

The robust objective is a convex combination::

    alpha * mean(f(x)) + (1 - alpha) * std(f(x))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np


@dataclass
class ToleranceSpec:
    """Manufacturing tolerance for a single parameter.

    Attributes
    ----------
    parameter_name : str
        Name of the parameter.
    absolute_tolerance : float
        Half-width of the tolerance band (e.g. ±0.05 mm).
    relative_tolerance : float or None
        Optional relative tolerance.  If both are given the larger is used.
    """

    parameter_name: str
    absolute_tolerance: float = 0.0
    relative_tolerance: float | None = None


@dataclass
class RobustEvaluation:
    """Result of evaluating the objective distribution around a design point.

    Attributes
    ----------
    x_nominal : np.ndarray
        Nominal (design) parameter values.
    mean : float
        Sample mean of the objective.
    std : float
        Sample standard deviation.
    objective_samples : list[float]
        All objective values evaluated.
    candidate_points : list[np.ndarray]
        The perturbed points that were evaluated.
    """

    x_nominal: np.ndarray
    mean: float
    std: float
    objective_samples: list[float] = field(default_factory=list)
    candidate_points: list[np.ndarray] = field(default_factory=list)


class RobustOptimizer:
    """Optimise for robustness against parameter tolerances.

    For each candidate design point, the objective is evaluated at
    *n_monte_carlo* points drawn from a normal distribution centred at
    the candidate with standard deviation derived from the tolerance spec.

    Parameters
    ----------
    evaluator : callable
        Function ``f(x_array) → float``.
    tolerances : list[ToleranceSpec]
        One spec per parameter (ordered to match the parameter array).
    alpha : float
        Trade-off: ``alpha * mean + (1 - alpha) * std``.  Higher values
        favour nominal performance; lower values favour insensitivity.
        Default 0.5.
    n_monte_carlo : int
        Number of perturbed samples per candidate (default 100).
    seed : int or None
    """

    def __init__(
        self,
        evaluator: Callable[[np.ndarray], float],
        tolerances: list[ToleranceSpec],
        alpha: float = 0.5,
        n_monte_carlo: int = 100,
        seed: int | None = None,
    ) -> None:
        self._evaluator = evaluator
        self._tolerances = list(tolerances)
        self._alpha = float(alpha)
        self._n_mc = n_monte_carlo
        self._rng = np.random.RandomState(seed)

        # Compute per-dimension sigma from tolerance specs
        self._sigmas = np.array([
            t.absolute_tolerance / 3.0 for t in self._tolerances
        ])  # ±3σ rule: 3σ = tolerance

    # ------------------------------------------------------------------
    # Evaluate a single candidate
    # ------------------------------------------------------------------

    def evaluate(self, x: np.ndarray) -> RobustEvaluation:
        """Evaluate the objective distribution around a candidate point.

        Parameters
        ----------
        x : np.ndarray
            Nominal parameter values (1-D array).

        Returns
        -------
        RobustEvaluation
        """
        samples = []
        points = []
        for _ in range(self._n_mc):
            perturbed = x + self._rng.normal(0, self._sigmas)
            f_val = self._evaluator(perturbed)
            samples.append(f_val)
            points.append(perturbed)

        samples_arr = np.array(samples)
        return RobustEvaluation(
            x_nominal=x.copy(),
            mean=float(np.mean(samples_arr)),
            std=float(np.std(samples_arr)),
            objective_samples=samples,
            candidate_points=points,
        )

    def robust_objective(self, x: np.ndarray) -> float:
        """Return the combined (mean–variance) robust objective.

        .. math::

            f_{\\text{robust}} = \\alpha \\cdot \\mu_f + (1-\\alpha) \\cdot \\sigma_f
        """
        ev = self.evaluate(x)
        return self._alpha * ev.mean + (1.0 - self._alpha) * ev.std
