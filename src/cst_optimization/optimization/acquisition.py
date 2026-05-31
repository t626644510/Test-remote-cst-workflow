"""Acquisition functions for Bayesian optimisation.

Each function evaluates the utility of probing a candidate point *x*
given the current GP surrogate model and the best observed value so far.

All functions follow the convention: **higher = better** (to be maximised
by the optimiser that selects the next query point).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from scipy.stats import norm


class AcquisitionFunction(ABC):
    """Abstract base for an acquisition function."""

    @abstractmethod
    def evaluate(
        self,
        x: np.ndarray,
        gp_model: Any,
        y_best: float,
    ) -> float:
        """Evaluate the acquisition function at *x*.

        Parameters
        ----------
        x : np.ndarray
            Single point (1-D array) in the design space.
        gp_model : sklearn.gaussian_process.GaussianProcessRegressor
            Fitted GP surrogate.
        y_best : float
            Best observed objective value so far (in minimisation sense).

        Returns
        -------
        float
            Acquisition value (higher is better).
        """
        ...


class ExpectedImprovement(AcquisitionFunction):
    """Expected Improvement (EI) acquisition.

    .. math::

        EI(x) = (y_best - mu(x)) * Phi(Z) + sigma(x) * phi(Z)

    where Z = (y_best - mu(x)) / sigma(x) when sigma > 0, else 0.

    Parameters
    ----------
    xi : float
        Exploration parameter.  Larger values encourage exploration.
        Default 0.01.
    """

    def __init__(self, xi: float = 0.01) -> None:
        self._xi = float(xi)

    def evaluate(
        self,
        x: np.ndarray,
        gp_model: Any,
        y_best: float,
    ) -> float:
        x_2d = x.reshape(1, -1)
        mu, sigma = gp_model.predict(x_2d, return_std=True)
        mu = float(mu[0])
        sigma = float(sigma[0])

        if sigma < 1e-12:
            return 0.0

        improvement = y_best - mu - self._xi
        Z = improvement / sigma
        return float(improvement * norm.cdf(Z) + sigma * norm.pdf(Z))


class UpperConfidenceBound(AcquisitionFunction):
    """Upper Confidence Bound (UCB) acquisition.

    .. math::

        UCB(x) = -(mu(x) - kappa * sigma(x))

    The negation maps the UCB into a maximisation sense (since we want to
    minimise the objective).

    Parameters
    ----------
    kappa : float
        Exploration–exploitation trade-off.  Higher values favour
        exploration.  Default 2.0.
    """

    def __init__(self, kappa: float = 2.0) -> None:
        self._kappa = float(kappa)

    def evaluate(
        self,
        x: np.ndarray,
        gp_model: Any,
        y_best: float,
    ) -> float:
        x_2d = x.reshape(1, -1)
        mu, sigma = gp_model.predict(x_2d, return_std=True)
        mu = float(mu[0])
        sigma = float(sigma[0])

        # Negate because the outer maximiser is choosing the next point,
        # and lower UCB is better (we minimise).
        return float(-(mu - self._kappa * sigma))


class ProbabilityOfImprovement(AcquisitionFunction):
    """Probability of Improvement (PI) acquisition.

    .. math::

        PI(x) = Phi((y_best - xi - mu(x)) / sigma(x))

    Parameters
    ----------
    xi : float
        Exploration parameter.  Default 0.01.
    """

    def __init__(self, xi: float = 0.01) -> None:
        self._xi = float(xi)

    def evaluate(
        self,
        x: np.ndarray,
        gp_model: Any,
        y_best: float,
    ) -> float:
        x_2d = x.reshape(1, -1)
        mu, sigma = gp_model.predict(x_2d, return_std=True)
        mu = float(mu[0])
        sigma = float(sigma[0])

        if sigma < 1e-12:
            return 0.0

        Z = (y_best - mu - self._xi) / sigma
        return float(norm.cdf(Z))
